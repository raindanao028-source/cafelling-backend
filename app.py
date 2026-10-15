from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import os
import json
from urllib.parse import unquote

app = Flask(__name__)

# =========================
# CONFIGURATION
# =========================

CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE = os.path.join(BASE_DIR, "cafelling.db")


# =========================
# PRODUCTS AND PRICES
# =========================

PRODUCTS = {
    "Americano": 80,
    "Spanish Latte": 90,
    "Cappuccino": 90,
    "White Chocolate Mocha": 120,
    "Ice coffee": 85,
    "Iced Matcha Latte": 95,
    "Caramel Macchiato": 110,
    "Vanilla Latte": 100,
    "Chocolate Croissant": 75,
    "Cheese Bread": 60,
    "Cinnamon Roll": 70,
    "Blueberry Muffin": 65
}

ALLOWED_AVAILABILITY = [
    "Available",
    "Unavailable",
    "Out of Stock"
]

ALLOWED_ORDER_STATUSES = [
    "Pending",
    "Preparing",
    "Delivered",
    "Cancelled"
]


# =========================
# DATABASE CONNECTION
# =========================

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# =========================
# INITIALIZE DATABASE
# =========================

def initialize_database():
    with get_db() as db:

        # Customer orders
        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                items TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Product availability
        db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                name TEXT PRIMARY KEY,
                price REAL NOT NULL,
                availability TEXT NOT NULL DEFAULT 'Available'
            )
        """)

        # Insert default products without overwriting
        # existing availability settings.
        for name, price in PRODUCTS.items():
            db.execute("""
                INSERT OR IGNORE INTO products
                    (name, price, availability)
                VALUES (?, ?, 'Available')
            """, (name, price))


initialize_database()


# =========================
# HELPERS
# =========================

def product_to_dict(row):
    return {
        "name": row["name"],
        "price": row["price"],
        "availability": row["availability"]
    }


def order_to_dict(row):
    try:
        items = json.loads(row["items"])
    except (TypeError, ValueError):
        items = []

    return {
        "id": row["id"],
        "orderNumber": row["id"],
        "customerName": row["customer_name"],
        "items": items,
        "total": row["total"],
        "status": row["status"],
        "date": row["created_at"]
    }


# =========================
# HOME
# =========================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Cafélling Backend is running!"
    })


# =========================
# HEALTH CHECK
# =========================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "message": "Cafélling database is ready."
    })


# =========================
# GET ALL PRODUCTS
# =========================

@app.route("/api/products", methods=["GET"])
def get_products():
    with get_db() as db:
        rows = db.execute("""
            SELECT name, price, availability
            FROM products
            ORDER BY name
        """).fetchall()

    return jsonify([
        product_to_dict(row)
        for row in rows
    ])


# =========================
# GET ONE PRODUCT
# =========================

@app.route("/api/products/<path:product_name>", methods=["GET"])
def get_product(product_name):
    product_name = unquote(product_name)

    with get_db() as db:
        row = db.execute("""
            SELECT name, price, availability
            FROM products
            WHERE name = ?
        """, (product_name,)).fetchone()

    if row is None:
        return jsonify({
            "error": "Product not found."
        }), 404

    return jsonify(product_to_dict(row))


# =========================
# UPDATE PRODUCT AVAILABILITY
# =========================

@app.route(
    "/api/products/<path:product_name>/availability",
    methods=["PATCH"]
)
def update_product_availability(product_name):
    product_name = unquote(product_name)

    data = request.get_json(silent=True) or {}
    availability = data.get("availability")

    if availability not in ALLOWED_AVAILABILITY:
        return jsonify({
            "error": "Invalid availability status.",
            "allowedStatuses": ALLOWED_AVAILABILITY
        }), 400

    with get_db() as db:
        cursor = db.execute("""
            UPDATE products
            SET availability = ?
            WHERE name = ?
        """, (availability, product_name))

        if cursor.rowcount == 0:
            return jsonify({
                "error": "Product not found."
            }), 404

    return jsonify({
        "message": "Product availability updated successfully.",
        "name": product_name,
        "availability": availability
    })


# =========================
# CREATE CUSTOMER ORDER
# =========================

@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}

    customer_name = str(
        data.get("customerName", "")
    ).strip()

    items = data.get("items")

    # Validate customer name
    if not customer_name:
        return jsonify({
            "error": "Customer name is required."
        }), 400

    if len(customer_name) > 100:
        return jsonify({
            "error": "Customer name is too long."
        }), 400

    # Validate items
    if not isinstance(items, list) or not items:
        return jsonify({
            "error": "Order items are required."
        }), 400

    validated_items = []
    calculated_total = 0

    with get_db() as db:

        for item in items:

            if not isinstance(item, dict):
                return jsonify({
                    "error": "Invalid order item."
                }), 400

            item_name = str(
                item.get("name", "")
            ).strip()

            try:
                quantity = int(item.get("quantity"))
            except (TypeError, ValueError):
                return jsonify({
                    "error": "Invalid product quantity."
                }), 400

            if quantity < 1 or quantity > 100:
                return jsonify({
                    "error": "Product quantity must be between 1 and 100."
                }), 400

            base_name = item_name

            if " - " in item_name:
                possible_base = item_name.split(" - ", 1)[0]

                if possible_base in PRODUCTS:
                    base_name = possible_base

            if base_name not in PRODUCTS:
                return jsonify({
                    "error": "Unknown product: " + item_name
                }), 400

            official_price = PRODUCTS[base_name]

            product = db.execute("""
                SELECT availability
                FROM products
                WHERE name = ?
            """, (base_name,)).fetchone()

            if product is None:
                return jsonify({
                    "error": "Product not found: " + base_name
                }), 404

            if product["availability"] != "Available":
                return jsonify({
                    "error": (
                        base_name
                        + " is currently "
                        + product["availability"].lower()
                        + ". Please remove it from your order."
                    )
                }), 409

            validated_items.append({
                "name": item_name,
                "price": official_price,
                "quantity": quantity
            })

            calculated_total += official_price * quantity

        cursor = db.execute("""
            INSERT INTO orders (
                customer_name,
                items,
                total,
                status
            )
            VALUES (?, ?, ?, 'Pending')
        """, (
            customer_name,
            json.dumps(validated_items),
            calculated_total
        ))

        order_id = cursor.lastrowid

    return jsonify({
        "message": "Order created successfully.",
        "id": order_id,
        "orderNumber": order_id,
        "customerName": customer_name,
        "items": validated_items,
        "total": calculated_total,
        "status": "Pending"
    }), 201


# =========================
# GET ALL ORDERS
# =========================

@app.route("/api/orders", methods=["GET"])
def get_orders():
    with get_db() as db:
        rows = db.execute("""
            SELECT *
            FROM orders
            ORDER BY id DESC
        """).fetchall()

    return jsonify([
        order_to_dict(row)
        for row in rows
    ])


# =========================
# GET ONE ORDER
# =========================

@app.route("/api/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    with get_db() as db:
        row = db.execute("""
            SELECT *
            FROM orders
            WHERE id = ?
        """, (order_id,)).fetchone()

    if row is None:
        return jsonify({
            "error": "Order not found."
        }), 404

    return jsonify(order_to_dict(row))


# =========================
# UPDATE ORDER STATUS
# =========================

@app.route(
    "/api/orders/<int:order_id>/status",
    methods=["PATCH"]
)
def update_order_status(order_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")

    if status not in ALLOWED_ORDER_STATUSES:
        return jsonify({
            "error": "Invalid order status.",
            "allowedStatuses": ALLOWED_ORDER_STATUSES
        }), 400

    with get_db() as db:
        cursor = db.execute("""
            UPDATE orders
            SET status = ?
            WHERE id = ?
        """, (status, order_id))

        if cursor.rowcount == 0:
            return jsonify({
                "error": "Order not found."
            }), 404

    return jsonify({
        "message": "Order status updated successfully.",
        "orderNumber": order_id,
        "status": status
    })


# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
