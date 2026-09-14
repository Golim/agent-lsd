# Trap-Augment Challenges

To augment a challenge with traps, add the following to the challenge's Python flask source:

```python
from deception_runtime import configure_trapped_app

rt = configure_trapped_app(app, "example_challenge")

logger = logging.getLogger('request_logger')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('requests.log', maxBytes=5 * 1024 * 1024, backupCount=2)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
logger.addHandler(handler)

@app.before_request
def log_request():
    data_repr = None
    try:
        if request.form:
            data = dict(request.form)
            data_repr = data
        else:
            json_body = request.get_json(silent=True)
            if json_body:
                data_repr = json_body
    except Exception:
        data_repr = '<unreadable>'

    logger.info("%s %s from=%s Instance-ID=%s data=%s",
                request.method,
                request.path,
                request.remote_addr,
                request.headers.get('X-Instance-Id', ''),
                data_repr)
```

When building the challenge images, keep the challenge folder as the main build
context and pass the repository root as the named `repo` context so the shared
runtime and generated instances are available:

```bash
docker buildx build --build-context repo=../../../framework -f Dockerfile . -t web
```
