# AgentLSD: Deception Research Framework for Web CTF Challenges

A comprehensive research framework for studying deception mechanisms in web-based Capture The Flag challenges. This project provides tools for generating, deploying, verifying, and analyzing deceptions that can mislead automated agents while remaining solvable for human participants.

## What This Project Does

AgentLSD enables researchers to:

1. **Generate** thousands of deception instances from primitive templates
2. **Deploy** deceptions into Flask-based CTF challenges with minimal code changes
3. **Verify** that deceptions work as intended using automated testing
4. **Track** student interactions through comprehensive telemetry
5. **Detect** when students access honeytokens embedded in deceptions

## Project Structure

```bash
agent-lsd/
├── deceptions/              # Deception definitions and instances
│   ├── primitives/          # Template definitions (DOM, pixel, hybrid)
│   ├── instances/           # Generated concrete instances
│   └── schemas/             # JSON schemas for validation
├── deception_runtime/       # Flask extension package
│   ├── README.md            # Runtime documentation →
│   └── ...
├── tools/                   # Generation and verification tools
│   ├── generate_instances.py
│   ├── verify_dom.py
│   ├── verify_pixel.py
│   └── ...
├── examples/                # Example Flask applications
│   ├── README.md            # Examples and Docker setup →
│   ├── flask_app_minimal.py
│   ├── flask_app_telemetry.py
│   └── docker-compose.yml
├── docs/
│   └── VERIFICATION.md      # Verification system documentation →
├── 01_simple_login/         # Example CTF challenge
├── 06_web_lab_1/            # Example CTF challenge
└── README.md                # This file
```

## Quick Start

### 1. Generate Deception Instances

Generate concrete instances from primitive templates:

```bash
# Generate 20 instances per primitive (default)
python tools/generate_instances.py

# Custom configuration
python tools/generate_instances.py --count 10 --seed 12345

# Avoid collision with real solution routes
python tools/generate_instances.py --real-routes "/login,/submit,/flag"
```

**Output:** `deceptions/instances/generated/` containing `.yaml` and `.resolved.yaml` files.

### 2. Integrate Runtime into Flask Challenge

Add deception support to any Flask app with 3 lines:

```python
from flask import Flask
from deception_runtime import DeceptionRuntime

app = Flask(__name__)
app.config["DECEPTIONS_ENABLED"] = True

# Initialize runtime
DeceptionRuntime().init_app(app)

# Your existing routes work unchanged
```

See [deception_runtime/README.md](deception_runtime/README.md) for complete documentation on the runtime package.

### 3. Verify Deceptions Work

Run automated verification to ensure deceptions are detectable:

```bash
# Start your Flask app first (this may take a few seconds to load instances)
python your_app.py

# Verify DOM-based deceptions
python tools/verify_dom.py --base-url http://localhost:5000

# Verify pixel-based deceptions
python tools/verify_pixel.py --base-url http://localhost:5000
```

See [docs/VERIFICATION.md](docs/VERIFICATION.md) for verification documentation.

### 4. Enable Telemetry and Honeytokens

Track student interactions and detect honeytoken access:

```python
app.config.update({
    "DECEPTIONS_ENABLED": True,
    "DECEPTIONS_TELEMETRY_ENABLED": True,
    "DECEPTIONS_TELEMETRY_SINK": "jsonl",
    "DECEPTIONS_HONEYTOKENS_ENABLED": True,
})
```

Analyze telemetry data:

```bash
# View statistics
python -m deception_runtime.cli_telemetry stats telemetry.jsonl

# Query honeytoken hits
python -m deception_runtime.cli_telemetry query telemetry.jsonl \
  --event-type honeytoken_hit
```

## Components

### Instance Generator

Generates deterministic, validated deception instances from YAML primitives.

**Key Features:**

- Deterministic seeding for reproducible outputs
- Template rendering with randomized parameters
- Schema validation for all instances
- Support for DOM, pixel, and hybrid deceptions

**Usage:**

