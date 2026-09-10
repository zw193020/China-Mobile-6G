#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键完成 GitHub 侧配置：创建仓库 -> 推送代码 -> 写入 Secrets -> 触发 workflow

用法（token 只在本机内存使用，不写入任何文件）：
  python tools/setup_github.py --token <GITHUB_PAT> \
      --smtp-host smtp.qq.com --smtp-port 465 \
      --smtp-user xxx@qq.com --smtp-pass <授权码> --smtp-to yyy@qq.com
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

try:
    from nacl import encoding, public
except ImportError:
    print("缺少 pynacl，请先 pip install pynacl")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.github.com"


def gh(method, path, token, data=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "cmcc-monitor-setup",
        })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            body = json.loads(body)
        except Exception:
            pass
        return e.code, body


def git(*args):
    p = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def encrypt_secret(pub_key_b64, value):
    pk = public.PublicKey(pub_key_b64.encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pk).encrypt(value.encode("utf-8"))
    return base64.b64encode(sealed).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--owner", default="zaki")
    ap.add_argument("--repo", default="China-Mobile-6G")
    ap.add_argument("--smtp-host", required=True)
    ap.add_argument("--smtp-port", default="465")
    ap.add_argument("--smtp-user", required=True)
    ap.add_argument("--smtp-pass", required=True)
    ap.add_argument("--smtp-to", required=True)
    ap.add_argument("--site-url", default="https://f9164e2a48194f9dbcd699f370869df7.app.workbuddy.link")
    a = ap.parse_args()

    code, me = gh("GET", "/user", a.token)
    if code != 200:
        print("token 无效或无权限:", me); sys.exit(1)
    print("已登录 GitHub 账号:", me.get("login"))

    # 1) 仓库不存在则创建
    code, info = gh("GET", f"/repos/{a.owner}/{a.repo}", a.token)
    if code == 200:
        print(f"仓库已存在：{info.get('full_name')}")
    else:
        code, info = gh("POST", "/user/repos", a.token, {
            "name": a.repo, "private": False, "auto_init": False,
            "description": "中国移动资费监控（全网+湖南）"})
        if code not in (200, 201):
            print("创建仓库失败:", info); sys.exit(1)
        print("已创建仓库：", info.get("full_name"))

    # 2) 推送代码
    remote = f"https://{a.owner}:{a.token}@github.com/{a.owner}/{a.repo}.git"
    if not os.path.exists(os.path.join(ROOT, ".git")):
        git("git", "init", "-b", "main")
    git("git", "config", "user.name", a.owner)
    git("git", "config", "user.email", f"{a.owner}@users.noreply.github.com")
    git("git", "add", "-A")
    git("git", "commit", "-m", "init: 中国移动资费监控（全网+湖南）")
    code, out = git("git", "push", "-u", remote, "main")
    if code != 0:
        print("推送失败:\n", out); sys.exit(1)
    print("代码已推送到 GitHub")

    # 3) 写入 Secrets
    code, pk = gh("GET", f"/repos/{a.owner}/{a.repo}/actions/secrets/public-key", a.token)
    if code != 200:
        print("获取仓库公钥失败:", pk); sys.exit(1)
    secrets = {
        "SMTP_HOST": a.smtp_host, "SMTP_PORT": a.smtp_port,
        "SMTP_USER": a.smtp_user, "SMTP_PASSWORD": a.smtp_pass,
        "SMTP_TO": a.smtp_to, "SITE_URL": a.site_url,
    }
    for k, v in secrets.items():
        code, r = gh("PUT", f"/repos/{a.owner}/{a.repo}/actions/secrets/{k}", a.token, {
            "encrypted_value": encrypt_secret(pk["key"], v), "key_id": pk["key_id"]})
        print(("  ✓ " if code in (200, 201, 204) else "  ✗ ") + k + ("" if code in (200, 201, 204) else f" -> {r}"))

    # 4) 触发一次 workflow
    code, r = gh("POST", f"/repos/{a.owner}/{a.repo}/actions/workflows/monitor.yml/dispatches",
                 a.token, {"ref": "main"})
    print("已触发定时任务" if code in (200, 204) else f"触发失败: {r}")
    print(f"\n完成！查看运行结果：https://github.com/{a.owner}/{a.repo}/actions")


if __name__ == "__main__":
    main()
