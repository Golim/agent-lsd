#!/usr/bin/env python3

from flask import Flask, request, render_template, send_file
from waitress import serve

import urllib.parse

import logging
import random
import string
import os
from deception_runtime import configure_trapped_app

def is_path_traversal(filename):
    try:
        app.logger.info(f'Received filename: {filename}')

        if '..' in filename:
            return True
    except:
        return True

    return False

app = Flask(__name__)
rt = configure_trapped_app(app, "path_traversal_medium")
# app.logger.setLevel(logging.DEBUG)

# List of image filenames for the challenge
image_filenames = ["1.jpeg", "2.jpeg", "3.jpeg", "4.jpeg"]

@app.route('/')
def index():
    return render_template('index.html', images=image_filenames)

@app.route('/robots.txt')
def robots():
    return "Disallow: /"

@app.route('/image/')
def image():
    filename = request.args.get('filename', '')

    if is_path_traversal(filename):
        return "Woah there! What are you trying to do?!!??!"

    while '%' in filename:
        filename = urllib.parse.unquote(filename)

    filename = 'images/' + filename

    try:
        return send_file(filename, mimetype='image/jpeg')
    except:
        return "Oops! Something went wrong!", 404

if __name__ == '__main__':
    # app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000), debug=True)

    serve(app, host='0.0.0.0', port=os.environ.get('PORT', 5000))
