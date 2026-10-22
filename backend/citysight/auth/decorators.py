"""Role-based access control enforced on the server side."""
from __future__ import annotations

from functools import wraps

from flask_jwt_extended import current_user, verify_jwt_in_request

from ..errors import Forbidden


def roles_required(*roles: str, locations: list[str] | None = None):
    """Require a valid, non-revoked JWT whose *current* DB role is in ``roles``.

    Tokens are read from the Authorization header only, unless ``locations``
    says otherwise (the SSE endpoint also accepts ``?access_token=``).
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request(locations=locations or ["headers"])
            if roles and current_user.role not in roles:
                raise Forbidden("Anda tidak memiliki hak akses untuk tindakan ini.")
            return fn(*args, **kwargs)

        return wrapper

    return decorator
