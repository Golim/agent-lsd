# Deception Runtime for Flask Challenges

A reusable package that enables automated deception injection in Flask-based CTF web challenges.

## Features

- **Drop-in integration**: Add to any Flask app with minimal changes
- **Instance registry**: Automatically loads and indexes resolved deception instances
- **Request-scoped context**: Access active deceptions via `g.deception_ctx`
- **Multiple activation modes**: Header (`X-Instance-Id`) or query parameter (`?instance=`)
- **Health endpoint**: `/__deception__/health` for diagnostics
- **CLI tools**: Validate and inspect the registry
- **Fail-safe modes**: Configurable fail-closed (400 on invalid) or fail-open
- **Structured logging**: Comprehensive logging with context fields

## Quick Start

### Installation

```bash
# Install dependencies
pip install flask pyyaml

# Optional: for schema validation
pip install jsonschema
```

### Integration

```python
from flask import Flask
from deception_runtime import DeceptionRuntime

app = Flask(__name__)
app.config["DECEPTIONS_ENABLED"] = True  # Or use env var

rt = DeceptionRuntime()
rt.init_app(app)

# Your routes work unchanged!
```

### Accessing Active Deception

```python
from deception_runtime import get_active_instance

@app.route("/login")
def login():
    instance = get_active_instance()

    if instance:
        # Access deception data
        print(f"Active: {instance.instance_id}")
        print(f"Payload: {instance.payload_text}")
        print(f"Channel: {instance.channel}.{instance.surface}")

    return render_template("login.html")
```

### Testing

```bash
# Start your Flask app
python app.py

# Test with header
curl -H "X-Instance-Id: dom_a11y_authoritative_hint_000" http://localhost:5000/

# Test with query parameter
curl "http://localhost:5000/?instance=dom_a11y_authoritative_hint_000"

# Check health endpoint
curl http://localhost:5000/__deception__/health
```

## Configuration

Configure via Flask config or environment variables:

| Config Key | Env Var | Default | Description |
|------------|---------|---------|-------------|
| `DECEPTIONS_ENABLED` | `DECEPTIONS_ENABLED` | `false` | Enable/disable deceptions |
| `DECEPTIONS_INSTANCES_DIR` | `DECEPTIONS_INSTANCES_DIR` | `deceptions/instances/generated` | Instance files directory |
| `DECEPTIONS_SCHEMA_PATH` | `DECEPTIONS_SCHEMA_PATH` | `deceptions/schemas/deception.schema.json` | JSON schema path |
| `DECEPTIONS_INSTANCE_HEADER` | `DECEPTIONS_INSTANCE_HEADER` | `X-Instance-Id` | Header name for instance ID |
| `DECEPTIONS_INSTANCE_QUERY` | `DECEPTIONS_INSTANCE_QUERY` | `instance` | Query param for instance ID |
| `DECEPTIONS_STUDENT_HEADER` | `DECEPTIONS_STUDENT_HEADER` | `X-Student-Id` | Header name for student ID |
| `DECEPTIONS_STUDENT_COOKIE` | `DECEPTIONS_STUDENT_COOKIE` | `student_id` | Cookie name for student ID |
| `DECEPTIONS_CHALLENGE_ID` | `DECEPTIONS_CHALLENGE_ID` | `app.name` | Challenge identifier |
| `DECEPTIONS_FAIL_CLOSED` | `DECEPTIONS_FAIL_CLOSED` | `true` | Return 400 if instance not found |
| `DECEPTIONS_TELEMETRY_ENABLED` | `DECEPTIONS_TELEMETRY_ENABLED` | `false` | Enable telemetry |
| `DECEPTIONS_TELEMETRY_SINK` | `DECEPTIONS_TELEMETRY_SINK` | `jsonl` | Telemetry sink (`jsonl` or `sqlite`) |
| `DECEPTIONS_TELEMETRY_PATH` | `DECEPTIONS_TELEMETRY_PATH` | `telemetry.jsonl` | Telemetry file/database path |
| `DECEPTIONS_TELEMETRY_SAMPLE_RATE` | `DECEPTIONS_TELEMETRY_SAMPLE_RATE` | `1.0` | Sampling rate (0.0-1.0) |
| `DECEPTIONS_HONEYTOKENS_ENABLED` | `DECEPTIONS_HONEYTOKENS_ENABLED` | `false` | Enable honeytoken detection |
| `DECEPTIONS_HONEYTOKEN_RESPONSE_MODE` | `DECEPTIONS_HONEYTOKEN_RESPONSE_MODE` | `200` | Response mode (`200` or `404`) |
| `DECEPTIONS_PROTECTED_ROUTES` | `DECEPTIONS_PROTECTED_ROUTES` | `` | Protected routes (no active endpoints) |
| `DECEPTIONS_ENDPOINT_TRAPS_ENABLED` | `DECEPTIONS_ENDPOINT_TRAPS_ENABLED` | `false` | Enable endpoint-specific trap pages |
| `DECEPTIONS_ENDPOINT_TRAPS_INTERACTIVE` | `DECEPTIONS_ENDPOINT_TRAPS_INTERACTIVE` | `false` | Enable bounded step-based trap flow |
| `DECEPTIONS_ENDPOINT_TRAPS_MAX_STEPS` | `DECEPTIONS_ENDPOINT_TRAPS_MAX_STEPS` | `2` | Max interactive step index |
| `DECEPTIONS_ENDPOINT_TRAPS_FAKE_GOALS_ENABLED` | `DECEPTIONS_ENDPOINT_TRAPS_FAKE_GOALS_ENABLED` | `false` | Allow terminal fake-goal state in endpoint traps |
| `DECEPTIONS_ENDPOINT_TRAPS_RABBIT_HOLES_ENABLED` | `DECEPTIONS_ENDPOINT_TRAPS_RABBIT_HOLES_ENABLED` | `false` | Allow rabbit-hole hops to render endpoint traps |
| `DECEPTIONS_ENDPOINT_TRAP_MAP_FILE` | `DECEPTIONS_ENDPOINT_TRAP_MAP_FILE` | `` | Optional JSON `path -> trap_type` override map |
| `DECEPTIONS_ENDPOINT_TRAPS_OPAQUE_PATTERNS` | `DECEPTIONS_ENDPOINT_TRAPS_OPAQUE_PATTERNS` | `` | Optional comma-separated regex list for opaque endpoint classification |

