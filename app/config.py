import os


class Config:
    # 可选：部署后在控制台页脚显示，便于确认是否已同步最新代码（例：2026-04-03-1）
    DEPLOY_TAG = os.getenv("DEPLOY_TAG", "").strip()

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 开发时关闭 debug 也要能立刻看到模板更新，避免一直停留在旧版 dashboard
    TEMPLATES_AUTO_RELOAD = True

    JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "24"))

    # 可选：静态页在别的端口/域名时，把落地页上的「登录/订阅」等链接指到本应用根，例如 http://127.0.0.1:5001
    AUTH_PAGE_BASE_URL = os.getenv("AUTH_PAGE_BASE_URL", "").strip().rstrip("/")

    XUI_BASE_URL = os.getenv("XUI_BASE_URL", "http://127.0.0.1:2053").rstrip("/")
    # 3X-UI「面板设置」中的 Web 基础路径（如 /LIpz75bRbfQtHWunT5），与浏览器地址栏 /xxx/panel/inbounds 一致。
    # 若 XUI_BASE_URL 已含该路径可留空；仅写 http://ip:port 时必须设置。
    XUI_WEB_BASE_PATH = os.getenv("XUI_WEB_BASE_PATH", "").strip()
    XUI_USERNAME = os.getenv("XUI_USERNAME", "admin")
    XUI_PASSWORD = os.getenv("XUI_PASSWORD", "admin")
    XUI_INBOUND_ID = int(os.getenv("XUI_INBOUND_ID", "1"))
    XUI_VERIFY_SSL = os.getenv("XUI_VERIFY_SSL", "true").lower() == "true"
    XUI_PUBLIC_HOST = os.getenv("XUI_PUBLIC_HOST", "")
    # 3X-UI 客户端 limitIp：每个 UUID 同一时间允许的不同来源公网 IP 数（0 = 不限制）。
    XUI_CLIENT_LIMIT_IP = int(os.getenv("XUI_CLIENT_LIMIT_IP", "2"))
    NODES_JSON = os.getenv("NODES_JSON", "")
    # 管理接口 /api/admin/orders*：留空则禁用（请求返回 403）
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
