import sqlite3

con = sqlite3.connect("database.db",timeout=60)
cur = con.cursor()

# DROP OLD TABLES (FIX)
cur.execute("DROP TABLE IF EXISTS users")
cur.execute("DROP TABLE IF EXISTS teachers")
cur.execute("DROP TABLE IF EXISTS students")
cur.execute("DROP TABLE IF EXISTS attendance")
cur.execute("DROP TABLE IF EXISTS marks")

# RECREATE TABLES
cur.execute("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    subject TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL
)
""")

cur.execute("""
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    roll_no TEXT UNIQUE NOT NULL,
    semester TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no TEXT NOT NULL,
    subject TEXT NOT NULL,
    lecture_no INTEGER,
    status  TEXT NOT NULL,
    date TEXT NOT NULL
)
""")



cur.execute("""
CREATE TABLE marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no TEXT NOT NULL,
    subject TEXT NOT NULL,
    type TEXT NOT NULL,        -- NEW: Theory or Practical
    marks INTEGER NOT NULL,    -- Marks obtained
    max_marks INTEGER NOT NULL -- Maximum marks for that exam
)
""")
cur.execute("""
INSERT INTO users (username,password,role)
VALUES ('admin','admin123','admin')
""")

con.commit()
con.close()

print("✅ Database reset & recreated successfully")
