import os, json, requests

os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"

HEADERS = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03",
    "Content-Type": "application/json"
}

PAGE_ID = "37d16170-544f-8091-9350-e67303be5b82"

def api(method, url, data=None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    r = requests.request(method, url, headers=HEADERS, data=body)
    r.raise_for_status()
    return r.json()

# Archive old blocks
blocks = api("GET", f"https://api.notion.com/v1/blocks/{PAGE_ID}/children?page_size=50")
for b in blocks["results"]:
    bid = b["id"]
    bt = b["type"]
    txt = b[bt]["rich_text"][0]["text"]["content"] if b[bt].get("rich_text") else ""
    if "支持" in txt or "概述" in txt or "项目" in txt or "任务" in txt:
        continue
    api("PATCH", f"https://api.notion.com/v1/blocks/{bid}", {"archived": True})
print("Cleaned old blocks")

# New content
children = [
    {"type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":"1. 业务概述"}}]}},
    {"type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"通过企业微信定时提醒顾客上传三餐照片，自动识别餐食中碳水、蔬菜、肉类的占比，并通知对应服务人员进行点评。若服务人员超时未点评，自动逐级升级通知（服务人员 → 上级 → BOSS）。"}}]}},
    {"type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"核心流程：定时器触发 → 发送提醒 → 顾客拍照上传 → AI识别分析(GPT-4o Vision) → 通知服务人员点评 → 5分钟超时→通知上级 → 10分钟再超时→通知BOSS"}}]}},
    {"type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":"2. 定时调度"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"07:00 早餐提醒"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"12:00 午餐提醒"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"18:00 晚餐提醒"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"21:00 每日饮食报告汇总"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"每1分钟 检查点评超时升级"}}]}},
    {"type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":"3. 图片分析流程"}}]}},
    {"type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"顾客发图 → 企业微信回调推送MediaId → 后端下载图片 → GPT-4o Vision分析 → 返回碳/蔬/肉占比、预估热量、营养建议"}}]}},
    {"type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":"4. 点评升级机制"}}]}},
    {"type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"顾客上传照片 → AI分析完成 → 通知服务人员点评"}}]}},
    {"type":"numbered_list_item","numbered_list_item":{"rich_text":[{"type":"text","text":{"content":"5分钟内未点评 → 通知服务人员上级"}}]}},
    {"type":"numbered_list_item","numbered_list_item":{"rich_text":[{"type":"text","text":{"content":"上级10分钟未回应 → 通知BOSS"}}]}},
    {"type":"numbered_list_item","numbered_list_item":{"rich_text":[{"type":"text","text":{"content":"15分钟仍未处理 → BOSS介入"}}]}},
    {"type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":"5. 数据模型"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","annotations":{"bold":True},"text":{"content":"customer_staff_binding"}},{"type":"text","text":{"content":" — 顾客与服务员绑定关系（含上级和BOSS）"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","annotations":{"bold":True},"text":{"content":"analysis_records"}},{"type":"text","text":{"content":" — AI分析结果（碳/蔬/肉占比、热量、建议）"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","annotations":{"bold":True},"text":{"content":"staff_reviews"}},{"type":"text","text":{"content":" — 服务人员点评记录"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","annotations":{"bold":True},"text":{"content":"escalation_tasks"}},{"type":"text","text":{"content":" — 超时升级任务状态跟踪"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","annotations":{"bold":True},"text":{"content":"meal_reminders"}},{"type":"text","text":{"content":" — 定时提醒配置"}}]}},
    {"type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":"6. 配置清单"}}]}},
    {"type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"WECOM_CORPID / WECOM_CORPSECRET / WECOM_AGENTID / WECOM_TOKEN / WECOM_ENCODING_AES_KEY / WECOM_BOSS_USERID / OPENAI_API_KEY / ESCALATION_STAFF_TIMEOUT(5min) / ESCALATION_SUPERIOR_TIMEOUT(10min) / ESCALATION_BOSS_TIMEOUT(15min)"}}]}},
    {"type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":"7. 部署步骤"}}]}},
    {"type":"numbered_list_item","numbered_list_item":{"rich_text":[{"type":"text","text":{"content":"企业微信后台创建自建应用，配置回调URL"}}]}},
    {"type":"numbered_list_item","numbered_list_item":{"rich_text":[{"type":"text","text":{"content":"回调URL需公网可达（云服务器或frp/ngrok）"}}]}},
    {"type":"numbered_list_item","numbered_list_item":{"rich_text":[{"type":"text","text":{"content":"勾选接收图片消息和文本消息"}}]}},
    {"type":"numbered_list_item","numbered_list_item":{"rich_text":[{"type":"text","text":{"content":"首次使用需手动绑定顾客-服务员-上级-BOSS关系"}}]}},
    {"type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":"8. 注意事项"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"企业微信图片素材有效期3天，需及时下载转存"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"用MsgId做消息去重，防止重复处理"}}]}},
    {"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"API密钥用环境变量管理，不硬编码"}}]}},
]

result = api("PATCH", f"https://api.notion.com/v1/blocks/{PAGE_ID}/children", {"children": children})
print(f"OK: added {len(result['results'])} blocks")

# Verify
check = api("GET", f"https://api.notion.com/v1/blocks/{PAGE_ID}/children?page_size=35")
for b in check["results"]:
    t = b["type"]
    if t == "heading_2":
        txt = b[t]["rich_text"][0]["text"]["content"]
        print(f"\n## {txt}")
    elif t in ("paragraph", "bulleted_list_item", "numbered_list_item"):
        parts = [r["text"]["content"] for r in b[t]["rich_text"]]
        print("".join(parts))
