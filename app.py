import os
import sqlite3
import time
import threading
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ——— Token Auto-Refresh Manager ———————————————————
_token      = None
_expires_at = 0
_lock       = threading.Lock()

def _fetch_new_token():
    global _token, _expires_at
    resp = requests.post(
        "https://live.tradovateapi.com/v1/auth/accesstokenrequest",
        json={
            "name":       os.environ["TRADOVATE_USER"],
            "password":   os.environ["TRADOVATE_API_PASSWORD"],
            "appId":      "tradingview",
            "appVersion": "0.0.1",
            "deviceId":   os.environ.get("TRADOVATE_DEVICE_ID", ""),
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

    expires_in = data.get("expires_in") or data.get("expirationTime")
    if isinstance(expires_in, (int, float)):
        _expires_at = time.time() + expires_in - 300
    else:
        from datetime import datetime, timezone
        exp_dt = datetime.fromisoformat(expires_in.replace("Z", "+00:00"))
        _expires_at = exp_dt.replace(tzinfo=timezone.utc).timestamp() - 300


def _get_token():
    with _lock:
        if _token is None or time.time() >= _expires_at:
            _fetch_new_token()
        return _token

# Kick off the first fetch in background
threading.Thread(target=_fetch_new_token, daemon=True).start()
# ————————————————————————————————————————————————

DB_PATH = os.path.join(os.path.dirname(__file__), "trades.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        # 1) Verify your own webhook key
        key = request.args.get("key", "")
        if key != os.environ.get("WEBHOOK_API_KEY", ""):
            return jsonify(error="invalid API key"), 401

        # 2) Parse TradingView payload
        payload = request.get_json(force=True)
        symbol = payload["symbol"]
        action = payload["action"].lower()       # MUST be lowercase
        qty    = int(payload["quantity"])
        price  = float(payload.get("price", 0))
        ts     = int(payload.get("timestamp", time.time() * 1000))

        # 3) Build order request
        token = _get_token()
        order_req = {
            "accountId":   int(os.environ["TRADOVATE_ACCOUNT_ID"]),
            "accountSpec": os.environ["TRADOVATE_ACCOUNT_SPEC"],
            "symbol":      symbol,
            "action":      action,
            "quantity":    qty,
            "orderType":   payload.get("orderType", "MKT"),
            "exchange":    payload.get("exchange", "GLOBEX"),
            "timestamp":   ts
        }
        resp = requests.post(
            "https://live.tradovateapi.com/v1/order/placeOrder",
            json=order_req,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        if resp.status_code != 200:
            # Return full Tradovate error for debugging
            try:
                details = resp.json()
            except ValueError:
                details = resp.text
            return jsonify(
                error="Bad Request",
                details=details
            ), resp.status_code

        result = resp.json()

        # 4) Log the trade locally (optional)
        db = get_db()
        db.execute(
            "INSERT INTO trades (symbol, action, entry_price, timestamp) VALUES (?, ?, ?, ?)",
            (symbol, action, price, int(time.time()))
        )
        db.commit()
        db.close()

        return jsonify(status="ok", result=result), 200

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        app.logger.error(tb)
        return jsonify(error=str(e), traceback=tb), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
