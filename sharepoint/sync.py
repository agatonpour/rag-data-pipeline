from pathlib import Path
from sharepoint.client import ensure_folder_path, upload_file


def sync_local_folder(graph, drive_id: str, local_root: Path, remote_root: str):
    """
    Mirrors local_root into SharePoint drive under remote_root.
    Returns summary dict.
    """
    local_root = Path(local_root)
    remote_root = remote_root.strip("/")

    ensure_folder_path(graph, drive_id, remote_root)

    summary = {
        "files_created": 0,
        "files_updated": 0,
        "files_failed": 0,
    }

    for p in local_root.rglob("*"):
        if p.is_dir():
            continue

        rel = p.relative_to(local_root).as_posix()
        remote_path = f"{remote_root}/{rel}" if remote_root else rel

        try:
            result = upload_file(graph, drive_id, remote_path, str(p))
            if result == "created":
                summary["files_created"] += 1
            else:
                summary["files_updated"] += 1
        except Exception:
            summary["files_failed"] += 1

    return summary
