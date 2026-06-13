import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}

PAGE_ID = "37916170-544f-80ec-ab3d-f400a89ac033"
r = requests.get(f"https://api.notion.com/v1/blocks/{PAGE_ID}/children?page_size=70", headers=h, timeout=30)
data = r.json()
print(f"Total blocks: {len(data.get('results', []))}")
with open("C:/Users/ADMINI~1/AppData/Local/Temp/opencode/verify_section27.txt", "w", encoding="utf-8") as f:
    for b in data.get("results", []):
        t = b.get("type", "")
        txt = ""
        if t in b and b[t].get("rich_text"):
            txt = "".join([rb["text"]["content"] for rb in b[t]["rich_text"]])
        elif t == "code" and b.get("code"):
            txt = b["code"]["rich_text"][0]["text"]["content"][:80] + "..."
        f.write(f"[{t}] {txt}\n")
print("Written to verify file")
