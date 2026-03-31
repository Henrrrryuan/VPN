from datetime import datetime, timedelta, UTC

import jwt
from flask import current_app


def generate_access_token(user_id: int) -> str:
    expires_hours = current_app.config["JWT_EXPIRES_HOURS"]
    payload = {
        "sub": str(user_id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=expires_hours),
    }
    token = jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")
    return token


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
