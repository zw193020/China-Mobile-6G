# -*- coding: utf-8 -*-
"""邮件通知模块：有变化时发详细变更邮件，无变化时发心跳邮件。

凭据一律从环境变量读取（SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_TO），
不写死在代码里。未配置 SMTP 时静默跳过，不影响抓取流程。
"""
import html
import smtplib
import time
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from config import SMTP, SITE_URL
from province_table import section_name

# 邮件正文字段展示顺序
FIELD_ORDER = [
    "资费标准", "资费类型", "适用地区", "上线日期", "有效期限", "违约责任",
    "方案编号", "适用范围", "销售渠道", "下线日期", "在网要求", "退订方式",
    "超出资费说明", "国内通话", "国内通用流量", "宽带", "移动高清", "其他服务内容",
]
_ORDER = {f: i for i, f in enumerate(FIELD_ORDER)}

BASE_FIELDS = [
    "资费类型", "归属", "资费标准", "适用地区",
    "国内通话", "国内通用流量", "宽带", "移动高清",
]

SHORT_ABOVE = 15          # 单类变化超过该条数改用一行式精简渲染
MAX_ITEMS_PER_GROUP = 80  # 每组最多展示条数，防止邮件过长


def _e(s):
    return html.escape("" if s is None else str(s))


def _sort_fields(fields: dict) -> list:
    return sorted(fields, key=lambda k: _ORDER.get(k, 1000))


def _tag(fields: dict) -> str:
    a = (fields or {}).get("归属") or ""
    b = (fields or {}).get("资费类型") or ""
    return f"{a}·{b}".strip("·")


def _item_full(item: dict) -> str:
    name = _e(item.get("name", ""))
    fields = item.get("fields") or {}
    rows = "".join(
        f"<tr><td class='k'>{_e(k)}</td><td>{_e(fields.get(k))}</td></tr>"
        for k in _sort_fields(fields) if _e(fields.get(k))
    )
    return (f"<div class='item'><div class='tt'>【{_e(_tag(fields))}】{name}</div>"
            f"<table>{rows}</table></div>")


def _item_basic(item: dict) -> str:
    name = _e(item.get("name", ""))
    fields = item.get("fields") or {}
    rows = "".join(
        f"<tr><td class='k'>{_e(k)}</td><td>{_e(fields.get(k))}</td></tr>"
        for k in _sort_fields(fields)
        if k in BASE_FIELDS and _e(fields.get(k))
    )
    return (f"<div class='item'><div class='tt'>【{_e(_tag(fields))}】{name}</div>"
            f"<table>{rows}</table></div>")


def _item_short(item: dict) -> str:
    fields = item.get("fields") or {}
    fee = _e(fields.get("资费标准") or "-")
    area = _e(fields.get("适用地区") or "-")
    return (f"<div class='short'>·【{_e(_tag(fields))}】{_e(item.get('name', ''))}"
            f"　<span class='m'>({fee}｜{area})</span></div>")


def _item_modified(m: dict) -> str:
    changed = m.get("changed") or {}
    rows = []
    for k in _sort_fields(changed):
        old_v, new_v = changed[k]
        if old_v is None:
            v = f"{_e(new_v)} <span class='add'>(新增该字段)</span>"
        elif new_v is None:
            v = f"{_e(old_v)} <span class='del'>(字段已移除)</span>"
        else:
            v = f"<span class='old'>{_e(old_v)}</span> → <span class='add'>{_e(new_v)}</span>"
        rows.append(f"<tr><td class='k'>{_e(k)}</td><td>{v}</td></tr>")
    return (f"<div class='item'><div class='tt'>【{_e(m.get('name', ''))}】</div>"
            f"<table>{''.join(rows)}</table></div>")


def _group(title: str, color: str, items: list, use_short: bool) -> str:
    if not items:
        return ""
    shown = items[:MAX_ITEMS_PER_GROUP]
    more = len(items) - len(shown)
    fn = _item_short if use_short else (_item_full if color == "add" else _item_basic)
    body = "".join(fn(it) if isinstance(it, dict) else f"<div class='short'>·{_e(it)}</div>"
                   for it in shown)
    tail = f"<div class='more'>…另有 {more} 条未列出，请到监控平台查看完整清单。</div>" if more > 0 else ""
    return (f"<h3 class='{color}'>{_e(title)}（{len(items)} 条）</h3>{body}{tail}")


