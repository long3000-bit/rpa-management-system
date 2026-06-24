"""
逐个采购-建立评分规则表方案二期 第七轮真实采购验收辅助脚本
根据第六轮测试"第七轮真实采购验收方案"：
1. 记录测试前规则快照、候选评分、候选表和失败原因记录数量
2. 采购后验证各项指标
"""
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.database import Database

DB_PATH = PROJECT_ROOT / "data" / "app.db"
BACKUP_DIR = PROJECT_ROOT / "data" / "backups"


def get_counts(db: Database) -> dict:
    """获取各表当前记录数"""
    conn = db.get_connection()
    cursor = conn.cursor()
    counts = {}

    # 规则快照数
    cursor.execute("SELECT COUNT(*) as cnt FROM smart_match_rule_snapshots")
    counts["snapshots"] = cursor.fetchone()["cnt"]

    # 候选评分数
    cursor.execute("SELECT COUNT(*) as cnt FROM purchase_candidate_scores")
    counts["candidate_scores"] = cursor.fetchone()["cnt"]

    # 智能采购候选数
    cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_candidates")
    counts["smart_candidates"] = cursor.fetchone()["cnt"]

    # 失败原因数
    cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_failure_reasons")
    counts["failure_reasons"] = cursor.fetchone()["cnt"]

    return counts


def get_latest_snapshot(db: Database) -> dict:
    """获取最新规则快照"""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT snapshot_id, fallback_used, fallback_reason, created_at "
        "FROM smart_match_rule_snapshots ORDER BY created_at DESC LIMIT 1"
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    return {}


def verify_post_purchase(db: Database, before_counts: dict, batch_id: str = None) -> dict:
    """采购后验证，返回验证结果"""
    after_counts = get_counts(db)
    latest_snapshot = get_latest_snapshot(db)
    results = {}

    # 1. 检查是否生成了新的规则快照
    results["new_snapshot"] = after_counts["snapshots"] > before_counts["snapshots"]

    # 2. 检查最新快照不是fallback
    results["snapshot_not_fallback"] = (
        latest_snapshot.get("fallback_used") == 0
        or latest_snapshot.get("fallback_used") == "0"
    )
    results["fallback_reason"] = latest_snapshot.get("fallback_reason", "")

    # 3. 检查候选评分是否有rule_snapshot_id
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as total, "
        "SUM(CASE WHEN rule_snapshot_id IS NOT NULL AND rule_snapshot_id != '' THEN 1 ELSE 0 END) as has_snapshot "
        "FROM purchase_candidate_scores"
    )
    row = cursor.fetchone()
    results["pcs_total"] = row["total"]
    results["pcs_has_snapshot"] = row["has_snapshot"]

    # 4. 检查智能采购候选是否有rule_snapshot_id
    cursor.execute(
        "SELECT COUNT(*) as total, "
        "SUM(CASE WHEN rule_snapshot_id IS NOT NULL AND rule_snapshot_id != '' THEN 1 ELSE 0 END) as has_snapshot "
        "FROM smart_purchase_candidates"
    )
    row = cursor.fetchone()
    results["spc_total"] = row["total"]
    results["spc_has_snapshot"] = row["has_snapshot"]

    # 5. 检查双表快照ID是否一致
    if batch_id:
        cursor.execute(
            "SELECT rule_snapshot_id FROM purchase_candidate_scores "
            "WHERE purchase_batch_id = ? AND rule_snapshot_id IS NOT NULL AND rule_snapshot_id != '' "
            "LIMIT 1",
            (batch_id,)
        )
        pcs_row = cursor.fetchone()
        cursor.execute(
            "SELECT rule_snapshot_id FROM smart_purchase_candidates "
            "WHERE purchase_batch_id = ? AND rule_snapshot_id IS NOT NULL AND rule_snapshot_id != '' "
            "LIMIT 1",
            (batch_id,)
        )
        spc_row = cursor.fetchone()
        if pcs_row and spc_row:
            results["dual_snapshot_match"] = pcs_row["rule_snapshot_id"] == spc_row["rule_snapshot_id"]
            results["shared_snapshot_id"] = pcs_row["rule_snapshot_id"]
        else:
            results["dual_snapshot_match"] = False
            results["shared_snapshot_id"] = None

    # 6. 检查失败原因结构完整性
    cursor.execute(
        "SELECT COUNT(*) as total, "
        "SUM(CASE WHEN failure_stage IS NOT NULL AND failure_stage != '' THEN 1 ELSE 0 END) as has_stage, "
        "SUM(CASE WHEN failure_code IS NOT NULL AND failure_code != '' THEN 1 ELSE 0 END) as has_code, "
        "SUM(CASE WHEN failure_detail IS NOT NULL AND failure_detail != '' THEN 1 ELSE 0 END) as has_detail, "
        "SUM(CASE WHEN suggestion IS NOT NULL AND suggestion != '' THEN 1 ELSE 0 END) as has_suggestion, "
        "SUM(CASE WHEN rule_snapshot_id IS NOT NULL AND rule_snapshot_id != '' THEN 1 ELSE 0 END) as has_snapshot "
        "FROM smart_purchase_failure_reasons"
    )
    row = cursor.fetchone()
    results["failure_total"] = row["total"]
    results["failure_has_stage"] = row["has_stage"]
    results["failure_has_code"] = row["has_code"]
    results["failure_has_detail"] = row["has_detail"]
    results["failure_has_suggestion"] = row["has_suggestion"]
    results["failure_has_snapshot"] = row["has_snapshot"]

    return results


