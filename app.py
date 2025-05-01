import os
import time
import threading
import sqlite3
import requests
from flask import Flask, request, jsonify, abort

app = Flask(__name__)

# ────────────── CONFIG ─────────────────────────────────────────────────────────
# Tradovate credentials & endpoints (set these in your Render environment)
TRADOVATE_API_BASE    = os.getenv("TRADOVATE_API_BASE", "https://live.tradovateapi.com")
TRADOVATE_USERNAME    = os.getenv("TRADOVATE_USERNAME")
TRADOVATE_PASSWORD    = os.getenv("TRADOVATE_PASSWORD")
TRADOVATE_SUB_ACCOUNT = os.getenv("TRADOVATE_SUB_ACCOUNT_ID")   # your sub-account spec ID

if not all([TRADOVATE_USERNAME, TRADOVATE_PASSWORD, TRADOVATE_SUB_ACCOUNT]):
    raise RuntimeError("Must set TRADOVATE_USERNAME, TRADOVATE_PASSWORD & TRADOVATE_SUB_ACCOUNT_ID")

# Path to your SQLite file created by init_db.py
DB_PATH = os.getenv("DB_PATH", "trades.db")

# In-memory cache for Tradovate token
_token      = None
_token_exp  = 0
_token_lock = threading.Lock()


# ────────────── HELPERS ────────────────────────────────────────────────────────
def get_tradovate_token():
    global _token, _token_exp
    with _token_lock:
        if _token and _token_exp > time.time():
            return _token

        resp = requests.post(
            f"{TRADOVATE_API_BASE}/auth/authenticate",
            json={"name": TRADOVATE_USERNAME, "password": TRADOVATE_PASSWORD}
        )
        resp.raise_for_status()
        data = resp.json()

        _token     = data["accessToken"]
        # expiresIn is seconds until expiry; subtract 30s for safety
        _token_exp = time.time() + data.get("expiresIn", 1800) - 30
        return _token

def is_valid_api_key(key: str) -> bool:
    """Check `users` table for this key."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT 1 FROM users WHERE apiKey = ?", (key,))
    valid = cur.fetchone() is not None
    con.close()
    return valid


# ────────────── WEBHOOK ENDPOINT ───────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    # 1) Validate your TradingView key
    key = request.args.get("key", "")
    if not is_valid_api_key(key):
        return jsonify({"error": "Invalid API key"}), 401

    # 2) Parse & validate JSON payload
    try:
        p = request.get_json(force=True)
    except:
        return jsonify({"error": "Invalid JSON"}), 400

    required = ["symbol", "price", "action", "quantity", "orderType", "exchange", "timestamp"]
    missing  = [f for f in required if f not in p]
    if missing:
        return jsonify({"error": "Missing field(s)", "fields": missing}), 400

    # 3) Normalize & map enums
    action = p["action"].strip().lower()
    if action not in ("buy", "sell"):
        return jsonify({"error": "Invalid action, must be buy or sell"}), 400
    action = "Buy" if action == "buy" else "Sell"

    otype = p["orderType"].strip().lower()
    if otype not in ("market", "limit"):
        return jsonify({"error": "Invalid orderType, use market or limit"}), 400
    otype = "Market" if otype == "market" else "Limit"

    # 4) Build Tradovate order payload
    order = {
        "accountSpec": [
            {
                "accountSpecId": TRADOVATE_SUB_ACCOUNT,
                "quantity": p["quantity"]
            }
        ],
        "action": action,
        "orderType": otype,
        "timestamp": p["timestamp"],
        "symbol": p["symbol"],
        "exchange": p["exchange"],
        "price": p["price"]
    }

    # 5) Send to Tradovate
    token = get_tradovate_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{TRADOVATE_API_BASE}/v1/order/placeOrder",
        json=order,
        headers=headers
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        # bubble up Tradovate’s error text if any
        return jsonify({
            "error": "Tradovate order failed",
            "details": resp.json()
        }), resp.status_code

    return jsonify(resp.json()), 200


# ────────────── STARTUP ────────────────────────────────────────────────────────
if __name__ == "__main__":
    # render listens on $PORT by default; fallback to 5000 locally
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
