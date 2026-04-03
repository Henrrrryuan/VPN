from flask import Blueprint, jsonify, make_response, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/api/health")
def health():
    """用于排查 Nginx/反代是否把 /api 转到本应用。"""
    return jsonify({"success": True})


def _html_no_cache(template: str):
    """避免部署更新后浏览器仍缓存旧版 HTML（例如已删除的 dashboard 区块）。"""
    resp = make_response(render_template(template))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@pages_bp.get("/")
def index():
    return _html_no_cache("landing.html")


@pages_bp.get("/login")
def login():
    return _html_no_cache("index.html")


@pages_bp.get("/dashboard")
def dashboard():
    return _html_no_cache("dashboard.html")


@pages_bp.get("/admin")
def admin_page():
    """管理员：调整用户到期与流量并同步 X-UI（需配置 ADMIN_TOKEN）。"""
    return _html_no_cache("admin.html")
