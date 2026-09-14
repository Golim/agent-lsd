# Deception Verification System

Automated verification tools for DOM and pixel-based deception instances using Playwright.

## Overview

The verification system validates that:

- **DOM deceptions** are detectable in HTML, visible text, or accessibility tree
- **Pixel deceptions** cause measurable visual changes
- **Hidden DOM deceptions** don't leak visually
- **Pixel deceptions** don't leak to DOM

## Components

```bash
tools/
├── verify_dom.py              # DOM verifier CLI
├── verify_pixel.py            # Pixel verifier CLI
├── verification_report.py     # Merge and summarize results
├── verifier_lib.py           # Shared utilities
└── verification_schema.json  # Result schema
```

## Requirements

Install dependencies:

```bash
pip install playwright pyyaml jsonschema pillow numpy
playwright install chromium
```

## Usage

### Prerequisites

1. **Start the web challenge server** at `http://127.0.0.1:5000`
2. **Implement instance activation** via:
   - Header: `X-Instance-Id: <instance_id>`
   - Query param: `?instance=<instance_id>`
3. **Generate instances** using `tools/generate_instances.py`

### DOM Verification

Verifies DOM-based deceptions are detectable:

```bash
# Basic usage
python tools/verify_dom.py

# Custom configuration
python tools/verify_dom.py \
  --base-url http://localhost:5000 \
  --instances-dir deceptions/instances/generated \
  --routes "/,/login,/help" \
  --instance-mode header \
  --workers 4 \
  --output verification/dom_results.jsonl
```

**Options:**

- `--base-url`: Base URL (default: `http://127.0.0.1:5000`)
- `--instances-dir`: Instance directory (default: `deceptions/instances/generated`)
- `--routes`: Comma-separated default routes (default: `/,/login,/help`)
- `--instance-mode`: `header`, `query`, or `both` (default: `header`)
- `--timeout-ms`: Navigation timeout (default: `30000`)
- `--wait-extra-ms`: Extra wait after network idle (default: `250`)
- `--workers`: Concurrent workers (default: `4`)
- `--limit`: Limit instances to test
- `--output`: Output JSONL (default: `verification/dom_results.jsonl`)
- `--soft-fail`: Exit 0 even on failures

**DOM Verification Logic:**

For `dom.*` channels:

- ✅ **Pass**: Payload found in HTML, visible text, or a11y tree
- ❌ **Fail**: Payload not detected or selector missing

For `pixel.*` channels:

- ✅ **Pass**: Payload NOT in DOM (no leakage)
- ❌ **Fail**: Payload found in DOM (leakage detected)

### Pixel Verification

Verifies pixel-based deceptions cause visual changes:

```bash
# Basic usage
python tools/verify_pixel.py

# With screenshot saving
python tools/verify_pixel.py \
  --base-url http://localhost:5000 \
  --threshold 2.0 \
  --threshold-small 0.5 \
  --element-threshold 1.0 \
  --workers 2 \
  --screenshots-dir verification/screenshots \
  --output verification/pixel_results.jsonl
```

**Options:**

- `--base-url`: Base URL (default: `http://127.0.0.1:5000`)
- `--instances-dir`: Instance directory
- `--routes`: Default routes
- `--instance-mode`: Instance activation mode
- `--timeout-ms`: Navigation timeout
- `--wait-extra-ms`: Extra wait time
- `--threshold`: Fullpage MAD threshold for pixel deceptions (default: `2.0`)
- `--threshold-small`: Threshold for hidden DOM leakage (default: `0.5`)
- `--element-threshold`: Element-specific threshold (default: `1.0`)
- `--workers`: Concurrent workers (default: `4`)
- `--limit`: Limit instances
- `--output`: Output JSONL
- `--screenshots-dir`: Save screenshots to directory
- `--soft-fail`: Exit 0 on failures
- `--strict`: Fail hard on visual leakage

**Pixel Verification Logic:**

Computes Mean Absolute Difference (MAD) between baseline and deception screenshots.

For `pixel.*` channels:

- ✅ **Pass**: MAD > threshold (visual changes detected)
- ❌ **Fail**: MAD ≤ threshold (no visual changes)

For `dom.hidden`, `dom.a11y`, `dom.metadata`:

- ✅ **Pass**: MAD ≤ threshold_small (no visual leakage)
- ❌ **Fail**: MAD > threshold_small (unexpected visual changes)

### Merge and Report

Combines DOM and pixel results with summary statistics:

```bash
python tools/verification_report.py \
  --dom-results verification/dom_results.jsonl \
  --pixel-results verification/pixel_results.jsonl \
  --output verification/merged.jsonl \
  --summary-json verification/summary.json
```