### Example Configuration

```python
# Via Flask config
app.config.update({
    "DECEPTIONS_ENABLED": True,
    "DECEPTIONS_INSTANCES_DIR": "instances/generated",
    "DECEPTIONS_CHALLENGE_ID": "my_challenge",
    "DECEPTIONS_FAIL_CLOSED": True,
})
```

```bash
# Via environment variables
export DECEPTIONS_ENABLED=true
export DECEPTIONS_INSTANCES_DIR=/path/to/instances
export DECEPTIONS_CHALLENGE_ID=my_challenge
```

## CLI Commands

### Validate Registry

```bash
python -m deception_runtime.cli validate \
  --instances-dir deceptions/instances/generated \
  --schema-path deceptions/schemas/deception.schema.json

# Output:
# ✓ Registry loaded successfully
#   Total instances: 580
# 
# Statistics:
#   Total instances: 580
#   Total routes: 3
# 
# By channel:
#   dom: 348
#   hybrid: 116
#   pixel: 116
```

### List Instances

```bash
python -m deception_runtime.cli list \
  --instances-dir deceptions/instances/generated \
  --limit 10

# Output:
# Instances in deceptions/instances/generated:
#   Showing 10 of 580 total
# 
#   dom_a11y_authoritative_hint_000
#     Channel: dom.a11y → /
#     Primitive: dom_a11y_authoritative_hint
```

## API Reference

### DeceptionRuntime

Flask extension that loads the registry and sets up request hooks.

```python
from deception_runtime import DeceptionRuntime

rt = DeceptionRuntime()
rt.init_app(app)
```

### DeceptionContext

Request-scoped context available via `flask.g.deception_ctx`:

```python
from flask import g

@app.route("/")
def index():
    ctx = g.deception_ctx

    print(f"Enabled: {ctx.enabled}")
    print(f"Instance ID: {ctx.instance_id}")
    print(f"Student ID: {ctx.student_id}")
    print(f"Request ID: {ctx.request_id}")
```

**Attributes:**

- `enabled` (bool): Whether deceptions are enabled for this request
- `challenge_id` (str): Challenge identifier
- `instance_id` (str | None): Active deception instance ID
- `student_id` (str | None): Student identifier (if provided)
- `request_id` (str): Unique UUID4 for this request

### DeceptionInstance

Loaded instance with indexed access to key fields:

