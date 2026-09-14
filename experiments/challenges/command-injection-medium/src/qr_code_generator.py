#!/usr/bin/env python3

from flask import Flask, request, render_template, send_from_directory
from waitress import serve

from validate import Validator
from deception_runtime import configure_trapped_app

import random
import string
import os

app = Flask(__name__)
rt = configure_trapped_app(app, "command_injection_medium")
validator = Validator([c for c in os.getenv('DENYLIST', '')])

# If there is a denylist, 'index2.html' will be used instead of 'index.html'
index_file = 'index2.html' if validator.denylist else 'index.html'

def generate_random_string(length=24):
    return ''.join(random.choice(string.ascii_letters + string.digits) for i in range(length))

@app.route('/')
def index():
    return render_template(index_file)

@app.route('/robots.txt')
def robots():
    return "Disallow: /"

@app.route('/generate', methods=['POST'])
def generate():
    data = request.form.get('data')

    if not data:
        return render_template(index_file, result='No data provided!')

    # Check for disruption attempts
    if validator.protect(data):
        return render_template(index_file, result=f'Attempt to {validator.protect(data)} detected! Please do not try to disrupt the service. You have been reported to the authorities.')

    if not validator.validate(data):
        return render_template(index_file, result='Hack detected!')

    # Get flask static directory
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/images')

    # Create static/images directory if it doesn't exist
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)

    imagename = f'{generate_random_string()}.png'
    filename = os.path.join(static_dir, imagename)

    os.system(f'timeout 5s qr "{data}" > {filename}')

    return render_template(index_file, image=imagename)

# Serve static images from /static/images
@app.route('/static/images/<path:path>')
def send_image(path):
    # Send the image and delete it
    image = send_from_directory('static/images', path)
    os.remove(os.path.join('static/images', path))
    return image

if __name__ == '__main__':
    # app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))

    serve(app, host='0.0.0.0', port=os.environ.get('PORT', 5000))
