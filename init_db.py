# FILE: init_db.py
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "trades.db")

# If you ever want to reset, uncomment the next line:
# os.remove(DB_PATH) if os.path.exists(DB_PATH) else None

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Create users table if missing
c.execute("""
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE,
  password BLOB,
  api_key TEXT UNIQUE
)
""")

# Create trades table with timestamp column
c.execute("""
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY,
  symbol TEXT,
  action TEXT,
  entry_price REAL,
  exit_price REAL,
  direction TEXT,
  result TEXT,
  pnl REAL,
  timestamp TEXT
)
""")

conn.commit()
conn.close()
print("✅ Initialized trades.db with users and trades tables")
