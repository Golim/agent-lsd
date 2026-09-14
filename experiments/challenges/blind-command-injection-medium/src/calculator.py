#!/usr/bin/env python3

__author__ = 'REDACTED'

from flask import Flask, request, render_template
from waitress import serve

import subprocess
import random
import os
from deception_runtime import configure_trapped_app

error_messages = [
    'What are you trying to do?',
    'You are so wrong!',
    'I am just a calculator!',
    'Learn math!',
    'Leave me alone!',
    'Are you kidding me?',
    'Oh oh you almost got me this time!',
]

app = Flask(__name__)
rt = configure_trapped_app(app, "blind_command_injection_medium")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/robots.txt')
def robots():
    return "Disallow: /"

@app.route('/execute', methods=['POST'])
def execute():
    expression = request.get_data(as_text=True).replace('expression=', '')

    command = b'echo "' + expression.encode('utf-8') + b'"|bc -l'

    ps = subprocess.Popen(command.decode('utf-8'), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result = ps.communicate()[0]

    try:
        return str(float(result.strip()))
    except ValueError:
        return random.choice(error_messages)
        # return command.decode('utf-8') + " " + result.decode('utf-8')

if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=os.environ.get('PORT', 5000))