```python
from deception_runtime import get_active_instance

instance = get_active_instance()

if instance:
    print(instance.instance_id)     # "dom_a11y_authoritative_hint_000"
    print(instance.primitive_id)    # "dom_a11y_authoritative_hint"
    print(instance.channel)         # "dom"
    print(instance.surface)         # "a11y"
    print(instance.payload_text)    # Resolved payload content
    print(instance.route)           # "/login" (if specified)
    print(instance.placement)       # Dict with selector, attribute, etc.
    print(instance.honeytoken)      # Dict or None
    print(instance.raw)             # Full raw YAML data
```

### Helper Functions

```python
from deception_runtime import (
    get_active_instance,
    get_runtime,
    is_deceptions_enabled,
)

# Get active instance (returns None if disabled or not found)
instance = get_active_instance()

# Get runtime extension
runtime = get_runtime()
registry = runtime.registry
config = runtime.config

# Check if enabled for current request
if is_deceptions_enabled():
    # Apply deceptions
    pass
```

## Health Endpoint

The runtime automatically registers a health check endpoint:

```bash
GET /__deception__/health
```

**Response:**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "enabled": true,
  "challenge_id": "example_challenge",
  "registry_size": 580,
  "config": {
    "instances_dir": "deceptions/instances/generated",
    "fail_closed": true,
    "instance_header": "X-Instance-Id",
    "instance_query": "instance"
  }
}
```

## Architecture

```bash
deception_runtime/
├── __init__.py          # Package exports
├── context.py           # DeceptionContext dataclass
├── config.py            # Configuration management
├── registry.py          # Instance loading and indexing
├── extension.py         # Flask extension
├── runtime.py           # Helper functions
├── logging.py           # Structured logging
├── events.py            # Telemetry event creation/validation
├── sinks.py             # Telemetry storage backends
├── telemetry.py         # Telemetry coordinator
├── honeytokens.py       # Honeytoken parsing/matching
├── trap_catalog.py      # Endpoint trap catalog + classifier
├── trap_pages.py        # Endpoint trap rendering + telemetry helpers
├── blueprints.py        # Flask blueprints (honeytoken endpoints)
├── cli.py               # CLI commands (registry)
└── cli_telemetry.py     # CLI commands (telemetry)
```

### Request Flow

1. **Startup**: `DeceptionRuntime.init_app()` loads registry from disk
2. **Before Request**: Extension reads `X-Instance-Id` header or `?instance=` query param
3. **Context Population**: Creates `g.deception_ctx` with instance details
4. **Honeytoken Check**: Passive detection for URL/param/header/cookie honeytokens
5. **Endpoint Trap Branch (optional)**: Honeytoken/decoy endpoints classify path and render bounded endpoint trap page
6. **Telemetry**: Emits `request_start`, `instance_selected`, and trap-specific events when applicable
7. **Route Handler**: Access via `get_active_instance()` or `g.deception_ctx`
8. **Response**: Emits `request_end` event with status code
9. **Exception Handling**: Emits `request_end` with status 500 on errors

## Telemetry

Track student interactions with deceptions using structured events.

### Telemetry Configuration

| Config Key | Env Var | Default | Description |
|------------|---------|---------|-------------|
| `DECEPTIONS_TELEMETRY_ENABLED` | `DECEPTIONS_TELEMETRY_ENABLED` | `false` | Enable telemetry |
| `DECEPTIONS_TELEMETRY_SINK` | `DECEPTIONS_TELEMETRY_SINK` | `jsonl` | Storage backend (`jsonl` or `sqlite`) |
| `DECEPTIONS_TELEMETRY_PATH` | `DECEPTIONS_TELEMETRY_PATH` | `telemetry.jsonl` | Path to telemetry file/database |
| `DECEPTIONS_TELEMETRY_FSYNC` | `DECEPTIONS_TELEMETRY_FSYNC` | `false` | Force fsync after writes (JSONL only) |
| `DECEPTIONS_TELEMETRY_SAMPLE_RATE` | `DECEPTIONS_TELEMETRY_SAMPLE_RATE` | `1.0` | Sampling rate (0.0-1.0) |

### Event Types

- `request_start`: Request begins processing
- `request_end`: Request completes (includes `status_code`)
- `instance_selected`: Deception instance activated
- `honeytoken_hit`: Honeytoken accessed (includes `token_type`)
- `deception_rendered`: Deception rendered in response (future)
- `deception_interacted`: Student interacted with deception (future)
- `endpoint_trap_viewed` / `endpoint_trap_step` / `endpoint_trap_action` / `endpoint_trap_terminal`: Endpoint trap rendering and bounded interactions

### Event Format

```json
{
  "timestamp": "2026-02-04T10:30:15.123456Z",
  "event_type": "request_start",
  "request_id": "a1b2c3d4-...",
  "challenge_id": "example_challenge",
  "route": "/login",
  "method": "GET",
  "instance_id": "dom_a11y_authoritative_hint_000",
  "student_id": "student123",
  "status_code": 200,
  "user_agent": "Mozilla/5.0...",
  "remote_addr": "127.0.0.1",
  "extra": {
    "custom_field": "value"
  }
}
```

### Example Setup

```python
app.config.update({
    "DECEPTIONS_ENABLED": True,
    "DECEPTIONS_TELEMETRY_ENABLED": True,
    "DECEPTIONS_TELEMETRY_SINK": "jsonl",
    "DECEPTIONS_TELEMETRY_PATH": "logs/telemetry.jsonl",
    "DECEPTIONS_TELEMETRY_SAMPLE_RATE": 1.0,  # 100% sampling
})
```

### CLI Tools

**Validate Events:**

```bash
python -m deception_runtime.cli_telemetry validate-events logs/telemetry.jsonl
```

**Statistics:**

```bash
python -m deception_runtime.cli_telemetry stats logs/telemetry.jsonl

