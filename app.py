# FILE: app.py
import os
import sqlite3
import time
import threading
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# —— Token & Account Auto-Refresh Manager ——
_token = None
_expires_at = 0
_lock = threading.Lock()
_account_info = {}

def _fetch_new_token():
    global _token, _expires_at, _account_info
    # 1) Authenticate and get access token
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
    token_value = data.get("access_token") or data.get("accessToken")
    if not token_value:
        raise RuntimeError(f"No access token in response: {data}")
    _token = token_value
    # schedule renewal 5m before expiry
    expires_in = data.get("expires_in")
    _expires_at = time.time() + (expires_in or 3600) - 300

    # 2) Fetch session to auto-discover your accountSpec and accountId
    sess = requests.get(
        "https://live.tradovateapi.com/auth/session",
        headers={"Authorization": f"Bearer {_token}"}
    )
    sess.raise_for_status()
    sess_data = sess.json()
    default = sess_data.get("defaultAccount", sess_data)
    _account_info = {
        "accountId":   int(default.get("accountId") or default.get("acctId")),
        "accountSpec": default.get("accountSpec"),
        "subAccountId": default.get("subAccountId"),
    }


def _get_token():
    with _lock:
        if _token is None or time.time() >= _expires_at:
            _fetch_new_token()
        return _token

# Pre-fetch on startup
threading.Thread(target=_fetch_new_token, daemon=True).start()
# ————————————————————————————————————————

# —— Database Setup ——
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "trades.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# —— Webhook Endpoint ——
@app.route("/webhook", methods=["POST"])
def webhook():
    # 1) Validate your own TradingView key
    key = request.args.get("key", "")
    if key != os.environ.get("WEBHOOK_API_KEY", ""):
        return jsonify(error="invalid API key"), 401

    # 2) Parse TradingView JSON payload
    p = request.get_json(force=True)
    symbol = p.get("symbol")
    # Standardize action to "Buy"/"Sell"
    action = p.get("action", "").capitalize()
    qty    = int(p.get("quantity", 0))
    price  = float(p.get("price", 0))
    # Map MKT/LMT → full enum
    ot = p.get("orderType", "MKT").upper()
    order_type = "Market" if ot == "MKT" else "Limit"
    exchange = p.get("exchange", "GLOBEX")

    # 3) Place order on Tradovate
    token = _get_token()
    body = {
        "accountId":   _account_info["accountId"],
        "accountSpec": _account_info["accountSpec"],
        "action":      action,
        "symbol":      symbol,
        "quantity":    qty,
        "orderType":   order_type,
        "exchange":    exchange,
    }
    resp = requests.post(
        "https://live.tradovateapi.com/v1/order/placeOrder",
        json=body,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {token}"
        }
    )
    resp.raise_for_status()
    result = resp.json()

    # 4) Log locally
    db = get_db()
    db.execute(
        "INSERT INTO trades (symbol, action, entry_price, timestamp) VALUES (?, ?, ?, ?)",
        (symbol, action, price, int(time.time()))
    )
    db.commit()
    db.close()

    return jsonify(status="ok", result=result), 200

# —— Main ——
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=True)
