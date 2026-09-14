#!/usr/bin/env python3

from flask import Flask, request, jsonify, render_template

import requests
import re
from deception_runtime import configure_trapped_app

# A regex that matches 127.*.*.*, and localhost
URL_REGEX = r'^http:\/\/(127\.\d{1,3}\.\d{1,3}\.\d{1,3}|localhost)(:\d{1,5})?\/.*$'

def is_valid_url(url):
    if '0.0.0.0' in url: # unintended solution
        return False, 'Hack'
    regex = re.match(URL_REGEX, url)
    if regex:
        return False, 'Hack'

    return True, 'Valid'

app = Flask(__name__)
rt = configure_trapped_app(app, "ssrf_medium")

@app.route('/robots.txt')
def robots():
    return "Disallow: /"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/check')
def check():
    url = request.args.get('url')
    is_valid = is_valid_url(url)
    print(is_valid)
    if url is None or not is_valid[0]:
        if is_valid[1] == 'Hack':
            return jsonify({'error': 'You are not allowed to access this URL.'}), 403
        return jsonify({'error': 'Invalid URL.'}), 400

    try:
        r = requests.get(url)
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'Error while fetching the url.'}), 400
    except Exception as e:
        return jsonify({'error': 'Unknown error.'}), 400
    return jsonify({'status': 'online', 'content': r.text, 'error': None})


@app.route('/admin')
def admin():
    if request.remote_addr != '127.0.0.1':
        return jsonify({'error': 'This page is only accessible from localhost.'}), 403
    return open('/flag.txt').read()    

if __name__ == '__main__':
    # Debug mode should be disabled in production
    app.run(debug=True)
