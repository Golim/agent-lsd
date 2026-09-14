#!/usr/bin/env python3

__author__ = 'REDACTED'

from flask import Flask, render_template, request, redirect, url_for, session, flash
from waitress import serve

import secrets
import sqlite3
import logging
import os
from deception_runtime import configure_trapped_app

if os.path.exists('./flag.txt'):
    with open('./flag.txt', 'r') as f:
        FLAG = f.read().strip()
else:
    FLAG = 'CTF{REDACTED}'

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'supercomplicatedpasswordnobodyshouldusethis')


class Product:
    def __init__(self, id, name, price, expiration_date, description, image):
        self.id = id
        self.name = name
        self.price = price
        self.expiration_date = expiration_date
        self.description = description
        self.image = image

PRODUCTS = [
    Product(1, 'Arch Linux ISO USB stick', 2500, "01/01/1970", "I use Arch btw.", "archlinux.jpg"),
    Product(2, '3D-printed Crossbow', 500, "13/09/2024", "Because the best defence is attack.", "crossbow.jpg"),
    Product(3, 'Duck', 1000, "08/07/2027", "A friend that will never betray you.", "duck.jpg"),
    Product(4, 'Ping-Pong Ball', 100, "01/01/2030", "Wo does not love ping-pong?", "pingpong.jpg"),
    Product(5, '3D-printed phone stand', 150, "03/06/2024", "Carlo thought this was a good idea.", "phonestand.jpg"),
]

app = Flask(__name__)
rt = configure_trapped_app(app, "race_condition_medium")

app.secret_key = 'mysecretREDACTEDbankingkeythatnoonewilleverfind'

DATABASE = 'database.db'

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)


def drop_tables():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DROP TABLE IF EXISTS users')
    cursor.execute('DROP TABLE IF EXISTS products')
    conn.commit()
    conn.close()

def create_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            balance INTEGER,
            coupon INTEGER
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
    cursor.execute('INSERT INTO users (username, password, balance, coupon) VALUES (?, ?, ?, ?)', ('admin', ADMIN_PASSWORD, 1, 0))
    conn.commit()
    conn.close()

# Create the database
# drop_tables()
create_database()

# Create the admin user
create_admin()

def create_anonymous_user():
    username = f"anon_{secrets.token_urlsafe(16)}"

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password, balance, coupon) VALUES (?, ?, ?, ?)",
        (username, '', 50, 0)
    )
    conn.commit()

    user_id = cursor.lastrowid
    conn.close()
    return user_id, username


@app.before_request
def ensure_anonymous_session():
    if "user_id" not in session:
        user_id, username = create_anonymous_user()
        session["user_id"] = user_id
        session["username"] = username

@app.route('/robots.txt')
def robots():
    return "Disallow: /"

@app.route('/')
def index():
    if 'user_id' in session:
        # Update the current balance and fetch all registered users for the dropdown
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        if not user:
            # User does not exist
            session.clear()
            return redirect(url_for('login'))
        session['balance'] = user[3]
        session['coupon'] = user[4]

        return render_template('index.html', username=session['username'], balance=session['balance'], coupon=session['coupon'], products=PRODUCTS)
    else:
        return redirect(url_for('login'))

@app.route('/buy', methods=['GET'])
def buy():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    product_id = request.args.get('id')
    product = None
    for p in PRODUCTS:
        if p.id == int(product_id):
            product = p
            break
    if not product:
        flash('Product does not exist.', category='error')
        return redirect(url_for('index'))

    # Update the current balance
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    if not user:
        # User does not exist
        session.clear()
        return redirect(url_for('login'))
    session['balance'] = user[3]
    session['coupon'] = user[4]

    if product.price > (session['balance'] + session['coupon']): 
        flash('Not enough balance.', category='error')
        return redirect(url_for('index'))

    cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (product.price, session['user_id']))
    cursor.execute('UPDATE users SET coupon = 0 WHERE id = ?', (session['user_id'],))
    conn.commit()
    conn.close()
    return FLAG, 200

@app.route('/apply_coupon', methods=['POST'])
def apply_coupon():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    coupon = request.form['coupon']
    if coupon == 'GET10':
        # Update the coupon balance from the database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        if not user:
            # User does not exist
            session.clear()
            return redirect(url_for('login'))
        session['coupon'] = user[4]
        conn.close()

        # Check if the coupon has already been applied
        if session['coupon'] > 0:
            # flash('Coupon already applied.', category='error')
            # return redirect(url_for('index'))
            return "Coupon already applied.", 400

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        # Sum 10 to the user's coupon balance
        cursor.execute('UPDATE users SET coupon = coupon + 10 WHERE id = ?', (session['user_id'],))
        conn.commit()
        conn.close()

        session['coupon'] += 10

        # flash('Coupon applied successfully.', category='success')
        return "Coupon applied successfully.", 200
    else:
        # flash('Invalid coupon.', category='error')
        return "Invalid coupon.", 400
    return redirect(url_for('index'))

@app.route('/remove_coupon', methods=['POST'])
def remove_coupon():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET coupon = 0 WHERE id = ?', (session['user_id'],))
    conn.commit()
    conn.close()

    session['coupon'] = 0

    flash('Coupon removed successfully.', category='success')
    return redirect(url_for('index'))


if __name__ == '__main__':
    # Development
    # app.run(debug=True)

    # Production
    serve(app, host='0.0.0.0', port=5000)
