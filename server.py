"""
Legacy entrypoint: the CTAP stack is served by the Flask app in `backend.app`.

Prefer:
  flask --app backend.app run --host 0.0.0.0 --port 8766
or:
  python -m backend.app

TLS (HTTPS/WSS): set environment variables SSL_CERTFILE and SSL_KEYFILE to PEM paths
before starting (see README).
"""

import os

from backend.app import app


def _ssl_context():
    cert = os.environ.get("SSL_CERTFILE")
    key = os.environ.get("SSL_KEYFILE")
    if cert and key and os.path.isfile(cert) and os.path.isfile(key):
        return (cert, key)
    return None


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8766,
        threaded=True,
        use_reloader=False,
        ssl_context=_ssl_context(),
    )
