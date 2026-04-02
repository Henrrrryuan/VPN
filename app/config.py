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
    # 3X-UI client limitIp: max distinct source IPs online at once per UUID (0 = unlimited).
    XUI_CLIENT_LIMIT_IP = int(os.getenv("XUI_CLIENT_LIMIT_IP", "2"))
    NODES_JSON = os.getenv("NODES_JSON", "")
    # usage estimate window
    USAGE_ONLINE_WINDOW_MS = int(os.getenv("USAGE_ONLINE_WINDOW_MS", "120000"))
