import os, json, requests, time, sys
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
h = {
    "Authorization": "Bearer ntn_y59297188638JzJ1dUrSDZ0F1CaINKfCzvvdJESNLuy1Mj",
    "Notion-Version": "2025-09-03"
}

PAGE_ID = "37916170-544f-80ec-ab3d-f400a89ac033"

print("Step 1: Getting existing blocks...", flush=True)
r = requests.get(f"https://api.notion.com/v1/blocks/{PAGE_ID}/children?page_size=50", headers=h, timeout=30)
r.raise_for_status()
existing = r.json().get("results", [])
print(f"Found {len(existing)} existing blocks", flush=True)

print("Step 2: Archiving existing blocks...", flush=True)
for i, b in enumerate(existing):
    resp = requests.patch(f"https://api.notion.com/v1/blocks/{b['id']}", headers=h, json={"archived": True}, timeout=15)
    if i % 10 == 0:
        print(f"  archived {i}/{len(existing)}", flush=True)
print("Done archiving", flush=True)

print("Step 3: Building new blocks...", flush=True)
lines = [
    ("heading_2", "27. 评分规则表与数据落库设计"),
    ("paragraph", "近期连续出现 36s、12片*3板、7片*4板、80mg*7粒 与 80mg*28粒 等边界问题，说明采购规则不能继续全部写死在代码中。"),
    ("paragraph", "本阶段不切换 MySQL，继续使用 SQLite。当前主要问题不是数据库引擎性能，而是规则、候选、购物车快照和反写过程没有结构化落库。新表设计应避免 SQLite 专属写法，为后续迁移 MySQL 预留空间。"),
    ("heading_3", "27.1 开发目标"),
    ("code", "规则可维护\n候选可追溯\n反写可复盘\n失败原因可统计\n旧数据不强制迁移\n规则表为空时仍可使用内置默认规则运行"),
    ("heading_3", "27.2 规则集表 smart_match_rule_sets"),
    ("paragraph", "保存不同版本的采购匹配规则集。"),
    ("code", "CREATE TABLE smart_match_rule_sets (\n  rule_set_id TEXT PRIMARY KEY,\n  rule_set_code TEXT NOT NULL UNIQUE,\n  rule_set_name TEXT NOT NULL,\n  description TEXT,\n  is_default INTEGER DEFAULT 0,\n  status TEXT DEFAULT 'enabled',\n  version_no INTEGER DEFAULT 1,\n  created_by TEXT,\n  created_at TEXT NOT NULL,\n  updated_at TEXT NOT NULL\n);"),
    ("paragraph", "默认初始化："),
    ("code", "default_v1：默认采购规则，is_default=1\nstrict_spec_v1：严格规格测试规则，默认禁用"),
    ("heading_3", "27.3 规格单位别名表 smart_spec_unit_aliases"),
    ("paragraph", "维护 s、片装、粒装、板、盒 等单位映射。"),
    ("code", "CREATE TABLE smart_spec_unit_aliases (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  rule_set_id TEXT NOT NULL,\n  alias TEXT NOT NULL,\n  normalized_unit TEXT NOT NULL,\n  unit_type TEXT NOT NULL,\n  is_count_unit INTEGER DEFAULT 1,\n  is_multiplier INTEGER DEFAULT 1,\n  enabled INTEGER DEFAULT 1,\n  remark TEXT,\n  created_at TEXT NOT NULL,\n  updated_at TEXT NOT NULL,\n  UNIQUE(rule_set_id, alias)\n);"),
    ("paragraph", "默认初始化："),
    ("code", "s -> 片\n片 -> 片\n粒 -> 粒\n丸 -> 丸\n袋 -> 袋\n支 -> 支\n瓶 -> 瓶\n盒 -> 盒\n板 -> 板\n贴 -> 贴\n包 -> 包\n枚 -> 枚\n只 -> 只\n管 -> 管\n条 -> 条\n片装 -> 片\n粒装 -> 粒\n袋装 -> 袋\n支装 -> 支\n瓶装 -> 瓶\n盒装 -> 盒"),
    ("heading_3", "27.4 规格解析规则表 smart_spec_parse_rules"),
    ("paragraph", "维护规格解析表达式和优先级。第一版可先初始化规则，但界面暂不开放复杂正则编辑。"),
    ("code", "CREATE TABLE smart_spec_parse_rules (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  rule_set_id TEXT NOT NULL,\n  rule_name TEXT NOT NULL,\n  rule_type TEXT NOT NULL,\n  pattern TEXT NOT NULL,\n  priority INTEGER DEFAULT 100,\n  enabled INTEGER DEFAULT 1,\n  remark TEXT,\n  created_at TEXT NOT NULL,\n  updated_at TEXT NOT NULL\n);"),
    ("paragraph", "规则类型："),
    ("code", "strength：识别 0.6g、75mg、100ml:66.7g\npackage_count：识别 36s、12片*3板、7片*4板\nnoise_remove：去除 10盒起购、包邮、首推、日常热卖等营销噪声"),
    ("heading_3", "27.5 评分阈值表 smart_match_thresholds"),
    ("paragraph", "维护评分权重、阈值、硬拦规则。"),
    ("code", "CREATE TABLE smart_match_thresholds (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  rule_set_id TEXT NOT NULL,\n  name_weight REAL DEFAULT 0.62,\n  spec_weight REAL DEFAULT 0.20,\n  maker_weight REAL DEFAULT 0.18,\n  auto_pass_score INTEGER DEFAULT 85,\n  suspect_score INTEGER DEFAULT 70,\n  min_purchase_score INTEGER DEFAULT 70,\n  cart_backfill_min_score INTEGER DEFAULT 62,\n  spec_conflict_block INTEGER DEFAULT 1,\n  supplier_scope_required INTEGER DEFAULT 1,\n  price_check_enabled INTEGER DEFAULT 1,\n  enabled INTEGER DEFAULT 1,\n  created_at TEXT NOT NULL,\n  updated_at TEXT NOT NULL\n);"),
    ("paragraph", "默认规则："),
    ("code", "自动通过阈值：85\n疑似匹配阈值：70\n采购最低通过分：70\n购物车反写最低分：62\n规格包装总数冲突：硬拦截\n药师帮编码：仅用于辅助识别和购物车反写匹配，不作为采购优先依据"),
    ("heading_3", "27.6 厂家与品牌别名表 smart_name_aliases"),
    ("paragraph", "维护厂家、品牌、商品名简称。"),
    ("code", "CREATE TABLE smart_name_aliases (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  rule_set_id TEXT NOT NULL,\n  alias_type TEXT NOT NULL,\n  alias TEXT NOT NULL,\n  normalized_value TEXT NOT NULL,\n  enabled INTEGER DEFAULT 1,\n  remark TEXT,\n  created_at TEXT NOT NULL,\n  updated_at TEXT NOT NULL,\n  UNIQUE(rule_set_id, alias_type, alias)\n);"),
    ("paragraph", "别名类型："),
    ("code", "manufacturer\nbrand\nproduct_name\nsupplier"),
    ("paragraph", "示例："),
    ("code", "国风 -> 上海医药集团青岛国风药业股份有限公司\n泰嘉 -> 硫酸氢氯吡格雷片品牌提示\n代文 -> 缬沙坦胶囊品牌提示"),
    ("heading_3", "27.7 候选记录表 smart_purchase_candidates"),
    ("paragraph", "保存每次搜索到的候选与评分过程。每行至少保存最佳候选；如果页面返回多个候选，建议保存前 10 个。"),
    ("code", "CREATE TABLE smart_purchase_candidates (\n  candidate_id TEXT PRIMARY KEY,\n  batch_id TEXT NOT NULL,\n  item_id TEXT NOT NULL,\n  row_number INTEGER,\n  search_keyword TEXT,\n  candidate_rank INTEGER,\n  ysb_code TEXT,\n  candidate_name TEXT,\n  candidate_spec TEXT,\n  candidate_maker TEXT,\n  candidate_supplier TEXT,\n  candidate_supplier_full TEXT,\n  candidate_price REAL,\n  candidate_stock REAL,\n  min_purchase_quantity REAL,\n  name_score INTEGER,\n  spec_score INTEGER,\n  maker_score INTEGER,\n  total_score INTEGER,\n  price_pass INTEGER,\n  supplier_pass INTEGER,\n  spec_pass INTEGER,\n  maker_pass INTEGER,\n  final_pass INTEGER,\n  selected INTEGER DEFAULT 0,\n  reject_reason TEXT,\n  raw_data TEXT,\n  created_at TEXT NOT NULL\n);"),
    ("heading_3", "27.8 购物车快照表 smart_cart_snapshots"),
    ("paragraph", "保存每次读取购物车的快照批次。"),
    ("code", "CREATE TABLE smart_cart_snapshots (\n  snapshot_id TEXT PRIMARY KEY,\n  batch_id TEXT NOT NULL,\n  source TEXT NOT NULL,\n  item_count INTEGER DEFAULT 0,\n  captured_at TEXT NOT NULL,\n  created_by TEXT\n);"),
    ("heading_3", "27.9 购物车快照明细表 smart_cart_snapshot_items"),
    ("paragraph", "保存购物车真实商品行。"),
    ("code", "CREATE TABLE smart_cart_snapshot_items (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  snapshot_id TEXT NOT NULL,\n  ysb_code TEXT,\n  product_name TEXT,\n  spec TEXT,\n  manufacturer TEXT,\n  supplier TEXT,\n  price REAL,\n  quantity REAL,\n  valid_date TEXT,\n  raw_data TEXT,\n  created_at TEXT NOT NULL\n);"),
    ("heading_3", "27.10 购物车反写匹配明细表 smart_cart_backfill_matches"),
    ("paragraph", "保存采购表行与购物车行的匹配过程。"),
    ("code", "CREATE TABLE smart_cart_backfill_matches (\n  match_id TEXT PRIMARY KEY,\n  batch_id TEXT NOT NULL,\n  item_id TEXT NOT NULL,\n  snapshot_id TEXT NOT NULL,\n  cart_item_id INTEGER,\n  match_method TEXT,\n  match_score INTEGER,\n  ysb_code_match INTEGER DEFAULT 0,\n  name_score INTEGER,\n  spec_score INTEGER,\n  maker_score INTEGER,\n  spec_conflict INTEGER DEFAULT 0,\n  matched INTEGER DEFAULT 0,\n  reject_reason TEXT,\n  created_at TEXT NOT NULL\n);"),
    ("heading_3", "27.11 索引要求"),
    ("code", "CREATE INDEX idx_smart_purchase_items_status ON smart_purchase_items(batch_id, purchase_status);\nCREATE INDEX idx_smart_purchase_items_code ON smart_purchase_items(batch_id, ysb_code, actual_ysb_code);\nCREATE INDEX idx_smart_purchase_candidates_item ON smart_purchase_candidates(item_id);\nCREATE INDEX idx_smart_purchase_candidates_batch ON smart_purchase_candidates(batch_id, row_number);\nCREATE INDEX idx_cart_snapshot_batch ON smart_cart_snapshots(batch_id, captured_at);\nCREATE INDEX idx_cart_snapshot_items_snapshot ON smart_cart_snapshot_items(snapshot_id);\nCREATE INDEX idx_cart_backfill_item ON smart_cart_backfill_matches(batch_id, item_id);"),
    ("heading_3", "27.12 代码改造边界"),
    ("paragraph", "第一版只配置化以下内容："),
    ("code", "数量单位别名\n包装总数识别\n自动通过阈值\n疑似匹配阈值\n采购最低通过分\n购物车反写最低分\n规格冲突是否硬拦截"),
    ("paragraph", "暂不做复杂可视化规则表达式编辑器。复杂正则规则先由初始化数据维护。"),
    ("heading_3", "27.13 规则加载流程"),
    ("code", "启动采购任务\n读取默认 rule_set\n加载单位别名、规格解析规则、阈值和别名\n生成规则配置 JSON\nPython 服务层使用该配置进行预处理和反写评分\nNode 适配器通过输入 JSON 获取规则配置\n若规则表为空或读取失败，使用代码内置默认规则"),
    ("paragraph", "规则修改生效范围："),
    ("code", "只对新开始的采购任务生效\n执行中的任务继续使用启动时加载的规则快照\n历史结果不自动重算"),
    ("heading_3", "27.14 验收用例"),
    ("paragraph", "必须通过以下用例："),
    ("code", "养心氏片（薄膜衣片）：0.6g*36s 应匹配 0.6g*12片*3板\n代文 缬沙坦胶囊80mg*7粒 不应反写到 80mg*28粒\n代文 缬沙坦胶囊80mg*28粒 应反写到 80mg*28粒\n泰嘉 硫酸氢氯吡格雷片75mg*7片 不应匹配 75mg*7片*4板\n泰嘉 硫酸氢氯吡格雷片75mg*7片*4板 应匹配 75mg*7片*4板\n缺少药师帮编码时，仍能按名称、规格、厂家采购\n药师帮编码存在但名称、规格、厂家不通过时，不允许凭编码采购\n购物车已有同品种时，应反写购物车真实供应商、价格、规格、厂家、数量\n匹配失败时，只写失败原因，不写采购商品、供应商、价格"),
    ("heading_3", "27.15 发布策略"),
    ("paragraph", "建议分两步发布："),
    ("code", "第一步：只建表、写默认规则、记录候选和购物车快照，不改变现有评分结果\n第二步：逐步让采购评分和反写评分读取规则表"),
    ("paragraph", "这样可以降低风险，并便于对比代码规则和表规则的结果差异。"),
]

