# Magic Squares 2

The challenge is the same as the previous one, but this time the user input is sanitized to prevent the use of backticks and `$()`. Something like:

```python
data = request.form.get('data')

if '`' in data or '$' in data:
    return 'Invalid input'
```

To solve the challenge, we can `cat` the content of `./flag.txt` directly into the output image file. We first need to close the double quotes prepended by the server to the command, and then we can use the semicolon to separate the `cat` command from the rest of the command. Finally, we the server appends a double quote to the end of the command, so we need to open a new one. The resulting payload is:

```plaintext
"; cat "./flag.txt
```

The resulting file has the `png` extension, but it is actually a text file containing the flag.
