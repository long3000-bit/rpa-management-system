import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}
# Check the page we found
r = requests.get("https://api.notion.com/v1/pages/37916170-544f-80ec-ab3d-f400a89ac033", headers=h)
data = r.json()
props = data["properties"]
for key, val in props.items():
    ptype = val.get("type", "")
    title = ""
    if ptype == "title":
        title = "".join([t["text"]["content"] for t in val.get("title", [])])
    elif val.get(ptype) and isinstance(val[ptype], dict):
        title = val[ptype].get("rich_text", [{}])[0].get("text", {}).get("content", "")
    print(f"{key} ({ptype}): {title[:50]}")
