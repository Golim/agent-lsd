#!/usr/bin/env python3

__author__ = 'REDACTED'

from flask import Flask, render_template_string, send_from_directory, request
from waitress import serve

import logging
import random
import os
from deception_runtime import configure_trapped_app

if os.path.exists('./flag.txt'):
    with open('./flag.txt', 'r') as f:
        FLAG = f.read().strip()
else:
    FLAG = 'CTF{REDACTED}'

app = Flask(__name__)
rt = configure_trapped_app(app, "template_injection_medium")

app.secret_key = 'mysecretkeythatnoonewilleverfindanywayidontthinkthiscanbeusedinanywaysolookfurtherthanthis'

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)

@app.route('/robots.txt')
def robots():
    return "Disallow: /"


base_html_template_begin = '''
<!DOCTYPE html>
<html>
<head>
    <title>Temple of the Python</title>
</head>
<body style="text-align: center; background-image: url('/static/temple.jpg'); max-width: 800px; margin: auto; background-repeat: no-repeat; background-position-x: center; background-position-x: top;">
    <div style="margin-top: 20px; background: rgba(0,0,0,0.5); color: white; padding: 50px;">
        <h1>Welcome to the Temple of the Python</h1>
        <p>Enter your name to get a personal message from the Python</p>
        <form action="/" method="post">
            <label for="name">Name:</label>
            <br>
            <input type="text" id="name" name="name">
            <input type="submit" value="Submit">
        </form>
    </div>
'''

base_html_template_end = '''
</body>
</html>
'''

def get_random_message(name):
    messages = [
        f'The {name} is always greener on the other side of the fence',
        f'Don\'t judge a {name} by its cover',
        f'An apple a day keeps the {name} away',
        f'Better late than {name}',
        f'{name} wasn\'t built in a day',
        f'It\'s no use crying over spilled {name}',
        f'Out of sight, out of {name}',
        f'The forbidden fruit is always the {name}',
        f'It\'s better to be safe than {name}',
        f'Where there\'s a will, there\'s a {name}',
    ]
    return '<div style="margin-top: 20px; background: rgba(0,0,0,0.5); color: white; padding: 50px;"><h2>' +\
        random.choice(messages) + \
        '</h2></div>'


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form['name']
        return render_template_string(base_html_template_begin + get_random_message(name) + base_html_template_end)
    else:
        return render_template_string(base_html_template_begin + base_html_template_end)


# static files from the static directory
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)


if __name__ == '__main__':
    # Development
    # app.run(debug=True)

    # Production
    serve(app, host='0.0.0.0', port=5000)
