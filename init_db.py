import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "trades.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password BLOB NOT NULL,
    api_key TEXT UNIQUE NOT NULL
);
""")

c.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    action TEXT,
    entry_price REAL,
    exit_price REAL,
    direction TEXT,
    result TEXT,
    pnl REAL,
    timestamp TEXT
);
""")

conn.commit()
conn.close()

print("Initialized trades.db with users and trades tables")
