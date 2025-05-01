# FILE: app.py
import os
import re
import sqlite3
import time
import threading
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import bcrypt

app = Flask(__name__)
CORS(app)

# ——— Token Auto-Refresh Manager ——————————————————
_token      = None
_expires_at = 0
_lock       = threading.Lock()

def _fetch_new_token():
    global _token, _expires_at
    resp = requests.post(
        "https://live.tradovateapi.com/auth/accessTokenRequest",
        json={
            "name":       os.environ["TRADOVATE_USER"],
            "password":   os.environ["TRADOVATE_API_PASSWORD"],
            "appId":      "1",
            "appVersion": "1.0",
            "cid":        os.environ["TRADOVATE_CID"],
            "sec":        os.environ["TRADOVATE_SECRET"],
        },
    )
    resp.raise_for_status()
    data = resp.json()
    _token      = data["access_token"]
    # schedule renewal 5m before expiry
    _expires_at = time.time() + data["expires_in"] - 300

def _get_token():
    with _lock:
        if _token is None or time.time() >= _expires_at:
            _fetch_new_token()
        return _token

# kick off initial fetch in background
threading.Thread(target=_fetch_new_token, daemon=True).start()
# ——————————————————————————————————————————————

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "trades.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(force=True)
    app.logger.info(f"Received alert: {payload}")

    # pull fields from TradingView alert JSON
    symbol    = payload.get("symbol")
    action    = payload.get("action", "").upper()
    qty       = int(payload.get("quantity", 0))
    orderType = payload.get("orderType", "MKT")
    exchange  = payload.get("exchange", "GLOBEX")

    # place order on Tradovate
    token = _get_token()
    tradovate_resp = requests.post(
        "https://live.tradovateapi.com/v1/order/place",
        json={
            "acctId":    int(os.environ["TRADOVATE_ACCOUNT_ID"]),
            "conId":     symbol,
            "orderQty":  qty,
            "action":    action,
            "orderType": orderType,
            "secType":   "FUT",
            "exchange":  exchange
        },
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {token}"
        }
    )
    tradovate_resp.raise_for_status()
    order_result = tradovate_resp.json()

    # also log into your local DB if desired
    db = get_db()
    db.execute(
        """INSERT INTO trades
           (symbol, action, entry_price, timestamp)
           VALUES (?, ?, ?, ?)""",
        (symbol, action, float(payload.get("price", 0)), int(time.time()))
    )
    db.commit()
    db.close()

    return jsonify(status="ok", tradovate=order_result), 200

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

# ... (other routes like signup/login unchanged) ...

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)

