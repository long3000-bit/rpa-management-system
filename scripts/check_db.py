import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}
# Check the database
db_id = "37616170-544f-8025-81f0-000bc9f2cb2b"
r = requests.get(f"https://api.notion.com/v1/databases/{db_id}", headers=h)
data = r.json()
print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
print(f"\n---title---")
print(json.dumps(data.get("title", []), ensure_ascii=False))
