# Wallpapers 4

This challenge is the same as the previous ones, but this time the server checks if the `filename` includes `..`. We cannot bypass this by using an absolute path because the server prepends to the path the `images/` directory. Moreover, the server also URL-decodes the `filename` before checking if it includes `..`.

The vulnerability arises from the fact that the server decodes the URL-encoded string twice (or until there are `%` characters in the `filename`). This means that we can double-encode the `..` characters to bypass the check:

```bash
curl "http://host:port/image/?filename=%252e%252e%2F%252e%252e%2Fflag.txt"
```
