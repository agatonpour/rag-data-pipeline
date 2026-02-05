def build_page_index(pages):
    index = {}
    for page in pages:
        index[page["id"]] = page
    return index


def compute_page_path(page, page_index):
    ancestors = page.get("ancestors", [])
    titles = [a["title"] for a in ancestors]
    titles.append(page["title"])
    return "/".join(titles)

def fetch_space_info(client, space_key):
    data = client.get(f"/wiki/rest/api/space/{space_key}")
    return {
        "key": data["key"],
        "name": data["name"]
    }
