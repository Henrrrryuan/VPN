import os

from sqlalchemy import inspect, text

from app.extensions import db


def _users_column_names() -> set[str]:
    insp = inspect(db.engine)
    return {c["name"] for c in insp.get_columns("users")}


def ensure_schema_compatibility() -> None:
    """补齐极旧 SQLite 库中 users 表缺失列（如仅有 id/username/password 的 MVP 库）。"""
    # 避免线上因为 sqlite 路径所在目录不存在导致启动失败：
    # sqlalchemy 在首次连接/inspect 时会触发 sqlite3.OperationalError: unable to open database file
    try:
        url = db.engine.url
        if url.drivername.startswith("sqlite") and url.database:
            db_path = str(url.database)
            if db_path and db_path != ":memory:":
                full_path = db_path if os.path.isabs(db_path) else os.path.abspath(db_path)
                parent = os.path.dirname(full_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                # 不存在时创建一个空文件，确保 sqlite 能打开
                if not os.path.exists(full_path):
                    open(full_path, "a", encoding="utf-8").close()
    except Exception:
        # 如果这里失败，让后续 inspect/迁移报出原始错误更有利于排查
        pass

    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return

    columns = _users_column_names()

    # 旧字段名 password → password_hash
    if "password_hash" not in columns and "password" in columns:
        try:
            db.session.execute(text("ALTER TABLE users RENAME COLUMN password TO password_hash"))
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        columns = _users_column_names()

    if "email" not in columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(120)"))
        db.session.commit()
        db.session.execute(
            text(
                "UPDATE users SET email = 'user-' || CAST(id AS TEXT) || '@migrated.local' "
                "WHERE email IS NULL OR TRIM(COALESCE(email, '')) = ''"
            )
        )
        db.session.commit()
        columns = _users_column_names()

    if "uuid" not in columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN uuid VARCHAR(64)"))
        db.session.commit()
        db.session.execute(
            text(
                "UPDATE users SET uuid = lower(hex(randomblob(16))) || lower(hex(randomblob(8))) "
                "WHERE uuid IS NULL OR TRIM(COALESCE(uuid, '')) = ''"
            )
        )
        db.session.commit()
        columns = _users_column_names()

    if "vless_link" not in columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN vless_link TEXT"))
        db.session.commit()
        db.session.execute(text("UPDATE users SET vless_link = '' WHERE vless_link IS NULL"))
        db.session.commit()
        columns = _users_column_names()

    if "created_at" not in columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
        db.session.commit()
        db.session.execute(text("UPDATE users SET created_at = datetime('now') WHERE created_at IS NULL"))
        db.session.commit()
        columns = _users_column_names()

    if "current_node_id" not in columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN current_node_id INTEGER"))
        db.session.commit()

    if "is_disabled" not in columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN is_disabled INTEGER NOT NULL DEFAULT 0"))
        db.session.commit()
