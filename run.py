"""Start the Apple App Store Scraper API.

    python run.py            # http://localhost:8000
    PORT=9000 python run.py  # another port

Then:  curl "http://localhost:8000/apps/details?app=6448311069"
"""
import bottle
from cheroot import wsgi

import config
import routes  # noqa: F401  (mounts the routes on bottle's default app)


def main():
    app = bottle.default_app()
    print(f"Apple App Store Scraper listening on http://localhost:{config.PORT}/")
    print(f"Try:  curl \"http://localhost:{config.PORT}/apps/details?app=6448311069\"")
    server = wsgi.Server(("0.0.0.0", config.PORT), app, server_name="apple-app-store-scraper", numthreads=16)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
