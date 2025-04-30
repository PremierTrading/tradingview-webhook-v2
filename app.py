from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import sqlite3
import bcrypt
import os

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "trades.db")

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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password, api_key FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode("utf-8"), row[0]):
        return jsonify(status="success", api_key=row[1])
    return jsonify(error="invalid credentials"), 401

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    app.logger.info(f"📢 TV alert received: {data}")
    # TODO: persist trade data into DB
    return jsonify(status="received"), 200

@app.route("/download-backup", methods=["GET"])
def download_backup():
    return send_file(DB_PATH, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)