**Output:**

- Merged JSONL with combined results
- Console summary with pass/fail counts
- Optional JSON summary file

## Output Format

### DOM Results

```json
{
  "instance_id": "dom_a11y_authoritative_hint_000",
  "primitive_id": "dom_a11y_authoritative_hint",
  "route": "/",
  "channel": "dom.a11y",
  "surface": "aria_label",
  "dom_present": true,
  "dom_leakage": false,
  "selector_missing": false,
  "html_present": false,
  "visible_present": false,
  "a11y_present": true,
  "human_visibility": "human_subtle",
  "payload_length": 42,
  "errors": [],
  "pass": true
}
```

### Pixel Results

```json
{
  "instance_id": "pixel_canvas_goal_hijack_hint_005",
  "primitive_id": "pixel_canvas_goal_hijack_hint",
  "route": "/",
  "channel": "pixel.canvas",
  "surface": "canvas_drawtext",
  "diff_fullpage": 3.45,
  "diff_element": 12.34,
  "pixel_expected": true,
  "pixel_confirmed": true,
  "visual_leakage": false,
  "baseline_saved": true,
  "deception_saved": true,
  "errors": [],
  "pass": true
}
```

### Merged Results

```json
{
  "instance_id": "hybrid_js_generated_goal_hijack_010",
  "primitive_id": "hybrid_js_generated_goal_hijack",
  "route": "/",
  "channel": "hybrid",
  "surface": "js_generated_dom",
  "dom_pass": true,
  "pixel_pass": true,
  "overall_pass": true,
  "errors": []
}
```

## Determinism

The verification system is designed for deterministic, CI-friendly execution:

- **Fixed viewport**: 1280x720
- **Reduced motion**: Animations disabled
- **Network idle**: Waits for network idle + 250ms
- **Locale/timezone**: en-US, America/New_York
- **Headless**: No GUI required

## Example Workflow

```bash
# 1. Generate instances
python tools/generate_instances.py --seed 42 --count 20

# 2. Start web server (in separate terminal)
cd 01_simple_login && python -m flask run --port 8000

# 3. Run DOM verification
python tools/verify_dom.py --limit 10

# 4. Run pixel verification
python tools/verify_pixel.py --limit 10 --screenshots-dir verification/screenshots

# 5. Generate report
python tools/verification_report.py
```

## Concurrency

Both verifiers support concurrent execution:

```bash
# Use 8 workers for faster verification
python tools/verify_dom.py --workers 8
python tools/verify_pixel.py --workers 8
```

Each worker runs in its own browser context for isolation.

## Troubleshooting

TODO: Remove this part before finalizing the docs.

### Navigation Timeouts

Increase timeout if challenges are slow:

```bash
python tools/verify_dom.py --timeout-ms 60000
```

### Visual Changes Not Detected

Lower the threshold:

```bash
python tools/verify_pixel.py --threshold 1.0 --element-threshold 0.5
```

### Selector Not Found

Check that:

1. The web challenge includes the selector
2. The route is correct
3. The instance is properly activated

### Instance Not Activating

Verify header/query param handling:

```bash
# Test with curl
curl -H "X-Instance-Id: dom_a11y_authoritative_hint_000" http://localhost:5000/
curl "http://localhost:5000/?instance=dom_a11y_authoritative_hint_000"
```

## CI Integration

Exit codes:

- `0`: All instances passed (or `--soft-fail` used)
- `1`: One or more instances failed
- `2`: Fatal error (exception)

Example GitHub Actions:

```yaml
- name: Run DOM Verification
  run: python tools/verify_dom.py --workers 4

- name: Run Pixel Verification
  run: python tools/verify_pixel.py --workers 2

- name: Generate Report
  run: python tools/verification_report.py
  if: always()
```

## Performance

Approximate timing (580 instances on 4-core machine):

- **DOM verification**: ~2-3 minutes (with 4 workers)
- **Pixel verification**: ~5-8 minutes (with 4 workers, includes screenshots)
- **Total**: ~10 minutes for full verification suite

## Limitations

- **No OCR**: Cannot verify text rendered as images without DOM representation
- **No external services**: Fully local verification only
- **Simple selector matching**: Uses heuristics for selector validation in DOM verifier
- **Single route per instance**: Tests first applicable route only

## Schema Validation

Results conform to `verification_schema.json`. Validate manually:

```python
import json
import jsonschema
from validate import load_json_schema, load_yaml_instance, validate_instance

schema = load_json_schema("tools/verification_schema.json")

with open("verification/dom_results.jsonl") as f:
    for line in f:
        result = json.loads(line)
        validate_instance(result, schema)  # Raises on invalid
```
