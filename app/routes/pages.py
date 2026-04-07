import os
import re

from flask import Blueprint, abort, current_app, jsonify, make_response, redirect, render_template, send_from_directory, url_for

pages_bp = Blueprint("pages", __name__)

_QR_FILENAME = re.compile(
    r"^(?:(?:starter|standard|pro)_(?:week|month|quarter|half|year))|(?:recharge_(?:50|100|200))\.png$"
)


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


@pages_bp.get("/checkout")
def checkout():
    """套餐支付页（本地开发：http://127.0.0.1:5001/checkout）。"""
    return _html_no_cache("checkout.html")


@pages_bp.get("/qr/<filename>")
def checkout_qr(filename: str):
    """收款二维码：/qr/starter_month.png、/qr/recharge_100.png 等（文件位于 app/static/qr/）。"""
    if not _QR_FILENAME.match(filename):
        abort(404)
    directory = os.path.join(current_app.root_path, "static", "qr")
    return send_from_directory(directory, filename, mimetype="image/png")


@pages_bp.get("/recharge")
def recharge_page():
    """流量包支付页（例：http://127.0.0.1:5001/recharge?gb=100）。"""
    return _html_no_cache("recharge.html")


@pages_bp.get("/admin")
def admin_legacy_redirect():
    """旧「用户限额」页已移除；订单管理见 /admin/orders，配额请在 3X-UI 面板调整。"""
    return redirect(url_for("pages.admin_orders_page"), code=302)


@pages_bp.get("/admin/orders")
def admin_orders_page():
    """管理员：待审核支付订单列表，确认收款后调用 X-UI 开通（需 ADMIN_TOKEN）。"""
    return _html_no_cache("admin_orders.html")
