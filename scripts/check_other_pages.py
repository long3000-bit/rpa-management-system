import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}
page_ids = ["37c16170-544f-81cf-934c-e14ec0f65ccf", "37d16170-544f-8175-bc36-e080b5dec596"]
for pid in page_ids:
    r = requests.get(f"https://api.notion.com/v1/pages/{pid}", headers=h)
    data = r.json()
    props = data["properties"]
    for key, val in props.items():
        ptype = val.get("type", "")
        title = ""
        if ptype == "title":
            title = "".join([t["text"]["content"] for t in val.get("title", [])])
        if title:
            print(f"{pid}: {title}")
    print(f"  parent: {data['parent']}")