# Output:
# Event Statistics:
#   Total events: 1234
# 
# By event type:
#   request_start: 400
#   request_end: 400
#   instance_selected: 234
#   honeytoken_hit: 15
# 
# By challenge: ...
```

**Query Events:**

```bash
# Filter by event type
python -m deception_runtime.cli_telemetry query logs/telemetry.jsonl \
  --event-type honeytoken_hit

# Filter by instance
python -m deception_runtime.cli_telemetry query logs/telemetry.jsonl \
  --instance-id dom_a11y_authoritative_hint_000

# Filter by student
python -m deception_runtime.cli_telemetry query logs/telemetry.jsonl \
  --student-id student123
```

## Honeytokens

Detect when students access honeytokens embedded in deceptions.

### Honeytoken Configuration

| Config Key | Env Var | Default | Description |
|------------|---------|---------|-------------|
| `DECEPTIONS_HONEYTOKENS_ENABLED` | `DECEPTIONS_HONEYTOKENS_ENABLED` | `false` | Enable honeytoken detection |
| `DECEPTIONS_HONEYTOKEN_RESPONSE_MODE` | `DECEPTIONS_HONEYTOKEN_RESPONSE_MODE` | `200` | Response mode (`200` or `404`) |
| `DECEPTIONS_HONEYTOKEN_PARAM` | `DECEPTIONS_HONEYTOKEN_PARAM` | `ht` | Query param name |
| `DECEPTIONS_HONEYTOKEN_HEADER` | `DECEPTIONS_HONEYTOKEN_HEADER` | `X-Honeytoken` | Header name |
| `DECEPTIONS_HONEYTOKEN_COOKIE` | `DECEPTIONS_HONEYTOKEN_COOKIE` | `ht` | Cookie name |
| `DECEPTIONS_HONEYTOKEN_VALUE_PREFIX` | `DECEPTIONS_HONEYTOKEN_VALUE_PREFIX` | `` | Value prefix for param/header/cookie |
| `DECEPTIONS_PROTECTED_ROUTES` | `DECEPTIONS_PROTECTED_ROUTES` | `` | Comma-separated routes (no active endpoints) |

### Detection Modes

**Active (URL endpoints):**

- Registers Flask routes for honeytoken URLs
- Returns placeholder HTML/404 by default
- If endpoint traps are enabled, renders endpoint-specific trap pages instead of generic placeholder HTML
- Emits `honeytoken_hit` event

**Passive (monitoring):**

- Monitors query params, headers, cookies on all requests
- Falls back when active registration fails (route collisions)
- Always active alongside URL detection

### Endpoint Trap Pages

Optional endpoint trap pages are disabled by default and additive only.

- No behavior change when `DECEPTIONS_ENDPOINT_TRAPS_ENABLED=false`
- No override of real Flask routes
- Bounded deterministic flow (`step` query param), no server-side session state
- Fake-goal terminal is optional and separate from dynamic fake-goal routes

Supported trap types:

- `admin_console`
- `debug_service`
- `system_dashboard`
- `api_backup`
- `hidden_index`
- `opaque_internal`

Classification precedence:

1. Explicit map file (`DECEPTIONS_ENDPOINT_TRAP_MAP_FILE`)
2. Exact catalog path match
3. Catalog pattern match
4. Fallback `hidden_index`

Example endpoint mapping:

- `/console -> admin_console`
- `/debug/service -> debug_service`
- `/system/dashboard -> system_dashboard`
- `/45dfddb2 -> opaque_internal`
- `/dashboard -> admin_console`
- `/data -> api_backup`
- `/panel/api_v1/backup -> api_backup`
- `/hidden -> hidden_index`

### Honeytoken Example Setup

```python
app.config.update({
    "DECEPTIONS_ENABLED": True,
    "DECEPTIONS_HONEYTOKENS_ENABLED": True,
    "DECEPTIONS_HONEYTOKEN_RESPONSE_MODE": "200",
    "DECEPTIONS_HONEYTOKEN_PARAM": "token",
    "DECEPTIONS_HONEYTOKEN_VALUE_PREFIX": "HT_",
    "DECEPTIONS_PROTECTED_ROUTES": "/admin,/api",  # No active endpoints
})
```

### Honeytoken Hit Events

```json
{
  "event_type": "honeytoken_hit",
  "instance_id": "honeytoken_url_001",
  "student_id": "student123",
  "extra": {
    "token_type": "url",
    "token_id": "studentless::honeytoken_url_001",
    "detected_via": "active"
  }
}
```

### Stats Endpoint

Check honeytoken statistics:

```bash
curl http://localhost:5000/__deception__/telemetry_stats

