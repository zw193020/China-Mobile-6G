# 快照模块：存储历史数据并对比变化
import json
import os
import time

SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def _snapshot_path(section: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f"{section}.json")


def load_snapshot(section: str):
    """读取上次抓取结果，不存在返回 None"""
    path = _snapshot_path(section)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_snapshot(section: str, data: dict):
    """保存本次抓取结果"""
    with open(_snapshot_path(section), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse_name(item) -> str:
    """从资费条目里解析业务名称。新版 item 为 dict{'name':...}，兼容旧版字符串。"""
    if isinstance(item, dict):
        return (item.get("name") or "").strip()
    if isinstance(item, str):
        for sep in ("：", ":"):
            if sep in item:
                return item.split(sep, 1)[0].strip()
        return item.strip()
    return ""


def _same_structure(old_items: list, new_items: list) -> bool:
    """新旧快照数据格式是否一致（都是结构化 dict 或都是字符串）。"""
    def is_dict(l):
        return bool(l) and isinstance(l[0], dict)
    return is_dict(old_items) == is_dict(new_items)


def diff(old_items: list, new_items: list) -> dict:
    """对比新旧资费条目，返回新增/下架/修改三类。
    以业务名称为 key；同名下字段有变化的归入 modified，
    并附 changed: {字段名: (旧值, 新值)}。"""
    old_map = {_parse_name(i): i for i in (old_items or [])}
    new_map = {_parse_name(i): i for i in (new_items or [])}
    added = [new_map[k] for k in new_map if k not in old_map]                       # 新增条目
    removed = [old_map[k] for k in old_map if k not in new_map]                     # 下架条目
    modified = []                                                                   # 修改条目
    for k in old_map:
        if k not in new_map or old_map[k] == new_map[k]:
            continue
        old_item, new_item = old_map[k], new_map[k]
        if isinstance(old_item, dict) and isinstance(new_item, dict):
            old_f, new_f = old_item.get("fields", {}), new_item.get("fields", {})
            changed = {
                f: (old_f.get(f), new_f.get(f))
                for f in sorted(set(old_f) | set(new_f))
                if old_f.get(f) != new_f.get(f)
            }
            modified.append({"name": k, "old": old_f, "new": new_f, "changed": changed})
        else:
            modified.append({"name": k, "old": old_item, "new": new_item,
                             "changed": {k: (old_item, new_item)}})
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
    }


def check_section(section: str, new_data: dict):
    """对比某板块变化，返回变化报告 dict 或 None。
    若旧快照格式与新数据不兼容（如升级前的字符串快照），先重建基线不通知。"""
    old = load_snapshot(section)
    if old is not None and not _same_structure(old.get("items", []), new_data.get("items", [])):
        print(f"  [基线] 板块 {section} 快照格式已升级，重建基线不通知")
        save_snapshot(section, new_data)
        return None

    d = diff(old.get("items") if old else [], new_data.get("items", []))
    has_change = bool(d["added"] or d["removed"] or d["modified"])
    report = {
        "section": section,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "added": d["added"],
        "removed": d["removed"],
        "modified": d["modified"],
        "keep_old": None if not old else old.get("timestamp"),
    }
    save_snapshot(section, new_data)
    return report if has_change else None