def _build_html(reports: list) -> str:
    parts = []
    for r in reports:
        sec = r.get("section") or ""
        nm = "全网资费(全国)" if sec == "quanguo" else f"{section_name(sec)}资费"
        parts.append(f"<h2>{_e(nm)}</h2><div class='ts'>检测时间：{_e(r.get('timestamp', ''))}</div>")
        added = r.get("added") or []
        removed = r.get("removed") or []
        modified = r.get("modified") or []
        parts.append(_group("新增", "add", added, len(added) > SHORT_ABOVE))
        parts.append(_group("下架", "del", removed, len(removed) > SHORT_ABOVE))
        parts.append("".join(_item_modified(m) for m in modified[:MAX_ITEMS_PER_GROUP])
                     if modified else "")
        if modified:
            parts.insert(len(parts) - 1, f"<h3 class='mod'>修改（{len(modified)} 条）</h3>")
    link = (f"<p class='link'><a href='{_e(SITE_URL)}'>打开资费监控平台查看全部数据</a></p>"
            if SITE_URL else "")
    return f"""<html><head><meta charset="utf-8"><style>
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;
color:#222;line-height:1.7;margin:0;padding:16px;background:#f7f8fa}}
.box{{max-width:720px;margin:0 auto;background:#fff;border-radius:12px;padding:20px}}
h1{{font-size:17px;margin:0 0 4px}} h2{{font-size:16px;margin:22px 0 6px;
padding:8px 12px;background:#f0f5ff;border-radius:8px;color:#185FA5}}
h3{{font-size:15px;margin:16px 0 8px}} h3.add{{color:#3B6D11}} h3.del{{color:#A32D2D}}
h3.mod{{color:#854F0B}}
.ts{{color:#888;font-size:13px;margin-bottom:8px}}
.item{{border:1px solid #ececf0;border-radius:8px;padding:10px 12px;margin:8px 0}}
.tt{{font-weight:600;margin-bottom:6px}}
table{{width:100%;border-collapse:collapse}} td{{padding:2px 0;vertical-align:top;font-size:13px}}
td.k{{width:96px;color:#888;white-space:nowrap}}
.short{{padding:4px 0;font-size:13px}} .m{{color:#888}}
.add{{color:#3B6D11}} .del{{color:#A32D2D}} .old{{color:#888;text-decoration:line-through}}
.more{{color:#888;font-size:13px;padding:6px 0}}
.link{{margin-top:20px;text-align:center}}
.link a{{display:inline-block;background:#185FA5;color:#fff;text-decoration:none;
padding:10px 20px;border-radius:8px}}
</style></head><body><div class="box">
<h1>中国移动资费变更监控</h1>{''.join(parts)}{link}</div></body></html>"""


def _send(subject: str, html_body: str, plain: str) -> bool:
    if not (SMTP.get("user") and SMTP.get("password") and SMTP.get("to")):
        print("[notify] 未配置 SMTP（SMTP_USER/SMTP_PASSWORD/SMTP_TO），跳过邮件发送")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("资费监控", SMTP["user"]))
    msg["To"] = ", ".join(SMTP["to"])
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    last = None
    for i in range(3):
        try:
            if int(SMTP.get("port") or 465) == 465:
                s = smtplib.SMTP_SSL(SMTP["host"], int(SMTP["port"]), timeout=30)
            else:
                s = smtplib.SMTP(SMTP["host"], int(SMTP["port"]), timeout=30)
                s.starttls()
            with s:
                s.login(SMTP["user"], SMTP["password"])
                s.sendmail(SMTP["user"], SMTP["to"], msg.as_string())
            print(f"[notify] 邮件已发送至 {len(SMTP['to'])} 个收件人")
            return True
        except Exception as e:
            last = e
            print(f"[notify] 第 {i + 1} 次发送失败: {e}")
            time.sleep(5)
    print(f"[notify] 邮件发送最终失败: {last}")
    return False


def send_mail(reports: list, subject: str = None) -> bool:
    """有变化时发送完整变更邮件（函数名与 main.py 兼容）。"""
    if not reports:
        return False
    total = sum(len(r.get("added") or []) + len(r.get("removed") or [])
                + len(r.get("modified") or []) for r in reports)
    secs = "、".join(("全网" if r.get("section") == "quanguo" else section_name(r.get("section")))
                    for r in reports)
    subj = subject or f"【资费变更】{secs} 共 {total} 条变化"
    plain = "\n".join(
        f"{r.get('section')}: 新增{len(r.get('added') or [])} "
        f"下架{len(r.get('removed') or [])} 修改{len(r.get('modified') or [])}"
        for r in reports)
    return _send(subj, _build_html(reports), plain)


def send_nochange(timestamp: str = "") -> bool:
    html_body = f"""<html><head><meta charset="utf-8"></head><body
style="font-family:-apple-system,'PingFang SC',sans-serif;padding:16px">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:12px;padding:20px">
<h2 style="margin:0 0 8px">资费监控 · 心跳正常</h2>
<div style="color:#666">本次检测未发现资费变化。</div>
<div style="color:#888;margin-top:6px">检测时间：{_e(timestamp)}</div>
{"<p><a href='" + _e(SITE_URL) + "'>打开监控平台</a></p>" if SITE_URL else ""}
</div></body></html>"""
    return _send("【资费监控】本次无变化", html_body, f"本次无变化 {timestamp}")


def send_alert(message: str) -> bool:
    html_body = f"""<html><head><meta charset="utf-8"></head><body
style="font-family:-apple-system,'PingFang SC',sans-serif;padding:16px">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:12px;padding:20px">
<h2 style="margin:0 0 8px;color:#A32D2D">资费监控 · 异常提醒</h2>
<div>{_e(message)}</div>
<div style="color:#888;margin-top:8px">本次已跳过对比，历史快照未受影响。</div>
</div></body></html>"""
    return _send("【资费监控】抓取异常提醒", html_body, message)
