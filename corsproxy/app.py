import time
import logging
import jwt
from flask import Flask, request, abort, Response, jsonify
from urllib.parse import urlparse
from config import Config
from db import init_db
from auth import auth_bp
from rawg import rawg_bp
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

_UPSTREAM_CORS = frozenset([
    "access-control-allow-origin",
    "access-control-allow-credentials",
    "access-control-allow-methods",
    "access-control-allow-headers",
    "access-control-expose-headers",
    "access-control-max-age",
])

_HOP_BY_HOP = frozenset([
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
])


def _authenticated(headers: dict) -> bool:
    if Config.DEBUG:
        return True
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    try:
        jwt.decode(auth[7:], Config.JWT_SECRET, algorithms=["HS256"])
        return True
    except jwt.PyJWTError:
        return False


def _allowed(url: str) -> bool:
    if not Config.ALLOWED_ORIGINS:
        return True
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return any(origin.startswith(allowed) for allowed in Config.ALLOWED_ORIGINS)


def _strip(headers: dict, extras: frozenset = frozenset()) -> dict:
    blocked = _HOP_BY_HOP | extras
    return {k: v for k, v in headers.items() if k.lower() not in blocked}


def create_app():
    if Config.DEBUG:
        _app = Flask(__name__, static_folder="static", static_url_path="/silence")
        logger.warning("Running in DEBUG mode. This is not recommended for production!")
    else:
        _app = Flask(__name__)

    if Config.DEBUG:
        from flask import send_from_directory, redirect

        @_app.route("/silence")
        def silence_redirect():
            qs = request.query_string.decode()
            return redirect(f"/silence/?{qs}" if qs else "/silence/")

        @_app.route("/silence/")
        def silence_index():
            return send_from_directory(_app.static_folder, "index.html")

    _app.register_blueprint(auth_bp)
    _app.register_blueprint(rawg_bp)
    init_db()

    @_app.errorhandler(400)
    @_app.errorhandler(401)
    @_app.errorhandler(403)
    @_app.errorhandler(404)
    @_app.errorhandler(409)
    @_app.errorhandler(410)
    @_app.errorhandler(500)
    @_app.errorhandler(502)
    @_app.errorhandler(503)
    @_app.errorhandler(504)
    def json_error(e):
        return jsonify(error=str(e.description)), e.code

    @_app.before_request
    def _mark_start():
        request._start = time.monotonic()

    @_app.after_request
    def _add_cors(response: Response) -> Response:
        origin = request.headers.get("Origin", "*")
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        response.headers["Access-Control-Max-Age"] = "86400"
        response.headers["Vary"] = "Origin"
        return response

    @_app.after_request
    def _log(response: Response) -> Response:
        ms = (time.monotonic() - getattr(request, "_start", time.monotonic())) * 1000
        logger.info("method=%s path=%s status=%d ms=%.1f",
                    request.method, request.path, response.status_code, ms)
        return response

    @_app.route("/")
    def hello():
        return "Guten tag das monde!!!"

    @_app.route("/proxy", methods=["GET"])
    def proxy():
        target_url = request.args.get("url", "").strip()
        if not target_url:
            abort(400, "Missing required query parameter: url")
        if not target_url.startswith(("http://", "https://")):
            abort(400, "Parameter 'url' must start with http:// or https://")
        if not _allowed(target_url):
            abort(403, "Target URL is not in the allowed-origins list")
        if not _authenticated(dict(request.headers)):
            abort(403, "Not authenticated")
        forward_headers = _strip(dict(request.headers), extras=frozenset(["host"]))
        try:
            upstream = requests.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                params={k: v for k, v in request.args.items() if k != "url"},
                data=request.get_data(),
                timeout=Config.REQUEST_TIMEOUT,
                allow_redirects=True,
                stream=True,
            )
        except requests.exceptions.Timeout:
            logger.warning("timeout proxying %s", target_url)
            abort(504, "Upstream request timed out")
        except requests.exceptions.ConnectionError as exc:
            logger.warning("connection error proxying %s: %s", target_url, exc)
            abort(502, "Failed to connect to upstream")
        except requests.exceptions.RequestException as exc:
            logger.error("unexpected error proxying %s: %s", target_url, exc)
            abort(502, "Upstream request failed")
        response_headers = _strip(dict(upstream.headers), extras=_UPSTREAM_CORS)
        return Response(
            upstream.raw.stream(8192, decode_content=False),
            status=upstream.status_code,
            headers=response_headers,
            direct_passthrough=True,
        )

    return _app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0")
