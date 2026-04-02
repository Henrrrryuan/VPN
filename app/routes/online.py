from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func

from app.extensions import db
from app.models import Node, OnlineIpEvent, User

online_bp = Blueprint("online", __name__)


def _check_ingest_key() -> bool:
    expected = current_app.config.get("ONLINE_INGEST_KEY", "")
    provided = request.headers.get("X-Ingest-Key", "")
    return bool(expected) and provided == expected


@online_bp.post("/ingest")
def ingest():
    """
    节点侧上报在线事件。

    Body:
      {
        "events": [
          {"email":"u5@example.com","src_ip":"1.2.3.4","observed_at":"2026-04-02T12:00:00Z","node_id":1}
        ]
      }
    """
    if not _check_ingest_key():
        return jsonify({"success": False, "message": "invalid ingest key"}), 401

    payload = request.get_json(silent=True) or {}
    events = payload.get("events") or []
    if not isinstance(events, list):
        return jsonify({"success": False, "message": "events must be an array"}), 400

    accepted = 0
    rejected = 0
    for item in events:
        if not isinstance(item, dict):
            rejected += 1
            continue

        email = (item.get("email") or "").strip().lower()
        uuid_str = (item.get("uuid") or "").strip()
        src_ip = (item.get("src_ip") or "").strip()
        observed_at_raw = (item.get("observed_at") or "").strip()
        node_id = item.get("node_id")

        if (not email and not uuid_str) or not src_ip or not observed_at_raw:
            rejected += 1
            continue

        try:
            observed_at = datetime.fromisoformat(observed_at_raw.replace("Z", "+00:00"))
        except ValueError:
            rejected += 1
            continue

        # SQLite 存 naive UTC，避免与查询窗口比较时出现时区/类型不一致
        observed_naive = observed_at.astimezone(timezone.utc).replace(tzinfo=None)

        user = None
        if email:
            user = User.query.filter_by(email=email).first()
        if not user and uuid_str:
            user = User.query.filter(func.lower(User.uuid) == uuid_str.lower()).first()
        if not user:
            rejected += 1
            continue

        node = None
        if node_id is not None:
            try:
                node = Node.query.filter_by(id=int(node_id)).first()
            except (TypeError, ValueError):
                rejected += 1
                continue

        db.session.add(
            OnlineIpEvent(
                node_id=node.id if node else None,
                user_id=user.id,
                email=user.email,
                src_ip=src_ip,
                observed_at=observed_naive,
            )
        )
        accepted += 1

    db.session.commit()
    return jsonify({"success": True, "data": {"accepted": accepted, "rejected": rejected}})


@online_bp.post("/cleanup")
def cleanup():
    """清理过期在线事件（管理员用途，仍用 ingest key 保护）。"""
    if not _check_ingest_key():
        return jsonify({"success": False, "message": "invalid ingest key"}), 401

    payload = request.get_json(silent=True) or {}
    keep_seconds = int(payload.get("keep_seconds") or 3600)
    cutoff = datetime.now(timezone.utc).timestamp() - keep_seconds
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)

    deleted = OnlineIpEvent.query.filter(OnlineIpEvent.observed_at < cutoff_dt).delete()
    db.session.commit()
    return jsonify({"success": True, "data": {"deleted": int(deleted or 0)}})

