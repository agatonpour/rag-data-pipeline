import os
import json
import shutil
from pathlib import Path
from dotenv import load_dotenv

from confluence.client import ConfluenceClient
from confluence.pages import fetch_all_pages, fetch_page_html
from confluence.attachments import (
    fetch_attachments_for_page,
    normalize_attachment,
    download_attachment_binary,
    is_attachment_blocked,
)

from sharepoint.client import GraphClient, get_site_id, get_drive_id_by_name
from sharepoint.sync import delete_removed_files, sync_changed_files


def sanitize_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    for ch in bad:
        name = name.replace(ch, "")
    name = " ".join(name.split())
    return name.strip()


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {"pages": {}, "attachments": {}, "pendingDeletes": []}

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"pages": {}, "attachments": {}, "pendingDeletes": []}

    state.setdefault("pages", {})
    state.setdefault("attachments", {})
    state.setdefault("pendingDeletes", [])
    return state


def has_file_changed(previous_entry: dict | None, version, relative_path: str) -> bool:
    if not previous_entry:
        return True

    return (
        previous_entry.get("version") != version
        or previous_entry.get("relativePath") != relative_path
    )


def main():
    load_dotenv()

    base_url = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
    email = os.environ["CONFLUENCE_EMAIL"]
    token = os.environ["CONFLUENCE_API_TOKEN"]

    spaces = ["F2", "Support", "IN", "SPR"]

    SPACE_FOLDER_NAMES = {
        "F2": "Flowscape 2.0",
        "IN": "Installation",
        "Support": "Support",
        "SPR": "Software Products Releases",
    }

    EXCLUDED_PAGE_TITLES = {
        "Archived Products Home"
    }
    
    output_root = Path("output") / "dry_run"

    #Wipe local export output so we don't accidentally upload old folders
    if output_root.exists():
        shutil.rmtree(output_root)
    ensure_dir(output_root)

    state_dir = Path("state")
    ensure_dir(state_dir)
    manifest_path = state_dir / "manifest.json"
    sync_state_path = state_dir / "sync_state.json"
    previous_state = load_state(sync_state_path)

    client = ConfluenceClient(base_url=base_url, email=email, api_token=token)

    manifest = {"spaces": {}}
    next_state = {"pages": {}, "attachments": {}, "pendingDeletes": []}
    current_state = {"pages": {}, "attachments": {}}
    changed_files = []
    changed_tokens = set()
    skipped_files = 0

    for space_key in spaces:
        print(f"Processing space: {space_key}")

        space_folder = sanitize_name(SPACE_FOLDER_NAMES.get(space_key, space_key))
        space_dir = output_root / space_folder
        ensure_dir(space_dir)

        pages = fetch_all_pages(client, space_key)
        # Identify "folder pages" (pages that have children)
        has_children = set()
        for p in pages:
            ancestors = p.get("ancestors") or []
            parent_id = ancestors[-1]["id"] if ancestors else None
            if parent_id:
                has_children.add(parent_id)
        
        manifest["spaces"][space_key] = {"pages": {}, "attachments": {}}

        for page in pages:
            page_id = page["id"]
            page_title = sanitize_name(page.get("title") or f"page-{page_id}") or f"page-{page_id}"
            ancestors = page.get("ancestors") or []

            excluded_branch = page.get("title") in EXCLUDED_PAGE_TITLES or any(
                ancestor.get("title") in EXCLUDED_PAGE_TITLES
                for ancestor in ancestors
            )

            if excluded_branch:
                continue

            # Build hierarchy from ancestors' titles
            parent_folder = space_dir
            for a in ancestors:
                at = sanitize_name(a.get("title") or a.get("id") or "Untitled") or "Untitled"
                parent_folder = parent_folder / at
            ensure_dir(parent_folder)

            # Baseline structure style:
            # - A folder named after the page (for children + attachments)
            # - An HTML file named "<Page Title>.html" next to that folder
            page_folder = parent_folder / page_title
            ensure_dir(page_folder)

            html_file = None
            # Only export HTML for leaf pages (pages without children)
            if page_id not in has_children:
                html_file = parent_folder / f"{page_title}.html"
                relative_html_path = html_file.relative_to(output_root).as_posix()
                page_version = page.get("version", {}).get("number")
                page_state_entry = {
                    "spaceKey": space_key,
                    "version": page_version,
                    "relativePath": relative_html_path,
                }

                if has_file_changed(previous_state.get("pages", {}).get(page_id), page_version, relative_html_path):
                    html = fetch_page_html(client, page_id)
                    html_file.write_text(html, encoding="utf-8")
                    token = f"pages:{page_id}"
                    changed_files.append(
                        {
                            "token": token,
                            "local_path": str(html_file),
                            "relative_path": relative_html_path,
                        }
                    )
                    changed_tokens.add(token)
                else:
                    skipped_files += 1
                    next_state["pages"][page_id] = page_state_entry

                current_state["pages"][page_id] = page_state_entry

            manifest["spaces"][space_key]["pages"][page_id] = {
                "title": page.get("title"),
                "version": page.get("version", {}).get("number"),
                "parentId": ancestors[-1]["id"] if ancestors else None,
                "localPath": str(html_file) if html_file else None,
                "folderPath": str(page_folder),
            }

            if html_file:
                manifest["spaces"][space_key]["pages"][page_id]["relativePath"] = html_file.relative_to(output_root).as_posix()
                manifest["spaces"][space_key]["pages"][page_id]["needsUpload"] = f"pages:{page_id}" in changed_tokens

            # Attachments stored under the page folder
            atts = fetch_attachments_for_page(client, page_id)
            for att in atts:
                att_id, att_info = normalize_attachment(base_url, att)
                filename = att_info.get("title") or f"attachment-{att_id}"

                if is_attachment_blocked(filename):
                    continue

                content_id = att_info.get("contentId")
                if not content_id:
                    continue

                safe_fn = sanitize_name(filename) or f"attachment-{att_id}"
                att_dir = page_folder / "attachments"
                ensure_dir(att_dir)

                out_file = att_dir / safe_fn
                relative_attachment_path = out_file.relative_to(output_root).as_posix()
                attachment_state_entry = {
                    "spaceKey": space_key,
                    "pageId": page_id,
                    "version": att_info.get("version"),
                    "relativePath": relative_attachment_path,
                }

                if has_file_changed(
                    previous_state.get("attachments", {}).get(att_id),
                    att_info.get("version"),
                    relative_attachment_path,
                ):
                    try:
                        binary = download_attachment_binary(client, content_id)
                    except Exception:
                        continue

                    out_file.write_bytes(binary)
                    token = f"attachments:{att_id}"
                    changed_files.append(
                        {
                            "token": token,
                            "local_path": str(out_file),
                            "relative_path": relative_attachment_path,
                        }
                    )
                    changed_tokens.add(token)
                else:
                    skipped_files += 1
                    next_state["attachments"][att_id] = attachment_state_entry

                current_state["attachments"][att_id] = attachment_state_entry

                att_info["pageId"] = page_id
                att_info["localPath"] = str(out_file)
                att_info["relativePath"] = relative_attachment_path
                att_info["needsUpload"] = f"attachments:{att_id}" in changed_tokens
                manifest["spaces"][space_key]["attachments"][att_id] = att_info

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest written to {manifest_path}")

    # SharePoint sync
    host = os.environ["SHAREPOINT_HOST"]
    site_path = os.environ["SHAREPOINT_SITE_PATH"]
    drive_name = os.environ["SHAREPOINT_DRIVE_NAME"]
    sp_root = os.environ["SHAREPOINT_ROOT_FOLDER"]

    graph = GraphClient()
    site_id = get_site_id(graph, host, site_path)
    drive_id = get_drive_id_by_name(graph, site_id, drive_name)

    print("Syncing to SharePoint...")
    summary = sync_changed_files(graph, drive_id, changed_files, sp_root)

    successful_tokens = set(summary.pop("successful_tokens"))

    for page_id, current_entry in current_state["pages"].items():
        token = f"pages:{page_id}"
        if token in successful_tokens or token not in changed_tokens:
            next_state["pages"][page_id] = current_entry
            continue

        previous_entry = previous_state.get("pages", {}).get(page_id)
        if previous_entry:
            next_state["pages"][page_id] = previous_entry

    for att_id, current_entry in current_state["attachments"].items():
        token = f"attachments:{att_id}"
        if token in successful_tokens or token not in changed_tokens:
            next_state["attachments"][att_id] = current_entry
            continue

        previous_entry = previous_state.get("attachments", {}).get(att_id)
        if previous_entry:
            next_state["attachments"][att_id] = previous_entry

    stale_paths = set(previous_state.get("pendingDeletes", []))

    for page_id, previous_entry in previous_state.get("pages", {}).items():
        persisted_entry = next_state["pages"].get(page_id)
        if persisted_entry is None:
            stale_paths.add(previous_entry["relativePath"])
            continue

        if previous_entry.get("relativePath") != persisted_entry.get("relativePath"):
            stale_paths.add(previous_entry["relativePath"])

    for att_id, previous_entry in previous_state.get("attachments", {}).items():
        persisted_entry = next_state["attachments"].get(att_id)
        if persisted_entry is None:
            stale_paths.add(previous_entry["relativePath"])
            continue

        if previous_entry.get("relativePath") != persisted_entry.get("relativePath"):
            stale_paths.add(previous_entry["relativePath"])

    delete_summary = delete_removed_files(graph, drive_id, sorted(stale_paths), sp_root)
    deleted_paths = set(delete_summary.pop("successful_paths"))
    next_state["pendingDeletes"] = sorted(stale_paths - deleted_paths)

    sync_state_path.write_text(json.dumps(next_state, indent=2), encoding="utf-8")
    print(f"Sync state written to {sync_state_path}")

    print("\n--- SharePoint Sync Summary ---")
    print(f"Target: {host}{site_path} / {drive_name} / {sp_root}")
    print(f"Files updated: {summary['files_updated']}")
    print(f"Files deleted: {delete_summary['files_deleted']}")
    print(f"Files skipped: {skipped_files}")
    print(f"Files failed:  {summary['files_failed'] + delete_summary['files_failed']}")
    if summary["files_failed"] + delete_summary["files_failed"] == 0:
        print("SharePoint sync completed successfully.\n")
    else:
        print("SharePoint sync completed with warnings.\n")


if __name__ == "__main__":
    main()
