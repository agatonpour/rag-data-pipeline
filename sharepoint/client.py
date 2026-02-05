import os
import time
import requests
from urllib.parse import quote


class GraphClient:
    def __init__(self):
        self.tenant_id = os.environ["AZURE_TENANT_ID"]
        self.client_id = os.environ["AZURE_CLIENT_ID"]
        self.client_secret = os.environ["AZURE_CLIENT_SECRET"]

        self._token = None
        self._token_exp = 0

    def _get_token(self) -> str:
        now = int(time.time())
        if self._token and now < self._token_exp - 60:
            return self._token

        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default",
        }
        r = requests.post(url, data=data)
        r.raise_for_status()
        payload = r.json()

        self._token = payload["access_token"]
        self._token_exp = now + int(payload.get("expires_in", 3600))
        return self._token

    def request(self, method: str, url: str, **kwargs):
        token = self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Accept", "application/json")
        return requests.request(method, url, headers=headers, **kwargs)


def get_site_id(graph: GraphClient, host: str, site_path: str) -> str:
    # Graph format: /sites/{hostname}:{server-relative-path}
    url = f"https://graph.microsoft.com/v1.0/sites/{host}:{site_path}"
    r = graph.request("GET", url)
    r.raise_for_status()
    return r.json()["id"]


def get_drive_id_by_name(graph: GraphClient, site_id: str, drive_name: str) -> str:
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    r = graph.request("GET", url)
    r.raise_for_status()
    for d in r.json().get("value", []):
        if d.get("name") == drive_name:
            return d["id"]
    raise RuntimeError(f"Drive '{drive_name}' not found on site {site_id}")


def _get_item_by_path(graph: GraphClient, drive_id: str, path: str):
    # path must be URL encoded but keep slashes
    enc = quote(path.strip("/"), safe="/")
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{enc}"
    r = graph.request("GET", url)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def ensure_folder_path(graph: GraphClient, drive_id: str, folder_path: str):
    """
    Ensures folder_path exists under drive root.
    Creates missing folders segment-by-segment.
    """
    folder_path = folder_path.strip("/")

    if not folder_path:
        return

    segments = [s for s in folder_path.split("/") if s]
    current = ""

    for seg in segments:
        current = f"{current}/{seg}" if current else seg
        item = _get_item_by_path(graph, drive_id, current)
        if item is not None:
            continue

        parent_path = "/".join(current.split("/")[:-1])
        parent_enc = quote(parent_path, safe="/") if parent_path else ""
        children_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root"
            + (f":/{parent_enc}:" if parent_enc else "")
            + "/children"
        )

        payload = {
            "name": seg,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail"
        }
        r = graph.request("POST", children_url, json=payload)
        # If two runs race, folder might already exist; treat 409 as ok.
        if r.status_code not in (201, 409):
            r.raise_for_status()


def upload_file(graph: GraphClient, drive_id: str, remote_path: str, local_file_path: str) -> str:
    """
    Uploads (create/overwrite) a file to drive at remote_path.
    Uses simple upload for <=4MB, upload session for larger.
    Returns "created" or "updated" (best-effort).
    """
    remote_path = remote_path.strip("/")

    size = os.path.getsize(local_file_path)

    # Ensure parent folder exists
    parent = "/".join(remote_path.split("/")[:-1])
    if parent:
        ensure_folder_path(graph, drive_id, parent)

    # Try detect if exists to label created/updated
    existed = _get_item_by_path(graph, drive_id, remote_path) is not None

    if size <= 4 * 1024 * 1024:
        enc = quote(remote_path, safe="/")
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{enc}:/content"
        with open(local_file_path, "rb") as f:
            r = graph.request("PUT", url, data=f.read())
        r.raise_for_status()
        return "updated" if existed else "created"

    # Large file upload session
    enc = quote(remote_path, safe="/")
    sess_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{enc}:/createUploadSession"
    payload = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
    r = graph.request("POST", sess_url, json=payload)
    r.raise_for_status()
    upload_url = r.json()["uploadUrl"]

    chunk_size = 10 * 1024 * 1024  # 10MB
    with open(local_file_path, "rb") as f:
        start = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            end = start + len(chunk) - 1
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            }
            ru = requests.put(upload_url, headers=headers, data=chunk)
            # 202 = accepted, more chunks; 201/200 = completed
            if ru.status_code in (200, 201):
                return "updated" if existed else "created"
            if ru.status_code != 202:
                ru.raise_for_status()
            start = end + 1

    return "updated" if existed else "created"

def list_drives(graph: GraphClient, site_id: str):
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    r = graph.request("GET", url)
    r.raise_for_status()
    for d in r.json().get("value", []):
        print(f"- Drive name: {d['name']} | id: {d['id']}")