def backup_db() -> Path:
    """备份真实数据库"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"app_db_backup_{timestamp}.db"
    shutil.copy2(str(DB_PATH), str(backup_path))
    print(f"数据库已备份到: {backup_path}")
    return backup_path


def print_results(results: dict, title: str = "验证结果"):
    """打印验证结果"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    status_map = {
        "new_snapshot": ("新规则快照已生成", True),
        "snapshot_not_fallback": ("快照非fallback模式", True),
        "dual_snapshot_match": ("双表快照ID一致", True),
    }

    for key, (desc, expected) in status_map.items():
        if key in results:
            actual = results[key]
            mark = "PASS" if actual == expected else "FAIL"
            print(f"  [{mark}] {desc}: {actual}")

    # 数量类指标
    print(f"\n  候选评分表: 总计 {results.get('pcs_total', 0)}, 有快照ID {results.get('pcs_has_snapshot', 0)}")
    print(f"  智能候选表: 总计 {results.get('spc_total', 0)}, 有快照ID {results.get('spc_has_snapshot', 0)}")
    print(f"  失败原因表: 总计 {results.get('failure_total', 0)}")
    print(f"    - 有阶段: {results.get('failure_has_stage', 0)}")
    print(f"    - 有编码: {results.get('failure_has_code', 0)}")
    print(f"    - 有详情: {results.get('failure_has_detail', 0)}")
    print(f"    - 有建议: {results.get('failure_has_suggestion', 0)}")
    print(f"    - 有快照ID: {results.get('failure_has_snapshot', 0)}")

    if "shared_snapshot_id" in results and results["shared_snapshot_id"]:
        print(f"\n  共享快照ID: {results['shared_snapshot_id']}")

    if results.get("fallback_reason"):
        print(f"  Fallback原因: {results['fallback_reason']}")

    print(f"{'='*60}\n")


def main():
    """主入口"""
    if not DB_PATH.exists():
        print(f"错误: 数据库不存在 {DB_PATH}")
        sys.exit(1)

    db = Database(str(DB_PATH))
    db.initialize()

    if len(sys.argv) < 2:
        print("用法:")
        print(f"  python {sys.argv[0]} before     # 采购前记录计数")
        print(f"  python {sys.argv[0]} after      # 采购后验证（使用before保存的计数）")
        print(f"  python {sys.argv[0]} backup     # 备份数据库")
        print(f"  python {sys.argv[0]} verify [batch_id]  # 采购后验证（指定batch_id）")
        sys.exit(0)

    command = sys.argv[1]

    if command == "before":
        counts = get_counts(db)
        # 保存到临时文件
        count_file = PROJECT_ROOT / "data" / ".round7_before_counts.json"
        count_file.parent.mkdir(parents=True, exist_ok=True)
        with open(count_file, "w") as f:
            json.dump(counts, f, indent=2)
        print("采购前记录计数:")
        for k, v in counts.items():
            print(f"  {k}: {v}")
        print(f"\n计数已保存到: {count_file}")

    elif command == "after":
        count_file = PROJECT_ROOT / "data" / ".round7_before_counts.json"
        if not count_file.exists():
            print("错误: 请先执行 'before' 命令")
            sys.exit(1)
        with open(count_file) as f:
            before_counts = json.load(f)
        results = verify_post_purchase(db, before_counts)
        print_results(results, "第七轮采购后验证结果")

    elif command == "verify":
        batch_id = sys.argv[2] if len(sys.argv) > 2 else None
        count_file = PROJECT_ROOT / "data" / ".round7_before_counts.json"
        before_counts = {}
        if count_file.exists():
            with open(count_file) as f:
                before_counts = json.load(f)
        results = verify_post_purchase(db, before_counts, batch_id)
        print_results(results, f"第七轮验证结果{f' (batch_id={batch_id})' if batch_id else ''}")

    elif command == "backup":
        backup_db()

    else:
        print(f"未知命令: {command}")
        sys.exit(1)

    db.close()


if __name__ == "__main__":
    main()
