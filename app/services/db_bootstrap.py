from sqlalchemy import inspect, text

from app.extensions import db


def _users_column_names() -> set[str]:
    insp = inspect(db.engine)
    return {c["name"] for c in insp.get_columns("users")}


def ensure_schema_compatibility() -> None:
    """补齐极旧 SQLite 库中 users 表缺失列（如仅有 id/username/password 的 MVP 库）。"""
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
