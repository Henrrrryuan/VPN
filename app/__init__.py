import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from app.extensions import db, bcrypt
from app.services.db_bootstrap import ensure_schema_compatibility
from app.services.node_service import bootstrap_nodes_if_needed


def _register_api_error_handlers(app: Flask) -> None:
    """避免 /api/* 返回 HTML 500 页，前端把整页 HTML 当成 JSON message 展示。"""

    @app.errorhandler(Exception)
    def handle_exception(e: Exception):
        if isinstance(e, HTTPException):
            if request.path.startswith("/api/"):
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": e.description or str(e),
                        }
                    ),
                    e.code,
                )
            # Nginx 常把 /api/... 错转成正文路径 / → 仅 GET / 时得到 405 HTML
            if request.method == "POST" and request.content_type and "json" in request.content_type:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": e.description or str(e),
                            "hint": f"当前 path={request.path}。若你在登录/注册，应为 POST /api/auth/login 或 /api/auth/register；请检查 Nginx 的 proxy_pass 是否保留完整 URI（见 deploy/nginx-proxy.example.conf）。",
                        }
                    ),
                    e.code,
                )
            return e.get_response()

        app.logger.exception("unhandled exception path=%s method=%s", request.path, request.method)
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": str(e)}), 500
        # POST 到错误路径（常见于 Nginx 把 /api 转发丢路径）时也给 JSON，便于排查
        if request.method == "POST" and request.content_type and "json" in request.content_type:
            return jsonify(
                {
                    "success": False,
                    "message": str(e),
                    "hint": f"当前 path={request.path}；登录接口应为 POST /api/auth/login，请检查 Nginx proxy_pass 是否保留完整 URI。",
                }
            ), 500
        raise e


def create_app() -> Flask:
    load_dotenv()
    # 注意：必须在 load_dotenv() 之后再导入 Config，确保能读取到 .env 中的环境变量
    from app.config import Config

    app = Flask(__name__, template_folder="../templates", static_folder="static", static_url_path="/static")
    app.config.from_object(Config)

    db.init_app(app)
    bcrypt.init_app(app)

    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp
    from app.routes.nodes import nodes_bp
    from app.routes.pages import pages_bp
    from app.routes.plans import plans_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(nodes_bp, url_prefix="/api/nodes")
    app.register_blueprint(plans_bp, url_prefix="/api/plans")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(pages_bp)
    _register_api_error_handlers(app)

    with app.app_context():
        ensure_schema_compatibility()
        db.create_all()
        bootstrap_nodes_if_needed()
        from app.services.plan_service import bootstrap_plans_if_needed, ensure_canonical_plans

        bootstrap_plans_if_needed()
        ensure_canonical_plans()

    return app
