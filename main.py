# 中国移动资费监控软件 - 主入口
# 用法:
#   单次检查:  python main.py --once
#   循环监控:  python main.py --loop
#   初始化快照(不通知): python main.py --init
# 注意：源站（移动网关）会触发 TLS legacy renegotiation，较新 OpenSSL 默认拒绝。
#   在本文件最顶部注入 OPENSSL_CONF，确保任何 ssl 库初始化前生效（见 openssl_legacy.cnf）。
import os

_SSL_CNF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openssl_legacy.cnf")
if os.path.exists(_SSL_CNF):
    os.environ.setdefault("OPENSSL_CONF", _SSL_CNF)

import time

import fetcher
import notifier
import snapshot
from config import CHECK_INTERVAL

# 防误报护栏：本次抓取数量低于上次的该比例时，判定为"抓取不全"而非真实下架
ABNORMAL_DROP_RATIO = 0.7


def _is_abnormal_drop(section: str, new_items: list) -> bool:
    """本次抓取数量骤减（<上次70%）视为异常，跳过对比，避免误报下架"""
    old = snapshot.load_snapshot(section)
    if old is None:
        return False
    old_n = len(old.get("items") or [])
    new_n = len(new_items or [])
    # 上次一条都没有，或本次缺少不算异常（后续有基线再判断）
    if old_n == 0:
        return False
    return new_n < old_n * ABNORMAL_DROP_RATIO


def run_once(send_mail=True):
    """执行一轮抓取+对比+通知"""
    print("开始抓取资费数据...")
    data = fetcher.fetch_all()

    reports = []
    first_time = False  # 本轮是否有板块首次建立基线
    skipped = []        # 被防误报护栏拦截的板块
    for section, new_data in data.items():
        new_items = new_data.get("items", [])
        print(f"对比板块 {section} ({len(new_items)} 条)")

        # 抓取失败/部分分类失败：不对比、不覆盖快照，走异常提醒防误报
        if new_data.get("error"):
            print(f"  [异常] 板块 {section} 抓取失败，跳过对比")
            skipped.append(section)
            continue

        # 防误报护栏：抓取数量骤减，不对比、不覆盖快照，只提醒
        if _is_abnormal_drop(section, new_items):
            print(f"  [护栏] 板块 {section} 抓取数量异常骤减，跳过对比")
            skipped.append(section)
            continue

        # 首次运行：板块还没有基线快照，仅建立基线，不对比不发送
        if snapshot.load_snapshot(section) is None:
            snapshot.check_section(section, new_data)
            print(f"  [首次] 板块 {section} 已建立基线快照，本次不通知")
            first_time = True
            continue

        r = snapshot.check_section(section, new_data)
        if r:
            reports.append(r)

    if skipped:
        print(f"[护栏] 异常板块 {len(skipped)} 个: {skipped}")
        if send_mail:
            try:
                notifier.send_alert(f"资费监控疑似抓取不全，已跳过对比：{', '.join(skipped)}")
                print("[notify] 已发送抓取异常提醒")
            except Exception as e:
                print(f"[notify] 异常提醒发送失败: {e}")
        # 有板块被护栏拦截时，不发送"无变化心跳"，避免掩盖异常
        skipped_this_round = True
    else:
        skipped_this_round = False

    if reports:
        print(f"[变化] 检测到 {len(reports)} 个板块有变更")
        if send_mail:
            # 全网资费与湖南资费分开单独推送，各自一条钉钉消息，方便单独查看
            for r in reports:
                try:
                    if notifier.send_mail([r]):
                        print(f"[notify] 已单独推送板块 {r['section']} 变更通知")
                except Exception as e:
                    print(f"[notify] 板块 {r['section']} 推送失败: {e}")
        else:
            for r in reports:
                print(f"  {r['section']} 新增 {len(r['added'])} 条 / 消失 {len(r['removed'])} 条")
    elif not skipped_this_round:
        print("本次无资费变化。")
        # 无变化也发一条心跳通知（首次建基线那轮除外）
        if send_mail and not first_time:
            try:
                import datetime
                beijing = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
                notifier.send_nochange(beijing.strftime("%Y-%m-%d %H:%M:%S"))
                print("[notify] 已发送无变化心跳通知")
            except Exception as e:
                print(f"[notify] 心跳发送失败: {e}")


def main():
    import sys
    args = sys.argv[1:]
    if "--init" in args:
        print("初始化快照（不通知）...")
        run_once(send_mail=False)
        print("初始化完成。下次运行将基于此快照对比。")
    elif "--once" in args:
        run_once()
    else:
        print(f"进入循环监控模式，每 {CHECK_INTERVAL}s 检查一次 (Ctrl+C 退出)")
        run_once(send_mail=False)  # 首轮先建快照
        while True:
            time.sleep(CHECK_INTERVAL)
            try:
                run_once()
            except Exception as e:
                print(f"[error] {e}")


if __name__ == "__main__":
    main()
