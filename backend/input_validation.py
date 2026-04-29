"""Input validation to reduce injection / abuse surface on REST."""

from __future__ import annotations

import re

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
MAX_PASSWORD_LEN = 128
MIN_PASSWORD_LEN = 8


def validate_username(username: object) -> tuple[bool, str]:
    if not isinstance(username, str):
        return False, "Invalid username"
    u = username.strip()
    if not USERNAME_RE.match(u):
        return False, "Username must be 3-32 chars (letters, digits, underscore)"
    return True, u


def validate_password(password: object) -> tuple[bool, str]:
    if not isinstance(password, str):
        return False, "Invalid password"
    if len(password) < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters"
    if len(password) > MAX_PASSWORD_LEN:
        return False, "Password too long"
    return True, password