def make_block(block_type, text):
    if block_type == "heading_2":
        return {"type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}}
    elif block_type == "heading_3":
        return {"type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]}}
    elif block_type == "paragraph":
        return {"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}}
    elif block_type == "code":
        return {"type": "code", "code": {"language": "plain text", "rich_text": [{"type": "text", "text": {"content": text}}]}}
    return None

print(f"Total blocks to add: {len(lines)}", flush=True)
batch = []
for i, (btype, text) in enumerate(lines):
    block = make_block(btype, text)
    if block:
        batch.append(block)
    if len(batch) >= 20:
        payload = {"children": batch}
        r = requests.patch(f"https://api.notion.com/v1/blocks/{PAGE_ID}/children", headers=h, json=payload, timeout=30)
        if r.status_code == 200:
            print(f"Batch: added {len(batch)} blocks OK", flush=True)
        else:
            print(f"Batch error: {r.status_code} {r.text[:200]}", flush=True)
        batch = []
        time.sleep(0.3)

if batch:
    payload = {"children": batch}
    r = requests.patch(f"https://api.notion.com/v1/blocks/{PAGE_ID}/children", headers=h, json=payload, timeout=30)
    if r.status_code == 200:
        print(f"Final: added {len(batch)} blocks OK", flush=True)
    else:
        print(f"Final error: {r.status_code} {r.text[:200]}", flush=True)

print("ALL DONE", flush=True)
