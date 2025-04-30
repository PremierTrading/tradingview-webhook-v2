# FILE: app.py
import os
import sqlite3
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

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
    backup = os.path.join(BASE_DIR, "trades.db")
    return send_file(backup, as_attachment=True)

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT api_key, password FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode(), row["password"]):
        return jsonify(api_key=row["api_key"])
    return jsonify(error="Invalid credentials"), 401

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(force=True)
    msg = body.get("message", "")
    # parse out fields
    lines = [l.strip() for l in msg.splitlines() if l.strip()]
    d = {}
    for line in lines:
        if ":" in line:
            key, val = line.split(":", 1)
            d[key.strip().lower().replace(" ", "_")] = val.strip()
    # map Date → timestamp
    timestamp = d.get("date") or d.get("Date")
    symbol = lines[0].split()[0] if lines else ""
    action = d.get("action")
    entry = float(d.get("entry_price", 0))
    exit_p = float(d.get("exit_price", 0))
    direction = d.get("direction")
    result = d.get("result")
    pnl = float(d.get("pnl", 0))
    # insert into DB
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
      INSERT INTO trades
        (symbol, action, entry_price, exit_price, direction, result, pnl, timestamp)
      VALUES (?,?,?,?,?,?,?,?)
    """, (symbol, action, entry, exit_p, direction, result, pnl, timestamp))
    conn.commit()
    conn.close()
    return jsonify(status="received")

@app.route("/trades", methods=["GET"])
def get_trades():
    key = request.args.get("key")
    # (you may want to verify the key against users table)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM trades ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    trades = [dict(row) for row in rows]
    return jsonify(trades)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

