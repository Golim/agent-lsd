#!/usr/bin/env python3

__author__ = 'REDACTED'


from flask import Flask, render_template, request, redirect, url_for, session, flash
from waitress import serve
from lxml import etree
from json2html import *

import secrets
import markdown2
import sqlite3
import logging
import json
import os
from deception_runtime import configure_trapped_app

if os.path.exists('./flag.txt'):
    with open('./flag.txt', 'r') as f:
        FLAG = f.read().strip()
else:
    FLAG = 'CTF{REDACTED}'

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'swipe-whooping-varying-decompose')

app = Flask(__name__)
rt = configure_trapped_app(app, "xxe_medium")

app.secret_key = 'mysecretREDACTEDbountykeythatnoonewilleverfind'

DATABASE = 'database.db'

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)

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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            report TEXT
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

def create_anonymous_user():
    username = f"session_{secrets.token_urlsafe(4)}"

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (username, '')
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
        # Get the reports from this user
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reports WHERE username = ?', (session['username'],))
        reports = cursor.fetchall()
        conn.close()

        return render_template('index.html', username=session['username'], reports=reports)
    else:
        return redirect(url_for('login'))


@app.route('/report', methods=['POST'])
def report():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    format = request.form['format']
    report = request.form['report']

    # Turn the report into HTML from the selected format
    if format == 'markdown':
        report = markdown2.markdown(report)
    elif format == 'plaintext':
        report = '<pre>' + report + '</pre>'
    elif format == 'xml':
        try:
            # Parse the XML
            parser = etree.XMLParser(no_network=False)
            report = etree.tostring(etree.fromstring(str(report), parser)).decode('utf-8')
        except etree.XMLSyntaxError as e:
            return f'Invalid XML: {e}'
    elif format == 'json':
        report = json2html.convert(json = json.loads(report))

    # Save the report to the database
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO reports (username, report) VALUES (?, ?)', (session['username'], report))
    conn.commit()
    conn.close()
    flash('Report submitted successfully.', category='success')
    return redirect(url_for('index'))

@app.route('/report/<id>', methods=['GET'])
def report_get(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Get the report
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM reports WHERE id = ?', (id,))
    report = cursor.fetchone()

    # Delete the report
    cursor.execute('DELETE FROM reports WHERE id = ?', (id,))
    conn.commit()
    conn.close()

    if report:
        return render_template('report.html', report=report, username=session['username'])
    else:
        return redirect(url_for('index'))

if __name__ == '__main__':
    # Development
    # app.run(debug=True, host='0.0.0.0', port=5000)

    # Production
    serve(app, host='0.0.0.0', port=5000)
