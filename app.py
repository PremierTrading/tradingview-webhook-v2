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

    # support both snake_case and camelCase token fields
    token_value = data.get("access_token") or data.get("accessToken")
    if not token_value:
        raise RuntimeError(f"No access token in response: {data}")
    _token = token_value

    # compute expiry: use expires_in or parse expirationTime
    if "expires_in" in data:
        _expires_at = time.time() + data["expires_in"] - 300
    elif "expirationTime" in data:
        from datetime import datetime, timezone
        exp_dt = datetime.fromisoformat(data["expirationTime"].replace("Z", "+00:00"))
        _expires_at = exp_dt.replace(tzinfo=timezone.utc).timestamp() - 300
    else:
        # fallback to one hour
        _expires_at = time.time() + 3600 - 300

def _get_token():
    with _lock:
        if _token is None or time.time() >= _expires_at:
            _fetch_new_token()
        return _token

# Start initial fetch in the background
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
    try:
        # Simple API-key guard if you append ?key=… in the URL
        key = request.args.get("key")
        if key and key != os.environ.get("WEBHOOK_API_KEY"):
            return jsonify(error="invalid API key"), 401

        payload = request.get_json(force=True)
        app.logger.info(f"Received alert: {payload}")

        # Extract fields
        symbol    = payload.get("symbol")
        action    = payload.get("action", "").upper()
        qty       = int(payload.get("quantity", 0))
        orderType = payload.get("orderType", "MKT")
        exchange  = payload.get("exchange", "GLOBEX")

        # Place the order
        token = _get_token()
        tradovate_resp = requests.post(
            "https://live.tradovateapi.com/v1/order/placeOrder",
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

        # Log into SQLite
        db = get_db()
        db.execute(
            """INSERT INTO trades (symbol, action, entry_price, timestamp)
               VALUES (?, ?, ?, ?)""",
            (symbol, action, float(payload.get("price", 0)), int(time.time()))
        )
        db.commit()
        db.close()

        return jsonify(status="ok", tradovate=order_result), 200

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        app.logger.error(tb)
        return jsonify(error=str(e), traceback=tb), 500

# ... keep your other routes (health, register, login, trades, download-backup) unchanged ...

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
