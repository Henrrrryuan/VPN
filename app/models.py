from datetime import datetime, timezone

from app.extensions import db


class Node(db.Model):
    __tablename__ = "nodes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    region = db.Column(db.String(16), nullable=False, index=True)
    base_url = db.Column(db.String(255), nullable=False)
    username = db.Column(db.String(64), nullable=False)
    password = db.Column(db.String(128), nullable=False)
    inbound_id = db.Column(db.Integer, nullable=False)
    verify_ssl = db.Column(db.Boolean, nullable=False, default=True)
    public_host = db.Column(db.String(255), nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    uuid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    vless_link = db.Column(db.Text, nullable=False)
    current_node_id = db.Column(db.Integer, db.ForeignKey("nodes.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class UserNodeAccess(db.Model):
    __tablename__ = "user_node_accesses"
    __table_args__ = (
        db.UniqueConstraint("user_id", "node_id", name="uq_user_node_access"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    node_id = db.Column(db.Integer, db.ForeignKey("nodes.id"), nullable=False, index=True)
    uuid = db.Column(db.String(64), nullable=False)
    vless_link = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    traffic_limit_gb = db.Column(db.Float, nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    traffic_limit_gb = db.Column(db.Float, nullable=False)
    traffic_remaining_gb = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    plan = db.relationship("Plan", lazy="joined")
