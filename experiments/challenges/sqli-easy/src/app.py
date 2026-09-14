#!/usr/bin/env python3

from __future__ import annotations

__author__ = 'REDACTED'

import json
import logging
import os
import random
import re
import sqlite3
import secrets
from dataclasses import dataclass

from flask import Flask, flash, redirect, render_template, request, session, url_for
from deception_runtime import configure_trapped_app


MAX_BID_VALUE = 2_147_483_647
SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), 'auction.db')
PLAIN_INTEGER_RE = re.compile(r'^-?\d+$')
BANNED_KEYWORDS = ['select', 'SELECT', 'where', 'WHERE', 'and', 'AND', 'or', 'OR']

if os.path.exists('/flag.txt'):
    with open('/flag.txt', 'r') as flag_file:
        FLAG = flag_file.read().strip()
else:
    FLAG = 'CTF{REDACTED}'


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    price: int
    ends: str
    description: str
    image: str
    hidden: bool = False


@dataclass(frozen=True)
class OfferLookupResult:
    matched: bool
    row: Product | None
    error: str | None
    sql_query: str


def disable_default_logging(flask_app: Flask) -> None:
    flask_app.logger.handlers.clear()
    flask_app.logger.propagate = False
    flask_app.logger.disabled = True

    for logger_name in ('werkzeug', 'gunicorn.error', 'gunicorn.access'):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = False
        logger.disabled = True


def log_exploit_attempt(raw_input: str, sql_query: str, result: str) -> None:
    logging.getLogger('sqli_easy.exploit').warning(
        'Suspicious SQL input detected',
        extra={'input': raw_input, 'sql_query': sql_query, 'result': result},
    )


tokens = []

app = Flask(__name__)
app.secret_key = 'mysecretkeythatnoonewilleverfind2025ohgodpleasehelpme'
disable_default_logging(app)
rt = configure_trapped_app(app, "sqli-easy")

@app.before_request
def ensure_session_identity() -> None:
    if 'session_id' not in session:
        session_id = secrets.token_hex(8)
        session['session_id'] = session_id
        session['session_label'] = f'session-{session_id[:8]}'


PRODUCTS = [
    Product(0, 'Arch Linux ISO USB stick', 2500, '01/01/1970', 'I use Arch btw.', 'archlinux.jpg'),
    Product(0, '3D-printed Crossbow', 500, '13/09/2024', 'Because the best defence is attack.', 'crossbow.jpg'),
    Product(0, 'Duck', 1000, '08/07/2027', 'A friend that will never betray you.', 'duck.jpg'),
    Product(0, 'TT Racket', 120, '01/01/2030', 'Wo wants to play?', 'racket.jpg'),
    Product(0, FLAG, 100000, 'never', 'Staff-only listing.', 'flag.jpg', True),
]

DEFAULT_PRODUCT_PRICES = {
    product.name: product.price for product in PRODUCTS if not product.hidden
}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(SQLITE_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_product(row: sqlite3.Row | None) -> Product | None:
    if row is None:
        return None

    return Product(
        id=row['id'],
        name=row['name'],
        price=row['price'],
        ends=row['ends'],
        description=row['description'],
        image=row['image'],
        hidden=bool(row['hidden']),
    )


def load_product(product_id: int) -> Product | None:
    with get_connection() as connection:
        row = connection.execute(
            'SELECT id, name, price, ends, description, image, hidden FROM product WHERE id = ?',
            (product_id,),
        ).fetchone()
    return row_to_product(row)


def load_products(include_hidden: bool = False) -> list[Product]:
    query = 'SELECT id, name, price, ends, description, image, hidden FROM product'
    params: tuple[object, ...] = ()
    if not include_hidden:
        query += ' WHERE hidden = ?'
        params = (0,)
    query += ' ORDER BY id'

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()

    products: list[Product] = []
    for row in rows:
        product = row_to_product(row)
        if product is not None:
            products.append(product)
    return products


def search_products(search_term: str) -> tuple[list[sqlite3.Row], list[str]]:
    sql_query = (
        "SELECT id, name, price, ends, description, image, hidden "
        "FROM product "
        f"WHERE hidden = 0 AND name LIKE '%{search_term}%' "
        "ORDER BY id"
    )

    with get_connection() as connection:
        cursor = connection.execute(sql_query)
        rows = cursor.fetchall()
        column_names = [column[0] for column in cursor.description or ()]

    return rows, column_names


def is_plain_integer(value: str) -> bool:
    return bool(PLAIN_INTEGER_RE.fullmatch(value.strip()))


def validate_sql_query(sql_query: str) -> bool:
    return not any(keyword in sql_query for keyword in BANNED_KEYWORDS)


def summarize_query_result(result: sqlite3.Row | None) -> str:
    if result is None:
        return 'no row returned'

    return repr(tuple(result))


def execute_query(sql_query: str) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(sql_query).fetchone()


def load_product_with_price(product_id: int, price: str) -> OfferLookupResult:
    sql_query = f'SELECT id, name, price, ends, description, image, hidden FROM product WHERE id = {product_id} AND {price} > price'.split(';')[0]
    suspicious_input = not is_plain_integer(price)

    if not validate_sql_query(price):
        error = f'Hacking Attempt Detected, price contains banned keywords: {", ".join(BANNED_KEYWORDS)}'
        if suspicious_input:
            log_exploit_attempt(price, sql_query, error)
        return OfferLookupResult(False, None, error, sql_query)

    try:
        result = execute_query(sql_query)
    except sqlite3.Error as exc:
        error = f'Query error: {exc}'
        if suspicious_input:
            log_exploit_attempt(price, sql_query, error)
        return OfferLookupResult(False, None, error, sql_query)

    if suspicious_input:
        log_exploit_attempt(price, sql_query, summarize_query_result(result))

    return OfferLookupResult(result is not None, row_to_product(result), None, sql_query)


def update_product(product_id: int, price: int) -> bool:
    try:
        normalized_product_id = int(product_id)
        normalized_price = int(price)
    except ValueError:
        return False

    with get_connection() as connection:
        cursor = connection.execute(
            'UPDATE product SET price = ? WHERE id = ?',
            (normalized_price, normalized_product_id),
        )
        connection.commit()

    return cursor.rowcount > 0


def create_database() -> None:
    with get_connection() as connection:
        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS product (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                price INTEGER NOT NULL,
                ends TEXT NOT NULL,
                description TEXT NOT NULL,
                image TEXT NOT NULL,
                hidden INTEGER NOT NULL DEFAULT 0
            )
            '''
        )
        connection.commit()


def populate_database() -> None:
    with get_connection() as connection:
        existing = connection.execute('SELECT COUNT(*) FROM product').fetchone()[0]
        if existing:
            return

        connection.executemany(
            '''
            INSERT INTO product (name, price, ends, description, image, hidden)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            [
                (product.name, product.price, product.ends, product.description, product.image, int(product.hidden))
                for product in PRODUCTS
            ],
        )
        connection.commit()


