#!/usr/bin/env python3

__author__ = "REDACTED"

import logging
import os
import random
import sqlite3

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from deception_runtime import configure_trapped_app

if "FLAG" in os.environ:
    FLAG = os.environ["FLAG"]
else:
    FLAG = "CTF{REDACTED}"

app = Flask(__name__, static_folder="static")
rt = configure_trapped_app(app, "sqli_medium")


app.secret_key = "youshouldnotbeabletoreadthisnononoplease"

DATABASE = "database.db"

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger("main")
logger.setLevel(logging.DEBUG)


def sanitize(filename):
    while "../" in filename:
        filename = filename.replace("../", "")
    return filename


def prepare_statement(statement, values):
    """
    Safe way to prepare a SQL statement with values
    """
    for value in values:
        statement = statement.replace("?", f"'{value}'", 1)

    # print(f'Prepared statement: {statement}', flush=True)

    return statement


def clean_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS user")
    cursor.execute("DROP TABLE IF EXISTS license")
    conn.commit()
    conn.close()


def create_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            balance INTEGER DEFAULT 0
        )
    """)
    conn.commit()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT,
            password TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS license (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            key TEXT,
            FOREIGN KEY(user_id) REFERENCES user(id),
            FOREIGN KEY(key) REFERENCES password(key)
        )
    """)
    conn.close()


def populate_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM user WHERE username = 'admin'
    """)
    admin = cursor.fetchone()

    if not admin:
        cursor.execute("""
            INSERT INTO user (username, password, balance) VALUES
            ('admin', 'NoYouAreNotGuessingThisOneForSureButEvenMoreComplicated', 10000)
        """)
        conn.commit()
    conn.commit()
    conn.close()


# Clean the database
# clean_database()

# Create the database
create_database()

# Populate the database
populate_database()


@app.route('/robots.txt')
def robots():
    return "Disallow: /"


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_password = password  # I'm lazy :)

        # Check if the username is already taken
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user WHERE username = ?", (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash("Username is already taken. Please choose another.", category="error")
        else:
            # Add the new user to the database
            cursor.execute(
                "INSERT INTO user (username, password, balance) VALUES (?, ?, ?)",
                (username, hashed_password, 100),
            )
            conn.commit()
            flash("Registration successful. You can now log in.", category="success")
            conn.close()
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Check if the username exists
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user and user[2] == password:
            # Login successful, set session variables
            session["user_id"] = user[0]
            session["username"] = user[1]
            conn.close()
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password. Please try again.", category="error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/")
def index():
    if "user_id" in session:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user WHERE id = ?", (session["user_id"],))
        user = cursor.fetchone()
        if not user:
            # User does not exist
            session.clear()
            print("User does not exist", flush=True)
            return redirect(url_for("login"))
        conn.close()

        session["username"] = user[1]

        return render_template("index.html", username=session["username"])
    else:
        return redirect(url_for("login"))


@app.route("/fonts/<path:path>")
def send_static_fonts(path):
    return send_from_directory("fonts", path)


@app.route("/licenses")
def licenses():
    if "user_id" in session:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user WHERE id = ?", (session["user_id"],))
        user = cursor.fetchone()
        if not user:
            # User does not exist
            session.clear()
            return redirect(url_for("login"))
        conn.close()

        session["username"] = user[1]
        session["balance"] = user[3]

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM license WHERE user_id = ?", (session["user_id"],))
        licenses = cursor.fetchall()
        conn.close()

        return render_template(
            "licenses.html",
            licenses=licenses,
            username=session["username"],
            balance=session["balance"],
        )
    else:
        return redirect(url_for("login"))


@app.route("/buy-license", methods=["POST"])
def buy_license():
    if "user_id" in session:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        statement = prepare_statement(
            "SELECT * FROM user WHERE id = ?", (session["user_id"],)
        )
        cursor.execute(statement)
        user = cursor.fetchone()
        if not user:
            # User does not exist
            session.clear()
            return redirect(url_for("login"))
        conn.close()

        session["username"] = user[1]
        session["balance"] = user[3]

        # Generate a random license key
        license_key = "".join(
            random.choices(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=16
            )
        )

        # Check if the user has enough balance
        if session["balance"] < 100:
            flash(
                "You do not have enough balance to purchase a license.",
                category="error",
            )
            return redirect(url_for("licenses"))

        # Deduct the balance
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE user SET balance = balance - 100 WHERE id = ?",
            (session["user_id"],),
        )
        conn.commit()

        # Add the license to the database
        cursor.execute(
            "INSERT INTO license (user_id, key) VALUES (?, ?)",
            (session["user_id"], license_key),
        )
        conn.commit()

        # Add the password to the database
        password = "".join(
            random.choices(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=24
            )
        )
        cursor.execute(
            "INSERT INTO password (key, password) VALUES (?, ?)",
            (license_key, password),
        )
        conn.commit()

        conn.close()

        flash(
            "License purchased successfully, you can use it to redeem a password.",
            category="success",
        )
        return redirect(url_for("licenses"))
    else:
        return redirect(url_for("login"))


@app.route("/sell-license", methods=["POST"])
def sell_license():
    if "user_id" in session:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user WHERE id = ?", (session["user_id"],))
        user = cursor.fetchone()
        if not user:
            # User does not exist
            session.clear()
            return redirect(url_for("login"))
        conn.close()

        session["username"] = user[1]
        session["balance"] = user[3]

        license_key = request.form["license_key"]

        # Check if the license key exists
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        statement = prepare_statement(
            "SELECT * FROM license WHERE key = ?", (license_key,)
        )
        print(request.remote_addr, statement, flush=True)
        cursor.execute(statement)
        license = cursor.fetchone()

        if not license:
            flash("License key does not exist.", category="error")
            return redirect(url_for("licenses"))

        # Check if the license belongs to the user
        if license[1] != session["user_id"]:
            flash("License key does not belong to you.", category="error")
            return redirect(url_for("licenses"))

        # Remove the license from the database
        cursor.execute("DELETE FROM license WHERE key = ?", (license_key,))
        conn.commit()

        # Remove the password from the database
        result = cursor.execute("DELETE FROM password WHERE key = ?", (license_key,))
        conn.commit()

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE user SET balance = balance + 50 WHERE id = ?", (session["user_id"],)
        )
        conn.commit()

        conn.close()

        flash("License sold successfully.", category="success")
        return redirect(url_for("licenses"))
    else:
        return redirect(url_for("login"))


@app.route("/passwords")
def passwords():
    if "user_id" in session:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user WHERE id = ?", (session["user_id"],))
        user = cursor.fetchone()
        if not user:
            # User does not exist
            session.clear()
            return redirect(url_for("login"))
        conn.close()

        session["username"] = user[1]

        return render_template("passwords.html", username=session["username"])
    else:
        return redirect(url_for("login"))


@app.route("/download-font", methods=["POST"])
def download_font():
    # Get the font name and the password
    font = request.form["font"]
    password = request.form["password"]

    # Check if the password is correct
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM password WHERE password = ?", (password,))
    password = cursor.fetchone()

    if not password:
        flash(
            "Invalid password. Redeem a license for a password first.", category="error"
        )
        return redirect(url_for("passwords"))

    else:
        print(request.remote_addr, f"Password {password[1]} is correct", flush=True)
        flash(f"Password correct. Here's your flag: {FLAG}", category="success")
        flash(
            "If you actually want the font, you can find it here: https://www.collletttivo.it/typefaces/sneaky-times",
            category="info",
        )
        return redirect(url_for("index"))


if __name__ == "__main__":
    # Development
    app.run(host="0.0.0.0", port=5000, debug=True)
