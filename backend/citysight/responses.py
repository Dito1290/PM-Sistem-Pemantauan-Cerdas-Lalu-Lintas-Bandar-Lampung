"""Consistent JSON envelopes.

Success: ``{"data": ..., "meta": {...}}``; error: ``{"error": {"code", "message", "details"}}``.
"""
from __future__ import annotations

from typing import Any

from flask import jsonify


def ok(data: Any = None, status: int = 200, meta: dict | None = None):
    body: dict[str, Any] = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def error_body(code: str, message: str, details: Any = None) -> dict:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return {"error": payload}


def fail(status: int, code: str, message: str, details: Any = None):
    return jsonify(error_body(code, message, details)), status
