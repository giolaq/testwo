"""TableStory: the Flask application factory.

Wiring only. The recipe collection is loaded once, one in-memory My Cookbook
store is created per application, and the page and API route groups register
themselves. No domain logic and no legacy route lives here.
"""

from __future__ import annotations

from flask import Flask

from api_routes import register_api
from cookbook import CookbookStore
from page_routes import register_pages
from recipe_data import load_recipes


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.update(TESTING=testing)

    collection = load_recipes()
    store = CookbookStore(collection)

    register_pages(app, collection, store)
    register_api(app, collection, store)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
