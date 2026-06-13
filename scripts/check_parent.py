import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}
# Check the known page's parent
pid = "37d16170-544f-8091-9350-e67303be5b82"
r = requests.get(f"https://api.notion.com/v1/pages/{pid}", headers=h)
data = r.json()
print("Parent:", json.dumps(data["parent"], ensure_ascii=False))
print("Title:", json.dumps(data["properties"].get("页面名称", data["properties"].get("title", {}).get("title", [{}])[0].get("text", {}).get("content", "")), ensure_ascii=False))

# Show all property keys and types
props = data["properties"]
for key, val in props.items():
    ptype = val.get("type", "")
    print(f"  prop: {repr(key)} -> {ptype}")