```bash
python tools/generate_instances.py [OPTIONS]
```

**Options:**

- `--count N`: Generate N instances per primitive (default: 20)
- `--seed SEED`: Global seed for deterministic generation (default: 42)
- `--real-routes ROUTES`: Comma-separated routes to avoid (default: none)
- `--primitives-dir DIR`: Primitive definitions directory
- `--output-dir DIR`: Output directory for instances

**Generators:**

- `fake_route`: Generate decoy routes like `/admin/secret`
- `fake_endpoint`: Generate API endpoints like `/api/v1/secrets`
- `fake_filename`: Generate filenames like `config.bak`
- `paraphrase_set`: Select from predefined phrase sets
- `shuffle_tokens`: Shuffle and join tokens
- `hex_suffix`: Random hex strings

### Flask Runtime Package

A Flask extension that enables automated deception injection with minimal integration effort.

**Key Features:**

- Drop-in integration (2-5 lines of code)
- Request-scoped deception context
- Multiple activation modes (header, query parameter)
- Telemetry event tracking
- Honeytoken detection (active and passive)
- Health and diagnostic endpoints

**Documentation:** See [deception_runtime/README.md](deception_runtime/README.md)

### Verification System

Automated verification tools using Playwright to validate deception behavior.

**DOM Verifier** (`verify_dom.py`):

- Verifies DOM deceptions are detectable in HTML, text, or accessibility tree
- Verifies pixel deceptions do not leak to DOM
- Concurrent verification with configurable workers

**Pixel Verifier** (`verify_pixel.py`):

- Verifies pixel deceptions cause measurable visual changes
- Screenshot comparison with configurable thresholds
- Element-level change detection

**Documentation:** See [docs/VERIFICATION.md](docs/VERIFICATION.md)

### Telemetry and Honeytokens

Comprehensive observability for student interactions with deceptions.

**Telemetry Events:**

- `request_start` / `request_end`: Request lifecycle
- `instance_selected`: Deception instance activated
- `honeytoken_hit`: Honeytoken accessed
- `rabbit_hole_entered` / `rabbit_hole_hop` / `rabbit_hole_terminal`: Dynamic rabbit-hole flow
- `fake_goal_viewed` / `fake_goal_flag_shown` / `fake_goal_success_shown`: Dynamic fake-goal exposure
- `endpoint_trap_viewed` / `endpoint_trap_step` / `endpoint_trap_action` / `endpoint_trap_terminal`: Endpoint trap rendering and bounded interactions

**Storage Backends:**

- JSONL: Line-delimited JSON with optional fsync
- SQLite: Indexed database with query support

**Honeytoken Detection:**

- Active: Registers Flask routes for URL honeytokens
- Passive: Monitors query parameters, headers, cookies

**CLI Tools:**

```bash
# Validate events against schema
python -m deception_runtime.cli_telemetry validate-events FILE

# Compute statistics
python -m deception_runtime.cli_telemetry stats FILE

# Query events
python -m deception_runtime.cli_telemetry query FILE [--event-type TYPE]
```

### Dynamic Deception Families

Two optional runtime families are available when explicitly enabled:

- **Dynamic rabbit holes**: deterministic bounded decoy hop routes using canonical paths
- **Fake goals**: deterministic decoy terminal endpoints with plausible success state
- **Endpoint traps**: deterministic endpoint-specific trap pages for honeytoken/decoy paths

Safety and compatibility model:

- Disabled by default
- Additive only
- No changes to existing DOM/pixel deceptions when disabled
- No changes to existing request flow when disabled
- No real-route override (collisions are skipped or fail-fast based on config)

Dynamic CLI:

```bash
# Inspect one instance plan
python -m deception_runtime.cli_dynamic inspect \
  --instances-dir deceptions/instances/generated \
  --instance-id dom_a11y_authoritative_hint_000

# Generate deterministic plan file for all instances
python -m deception_runtime.cli_dynamic plan \
  --instances-dir deceptions/instances/generated \
  --output dynamic_plans.json

# Validate generated dynamic plans
python -m deception_runtime.cli_dynamic validate \
  --instances-dir deceptions/instances/generated
```

