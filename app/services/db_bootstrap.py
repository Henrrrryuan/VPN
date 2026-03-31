from sqlalchemy import inspect, text

from app.extensions import db


def ensure_schema_compatibility() -> None:
    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("users")}
    if "current_node_id" not in columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN current_node_id INTEGER"))
        db.session.commit()
