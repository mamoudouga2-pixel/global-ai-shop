import sqlite3
import pandas as pd
import datetime
import os

DB_PATH = 'global_manager_2040.db'

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (phone TEXT PRIMARY KEY,
                  business_name TEXT,
                  email TEXT,
                  joined_date TEXT,
                  expiry_date TEXT,
                  status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  owner_phone TEXT,
                  customer_phone TEXT,
                  customer_name TEXT,
                  village TEXT,
                  district TEXT,
                  quantity INTEGER,
                  total_amount INTEGER,
                  trust_score INTEGER,
                  status TEXT,
                  transcript TEXT,
                  audio_path TEXT,
                  order_date TEXT,
                  FOREIGN KEY (owner_phone) REFERENCES users (phone))''')
    conn.commit()
    return conn

conn = init_db()

def get_or_create_user(phone):
    c = conn.cursor()
    c.execute("SELECT phone, business_name, email, expiry_date, status FROM users WHERE phone=?", (phone,))
    user = c.fetchone()
    if user:
        return user
    joined = str(datetime.date.today())
    expiry = str(datetime.date.today() + datetime.timedelta(days=3))
    c.execute("INSERT INTO users (phone, business_name, email, joined_date, expiry_date, status) VALUES (?,?,?,?,?,?)",
              (phone, "My Business", "", joined, expiry, 'TRIAL'))
    conn.commit()
    return (phone, "My Business", "", expiry, 'TRIAL')

def extend_subscription(phone, days):
    c = conn.cursor()
    new_expiry = (datetime.date.today() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    c.execute("UPDATE users SET expiry_date=?, status='PREMIUM' WHERE phone=?", (new_expiry, phone))
    conn.commit()
    return new_expiry

def save_order(owner_phone, c_phone, c_name, village, district, qty, amount, score, status, transcript="N/A", audio="N/A"):
    try:
        c = conn.cursor()
        date_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('''INSERT INTO orders
                     (owner_phone, customer_phone, customer_name, village, district, quantity, total_amount, trust_score, status, transcript, audio_path, order_date)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (owner_phone, c_phone, c_name, village, district, qty, amount, score, status, transcript, audio, date_now))
        conn.commit()
        return True
    except Exception as e:
        print(f"Database Error: {e}")
        return False

def get_all_orders(owner_phone):
    try:
        query = "SELECT * FROM orders WHERE owner_phone = ? ORDER BY id DESC"
        return pd.read_sql_query(query, conn, params=(owner_phone,))
    except:
        return pd.DataFrame()

def update_order_status(order_id, new_status):
    c = conn.cursor()
    c.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    conn.commit()
