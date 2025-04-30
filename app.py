# FILE: app.py
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

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok")

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    email, password, api_key = data.get("email"), data.get("password"), data.get("api_key")
    if not all([email, password, api_key]):
        return jsonify(error="email, password, and api_key required"), 400
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    db = get_db()
    db.execute("INSERT INTO users (email,password,api_key) VALUES (?,?,?)",
               (email, pw_hash, api_key))
    db.commit()
    db.close()
    return jsonify(status="user created", email=email), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email, password = data.get("email"), data.get("password")
    if not all([email, password]):
        return jsonify(error="email and password required"), 400
    db = get_db()
    row = db.execute("SELECT password,api_key FROM users WHERE email=?", (email,)).fetchone()
    db.close()
    if row and bcrypt.checkpw(password.encode(), row["password"]):
        return jsonify(status="success", api_key=row["api_key"])
    return jsonify(error="invalid credentials"), 401

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    msg = data.get("message","")
    app.logger.info(f"Received TV alert: {msg}")

    # Parse lines into key/value
    lines = [l.strip() for l in msg.splitlines() if l.strip()]
    if not lines:
        return jsonify(error="empty message"), 400

    symbol = lines[0].split()[0]
    fields = {}
    for line in lines[1:]:
        m = re.match(r"^([\w\s]+?):\s*(.+)$", line)
        if m:
            k = m.group(1).strip().lower().replace(" ", "_")
            fields[k] = m.group(2).strip()

    # Required
    try:
        entry     = float(fields.get("entry_price", 0))
        exit_p    = float(fields.get("exit_price", 0))
        pnl       = float(fields.get("pnl", 0))
        timestamp = fields.get("date")
        action    = fields.get("action")
        direction = fields.get("direction")
        result    = fields.get("result")
        if not timestamp:
            raise ValueError("missing date")
    except Exception as e:
        return jsonify(error=f"parse error: {e}"), 400

    db = get_db()
    db.execute("""
      INSERT INTO trades
        (symbol,action,entry_price,exit_price,direction,result,pnl,timestamp)
      VALUES (?,?,?,?,?,?,?,?)
    """, (symbol, action, entry, exit_p, direction, result, pnl, timestamp))
    db.commit()
    db.close()
    return jsonify(status="received"), 200

@app.route("/trades", methods=["GET"])
def get_trades():
    key = request.args.get("key")
    if not key:
        return jsonify(error="API key required"), 400
    db = get_db()
    user = db.execute("SELECT 1 FROM users WHERE api_key=?", (key,)).fetchone()
    if not user:
        db.close()
        return jsonify(error="invalid API key"), 401

    rows = db.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/download-backup", methods=["GET"])
def download_backup():
    return send_file(DB_PATH, as_attachment=True)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)

