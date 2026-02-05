def fetch_all_pages(client, space_key):
    pages = []
    start = 0
    limit = 50

    while True:
        data = client.get(
            "/wiki/rest/api/content",
            params={
                "type": "page",
                "spaceKey": space_key,
                "limit": limit,
                "start": start,
                "expand": "version,ancestors"
            }
        )

        results = data.get("results", [])
        pages.extend(results)

        if len(results) < limit:
            break

        start += limit

    return pages

def fetch_page_html(client, page_id):
    data = client.get(
        f"/wiki/rest/api/content/{page_id}",
        params={"expand": "body.storage"}
    )
    return data["body"]["storage"]["value"]
