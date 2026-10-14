from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import os
import json

app = Flask(__name__)

# Enable frontend requests.
# For production, restrict this to your actual frontend domain.
CORS(app)

# Database location
DATABASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "cafelling.db"
)


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

        # Customer orders table
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

        # Products table
        db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                name TEXT PRIMARY KEY,
                price REAL NOT NULL,
                availability TEXT NOT NULL DEFAULT 'Available'
            )
        """)


# Initialize database when the application starts.
# Important when running with Gunicorn on Render.
initialize_database()


# =========================
# HOME ROUTE
# =========================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Cafelling Backend is running!"
    })


# =========================
# HEALTH CHECK
# =========================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "message": "Cafelling database is ready."
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
    total = data.get("total")

    # Validate customer name
    if not customer_name:
        return jsonify({
            "error": "Customer name is required."
        }), 400

    # Validate order items
    if not isinstance(items, list) or not items:
        return jsonify({
            "error": "Order items are required."
        }), 400

    # Validate total
    try:
        total = float(total)

        if total <= 0:
            raise ValueError

    except (TypeError, ValueError):
        return jsonify({
            "error": "Invalid order total."
        }), 400

    # Validate that items can be converted to JSON
    try:
        items_json = json.dumps(items)
    except (TypeError, ValueError):
        return jsonify({
            "error": "Invalid order items."
        }), 400

    # Save order to database
    with get_db() as db:
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
            items_json,
            total
        ))

        order_id = cursor.lastrowid

    return jsonify({
        "message": "Order created successfully.",
        "orderNumber": order_id,
        "customerName": customer_name,
        "status": "Pending"
    }), 201


# =========================
# GET ALL CUSTOMER ORDERS
# =========================

@app.route("/api/orders", methods=["GET"])
def get_orders():

    with get_db() as db:
        rows = db.execute("""
            SELECT *
            FROM orders
            ORDER BY id DESC
        """).fetchall()

    orders = []

    for row in rows:

        try:
            order_items = json.loads(row["items"])
        except (TypeError, ValueError):
            order_items = []

        orders.append({
            "id": row["id"],
            "orderNumber": row["id"],
            "customerName": row["customer_name"],
            "items": order_items,
            "total": row["total"],
            "status": row["status"],
            "date": row["created_at"]
        })

    return jsonify(orders)


# =========================
# GET ONE CUSTOMER ORDER
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

    try:
        order_items = json.loads(row["items"])
    except (TypeError, ValueError):
        order_items = []

    return jsonify({
        "id": row["id"],
        "orderNumber": row["id"],
        "customerName": row["customer_name"],
        "items": order_items,
        "total": row["total"],
        "status": row["status"],
        "date": row["created_at"]
    })


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

    allowed_statuses = [
        "Pending",
        "Preparing",
        "Delivered",
        "Cancelled"
    ]

    if status not in allowed_statuses:
        return jsonify({
            "error": "Invalid order status.",
            "allowedStatuses": allowed_statuses
        }), 400

    with get_db() as db:

        cursor = db.execute("""
            UPDATE orders
            SET status = ?
            WHERE id = ?
        """, (
            status,
            order_id
        ))

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