# Output:
# {
#   "total_events": 1234,
#   "event_types": {
#     "request_start": 400,
#     "honeytoken_hit": 15
#   }
# }
```

## Extension Points (Future)

The following features are designed for but not yet implemented:

- **HTML mutation**: Inject DOM-based deceptions into responses
- **Pixel overlays**: Apply visual deceptions via CSS/canvas

These will be added in future tasks while maintaining backward compatibility.

## Error Handling

### Fail Closed (default)

```python
app.config["DECEPTIONS_FAIL_CLOSED"] = True
```

Returns `400 Bad Request` if an invalid `instance_id` is provided:

```bash
$ curl -H "X-Instance-Id: invalid_id" http://localhost:5000/
HTTP/1.1 400 Bad Request
Invalid deception instance: invalid_id
```

### Fail Open

```python
app.config["DECEPTIONS_FAIL_CLOSED"] = False
```

Logs a warning but continues processing (deceptions disabled for request).

## Logging

The runtime uses structured logging with context fields:

```bash
2026-02-04 10:30:15 [INFO] deception_runtime.extension: Initializing DeceptionRuntime | enabled=True challenge_id=example_challenge instances_dir=deceptions/instances/generated
2026-02-04 10:30:15 [INFO] deception_runtime.registry: Loading instances | instances_dir=deceptions/instances/generated file_count=580
2026-02-04 10:30:16 [INFO] deception_runtime.registry: Registry loaded | loaded=580 failed=0 total_instances=580 routes=3
2026-02-04 10:30:20 [DEBUG] deception_runtime.extension: Deception context activated | instance_id=dom_a11y_authoritative_hint_000 student_id=student123 request_id=a1b2c3d4...
```

## Testing

See [examples/flask_app_minimal.py](examples/flask_app_minimal.py) for a complete minimal example.

### Unit Tests (Future)

```bash
# Run tests
pytest tests/

# Test coverage
pytest --cov=deception_runtime tests/
```

## Dependencies

**Required:**

- `flask` (any recent version)
- `pyyaml`

**Optional:**

- `jsonschema` (for schema validation)
- `pytest` (for testing)

## License

Part of the agent-lsd research project.

## Troubleshooting

### "ImportError: deception_runtime requires PyYAML"

Install PyYAML:

```bash
pip install pyyaml
```

### "RuntimeError: Failed to load deception registry"

Check that:

1. `DECEPTIONS_INSTANCES_DIR` points to a valid directory
2. Directory contains `*.resolved.yaml` files
3. YAML files are valid and contain required fields

Use CLI to debug:

```bash
python -m deception_runtime.cli validate --instances-dir path/to/instances
```

### Health endpoint returns 0 instances

Ensure:

1. `DECEPTIONS_ENABLED=true`
2. Registry directory exists and contains files
3. Check logs for loading errors

### Instance not activating

Verify:

1. Header/query parameter name matches config
2. Instance ID exists in registry (use `cli list`)
3. Request reaches Flask app (check server logs)

Test manually:

```bash
# List available instances
python -m deception_runtime.cli list --limit 5

# Test with curl
curl -v -H "X-Instance-Id: <instance_id>" http://localhost:5000/
```
