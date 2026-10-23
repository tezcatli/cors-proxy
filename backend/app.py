"""Flask app factory: the auth and games blueprints and `GET /healthz`.

API only — the SPA is served by nginx in prod and Vite in dev. Run by gunicorn
with `--workers 1`: the catalog, its worker and the rate limiter live in this
process's memory.
"""
import os
import time
import logging
from flask import Flask, request, Response, jsonify
from config import Config
from db import init_db
from auth import auth_bp
import catalog_state
from games import games_bp
from resolver import startup_warmup
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
            logger.warning("ADMIN_KEY is not set — POST /auth/invite will always return 403")

    # API only. The SPA is served by nginx in prod and by Vite in dev (which
    # proxies /auth and /games here), so Flask never serves a page.
    _app = Flask(__name__)

    _app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH
    _app.config['RATELIMIT_ENABLED'] = not testing

    # Behind nginx (one hop): trust X-Forwarded-For so request.remote_addr — and
    # thus the rate-limiter key — is the real client, not the proxy. No-op when no
    # proxy header is present (dev / direct).
    from werkzeug.middleware.proxy_fix import ProxyFix
    _app.wsgi_app = ProxyFix(_app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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
        return jsonify(status="ok", feedLoaded=bool(catalog_state.episodes)), 200

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
