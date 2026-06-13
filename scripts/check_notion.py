import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}
r = requests.get(
    "https://api.notion.com/v1/blocks/37d16170-544f-8091-9350-e67303be5b82/children?page_size=30",
    headers=h
)
data = r.json()
# Save raw response
with open("C:/Users/ADMINI~1/AppData/Local/Temp/opencode/notion_check.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# Print first few non-empty rich text values
for b in data["results"]:
    t = b["type"]
    if t in b and b[t].get("rich_text"):
        txt = "".join([rb["text"]["content"] for rb in b[t]["rich_text"]])
        if txt.strip():
            print(repr(txt[:80]))
