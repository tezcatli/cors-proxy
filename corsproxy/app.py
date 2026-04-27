import time
import logging
from flask import Flask, request, Response, jsonify
from config import Config
from db import init_db
from auth import auth_bp
from igdb import igdb_bp
from rss import rss_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)


def create_app():
    if Config.DEBUG:
        _app = Flask(__name__, static_folder="static")
        logger.warning("Running in DEBUG mode. This is not recommended for production!")
    else:
        _app = Flask(__name__)

    if Config.DEBUG:
        import pathlib
        from flask import send_from_directory, redirect

        @_app.route("/silence")
        def silence_redirect():
            qs = request.query_string.decode()
            return redirect(f"/silence/?{qs}" if qs else "/silence/")

        @_app.route("/silence/", defaults={"path": ""})
        @_app.route("/silence/<path:path>")
        def silence_spa(path):
            full = pathlib.Path(_app.static_folder) / path
            filename = path if full.is_file() else "index.html"
            resp = send_from_directory(_app.static_folder, filename)
            resp.headers["Cache-Control"] = "no-store"
            return resp

    _app.register_blueprint(auth_bp)
    _app.register_blueprint(igdb_bp)
    _app.register_blueprint(rss_bp)
    init_db()

    def json_error(e):
        return jsonify(error=str(e.description)), e.code

    for _code in (400, 401, 403, 404, 409, 410, 500, 502, 503, 504):
        _app.register_error_handler(_code, json_error)

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

    return _app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0")
