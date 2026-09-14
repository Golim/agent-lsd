# Website Status Checker 2.0

This website status checker is a simple tool that allows users to check whether a website is online or not. The tool sends a request to the specified website and checks the response code. If the response code is 200, the website is considered online, and the user receives a preview of the HTML content.

## Goal

The goal of the challenge is to access the admin panel on the `/admin` endpoint and find the secret new features that the developers are testing out.

## Vulnerability

The website is vulnerable to Server-Side Request Forgery (SSRF). The tool sends a request to the specified website without any validation or restriction. An attacker can abuse this functionality to send requests to internal services or other websites.

## Solution

We know that the challenge is internally listening on port 5000, based on the Dockerfile that we received.

This time, we cannot use the `http://localhost:5000/admin` URL because the server is blocking requests to `localhost`, and `127.*.*.*` IP addresses. We need to find a way to bypass the denylist.

To solve the challenge, we can use a simple SSRF protection bypass technique by using the `http://127.1:5000/admin` URL. There are several other possible ways to bypass this denylist; for example, we could use capital letters in the URL, URL encoding, or other tricks. Following are some examples:

- `http://loCAlhost:5000/admin`
- `http://2130706433:5000/admin`
- `http://017700000001:5000/admin`
