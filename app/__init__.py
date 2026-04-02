import os

from dotenv import load_dotenv
from flask import Flask

from app.extensions import db, bcrypt
from app.services.db_bootstrap import ensure_schema_compatibility
from app.services.node_service import bootstrap_nodes_if_needed


def create_app() -> Flask:
    load_dotenv()
    # 注意：必须在 load_dotenv() 之后再导入 Config，确保能读取到 .env 中的环境变量
    from app.config import Config

    app = Flask(__name__, template_folder="../templates")
    app.config.from_object(Config)

    db.init_app(app)
    bcrypt.init_app(app)

    from app.routes.auth import auth_bp
    from app.routes.nodes import nodes_bp
    from app.routes.online import online_bp
    from app.routes.pages import pages_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(nodes_bp, url_prefix="/api/nodes")
    app.register_blueprint(online_bp, url_prefix="/api/online")
    app.register_blueprint(pages_bp)

    with app.app_context():
        ensure_schema_compatibility()
        db.create_all()
        bootstrap_nodes_if_needed()

    return app