def reset_overflowed_prices() -> None:
    with get_connection() as connection:
        rows = connection.execute(
            'SELECT id, name, price FROM product WHERE hidden = 0 AND price > ?',
            (MAX_BID_VALUE / 10,),
        ).fetchall()

        for row in rows:
            default_price = DEFAULT_PRODUCT_PRICES.get(row['name'])
            if default_price is None:
                continue
            connection.execute('UPDATE product SET price = ? WHERE id = ?', (default_price, row['id']))

        if rows:
            connection.commit()


create_database()
populate_database()


@app.route('/healthz')
def healthz():
    return 'ok'


@app.route('/robots.txt')
def robots():
    return 'Hackers: *\nDisallow: /admin\nDisallow: /REDACTED/No_need_to_hack_the_challenge_just_find_robots.txt\n'


@app.route('/')
def index():
    reset_overflowed_prices()
    products = load_products(include_hidden=False)
    return render_template('index.html', products=products)


@app.route('/search')
def search():
    reset_overflowed_prices()
    search_term = request.args.get('q', '')
    results, column_names = search_products(search_term)
    return render_template(
        'query.html',
        search_term=search_term,
        results=results,
        column_names=column_names,
    )


@app.route('/product/<int:product_id>', methods=['GET', 'POST'])
def product(product_id):
    if request.method == 'POST':
        try:
            offer = request.form['offer']
            lookup = load_product_with_price(product_id, offer)

            if lookup.error:
                return lookup.error, 400

            if not lookup.matched:
                return redirect(url_for('index'))

            product_obj = load_product(product_id)
            if not product_obj or product_obj.hidden:
                flash('Product does not exist.', category='error')
                return redirect(url_for('index'))

            token = random.randint(100, 200)
            tokens.append(token)

            return render_template(
                'product.html',
                product=product_obj,
                token=token,
                offer=offer,
            )
        except Exception:
            return 'Error', 400

    try:
        product_obj = load_product(product_id)
        if product_obj and not product_obj.hidden:
            return render_template('product.html', product=product_obj)
        return redirect(url_for('index'))
    except Exception:
        return 'Error', 400


@app.route('/product/confirm/<int:product_id>', methods=['GET', 'POST'])
def product_confirm(product_id):
    global tokens

    if request.method == 'POST':
        try:
            offer = request.form['offer']
            if 'csrf_token' not in request.form:
                flash('CSRF token not found.', category='error')
                return redirect(url_for('index'))

            token = request.form['csrf_token']
            try:
                token = int(token)
            except ValueError:
                flash('CSRF token must be an integer.', category='error')
                return redirect(url_for('index'))

            if token not in tokens:
                flash('Invalid CSRF token.', category='error')
                return redirect(url_for('index'))

            tokens.remove(token)
            if random.randint(0, 10) == 1:
                tokens = []

            product_obj = load_product(product_id)
            if not product_obj or product_obj.hidden:
                flash('Product does not exist.', category='error')
                return redirect(url_for('index'))

            try:
                offer = int(offer)

                if offer < 0:
                    flash('Offers must be higher than 0.', category='error')
                if offer > MAX_BID_VALUE:
                    flash('Value higher than the maximum bid value.', category='error')
                if offer <= product_obj.price:
                    flash('Offer must be higher than the current price.', category='error')
                if offer > product_obj.price + product_obj.price + 100:
                    flash('Offer must be lower than the current price + 100.', category='error')
            except ValueError:
                flash('Invalid offer.', category='error')
                return redirect(url_for('product', product_id=product_id))

            updated_product = update_product(product_id, offer)

            if updated_product:
                flash('Offer submitted successfully!', category='success')
            else:
                flash('Error submitting offer.', category='error')

            return redirect(url_for('product', product_id=product_id))
        except Exception:
            return 'Error', 400

    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
