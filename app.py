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

    token_value = data.get("access_token") or data.get("accessToken")
    if not token_value:
        raise RuntimeError(f"No access token in response: {data}")
    _token = token_value

    if "expires_in" in data:
        _expires_at = time.time() + data["expires_in"] - 300
    elif "expirationTime" in data:
        from datetime import datetime, timezone
        exp_dt = datetime.fromisoformat(data["expirationTime"].replace("Z", "+00:00"))
        _expires_at = exp_dt.replace(tzinfo=timezone.utc).timestamp() - 300
    else:
        _expires_at = time.time() + 3600 - 300

def _get_token():
    with _lock:
        if _token is None or time.time() >= _expires_at:
            _fetch_new_token()
        return _token

# kick off initial fetch
threading.Thread(target=_fetch_new_token, daemon=True).start()
# ——————————————————————————————————————————————

DB_PATH = os.path.join(os.path.dirname(__file__), "trades.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        # API‐key guard
        key = request.args.get("key", "")
        if key != os.environ.get("WEBHOOK_API_KEY", ""):
            return jsonify(error="invalid API key"), 401

        p = request.get_json(force=True)
        app.logger.info(f"Alert payload: {p}")

        symbol = p.get("symbol")
        action = p.get("action", "").capitalize()   # e.g. "Buy" or "Sell"
        qty    = int(p.get("quantity", 0))

        # place market order
        token = _get_token()
        r = requests.post(
            "https://live.tradovateapi.com/v1/order/placeOrder",
            json={
                "accountSpec": os.environ["TRADOVATE_USER"],
                "accountId":   int(os.environ["TRADOVATE_ACCOUNT_ID"]),
                "action":      action,
                "symbol":      symbol,
                "orderQty":    qty,
                "orderType":   "Market",
                "isAutomated": True
            },
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        r.raise_for_status()
        order_result = r.json()

        # optionally log locally
        db = get_db()
        db.execute(
            "INSERT INTO trades (symbol, action, entry_price, timestamp) VALUES (?, ?, ?, ?)",
            (symbol, action, float(p.get("price", 0)), int(time.time()))
        )
        db.commit()
        db.close()

        return jsonify(status="ok", result=order_result), 200

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        app.logger.error(tb)
        return jsonify(error=str(e), traceback=tb), 500

# ... your other routes unchanged ...

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)

