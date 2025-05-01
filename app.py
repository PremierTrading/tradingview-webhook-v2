# FILE: app.py
import os
import time
import threading
import sqlite3
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ——— Token Auto-Refresh Manager —————————————————————————
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
    # support snake_case or camelCase
    token_value = data.get("access_token") or data.get("accessToken")
    if not token_value:
        raise RuntimeError(f"No access token in response: {data}")
    _token = token_value
    # schedule renewal 5m before expiry
    expires = data.get("expires_in")
    if expires:
        _expires_at = time.time() + expires - 300
    else:
        _expires_at = time.time() + 3600 - 300

def _get_token():
    with _lock:
        if _token is None or time.time() >= _expires_at:
            _fetch_new_token()
        return _token

# fetch first token in background
threading.Thread(target=_fetch_new_token, daemon=True).start()
# ——————————————————————————————————————————————————————

DB_PATH = os.path.join(os.path.dirname(__file__), "trades.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/webhook", methods=["POST"])
def webhook():
    # 1) verify our own key
    key = request.args.get("key", "")
    if key != os.environ.get("WEBHOOK_API_KEY", ""):
        return jsonify(error="invalid API key"), 401

    # 2) parse incoming JSON
    p = request.get_json(force=True)
    symbol = p.get("symbol")
    # capitalize so Tradovate accepts "Buy"/"Sell" :contentReference[oaicite:2]{index=2}&#8203;:contentReference[oaicite:3]{index=3}
    action_raw = p.get("action", "")
    action = action_raw.capitalize()
    qty = int(p.get("quantity", 0))
    # map MKT/LMT → full enum
    ot = p.get("orderType", "MKT").upper()
    order_type = "Market" if ot == "MKT" else "Limit"
    exchange = p.get("exchange", "GLOBEX")

    # 3) send to Tradovate
    token = _get_token()
    body = {
        "accountSpec": os.environ["TRADOVATE_USER"],
        "accountId":   int(os.environ["TRADOVATE_ACCOUNT_ID"]),
        "action":      action,
        "symbol":      symbol,
        "orderQty":    qty,
        "orderType":   order_type,
        "exchange":    exchange,
        "isAutomated": True
    }
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {token}"
    }
    r = requests.post("https://live.tradovateapi.com/v1/order/placeOrder",
                      json=body, headers=headers)
    r.raise_for_status()
    result = r.json()

    # 4) (optional) log it locally
    db = get_db()
    db.execute(
        "INSERT INTO trades (symbol, action, entry_price, timestamp) VALUES (?,?,?,?)",
        (symbol, action, float(p.get("price", 0)), int(time.time()))
    )
    db.commit()
    db.close()

    return jsonify(status="ok", tradovate=result), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
