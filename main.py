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
from sharepoint.sync import sync_local_folder


def sanitize_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    for ch in bad:
        name = name.replace(ch, "")
    name = " ".join(name.split())
    return name.strip()


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


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

    client = ConfluenceClient(base_url=base_url, email=email, api_token=token)

    manifest = {"spaces": {}}

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

            # Build hierarchy from ancestors' titles
            ancestors = page.get("ancestors") or []
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
                html = fetch_page_html(client, page_id)
                html_file = parent_folder / f"{page_title}.html"
                html_file.write_text(html, encoding="utf-8")

            manifest["spaces"][space_key]["pages"][page_id] = {
                "title": page.get("title"),
                "version": page.get("version", {}).get("number"),
                "parentId": ancestors[-1]["id"] if ancestors else None,
                "localPath": str(html_file) if html_file else None,
                "folderPath": str(page_folder),
            }

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

                try:
                    binary = download_attachment_binary(client, content_id)
                except Exception as e:
                    continue

                safe_fn = sanitize_name(filename) or f"attachment-{att_id}"
                att_dir = page_folder / "attachments"
                ensure_dir(att_dir)

                out_file = att_dir / safe_fn
                out_file.write_bytes(binary)

                att_info["pageId"] = page_id
                att_info["localPath"] = str(out_file)
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
    summary = sync_local_folder(graph, drive_id, output_root, sp_root)

    print("\n--- SharePoint Sync Summary ---")
    print(f"Target: {host}{site_path} / {drive_name} / {sp_root}")
    print(f"Files created: {summary['files_created']}")
    print(f"Files updated: {summary['files_updated']}")
    print(f"Files failed:  {summary['files_failed']}")
    if summary["files_failed"] == 0:
        print("SharePoint sync completed successfully.\n")
    else:
        print("SharePoint sync completed with warnings.\n")


if __name__ == "__main__":
    main()