Runtime debug endpoint:

```bash
GET /__deception__/dynamic_stats
```

## Deception Types

### DOM-Based Deceptions

Inject content into the HTML DOM that is visible to automated scrapers but may mislead agents.

**Channels:**

- `dom.html`: Direct HTML injection
- `dom.a11y`: Accessibility tree hints
- `dom.metadata`: Meta tags and structured data

**Example:** Hidden `<div>` with fake admin credentials

### Pixel-Based Deceptions

Visual content rendered as images that do not appear in the DOM.

**Channels:**

- `pixel.background`: CSS background images
- `pixel.canvas`: Canvas-rendered content
- `pixel.svg`: SVG embedded images

**Example:** Background image with fake API endpoint

### Hybrid Deceptions

Combine DOM and pixel techniques for layered deception.

**Example:** CSS pseudo-element with background image containing fake route

## Configuration

The runtime package supports configuration via Flask config or environment variables:

**Core Settings:**

- `DECEPTIONS_ENABLED`: Enable/disable deceptions (default: `false`)
- `DECEPTIONS_INSTANCES_DIR`: Instance files directory
- `DECEPTIONS_CHALLENGE_ID`: Challenge identifier

**Telemetry Settings:**

- `DECEPTIONS_TELEMETRY_ENABLED`: Enable telemetry (default: `false`)
- `DECEPTIONS_TELEMETRY_SINK`: Storage backend (`jsonl` or `sqlite`)
- `DECEPTIONS_TELEMETRY_PATH`: File path for telemetry data
- `DECEPTIONS_TELEMETRY_SAMPLE_RATE`: Sampling rate (0.0-1.0)

**Honeytoken Settings:**

- `DECEPTIONS_HONEYTOKENS_ENABLED`: Enable honeytoken detection (default: `false`)
- `DECEPTIONS_HONEYTOKEN_RESPONSE_MODE`: Response mode (`200` or `404`)
- `DECEPTIONS_PROTECTED_ROUTES`: Comma-separated routes to exclude

**Dynamic Route Settings (default: disabled):**

- `DECEPTIONS_DYNAMIC_ENABLED`: Master switch for dynamic route families (`false`)
- `DECEPTIONS_RABBIT_HOLES_ENABLED`: Enable rabbit-hole routes (`false`)
- `DECEPTIONS_FAKE_GOALS_ENABLED`: Enable fake-goal routes (`false`)
- `DECEPTIONS_DYNAMIC_ROUTE_PREFIX`: Namespaced dynamic route prefix (`/_deception`)
- `DECEPTIONS_RABBIT_MAX_DEPTH`: Max rabbit depth (`3`)
- `DECEPTIONS_RABBIT_MAX_BRANCHING`: Max rabbit branching (`1`)
- `DECEPTIONS_FAKE_GOAL_MODE`: Fake-goal mode (`flag|success_message|both`, default `both`)
- `DECEPTIONS_DYNAMIC_ROUTE_STYLE`: Dynamic route style (`namespaced|plausible`, default `namespaced`)
- `DECEPTIONS_DYNAMIC_FAIL_OPEN`: Continue on dynamic route collisions (`true`)
- `DECEPTIONS_DYNAMIC_REGISTER_BLUEPRINT`: Register dynamic routes using blueprint (`true`)

**Endpoint Trap Settings (default: disabled):**

