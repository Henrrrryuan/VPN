#!/usr/bin/env python3
"""
从 Xray access log 里提取用户 email 和来源 IP，并上报到 Flask。

使用方式（在 VPS 节点上运行）：
  1) 确保 Xray 开启 access log 到文件，例如 /var/log/xray/access.log
  2) 配置下面的环境变量
  3) 运行：python3 xray_online_shipper.py

环境变量：
  FLASK_INGEST_URL  例如：http://YOUR-FLASK-HOST:5001/api/online/ingest
  ONLINE_INGEST_KEY 与 Flask 的 ONLINE_INGEST_KEY 一致
  XRAY_ACCESS_LOG   access.log 路径，默认 /var/log/xray/access.log
  NODE_ID           可选：节点 ID（用于后续多节点分析）
"""

import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests


# 面板里常见：email: user@x.com 或 email=user@x.com
EMAIL_RE = re.compile(r"(?:email|Email)\s*[=:]\s*([^\s,\]]+)")
# 客户端 UUID（日志里可能出现，用于 email 未打印时的兜底）
UUID_RE = re.compile(
    r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b"
)
# 常见两种格式：
# 1) from 1.2.3.4 / from [ipv6]
# 2) 2024/07/16 21:27:57 127.0.0.1:15364 accepted tcp:...（无 "from "，这是多数 Xray 默认 access 行）
SRC_FROM = re.compile(r"from\s+(\[[0-9a-fA-F:]+\]|(?:\d{1,3}\.){3}\d{1,3})\b")
SRC_AFTER_TS = re.compile(
    r"\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\s+"
    r"(\[[0-9a-fA-F:]+\]|(?:\d{1,3}\.){3}\d{1,3}):\d+\s+accepted\b"
)


def extract_src_ip(line: str) -> Optional[str]:
    m = SRC_FROM.search(line)
    if m:
        return m.group(1).strip("[]")
    m = SRC_AFTER_TS.search(line)
    if m:
        return m.group(1).strip("[]")
    return None


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def follow(path: str):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.2)
                continue
            yield line.strip()


def parse_line(line: str):
    """返回 (email, src_ip) 或 (None, uuid, src_ip) 由 main 组装为 ingest 字段。"""
    src_ip = extract_src_ip(line)
    if not src_ip:
        return None
    m_email = EMAIL_RE.search(line)
    if m_email:
        return ("email", m_email.group(1).lower(), src_ip)
    m_uuid = UUID_RE.search(line)
    if m_uuid:
        return ("uuid", m_uuid.group(1).lower(), src_ip)
    return None


def main():
    ingest_url = os.getenv("FLASK_INGEST_URL", "").strip()
    ingest_key = os.getenv("ONLINE_INGEST_KEY", "").strip()
    access_log = os.getenv("XRAY_ACCESS_LOG", "/var/log/xray/access.log").strip()
    node_id = os.getenv("NODE_ID", "").strip()
    node_id_int = None
    if node_id:
        try:
            node_id_int = int(node_id)
        except ValueError:
            raise SystemExit("NODE_ID 必须是整数")

    if not ingest_url or not ingest_key:
        raise SystemExit("请设置 FLASK_INGEST_URL 和 ONLINE_INGEST_KEY 环境变量")

    session = requests.Session()
    headers = {"Content-Type": "application/json", "X-Ingest-Key": ingest_key}

    batch = []
    last_flush = time.time()

    for line in follow(access_log):
        parsed = parse_line(line)
        if parsed:
            kind, ident, src_ip = parsed
            event: dict = {"src_ip": src_ip, "observed_at": iso_now()}
            if kind == "email":
                event["email"] = ident
            else:
                event["uuid"] = ident
            if node_id_int is not None:
                event["node_id"] = node_id_int
            batch.append(event)

        now = time.time()
        if batch and (len(batch) >= 50 or (now - last_flush) >= 2):
            try:
                resp = session.post(ingest_url, json={"events": batch}, headers=headers, timeout=10)
                if resp.status_code != 200:
                    print("上报失败", resp.status_code, resp.text[:200])
                    time.sleep(1)
                    continue
                batch.clear()
                last_flush = now
            except Exception as e:
                print("上报异常", str(e)[:200])
                # 不清空 batch，稍后重试
                time.sleep(1)


if __name__ == "__main__":
    main()

