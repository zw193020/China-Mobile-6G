#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建站点数据：snapshots/ -> site/data/

用法：python scripts/build_site.py
  （本地与 GitHub Actions 通用，无参数）

输入：
  snapshots/{sec}.json        当前快照（由 main.py 抓取写入）
  snapshots/prev/{sec}.json   上一次快照副本（首次为空 -> 只建基线）
  snapshots/history.json      累积变更历史（首次为空）
输出：
  site/data/{sec}.json        当前全量资费，供前端列表页
  site/data/latest.json       仪表盘统计
  site/data/history.json      变更历史（最近 60 条）
  snapshots/prev/{sec}.json   本轮快照另存为下次对比基线
  snapshots/history.json      追加本轮变更记录
"""
import collections
import datetime
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(ROOT, "snapshots")
PREV = os.path.join(SNAP, "prev")
SITE_DATA = os.path.join(ROOT, "site", "data")
HISTORY = os.path.join(SNAP, "history.json")
for d in (PREV, SITE_DATA):
    os.makedirs(d, exist_ok=True)

SECTION_NAMES = {
    "quanguo": "全网(全国)",
    "beijing": "北京", "tianjin": "天津", "hebei": "河北", "shanxi": "山西",
    "neimenggu": "内蒙古", "liaoning": "辽宁", "jilin": "吉林",
    "heilongjiang": "黑龙江", "shanghai": "上海", "jiangsu": "江苏",
    "zhejiang": "浙江", "anhui": "安徽", "fujian": "福建", "jiangxi": "江西",
    "shandong": "山东", "henan": "河南", "hubei": "湖北", "hunan": "湖南",
    "guangdong": "广东", "guangxi": "广西", "hainan": "海南", "chongqing": "重庆",
    "sichuan": "四川", "guizhou": "贵州", "yunnan": "云南", "xizang": "西藏",
    "shaanxi": "陕西", "gansu": "甘肃", "qinghai": "青海", "ningxia": "宁夏",
    "xinjiang": "新疆",
}
DEFAULT_PROV = "hunan"
KEEP_HISTORY = 60


def now_str():
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))
    ).strftime("%Y-%m-%d %H:%M:%S")


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save(path, obj, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if compact:  # 站点数据用紧凑格式，显著减小体积（手机流量友好）
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=2)


def sec_name(sec):
    return SECTION_NAMES.get(sec, sec)


def all_sections():
    secs = []
    if os.path.isdir(SNAP):
        for fn in sorted(os.listdir(SNAP)):
            if fn.endswith(".json") and fn != "history.json" and fn != "peaks.json":
                sec = fn[:-5]
                if sec in SECTION_NAMES:
                    secs.append(sec)
    if "quanguo" in secs:
        secs.remove("quanguo")
        secs = ["quanguo"] + secs
    return secs


def name_of(item):
    return (item.get("name") or "").strip()


def field_diff(old, new):
    def fields_of(it):
        f = it.get("fields") if isinstance(it, dict) else None
        return f if isinstance(f, dict) else {}
    of, nf = fields_of(old), fields_of(new)
    keys = list(of.keys()) + [k for k in nf if k not in of]
    out = []
    for k in keys:
        ov = "" if of.get(k) is None else str(of.get(k)).strip()
        nv = "" if nf.get(k) is None else str(nf.get(k)).strip()
        if ov != nv:
            out.append({"field": k, "from": ov, "to": nv})
    return out


def diff_items(old_items, new_items):
    om = {name_of(i): i for i in (old_items or [])}
    nm = {name_of(i): i for i in (new_items or [])}
    added = [nm[k] for k in nm if k not in om]
    removed = [om[k] for k in om if k not in nm]
    modified, details = [], {}
    for k in om:
        if k in nm and om[k] != nm[k]:
            modified.append(om[k])
            details[k] = field_diff(om[k], nm[k])
    return added, removed, modified, details


def distribution(items):
    d = collections.defaultdict(collections.Counter)
    for it in items:
        f = it.get("fields") or {}
        d[f.get("归属") or "未知"][f.get("资费类型") or "未知"] += 1
    return {k: dict(v) for k, v in d.items()}


def main():
    sections = all_sections()
    if not sections:
        print("snapshots/ 下没有可用板块快照，跳过构建。")
        return
    now = now_str()
    cur = {}
    for sec in sections:
        j = load(os.path.join(SNAP, sec + ".json")) or {}
        cur[sec] = j.get("items") or []
        save(os.path.join(SITE_DATA, sec + ".json"), j, compact=True)

    # 变化历史：与 prev/ 对比
    history = load(HISTORY) or []
    rec = {"ts": now}
    has_change = False
    for sec in sections:
        old = load(os.path.join(PREV, sec + ".json"))
        old_items = (old or {}).get("items") if old else None
        if old_items is None:
            rec[sec] = {"note": "baseline"}
            continue
        added, removed, modified, details = diff_items(old_items, cur[sec])
        if added or removed or modified:
            has_change = True
        rec[sec] = {
            "added": len(added), "removed": len(removed), "modified": len(modified),
            "added_names": [name_of(a) for a in added[:60]],
            "removed_names": [name_of(r) for r in removed[:60]],
            "modified_names": [name_of(m) for m in modified[:60]],
        }
        if added:
            rec[sec]["added_details"] = {name_of(a): (a.get("fields") or {}) for a in added[:60]}
        if details:
            rec[sec]["modified_details"] = dict(list(details.items())[:60])
    if has_change:
        history.append(rec)
        history = history[-KEEP_HISTORY:]
    save(HISTORY, history)
    save(os.path.join(SITE_DATA, "history.json"), history, compact=True)

    # latest.json
    def_prov = DEFAULT_PROV if DEFAULT_PROV in sections else (
        sections[1] if len(sections) > 1 else sections[0])
    prov_stats = {}
    for sec in sections:
        dist = distribution(cur[sec])
        personal = sum((dist.get("个人资费") or {}).values())
        gq = sum((dist.get("政企资费") or {}).values())
        prov_stats[sec] = {"total": len(cur[sec]), "personal": personal, "gq": gq, "dist": dist}
    updated = ""
    for sec in sections:
        ts = (load(os.path.join(SNAP, sec + ".json")) or {}).get("timestamp") or ""
        if ts > updated:
            updated = ts
    latest = {
        "updated": updated or now,
        "default": def_prov,
        "sections": [
            {"section": sec, "name": sec_name(sec), "total": len(cur[sec]),
             "updated": (load(os.path.join(SNAP, sec + ".json")) or {}).get("timestamp") or ""}
            for sec in sections
        ],
        "quanguo_total": len(cur.get("quanguo", [])),
        "prov_total": len(cur.get(def_prov, [])),
        "prov_stats": prov_stats,
        "dist": distribution(cur.get("quanguo", [])),
        "def_dist": (distribution(cur.get(def_prov, [])).get("个人资费") or {}),
    }
    save(os.path.join(SITE_DATA, "latest.json"), latest, compact=True)

    # 本轮快照另存为下次基线
    for sec in sections:
        shutil.copy(os.path.join(SNAP, sec + ".json"), os.path.join(PREV, sec + ".json"))

    print("site built:", json.dumps({
        "sections": [sec_name(s) for s in sections],
        "updated": latest["updated"],
        "quanguo_total": latest["quanguo_total"],
        "prov_total": latest["prov_total"],
        "history_records": len(history),
        "this_change": has_change,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
