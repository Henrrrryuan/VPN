from functools import wraps

import jwt
from flask import jsonify, request, g

from app.models import User
from app.services.auth_service import decode_access_token


def jwt_required(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "未携带登录凭证（Authorization: Bearer …）"}), 401

        token = auth_header[7:]
        try:
            payload = decode_access_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "message": "登录已过期，请重新登录"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "message": "登录凭证无效，请重新登录"}), 401

        user_id = payload.get("sub")
        user = User.query.get(int(user_id)) if user_id else None
        if not user:
            return jsonify({"success": False, "message": "用户不存在或已被删除"}), 401

        g.current_user = user
        return handler(*args, **kwargs)

    return wrapper
