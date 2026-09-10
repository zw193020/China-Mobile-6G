# 中国移动资费监控 - 配置文件
# 两种配置方式：
#  1) 通过环境变量注入（GitHub Actions 云端运行，推荐，见《部署说明》）
#  2) 直接改本文件（本地运行）
import os

from province_table import PROVINCES, DEFAULT_SECTIONS  # noqa: F401

# ============ 邮件通知配置（全部走环境变量，绝不硬编码） ============
SMTP = {
    "host": os.getenv("SMTP_HOST", "smtp.qq.com"),           # SMTP 服务器
    "port": int(os.getenv("SMTP_PORT", "465")),              # SSL 端口
    "user": os.getenv("SMTP_USER", ""),                      # 发件邮箱
    "password": os.getenv("SMTP_PASSWORD", ""),              # SMTP 授权码（不是登录密码）
    "to": [x for x in os.getenv("SMTP_TO", "").split(",") if x.strip()],  # 收件邮箱
}

# ============ 抓取配置 ============
# 板块：quanguo=全网资费（全国），hunan=湖南资费
# 需要纳入更多省份时，用环境变量 TRACK_PROVINCES 注入（如 "hunan,guangdong"）
_track_env = os.getenv("TRACK_PROVINCES", "").strip()
if _track_env:
    _wanted = [s.strip() for s in _track_env.split(",")
               if s.strip() and s.strip() != "quanguo"]
    SECTIONS = ["quanguo"] + _wanted
else:
    SECTIONS = list(DEFAULT_SECTIONS)
SECTIONS = list(dict.fromkeys(SECTIONS))

# 轮询间隔（秒），本地循环模式用，默认 1 小时
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))

# 监控平台网址（部署后填写，邮件里带直达链接）
SITE_URL = os.getenv("SITE_URL", "")
