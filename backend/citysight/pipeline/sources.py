"""Validation and masking of camera stream URLs."""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit


class InvalidStreamUrl(ValueError):
    pass


def is_file_source(url: str) -> bool:
    return url.startswith("file://") or url.startswith("/")


def file_path(url: str) -> str:
    return url[len("file://"):] if url.startswith("file://") else url


def validate_stream_url(url: str, *, schemes: list[str], hosts: list[str], allow_files: bool) -> str:
    url = url.strip()
    if any(ch.isspace() for ch in url):
        raise InvalidStreamUrl("stream_url tidak boleh mengandung spasi.")
    if is_file_source(url):
        if not allow_files:
            raise InvalidStreamUrl("Sumber file lokal tidak diizinkan (ALLOW_FILE_SOURCES=false).")
        path = file_path(url)
        if not os.path.isabs(path) or not os.path.isfile(path):
            raise InvalidStreamUrl("File video tidak ditemukan di server.")
        return url
    parts = urlsplit(url)
    if parts.scheme.lower() not in schemes:
        raise InvalidStreamUrl(f"Skema URL harus salah satu dari: {', '.join(schemes)}.")
    if not parts.hostname:
        raise InvalidStreamUrl("URL harus memiliki host.")
    if hosts and parts.hostname.lower() not in {h.lower() for h in hosts}:
        raise InvalidStreamUrl("Host stream tidak termasuk daftar yang diizinkan (STREAM_ALLOWED_HOSTS).")
    return url


def mask_url(url: str) -> str:
    """Hide credentials and query tokens before logging a stream URL."""
    if is_file_source(url):
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-url>"
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    if parts.username:
        netloc = f"***@{netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, "***" if parts.query else "", ""))
