"""Small shared validators for competition request parameters."""

from __future__ import annotations

from datetime import date
import re
from uuid import uuid4


def day_value(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Day must be YYYY-MM-DD (UTC)")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("Day must be a valid YYYY-MM-DD date (UTC)") from None
    return value


def positive_id(value: str | int, label: str) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[1-9]\d{0,18}", str(value)):
        raise ValueError(f"{label} must be a positive integer")
    number = int(value)
    if number > 9223372036854775807:
        raise ValueError(f"{label} is too large")
    return number


def request_key(value: str | None) -> str:
    if value is None:
        return str(uuid4())
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", value):
        raise ValueError("request_id must contain 8–100 letters, digits, underscores or hyphens")
    return value
