# create_users_with_custom_api_keys.py

import sqlite3
import bcrypt

DB_PATH = "trades.db"

users = [
    ("dakoda.patton365@gmail.com",    "GM2024Chet",  "ec8ab2deb7f53b3fe4d1e2551691d40a"),
    ("dylan@jkmventures.net",         "miller@2025$", "aa3728af483a5eefc4063107fa1a7097"),
    ("cooperpatton2004@gmail.com",    "pattonc2",    "04529cd0b8bf793dbd106ba9e84686ca")
]

# open the DB
conn = sqlite3.connect(DB_PATH)
c    = conn.cursor()

# insert each user
for email, password, api_key in users:
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    c.execute(
        "INSERT INTO users (email, password, api_key) VALUES (?, ?, ?)",
        (email, pw_hash, api_key)
    )
    print(f"✅ Inserted user: {email}")

conn.commit()
conn.close()
print("🎉 All specified users created successfully!")
