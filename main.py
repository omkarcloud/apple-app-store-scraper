"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. Params are validated by the same schemas the API uses, so an
app id, a bundle id or an apps.apple.com link all work.
"""
import json
import os

from apple_app_store import api, schemas

os.makedirs("output", exist_ok=True)


def run(schema_cls, fn, **params):
    """Validate params like the API does, then call the scraper function."""
    return fn(**schema_cls().load(params))


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # an app id, a bundle id or any apps.apple.com app link
    save("app_chatgpt.json", run(schemas.AppSchema, api.app_details,
                                 app="https://apps.apple.com/us/app/chatgpt/id6448311069"))

    # 20 reviews per page, newest first
    save("reviews_chatgpt_recent.json", run(schemas.AppReviewsSchema, api.app_reviews, app="6448311069", sort="recent"))

    # the US top free iPhone apps, 50 ranked rows
    save("chart_top_free.json", run(schemas.ChartsListSchema, api.charts_list, chart="top-free"))