- `DECEPTIONS_ENDPOINT_TRAPS_ENABLED`: Enable endpoint-specific trap pages (`false`)
- `DECEPTIONS_ENDPOINT_TRAPS_INTERACTIVE`: Enable bounded step flow (`false`)
- `DECEPTIONS_ENDPOINT_TRAPS_MAX_STEPS`: Max trap step index (`2`)
- `DECEPTIONS_ENDPOINT_TRAPS_FAKE_GOALS_ENABLED`: Allow endpoint-trap terminal fake goals (`false`)
- `DECEPTIONS_ENDPOINT_TRAPS_RABBIT_HOLES_ENABLED`: Allow rabbit-hole hops to render endpoint traps (`false`)
- `DECEPTIONS_ENDPOINT_TRAP_MAP_FILE`: Optional JSON explicit path-to-trap map (`""`)
- `DECEPTIONS_ENDPOINT_TRAPS_OPAQUE_PATTERNS`: Optional comma-separated regex for opaque routes (`""`)

Endpoint trap mapping examples:

- `/console -> admin_console`
- `/debug/service -> debug_service`
- `/system/dashboard -> system_dashboard`
- `/45dfddb2 -> opaque_internal`
- `/dashboard -> admin_console`
- `/data -> api_backup`
- `/panel/api_v1/backup -> api_backup`
- `/hidden -> hidden_index`

### Dynamic Enablement Examples

Rabbit holes only:

```python
app.config.update({
    "DECEPTIONS_ENABLED": True,
    "DECEPTIONS_DYNAMIC_ENABLED": True,
    "DECEPTIONS_RABBIT_HOLES_ENABLED": True,
    "DECEPTIONS_FAKE_GOALS_ENABLED": False,
})
```

Fake goals only:

```python
app.config.update({
    "DECEPTIONS_ENABLED": True,
    "DECEPTIONS_DYNAMIC_ENABLED": True,
    "DECEPTIONS_RABBIT_HOLES_ENABLED": False,
    "DECEPTIONS_FAKE_GOALS_ENABLED": True,
})
```

Both via environment:

```bash
export DECEPTIONS_ENABLED=true
export DECEPTIONS_DYNAMIC_ENABLED=true
export DECEPTIONS_RABBIT_HOLES_ENABLED=true
export DECEPTIONS_FAKE_GOALS_ENABLED=true
```

See [deception_runtime/README.md](deception_runtime/README.md) for complete configuration reference.

## Installation

### Prerequisites

- Python 3.10 or later
- Flask 2.0 or later
- PyYAML

### Install Runtime Package

```bash
pip install -e .
```

### Install Verification Tools

```bash
pip install playwright pyyaml jsonschema pillow numpy
playwright install chromium
```

### Docker Setup

Run example applications using Docker:

```bash
# Build and start both example apps
cd examples/
docker-compose up --build

# Minimal app available at http://localhost:5000
# Telemetry app available at http://localhost:5001
```

See [examples/README.md](examples/README.md) for detailed Docker documentation.

## Testing

### Runtime Tests

```bash
pytest tests/test_runtime.py -v
pytest tests/test_integration.py -v
pytest tests/test_telemetry.py -v
```

### Verification Tests

Start a Flask app with deceptions enabled, then run verification:

```bash
python examples/flask_app_minimal.py &
python tools/verify_pixel.py --base-url http://localhost:5000
```

## Example Challenges

### 01_simple_login

Basic login challenge demonstrating deception integration.

## Research Use Cases

This framework supports research questions such as:

- How effective are different deception types at misleading LLM agents?
- Can agents distinguish between real and fake routes/credentials?
- Do agents follow honeytokens embedded in deceptions?
- What patterns emerge in agent behavior when encountering deceptions?

## License

Part of the AgentLSD research project.

## Further Documentation

- [Flask Runtime Package](deception_runtime/README.md) - Complete API reference and integration guide
- [Example Applications](examples/README.md) - Flask examples and Docker setup
- [Verification System](docs/VERIFICATION.md) - DOM and pixel verification tools
- [Runtime Quick Check](docs/QUICK_CHECK_RUNTIME.md) - Simple command checklist to validate traps, routes, and telemetry
- [Telemetry Events](deception_runtime/README.md#telemetry) - Event schema and CLI tools
- [Honeytokens](deception_runtime/README.md#honeytokens) - Detection modes and configuration
