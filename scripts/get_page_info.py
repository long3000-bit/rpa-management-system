import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}

# Get page info
pid = "37916170-544f-80ec-ab3d-f400a89ac033"
r = requests.get(f"https://api.notion.com/v1/pages/{pid}", headers=h)
data = r.json()
props = data["properties"]
for key, val in props.items():
    ptype = val.get("type", "")
    title = ""
    if ptype == "title":
        title = "".join([t["text"]["content"] for t in val.get("title", [])])
    elif val.get(ptype) and isinstance(val[ptype], dict):
        rich = val[ptype].get("rich_text", [])
        if rich:
            title = rich[0].get("text", {}).get("content", "")
    print(f"{key} ({ptype}): {title[:60]}")
print(f"\nurl: {data['url']}")

# Check existing blocks
r2 = requests.get(f"https://api.notion.com/v1/blocks/{pid}/children?page_size=50", headers=h)
blocks = r2.json()
print(f"\nExisting blocks: {len(blocks.get('results', []))}")
for b in blocks.get("results", [])[:10]:
    t = b.get("type", "")
    txt = ""
    if t in b and b[t].get("rich_text"):
        txt = "".join([rb["text"]["content"] for rb in b[t]["rich_text"]])
    print(f"  [{t}] {txt[:80]}")
