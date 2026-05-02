import sqlite3
con = sqlite3.connect("database.db")
cur = con.cursor()
cur.execute("PRAGMA table_info(users)")
for row in cur.fetchall():
    print(row)
con.close()

