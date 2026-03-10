from pathlib import Path
from sharepoint.client import delete_file, ensure_folder_path, upload_file


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


def sync_changed_files(graph, drive_id: str, files, remote_root: str):
    """
    Uploads only the changed files from a previous diff step.
    Each item in files must contain:
      - token: stable identifier for the caller
      - local_path: absolute/relative local file path
      - relative_path: path relative to the sync root
    """
    remote_root = remote_root.strip("/")
    ensure_folder_path(graph, drive_id, remote_root)

    summary = {
        "files_updated": 0,
        "files_failed": 0,
        "successful_tokens": [],
    }

    for file_info in files:
        remote_path = file_info["relative_path"]
        if remote_root:
            remote_path = f"{remote_root}/{remote_path}"

        try:
            upload_file(graph, drive_id, remote_path, file_info["local_path"])
            summary["files_updated"] += 1
            summary["successful_tokens"].append(file_info["token"])
        except Exception:
            summary["files_failed"] += 1

    return summary


def delete_removed_files(graph, drive_id: str, relative_paths, remote_root: str):
    """
    Deletes files from SharePoint based on paths relative to the sync root.
    """
    remote_root = remote_root.strip("/")
    summary = {
        "files_deleted": 0,
        "files_failed": 0,
        "successful_paths": [],
    }

    for relative_path in relative_paths:
        remote_path = relative_path
        if remote_root:
            remote_path = f"{remote_root}/{relative_path}"

        try:
            delete_file(graph, drive_id, remote_path)
            summary["files_deleted"] += 1
            summary["successful_paths"].append(relative_path)
        except Exception:
            summary["files_failed"] += 1

    return summary
