# FILE: app.py
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import sqlite3
import bcrypt
import os
import re

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "trades.db")

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok")

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    email = data.get("email")
    password = data.get("password")
    api_key = data.get("api_key")
    if not all([email, password, api_key]):
        return jsonify(error="email, password, and api_key required"), 400
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    conn = get_db_conn()
    conn.execute(
        "INSERT INTO users (email, password, api_key) VALUES (?, ?, ?)",
        (email, pw_hash, api_key)
    )
    conn.commit()
    conn.close()
    return jsonify(status="user created", email=email), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = data.get("email")
    password = data.get("password")
    if not all([email, password]):
        return jsonify(error="email and password required"), 400
    conn = get_db_conn()
    row = conn.execute(
        "SELECT password, api_key FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode("utf-8"), row["password"]):
        return jsonify(status="success", api_key=row["api_key"])
    return jsonify(error="invalid credentials"), 401

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    msg = data.get("message","")
    app.logger.info(f"📢 TV alert received: {msg}")

    # parse the TradingView message block
    # expected format:
    # SYMBOL
    # Action: buy
    # Entry Price: 100.5
    # Exit Price: 101.2
    # Direction: long
    # Result: open
    # PnL: 0
    # Date: 2025-04-30T12:00:00Z
    lines = msg.splitlines()
    symbol = lines[0].strip() if lines else None
    fields = {}
    for line in lines[1:]:
        m = re.match(r"^\s*(\w[\w\s]+?):\s*(.+)$", line)
        if m:
            key = m.group(1).lower().replace(" ", "_")
            fields[key] = m.group(2).strip()

    # coerce types
    entry = float(fields.get("entry_price", 0))
    exit_p = float(fields.get("exit_price", 0))
    pnl = float(fields.get("pnl", 0))
    date = fields.get("date")
    action = fields.get("action")
    direction = fields.get("direction")
    result = fields.get("result")

    # insert into DB
    conn = get_db_conn()
    conn.execute("""
      INSERT INTO trades
        (symbol, action, entry_price, exit_price, direction, result, pnl, date)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (symbol, action, entry, exit_p, direction, result, pnl, date))
    conn.commit()
    conn.close()

    return jsonify(status="received"), 200

@app.route("/trades", methods=["GET"])
def get_trades():
    api_key = request.args.get("key")
    if not api_key:
        return jsonify(error="API key required"), 400
    # verify api_key
    conn = get_db_conn()
    user = conn.execute("SELECT id FROM users WHERE api_key = ?", (api_key,)).fetchone()
    if not user:
        conn.close()
        return jsonify(error="invalid API key"), 401

    rows = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    conn.close()
    # convert rows to list of dict
    trades = [dict(r) for r in rows]
    return jsonify(trades)

@app.route("/download-backup", methods=["GET"])
def download_backup():
    return send_file(DB_PATH, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
