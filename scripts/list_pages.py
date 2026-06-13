import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}

r = requests.post("https://api.notion.com/v1/search", headers=h, json={"page_size": 50}, timeout=30)
data = r.json()
with open("C:/Users/ADMINI~1/AppData/Local/Temp/opencode/all_pages.txt", "w", encoding="utf-8") as f:
    for p in data.get("results", []):
        props = p.get("properties", {})
        title = ""
        ptype = p.get("object", "")
        pid = p.get("id", "")
        url = p.get("url", "")
        for key, val in props.items():
            if val.get("type") == "title":
                title = "".join([t["text"]["content"] for t in val.get("title", [])])
                break
        f.write(f"[{ptype}] {pid}: {title}\n  {url}\n")
        # Also store parent
        parent = p.get("parent", {})
        f.write(f"  parent: {json.dumps(parent, ensure_ascii=False)}\n")

print("Done, check file")
