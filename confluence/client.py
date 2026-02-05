import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ConfluenceClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")

        # Basic auth for Atlassian (email + API token)
        self.auth = (email, api_token)

        self.headers = {
            "Accept": "application/json",
        }

        # Reuse connections + retries
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.auth = self.auth

        retry = Retry(
            total=8,
            connect=8,
            read=8,
            status=8,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get(self, path: str, params=None):
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=60)

        # If we got a non-2xx after retries, raise
        resp.raise_for_status()
        return resp.json()
