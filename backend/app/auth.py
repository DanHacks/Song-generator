"""User accounts and JWT sessions (stdlib-only: pbkdf2 + HS256 JWT)."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid

from .storage import DATA_DIR

USERS_DIR = os.path.join(DATA_DIR, "users")
_SECRET_FILE = os.path.join(DATA_DIR, ".auth_secret")
_ALGO = "HS256"
_ITERATIONS = 200_000
TOKEN_TTL_S = 60 * 60 * 24 * 30  # 30 days

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def _ensure_dirs():
    os.makedirs(USERS_DIR, exist_ok=True)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64url(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _secret() -> bytes:
    if os.environ.get("AUTH_SECRET"):
        return os.environ["AUTH_SECRET"].encode()
    if os.path.exists(_SECRET_FILE):
        with open(_SECRET_FILE, "rb") as f:
            return f.read().strip()
    os.makedirs(os.path.dirname(_SECRET_FILE), exist_ok=True)
    key = secrets.token_bytes(32)
    with open(_SECRET_FILE, "wb") as f:
        f.write(key)
    return key


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return digest.hex()


def _user_path(username: str) -> str:
    return os.path.join(USERS_DIR, username + ".json")


def _load_user(username: str):
    path = _user_path(username)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def signup(username: str, password: str):
    """Create an account. Returns user dict or raises ValueError."""
    if not USERNAME_RE.match(username):
        raise ValueError("Username must be 3-32 characters: letters, numbers, underscore.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    _ensure_dirs()
    if _load_user(username):
        raise ValueError("Username is already taken.")
    salt = secrets.token_bytes(16)
    user = {
        "username": username,
        "password_hash": _hash_password(password, salt),
        "salt": salt.hex(),
        "client_id": "user_" + uuid.uuid4().hex[:12],
        "created_at": time.time(),
    }
    tmp = _user_path(username) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(user, f)
    os.replace(tmp, _user_path(username))
    return user


def verify(username: str, password: str):
    user = _load_user(username)
    if not user:
        return None
    salt = bytes.fromhex(user["salt"])
    if hmac.compare_digest(_hash_password(password, salt), user["password_hash"]):
        return user
    return None


def encode_token(username: str) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": _ALGO, "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({"sub": username, "iat": now, "exp": now + TOKEN_TTL_S}).encode())
    signing_input = header + "." + payload
    sig = hmac.new(_secret(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url(sig)


def decode_token(token: str):
    """Return username or None."""
    try:
        header, payload, sig = token.split(".")
        signing_input = header + "." + payload
        expected = hmac.new(_secret(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64url(sig)):
            return None
        head = json.loads(_unb64url(header))
        if head.get("alg") != _ALGO:
            return None
        claims = json.loads(_unb64url(payload))
        if int(claims["exp"]) < time.time():
            return None
        username = claims.get("sub")
        if not username or not _load_user(username):
            return None
        return username
    except Exception:
        return None


def user_from_token(token: str):
    username = decode_token(token)
    return _load_user(username) if username else None


def resolve_client(authorization, header_value):
    """Prefer a valid Bearer JWT; fall back to the X-Client-Id header."""
    if authorization and authorization.lower().startswith("bearer "):
        user = user_from_token(authorization[7:].strip())
        if user:
            return user["client_id"]
    return header_value if header_value else "anonymous"
