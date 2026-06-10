import secrets
import datetime
import bcrypt
import jwt
from flask import Blueprint, request, jsonify, abort
from db import get_db, utcnow
from config import Config
from limiter import limiter
import logging


logger = logging.getLogger(__name__)


auth_bp = Blueprint("auth", __name__, url_prefix="/silence/auth")


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _decode_jwt(token: str, scope: str | None = None):
    """Return the JWT claims if valid (and `scope` matches when given), else None."""
    try:
        claims = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if scope is not None and claims.get("scope") != scope:
        return None
    return claims


def _user_exists(claims) -> bool:
    """True if the token's subject still maps to a live user (revocation by deletion)."""
    try:
        uid = int(claims.get("sub"))
    except (TypeError, ValueError):
        return False
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone() is not None


def _validate_password(password: str):
    if len(password) < 8:
        abort(400, "Le mot de passe doit contenir au moins 8 caractères")


def _make_jwt(user_id: int, email: str) -> str:
    now = utcnow()
    payload = {
        "sub":   str(user_id),
        "email": email,
        "iat":   now,
        "exp":   now + datetime.timedelta(seconds=Config.JWT_TTL_SECONDS),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def _make_stream_token(user_id) -> str:
    """A short-lived token, scoped to the SSE stream, so the long-lived JWT never
    travels in the EventSource URL (and so it can't be used for data endpoints)."""
    now = utcnow()
    return jwt.encode({
        "sub":   str(user_id),
        "scope": "stream",
        "iat":   now,
        "exp":   now + datetime.timedelta(seconds=Config.STREAM_TTL_SECONDS),
    }, Config.JWT_SECRET, algorithm="HS256")


def _bearer_user_claims():
    """Claims for a valid full-API Bearer token of a still-existing user, else None.
    Rejects stream-scoped tokens (those are only for the SSE endpoint)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    claims = _decode_jwt(auth[7:])
    if claims and claims.get("scope") != "stream" and _user_exists(claims):
        return claims
    return None


def require_auth():
    if Config.DEBUG:
        return
    if _bearer_user_claims():
        return
    # EventSource can't set headers → accept a stream-scoped token in the query
    # string, but ONLY on the resolution-stream endpoint.
    if request.path.endswith("/resolution-stream"):
        claims = _decode_jwt(request.args.get("token", ""), scope="stream")
        if claims and _user_exists(claims):
            return
    abort(401, "Not authenticated")


@auth_bp.route("/stream-token")
def stream_token():
    claims = _bearer_user_claims() or abort(401, "Not authenticated")
    return jsonify(token=_make_stream_token(claims["sub"]))


@auth_bp.route("/refresh", methods=["POST"])
@limiter.limit("20 per minute")
def refresh():
    claims = _bearer_user_claims() or abort(401, "Not authenticated")
    return jsonify(access_token=_make_jwt(int(claims["sub"]), claims["email"]))


def _require_fields(data: dict, *fields):
    for f in fields:
        if not data.get(f):
            abort(400, f"Champ manquant : {f}")


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("10 per minute")
def register():
    data = request.get_json(silent=True) or {}
    _require_fields(data, "email", "password", "invitation_token")
    email    = data["email"].strip().lower()
    password = data["password"]
    invite   = data["invitation_token"]
    _validate_password(password)
    pw_hash = _hash(password)
    with get_db() as conn:
        inv = conn.execute(
            "SELECT email, used_at FROM invitations WHERE token = ?", (invite,)
        ).fetchone()
        # One generic message for missing / used / mismatched invites (no enumeration).
        if not inv or inv["used_at"] or inv["email"].lower() != email:
            abort(400, "Invitation invalide")
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            abort(409, "Cette adresse e-mail est déjà utilisée")
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, pw_hash),
        )
        user_id = cur.lastrowid
        conn.execute(
            "UPDATE invitations SET used_at = CURRENT_TIMESTAMP WHERE token = ?",
            (invite,),
        )
    return jsonify(access_token=_make_jwt(user_id, email)), 201


@auth_bp.route("/invite", methods=["POST"])
@limiter.limit("10 per minute")
def invite():
    from mail import send_invite_email

    if not Config.ADMIN_KEY or not secrets.compare_digest(
            request.headers.get("X-Admin-Key", ""), Config.ADMIN_KEY):
        abort(403, "Accès refusé")
    data = request.get_json(silent=True) or {}
    _require_fields(data, "email")
    email = data["email"].strip().lower()
    token = secrets.token_urlsafe(32)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO invitations (token, email) VALUES (?, ?)", (token, email)
        )
    invite_url = f"{Config.RESET_BASE_URL}/silence/?invite={token}"
    send_invite_email(email, invite_url)
    return jsonify(invite_url=invite_url), 201


@auth_bp.route("/invite-info/<token>", methods=["GET"])
def invite_info(token):
    with get_db() as conn:
        inv = conn.execute(
            "SELECT email, used_at FROM invitations WHERE token = ?", (token,)
        ).fetchone()
    if not inv:
        abort(404, "Invitation invalide")
    if inv["used_at"]:
        abort(410, "Cette invitation a déjà été utilisée")
    return jsonify(email=inv["email"])


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True) or {}
    _require_fields(data, "email", "password")
    email = data["email"].strip().lower()
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    if not user or not _check(data["password"], user["password_hash"]):
        abort(401, "E-mail ou mot de passe incorrect")
    return jsonify(access_token=_make_jwt(user["id"], email))


@auth_bp.route("/reset-request", methods=["POST"])
@limiter.limit("3 per minute")
def reset_request():
    from mail import send_reset_email
    data = request.get_json(silent=True) or {}
    _require_fields(data, "email")
    email = data["email"].strip().lower()
    reset_url = None
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            token   = secrets.token_urlsafe(32)
            expires = (utcnow() + datetime.timedelta(seconds=Config.RESET_TTL_SECONDS)).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user["id"], expires),
            )
            reset_url = f"{Config.RESET_BASE_URL}/silence/?reset={token}"
    if reset_url:
        send_reset_email(email, reset_url)
    return "", 204


@auth_bp.route("/reset-confirm", methods=["POST"])
@limiter.limit("5 per minute")
def reset_confirm():
    data = request.get_json(silent=True) or {}
    _require_fields(data, "token", "new_password")
    _validate_password(data["new_password"])
    pw_hash = _hash(data["new_password"])
    now     = utcnow().isoformat()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT user_id, expires_at FROM reset_tokens WHERE token = ?",
            (data["token"],),
        ).fetchone()
    if not existing:
        abort(400, "Lien invalide ou déjà utilisé")
    if existing["expires_at"] < now:
        # Separate transaction so the cleanup survives the abort below.
        with get_db() as conn:
            conn.execute("DELETE FROM reset_tokens WHERE token = ?", (data["token"],))
        abort(410, "Lien expiré")
    with get_db() as conn:
        row = conn.execute(
            "DELETE FROM reset_tokens WHERE token = ? RETURNING user_id",
            (data["token"],),
        ).fetchone()
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (pw_hash, row["user_id"]),
        )
    return "", 204
