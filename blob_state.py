import json
import os
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError


def _default_state() -> dict:
    return {
        "pages": {},
        "attachments": {},
        "pendingDeletes": [],
    }


def _get_blob_client():
    connection_string = os.getenv("AzureWebJobsStorage", "")
    container_name = os.getenv("STATE_CONTAINER", "confluence-sync-state")
    blob_name = os.getenv("STATE_BLOB_NAME", "sync_state.json")

    if not connection_string:
        raise RuntimeError("AzureWebJobsStorage is not set")

    service = BlobServiceClient.from_connection_string(connection_string)
    container = service.get_container_client(container_name)
    blob = container.get_blob_client(blob_name)
    return container, blob


def load_state_from_blob() -> dict:
    container, blob = _get_blob_client()

    try:
        data = blob.download_blob().readall()
        state = json.loads(data.decode("utf-8"))
    except ResourceNotFoundError:
        try:
            container.create_container()
        except Exception:
            pass
        return _default_state()
    except json.JSONDecodeError:
        return _default_state()

    state.setdefault("pages", {})
    state.setdefault("attachments", {})
    state.setdefault("pendingDeletes", [])
    return state


def save_state_to_blob(state: dict) -> None:
    _, blob = _get_blob_client()
    blob.upload_blob(
        json.dumps(state, ensure_ascii=False, indent=2),
        overwrite=True
    )