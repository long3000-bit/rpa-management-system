import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}

# Query the database contents
db = "37d16170-544f-80dc-8d1f-e8bac6121f8f"
r = requests.post(f"https://api.notion.com/v1/databases/{db}/query", headers=h, json={"page_size": 20}, timeout=30)
data = r.json()
print(f"Total results: {len(data.get('results', []))}")
for p in data.get("results", []):
    props = p["properties"]
    title = ""
    for key, val in props.items():
        if val.get("type") == "title":
            title = "".join([t["text"]["content"] for t in val.get("title", [])])
            break
    print(f"  {p['id'][:20]}: {title}"[:100])

# Also search broadly
print("\n--- Searching all pages ---")
r2 = requests.post(f"https://api.notion.com/v1/search", headers=h, json={"page_size": 30}, timeout=30)
data2 = r2.json()
for p in data2.get("results", []):
    props = p.get("properties", {})
    title = ""
    for key, val in props.items():
        if val.get("type") == "title":
            title = "".join([t["text"]["content"] for t in val.get("title", [])])
            break
    if title:
        obj = p.get("object", "")
        print(f"  [{obj}] {p['id'][:20]}: {title}"[:120])
