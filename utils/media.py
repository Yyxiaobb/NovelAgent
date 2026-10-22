"""Small local media store used for user avatars and project covers."""

from __future__ import annotations

import base64
import binascii
import re
import uuid
from pathlib import Path

from fastapi import HTTPException


MEDIA_ROOT = Path(__file__).resolve().parent.parent / "uploads"
_DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|jpg|webp|gif|svg\+xml));base64,(.+)$", re.IGNORECASE | re.DOTALL)
_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif", "image/svg+xml": "svg"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _decode_image(data_url: str) -> tuple[str, bytes]:
    match = _DATA_URL.match(data_url.strip())
    if not match:
        raise HTTPException(status_code=422, detail="请选择 PNG、JPG、WEBP、GIF 或 SVG 图片")
    media_type, encoded = match.groups()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise HTTPException(status_code=422, detail="图片内容无效，请重新选择") from error
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片大小不能超过 5 MB")
    return media_type.lower(), raw


def save_data_url(data_url: str, category: str) -> str:
    media_type, raw = _decode_image(data_url)
    extension = _EXTENSIONS[media_type]
    directory = MEDIA_ROOT / category
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{extension}"
    (directory / filename).write_bytes(raw)
    return f"/uploads/{category}/{filename}"


def save_svg(svg: str, category: str = "covers") -> str:
    raw = svg.encode("utf-8")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="生成的封面过大")
    directory = MEDIA_ROOT / category
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.svg"
    (directory / filename).write_bytes(raw)
    return f"/uploads/{category}/{filename}"
