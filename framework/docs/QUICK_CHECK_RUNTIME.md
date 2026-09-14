# Quick Check: Deception Runtime

This is a small checklist to verify that the runtime is working end-to-end:

- honeytokens are registered
- endpoint trap pages render
- dynamic rabbit-hole and fake-goal routes are active
- telemetry events are written

## Start the app

From the repo root:

```bash
: > verification/telemetry.jsonl # clear telemetry log
python 01_simple_login/src/app.py
```

Keep this terminal open.

## Basic health checks

In a second terminal, check the runtime health and config endpoints:

```bash
curl -s http://localhost:5000/__deception__/health | jq .
curl -s http://localhost:5000/__deception__/dynamic_stats | jq .
curl -s http://localhost:5000/__deception__/honeytokens | jq .
```

What to look for:

- `health.status` is `ok`
- `dynamic_stats.route_style` is `plausible`
- `honeytokens.paths` contains real-looking paths

## Hit a honeytoken endpoint

```bash
HT_PATH=$(curl -s http://localhost:5000/__deception__/honeytokens | jq -r '.paths[0]')
echo "Using honeytoken: $HT_PATH"
curl -s "http://localhost:5000${HT_PATH}"
```

You should see an HTML page that looks like an internal endpoint, not a plain placeholder.

## Walk trap steps

```bash
curl -s "http://localhost:5000${HT_PATH}" > /tmp/trap_page_1.html
NEXT_PATH=$(grep -o 'href="[^"]*"' /tmp/trap_page_1.html | head -n1 | sed 's/href="//; s/"$//')
echo "Next trap path: $NEXT_PATH"
curl -s "http://localhost:5000${NEXT_PATH}" > /tmp/trap_page_2.html
cat /tmp/trap_page_2.html
```

The content should progress through the flow and stop at a bounded terminal state.  
The links use opaque state tokens, so URLs do not expose `step=1`, `step=2`, etc.

## Hit dynamic rabbit-hole and fake-goal sample routes

```bash
RABBIT=$(curl -s http://localhost:5000/__deception__/dynamic_stats | jq -r '.rabbit_hole_route_samples[0]')
GOAL=$(curl -s http://localhost:5000/__deception__/dynamic_stats | jq -r '.fake_goal_route_samples[0]')

echo "Rabbit sample: $RABBIT"
echo "Goal sample:   $GOAL"

curl -s "http://localhost:5000${RABBIT}"
curl -s "http://localhost:5000${GOAL}"
```

## Check telemetry output

```bash
cat verification/telemetry.jsonl
```

You should see events like:

- `honeytoken_hit`
- `endpoint_trap_viewed`, `endpoint_trap_step`, `endpoint_trap_action`, `endpoint_trap_terminal`
- `rabbit_hole_entered`, `rabbit_hole_hop`, `rabbit_hole_terminal`
- `fake_goal_viewed` (and related fake-goal events)

If you prefer live monitoring while testing:

```bash
tail -f verification/telemetry.jsonl
```
