from flask import Blueprint, g, jsonify, request

from app.extensions import db
from app.models import Node, UserNodeAccess
from app.services.xui_client import XUIClient, XUIClientError
from app.utils.auth_guard import jwt_required

nodes_bp = Blueprint("nodes", __name__)


@nodes_bp.get("")
@jwt_required
def list_nodes():
    user = g.current_user
    nodes = Node.query.filter_by(is_enabled=True).order_by(Node.id.asc()).all()

    user_accesses = UserNodeAccess.query.filter_by(user_id=user.id).all()
    access_map = {a.node_id: a for a in user_accesses}

    return jsonify(
        {
            "success": True,
            "data": {
                "nodes": [
                    {
                        "id": n.id,
                        "name": n.name,
                        "region": n.region,
                        "selected": user.current_node_id == n.id,
                        "has_access": n.id in access_map,
                    }
                    for n in nodes
                ]
            },
        }
    )


@nodes_bp.post("/select")
@jwt_required
def select_node():
    user = g.current_user
    payload = request.get_json(silent=True) or {}
    try:
        node_id = int(payload.get("node_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "node_id 必须是整数"}), 400

    node = Node.query.filter_by(id=node_id, is_enabled=True).first()
    if not node:
        return jsonify({"success": False, "message": "节点不存在或已停用"}), 404

    access = UserNodeAccess.query.filter_by(user_id=user.id, node_id=node.id).first()
    if not access:
        xui = XUIClient.from_node(node)
        try:
            node_uuid, node_link = xui.create_vless_user(username=user.username, email=user.email)
        except XUIClientError as exc:
            return jsonify({"success": False, "message": str(exc)}), 502

        access = UserNodeAccess(
            user_id=user.id,
            node_id=node.id,
            uuid=node_uuid,
            vless_link=node_link,
        )
        db.session.add(access)

    user.current_node_id = node.id
    user.uuid = access.uuid
    user.vless_link = access.vless_link
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": "已切换节点",
            "data": {
                "current_node_id": user.current_node_id,
                "uuid": user.uuid,
                "vless_link": user.vless_link,
            },
        }
    )
