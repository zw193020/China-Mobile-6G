# 中国移动资费监控平台

定时抓取中国移动资费公示专区（全网资费 + 湖南资费），比对出**新增 / 下架 / 修改**，
有变化即发邮件提醒；全量数据发布为静态网页，手机电脑浏览器打开即可查看，国内外都能访问。

覆盖范围：个人 / 政企 × 套餐 / 加装包 / 营销活动，共六大类。

---

## 一、在 GitHub 上跑起来（3 步，零成本）

### 步骤 1：上传代码

在 GitHub 新建一个空仓库（Public），把本目录所有文件上传进去。
不会用 git 也行：仓库页面点 `Add file` → `Upload files`，把文件全部拖进去。
**注意 `.github` 文件夹要一起上传**（网页上传默认会包含，勾选后确认即可）。

### 步骤 2：配置邮件（仓库 Secrets）

进仓库 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`，依次添加：

| Name | 填什么 |
|---|---|
| `SMTP_HOST` | `smtp.qq.com`（QQ 邮箱）/ `smtp.163.com`（163）/ `smtp.gmail.com`（Gmail） |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | 发件邮箱完整地址 |
| `SMTP_PASSWORD` | **SMTP 授权码**（不是邮箱登录密码，获取方式见下方） |
| `SMTP_TO` | 收件邮箱，多个用英文逗号分隔 |
| `SITE_URL` | 监控平台网址（可选，邮件里会带直达链接） |

### 步骤 3：手动跑一次验证

仓库 `Actions` 标签页 → 左侧 `资费监控` → 右侧 `Run workflow`。
约 2 分钟后看日志，出现 `邮件已发送至 1 个收件人` 即成功。

之后无需操作：**每天北京时间 8:00 和 20:00 自动跑一次**。
想改频率，编辑 `.github/workflows/monitor.yml` 里的 `cron: "0 0,12 * * *"`。

---

## 二、SMTP 授权码怎么拿

- **QQ 邮箱**：设置 → 账号 → 开启 `IMAP/SMTP服务` → 发短信验证 → 得到 16 位授权码
- **163 邮箱**：设置 → POP3/SMTP/IMAP → 开启 SMTP → 设置授权码
- **Gmail**：账号 → 安全性 → 两步验证 → 应用专用密码（16 位）

---

## 三、本地运行（可选）

```bash
pip install pycryptodome
python main.py --init      # 首次建立基线快照（不发邮件）
python main.py --once      # 抓取一次并对比（有变化发邮件）
python main.py --loop      # 循环监控，每 1 小时一次
python scripts/build_site.py   # 生成网页数据到 site/data/
```

本地可用环境变量注入配置，也可直接改 `config.py`。

---

## 四、监控更多省份

默认只监控「全网 + 湖南」。要加省份，在仓库 `Settings` → `Secrets and variables`
→ `Actions` → `Variables` 里新增 `TRACK_PROVINCES`，值填省份拼音，逗号分隔，
如 `hunan,guangdong,zhejiang`。可选省份见 `province_table.py`。
每多一个省，单轮抓取约多 1 分钟。

---

## 五、目录结构

```
main.py              主入口：抓取 → 对比 → 通知
fetcher.py           直连官网接口（AES 加解密），六大类全量抓取
snapshot.py          快照存储与差异对比
notifier.py          邮件通知（HTML，含变更明细）
config.py            配置（全部支持环境变量）
province_table.py    31 省代码表
scripts/build_site.py   生成网页数据（site/data/）
site/                监控平台网页（静态，可部署到任意托管）
snapshots/           历史快照、变更历史
```

## 六、说明

- 数据来源于中国移动官网公开资费公示专区，仅供个人学习参考，办理业务以官方信息为准。
- 源站有限流策略，代码已内置 UA 轮换与降级自检；抓取间隔不建议低于 1 小时。
