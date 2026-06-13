import os, json, requests
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}
# Check all 4 pages' parent info
ids = ["37916170-544f-80ec-ab3d-f400a89ac033",  # 采购成功-自动补货规则
       "37d16170-544f-8091-9350-e67303be5b82",  # 定时机器人详细方案
       "37c16170-544f-81cf-934c-e14ec0f65ccf",  # 采购计划
       "37d16170-544f-8175-bc36-e080b5dec596"]  # 药师帮采购

for pid in ids:
    r = requests.get(f"https://api.notion.com/v1/pages/{pid}", headers=h)
    data = r.json()
    props = data["properties"]
    title = ""
    for key, val in props.items():
        ptype = val.get("type", "")
        if ptype == "title":
            title = "".join([t["text"]["content"] for t in val.get("title", [])])
            break
    parent = data["parent"]
    print(f"\n{pid[:20]}: {title}")
    print(f"  parent: {json.dumps(parent, ensure_ascii=False)}")
    print(f"  url: {data['url']}")
