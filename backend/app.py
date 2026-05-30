import os
import time
import logging
import requests
from flask import Flask, request, Response, jsonify
from config import Config
from db import init_db
from auth import auth_bp
from games import games_bp, startup_warmup
from limiter import limiter

logging.basicConfig(
    level=Config.LOGGER_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)


def create_app(testing=False):
    if not testing and not Config.DEBUG:
        if Config.JWT_SECRET == "dev-insecure-change-me":
            raise RuntimeError(
                "JWT_SECRET is set to the insecure default. "
                "Set the JWT_SECRET environment variable before starting in production."
            )
        if not Config.ADMIN_KEY:
            logger.warning("ADMIN_KEY is not set — POST /silence/auth/invite will always return 403")

    if Config.DEBUG:
        import pathlib
        from flask import send_from_directory, redirect

        _app = Flask(__name__, static_folder="static")
        logger.warning("DEBUG mode is ON — authentication is DISABLED for all /games routes")

        @_app.route("/silence")
        def silence_redirect():
            qs = request.query_string.decode()
            return redirect(f"/silence/?{qs}" if qs else "/silence/")

        @_app.route("/silence/", defaults={"path": ""})
        @_app.route("/silence/<path:path>")
        def silence_spa(path):
            if Config.DEBUG and os.environ.get("VITE_DEV_SERVER", "false").lower() == "true":
                vite_url = f"http://frontend:5173/silence/{path}" if path else "http://frontend:5173/silence/"
                # Forward the raw query string. Re-serializing via requests' `params` from
                # request.args drops the distinction between `?foo` and `?foo=`, which Vite
                # uses to recognise virtual extensions like `&lang.css`.
                raw_qs = request.query_string.decode('latin-1')
                if raw_qs:
                    vite_url = f"{vite_url}?{raw_qs}"
                try:
                    vite_resp = requests.get(vite_url, timeout=5)
                    excluded = {"content-encoding", "content-length", "transfer-encoding", "connection"}
                    headers = [(k, v) for k, v in vite_resp.headers.items() if k.lower() not in excluded]
                    response = Response(vite_resp.content, status=vite_resp.status_code, headers=headers)
                    response.headers["Cache-Control"] = "no-store"
                    return response
                except requests.RequestException:
                    pass

            full = pathlib.Path(_app.static_folder) / path
            filename = path if full.is_file() else "index.html"
            resp = send_from_directory(_app.static_folder, filename)
            resp.headers["Cache-Control"] = "no-store"
            return resp
    else:
        _app = Flask(__name__)

    _app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH
    _app.config['RATELIMIT_ENABLED'] = not testing

    limiter.init_app(_app)
    _app.register_blueprint(auth_bp)
    _app.register_blueprint(games_bp)
    init_db()
    if not testing:
        if not Config.DEBUG or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            startup_warmup()

    @_app.route("/healthz")
    def healthz():
        # Liveness probe: 200 whenever the process is serving. `feedLoaded` is
        # informational — a not-yet-loaded feed must not fail the healthcheck,
        # or Docker would restart the container while it is still warming up.
        import games
        return jsonify(status="ok", feedLoaded=bool(games._cached_episodes)), 200

    def json_error(e):
        return jsonify(error=str(e.description)), e.code

    for _code in (400, 401, 403, 404, 409, 410, 500, 502, 503, 504):
        _app.register_error_handler(_code, json_error)

    @_app.before_request
    def _mark_start():
        request._start = time.monotonic()

    @_app.after_request
    def _log(response: Response) -> Response:
        ms = (time.monotonic() - getattr(request, "_start", time.monotonic())) * 1000
        logger.info("method=%s path=%s status=%d ms=%.1f",
                    request.method, request.path, response.status_code, ms)
        return response

    return _app


app = create_app(testing=os.getenv('TESTING', 'false').lower() == 'true')

if __name__ == "__main__":
    app.run(host="0.0.0.0")
