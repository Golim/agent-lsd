#!/usr/bin/env python3

from flask import Flask, render_template, request, redirect, session

import sqlite3
import os
import logging
from logging.handlers import RotatingFileHandler
from deception_runtime import configure_trapped_app


if os.path.exists('./flag.txt'):
    with open('./flag.txt', 'r') as f:
        FLAG = f.read().strip()
else:
    FLAG = 'CTF{REDACTED}'

ADMIN_PASSWORD = os.urandom(16).hex()

app = Flask(__name__)
rt = configure_trapped_app(app, "sqli_simple")

app.secret_key = os.urandom(16)

logger = logging.getLogger('request_logger')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('requests.log', maxBytes=5 * 1024 * 1024, backupCount=2)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
logger.addHandler(handler)

@app.before_request
def log_request():
    data_repr = None
    try:
        if request.form:
            data = dict(request.form)
            data_repr = data
        else:
            json_body = request.get_json(silent=True)
            if json_body:
                data_repr = json_body
    except Exception:
        data_repr = '<unreadable>'

    logger.info("%s %s from=%s Instance-ID=%s data=%s",
                request.method,
                request.path,
                request.remote_addr,
                request.headers.get('X-Instance-Id', ''),
                data_repr)

DATABASE = 'database.db'

def create_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    ''')
    conn.commit()
    conn.close()

def create_admin():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    admin = cursor.fetchone()
    if admin:
        # Delete the admin user
        cursor.execute('DELETE FROM users WHERE username = ?', ('admin',))
    cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', ADMIN_PASSWORD))
    conn.commit()
    conn.close()

# Create the database
create_database()

# Create the admin user
create_admin()

@app.route('/robots.txt')
def robots():
    return "Disallow: /"

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if the username exists
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE username = '{username}' AND password='{password}'")
        user = cursor.fetchone()
        conn.close()

        if user:
            # Login successful, set session variables
            session['user_id'] = user[0]
            session['username'] = user[1]
            if user[1] == 'admin':
                return FLAG
            return redirect('/')
        else:
            return 'Invalid username or password. Please try again.'

    return render_template('login.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
