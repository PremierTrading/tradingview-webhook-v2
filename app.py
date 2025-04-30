import os
import re
import sqlite3
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import bcrypt

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "trades.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok")

@app.route("/download-backup", methods=["GET"])
def download_backup():
    return send_file(DB_PATH, as_attachment=True)

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = data.get("email")
    password = data.get("password")
    conn = get_db_connection()
    row = conn.execute(
        "SELECT password, api_key FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode("utf-8"), row["password"]):
        return jsonify(api_key=row["api_key"])
    return jsonify(error="Invalid credentials"), 401

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(force=True)
    msg = body.get("message", "")
    # split and strip
    lines = [l.strip() for l in msg.splitlines() if l.strip()]
    # first line is symbol
    symbol = lines[0].split()[0] if lines else None

    # parse key: val lines into dict
    d = {}
    for line in lines[1:]:
        if ":" in line:
            key, val = line.split(":", 1)
            d[key.strip().lower().replace(" ", "_")] = val.strip()

    timestamp = d.get("date")
    action    = d.get("action")
    entry     = float(d.get("entry_price", 0))
    exit_p    = float(d.get("exit_price", 0))
    direction = d.get("direction")
    result    = d.get("result")
    pnl       = float(d.get("pnl", 0))

    conn = get_db_connection()
    conn.execute("""
      INSERT INTO trades 
        (symbol, action, entry_price, exit_price, direction, result, pnl, timestamp)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (symbol, action, entry, exit_p, direction, result, pnl, timestamp))
    conn.commit()
    conn.close()

    return jsonify(status="received")

@app.route("/trades", methods=["GET"])
def get_trades():
    key = request.args.get("key")
    if not key:
        return jsonify(error="API key required"), 400
    # (optionally verify key here)
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
