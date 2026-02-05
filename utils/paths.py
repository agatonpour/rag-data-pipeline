import re

def safe_folder_name(name: str) -> str:
    # Remove characters that are annoying for filesystems / SharePoint
    name = name.strip()
    name = re.sub(r"[<>:\"/\\|?*]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name
