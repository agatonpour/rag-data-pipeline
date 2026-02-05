import re
import requests
from pathlib import Path


# Blocked formats (denylist. These will NOT be downloaded into the AI knowledge folder
BLOCKED_EXTENSIONS = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff",

    # Archives
    ".zip", ".rar", ".7z", ".tar", ".gz",

    # Certificates / keys (very important to exclude)
    ".pfx", ".p12", ".cer", ".crt", ".pem", ".key", ".jks", ".pkcs8",

    # Diagrams / editor artifacts
    ".drawio",
}


def is_attachment_blocked(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in BLOCKED_EXTENSIONS


def fetch_attachments_for_page(client, page_id):
    """
    Fetch all attachments for a given Confluence page.
    Pagination-safe.
    """
    attachments = []
    start = 0
    limit = 50

    while True:
        data = client.get(
            f"/wiki/rest/api/content/{page_id}/child/attachment",
            params={
                "limit": limit,
                "start": start,
                "expand": "version,extensions,metadata,_links"
            }
        )

        results = data.get("results", [])
        attachments.extend(results)

        if len(results) < limit:
            break

        start += limit

    return attachments


def _extract_numeric_content_id(raw_id):
    """
    Confluence Cloud attachment IDs can be:
      - "123456789"          (good)
      - "att123456789"       (strip 'att')
      - something else weird (ignore)
    Returns numeric content id as string, or None.
    """
    if raw_id is None:
        return None

    s = str(raw_id)

    if s.isdigit():
        return s

    if s.startswith("att") and s[3:].isdigit():
        return s[3:]

    return None


def normalize_attachment(base_url, attachment_obj):
    """
    Normalize attachment metadata and extract a usable numeric content ID
    for downloading.
    """
    raw_id = attachment_obj.get("id")
    content_id = _extract_numeric_content_id(raw_id)

    title = attachment_obj.get("title")

    version_obj = attachment_obj.get("version") or {}
    version_number = version_obj.get("number")

    extensions = attachment_obj.get("extensions") or {}
    file_size = extensions.get("fileSize")
    media_type = extensions.get("mediaType") or extensions.get("fileMimeType")

    return str(raw_id), {
        "contentId": content_id,
        "title": title,
        "version": version_number,
        "size": file_size,
        "mediaType": media_type,
    }


def download_attachment_binary(client, content_id: str) -> bytes:
    """
    Robust Confluence Cloud attachment download.

    Uses:
      GET /wiki/rest/api/content/{contentId}/download
    which returns a redirect to the actual binary.
    """
    if not content_id or not content_id.isdigit():
        raise ValueError(f"Invalid attachment contentId: {content_id}")

    url = f"{client.base_url}/wiki/rest/api/content/{content_id}/download"

    r = client.session.get(url, allow_redirects=False, timeout=60)

    # Expect redirect to the actual binary
    if r.status_code in (301, 302, 303, 307, 308):
        download_url = r.headers.get("Location")
        if not download_url:
            raise RuntimeError(f"No redirect Location for attachment {content_id}")

        r2 = client.session.get(download_url, timeout=120)
        r2.raise_for_status()
        return r2.content

    # Some tenants may allow direct download
    r.raise_for_status()
    return r.content
