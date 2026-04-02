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

import requests


EMAIL_RE = re.compile(r"(?:email=|email:)\s*([^\s,]+)")
SRC_RE = re.compile(r"from\s+(\[[0-9a-fA-F:]+\]|(?:\d{1,3}\.){3}\d{1,3})")


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
    # 尝试从一行日志里提取 email + src ip
    m_email = EMAIL_RE.search(line)
    m_ip = SRC_RE.search(line)
    if not m_email or not m_ip:
        return None
    email = m_email.group(1).lower()
    src_ip = m_ip.group(1).strip("[]")
    return email, src_ip


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
            email, src_ip = parsed
            event = {"email": email, "src_ip": src_ip, "observed_at": iso_now()}
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

