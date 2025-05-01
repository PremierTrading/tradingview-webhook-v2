import os
import time
import threading
import sqlite3
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ——— Token Auto-Refresh Manager —————————————————————————————————
_token = None
_expires_at = 0
_lock = threading.Lock()

def _fetch_new_token():
    global _token, _expires_at
    resp = requests.post(
        "https://live.tradovateapi.com/auth/accessTokenRequest",
        json={
            "name": os.environ["TRADOVATE_USER"],
            "password": os.environ["TRADOVATE_API_PASSWORD"],
            "appId": "1",
            "appVersion": "1.0",
            "cid": os.environ["TRADOVATE_CID"],
            "sec": os.environ["TRADOVATE_SECRET"],
        },
    )
    resp.raise_for_status()
    data = resp.json()
    token_value = data.get("access_token") or data.get("accessToken")
    if not token_value:
        raise RuntimeError(f"No access token in response: {data}")
    _token = token_value
    expires = data.get("expires_in", 3600)
    _expires_at = time.time() + expires - 300

def _get_token():
    with _lock:
        if _token is None or time.time() >= _expires_at:
            _fetch_new_token()
        return _token

# Pre-fetch on startup
threading.Thread(target=_fetch_new_token, daemon=True).start()
# ————————————————————————————————————————————————————————————————

DB_PATH = os.path.join(os.path.dirname(__file__), "trades.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/webhook", methods=["POST"])
def webhook():
    # 1) Verify API key
    key = request.args.get("key", "")
    if key != os.environ.get("WEBHOOK_API_KEY", ""):
        return jsonify(error="invalid API key"), 401

    # 2) Parse JSON
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify(error="invalid JSON payload"), 400

    symbol = payload.get("symbol")
    if not symbol:
        return jsonify(error="missing symbol"), 400

    # 3) Map action enum
    raw_action = payload.get("action", "").strip().upper()
    action_map = {"BUY": "Buy", "SELL": "Sell"}
    action = action_map.get(raw_action)
    if not action:
        return jsonify(error="invalid action, must be BUY or SELL"), 400

    # 4) Map orderType enum
    raw_ot = payload.get("orderType", "").strip().upper()
    ot_map = {"MKT": "Market", "LMT": "Limit", "MARKET": "Market", "LIMIT": "Limit"}
    order_type = ot_map.get(raw_ot)
    if not order_type:
        return jsonify(error="invalid orderType, must be MKT/LMT or MARKET/LIMIT"), 400

    # 5) Quantity
    try:
        qty = int(payload.get("quantity", 0))
    except Exception:
        return jsonify(error="invalid quantity"), 400
    if qty <= 0:
        return jsonify(error="quantity must be > 0"), 400

    exchange = payload.get("exchange", "GLOBEX")

    # 6) Build Tradovate request
    token = _get_token()
    body = {
        "accountSpec": os.environ["TRADOVATE_USER"],
        "accountId": int(os.environ["TRADOVATE_ACCOUNT_ID"]),
        "action": action,
        "symbol": symbol,
        "orderQty": qty,
        "orderType": order_type,
        "exchange": exchange,
        "isAutomated": True,
    }
    # Include price for limit orders
    if order_type == "Limit":
        try:
            body["limitPrice"] = float(payload.get("price", 0))
        except Exception:
            return jsonify(error="missing or invalid price for limit order"), 400

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"  
    }

    # 7) Send to Tradovate
    try:
        r = requests.post(
            "https://live.tradovateapi.com/v1/order/placeOrder",
            json=body,
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        tradovate_resp = r.json()
    except requests.exceptions.RequestException as e:
        return jsonify(error="order failed", details=str(e)), 400

    # 8) Log locally
    db = get_db()
    db.execute(
        "INSERT INTO trades (symbol, action, entry_price, timestamp) VALUES (?,?,?,?)",
        (symbol, action, float(payload.get("price", 0)), int(time.time()))
    )
    db.commit()
    db.close()

    return jsonify(status="ok", tradovate=tradovate_resp), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
