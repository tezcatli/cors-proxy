import secrets
import datetime
import bcrypt
import jwt
from flask import Blueprint, request, jsonify, abort
from db import get_db, utcnow
from config import Config
import logging


logger = logging.getLogger(__name__)


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _decode_jwt(token: str) -> bool:
    try:
        jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
        return True
    except jwt.PyJWTError:
        return False


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


def require_auth():
    if Config.DEBUG:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not _decode_jwt(auth[7:]):
        abort(401, "Not authenticated")


def _require_fields(data: dict, *fields):
    for f in fields:
        if not data.get(f):
            abort(400, f"Champ manquant : {f}")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    _require_fields(data, "email", "password", "invitation_token")
    email    = data["email"].strip().lower()
    password = data["password"]
    invite   = data["invitation_token"]
    _validate_password(password)
    with get_db() as conn:
        inv = conn.execute(
            "SELECT email, used_at FROM invitations WHERE token = ?", (invite,)
        ).fetchone()
        if not inv:
            abort(400, "Invitation invalide")
        if inv["used_at"]:
            abort(400, "Cette invitation a déjà été utilisée")
        if inv["email"].lower() != email:
            abort(400, "L'adresse e-mail ne correspond pas à l'invitation")
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            abort(409, "Cette adresse e-mail est déjà utilisée")
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, _hash(password)),
        )
        user_id = cur.lastrowid
        conn.execute(
            "UPDATE invitations SET used_at = CURRENT_TIMESTAMP WHERE token = ?",
            (invite,),
        )
    return jsonify(access_token=_make_jwt(user_id, email)), 201


@auth_bp.route("/invite", methods=["POST"])
def invite():
    from mail import send_invite_email
    
    if not Config.ADMIN_KEY or request.headers.get("X-Admin-Key") != Config.ADMIN_KEY:
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
def reset_request():
    from mail import send_reset_email
    data = request.get_json(silent=True) or {}
    _require_fields(data, "email")
    email = data["email"].strip().lower()
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            token   = secrets.token_urlsafe(32)
            expires = (utcnow() + datetime.timedelta(seconds=Config.RESET_TTL_SECONDS)).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user["id"], expires),
            )
            send_reset_email(email, f"{Config.RESET_BASE_URL}/silence/?reset={token}")
    return "", 204


@auth_bp.route("/reset-confirm", methods=["POST"])
def reset_confirm():
    data = request.get_json(silent=True) or {}
    _require_fields(data, "token", "new_password")
    _validate_password(data["new_password"])
    now = utcnow().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT user_id, expires_at FROM reset_tokens WHERE token = ?",
            (data["token"],),
        ).fetchone()
        if not row:
            abort(400, "Lien invalide ou déjà utilisé")
        if row["expires_at"] < now:
            conn.execute("DELETE FROM reset_tokens WHERE token = ?", (data["token"],))
            abort(410, "Ce lien a expiré")
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash(data["new_password"]), row["user_id"]),
        )
        conn.execute("DELETE FROM reset_tokens WHERE token = ?", (data["token"],))
    return "", 204
