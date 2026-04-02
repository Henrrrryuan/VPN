import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "24"))

    XUI_BASE_URL = os.getenv("XUI_BASE_URL", "http://127.0.0.1:2053").rstrip("/")
    XUI_USERNAME = os.getenv("XUI_USERNAME", "admin")
    XUI_PASSWORD = os.getenv("XUI_PASSWORD", "admin")
    XUI_INBOUND_ID = int(os.getenv("XUI_INBOUND_ID", "1"))
    XUI_VERIFY_SSL = os.getenv("XUI_VERIFY_SSL", "true").lower() == "true"
    XUI_PUBLIC_HOST = os.getenv("XUI_PUBLIC_HOST", "")
    # 3X-UI 客户端 limitIp：每个 UUID 同一时间允许的不同来源公网 IP 数（0 = 不限制）。
    XUI_CLIENT_LIMIT_IP = int(os.getenv("XUI_CLIENT_LIMIT_IP", "2"))
    NODES_JSON = os.getenv("NODES_JSON", "")
    # 在线占用估算时间窗
    USAGE_ONLINE_WINDOW_MS = int(os.getenv("USAGE_ONLINE_WINDOW_MS", "120000"))

    # 节点侧上报 access log 的采集密钥（请求头：X-Ingest-Key）
    ONLINE_INGEST_KEY = os.getenv("ONLINE_INGEST_KEY", "")

    # 在线统计窗口（秒）：统计最近 N 秒内出现过的不同来源 IP 数
    ONLINE_STATS_WINDOW_SEC = int(os.getenv("ONLINE_STATS_WINDOW_SEC", "30"))
    # 同一来源 IP 在统计窗口内至少出现 N 条事件，才计为在线（过高会导致轻量流量长期显示 0）。
    ONLINE_MIN_EVENTS_PER_IP = int(os.getenv("ONLINE_MIN_EVENTS_PER_IP", "2"))
    # 仅当超过该秒数都没有收到在线上报时，才回退到 x-ui 的 lastOnline 估算。
    ONLINE_FALLBACK_GRACE_SEC = int(os.getenv("ONLINE_FALLBACK_GRACE_SEC", "120"))
    # 是否启用 x-ui lastOnline 回退估算。精准展示建议关闭（false）。
    ONLINE_ENABLE_XUI_FALLBACK = os.getenv("ONLINE_ENABLE_XUI_FALLBACK", "false").lower() == "true"
