import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}

# Check if 37c16170 has children
pid = "37c16170-544f-81cf-934c-e14ec0f65ccf"
r = requests.get(f"https://api.notion.com/v1/blocks/{pid}/children?page_size=10", headers=h, timeout=30)
data = r.json()
print(f"Blocks: {len(data.get('results', []))}")
for b in data.get("results", []):
    t = b.get("type", "")
    txt = ""
    if t in b and b[t].get("rich_text"):
        txt = "".join([rb["text"]["content"] for rb in b[t]["rich_text"]])
    print(f"  {t}: {txt[:80]}")

# Also check page info
r2 = requests.get(f"https://api.notion.com/v1/pages/{pid}", headers=h, timeout=30)
props = r2.json()["properties"]
for key, val in props.items():
    if val.get("type") == "title":
        title = "".join([t["text"]["content"] for t in val.get("title", [])])
        print(f"\nTitle: {title}")
        break
print(f"Parent: {json.dumps(r2.json()['parent'], ensure_ascii=False)}")
