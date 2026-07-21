# Relay engine

The headless engine that `/relay` drives. `/autopilot` does not use this; it runs in-session.

## Pieces

| File | Role |
|------|------|
| `supervisor.py` | The loop. Idles on `<state>/baton.json`; relaunches fresh legs until the sidecar says COMPLETE or BLOCKED; chimes; back to idle. Reads only JSON, never Markdown. |
| `leg-contract.md` | The prompt every leg receives (with `{{PLAN_PATH}}` etc. substituted). One phase per leg, empirical verify, save state, pathspec commit, BLOCKED-not-guess. |

## Layout it expects

```
<project>/
  scripts/relay/supervisor.py      <- this engine
  scripts/relay/leg-contract.md
  state/relay/                     <- baton.json, run log, consumed batons, per-leg black-box logs
<plan>.relay.json                  <- sidecar written next to whatever plan is being relayed
```

Override any path with environment variables (see the docstring at the top of `supervisor.py`):

- `RELAY_PROJECT_DIR` — base project dir (default: two levels up from `supervisor.py`)
- `RELAY_ADD_DIR` — the `--add-dir` write root handed to each leg (default: the parent of the project dir)
- `RELAY_STATE_DIR` — where `baton.json` and logs live (default: `<project>/state/relay`)
- `RELAY_LEG_MODEL` — the model every leg is pinned to (default: `opus`)

## Start it

```bash
python scripts/relay/supervisor.py
```

It prints `SUPERVISOR START ... READY` and idles. Auto-start it on folder open with a VS Code task if you like:

```jsonc
// .vscode/tasks.json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "relay-supervisor",
      "type": "shell",
      "command": "python",
      "args": ["scripts/relay/supervisor.py"],
      "isBackground": true,
      "runOptions": { "runOn": "folderOpen" },
      "presentation": { "panel": "dedicated" }
    }
  ]
}
```

(VS Code prompts once to allow automatic tasks. Reload the window to activate.)

## Start a relay by hand (the `/relay` skill does this for you)

```powershell
$baton = @{ plan = "<path/to/your/plan.md>"; leg_cap = 8 } | ConvertTo-Json
[System.IO.File]::WriteAllText("<state>/relay/baton.json", $baton)   # no-BOM writer
```

Use a no-BOM writer. A UTF-8 BOM makes Python's `json.load` reject the file. The supervisor reads BOM-tolerantly on its side; write BOM-free on yours.

## Semantics worth knowing

- **BLOCKED** = a leg hit something only a human can clear (escalation gate, missing tool, undecided fork). Chime and stop. Fix it, re-drop a baton: the sidecar flips back to `IN_PROGRESS` and the relay retries from the plan's current state.
- **COMPLETE at pickup** = no-op; reset or delete the sidecar to re-run a finished plan.
- **Stopping mid-relay** = kill the supervisor process (Ctrl+C in its panel). A leg killed mid-write can leave a half-finished phase; review the plan file before restarting.
- **Leg detail** = the panel is a one-line ticker. Each leg's final output lands in `<state>/relay/leg-N-*.log`; the leg's full transcript persists as a normal Claude Code session, resumable with `claude --resume <id>`.
- **Watcher (in-session reporting)** = the supervisor tees every log line to `<state>/relay/supervisor.run.log` (truncated fresh per session). An open session can arm a monitor polling that file for `BATON|LEG|RELAY COMPLETE|RELAY BLOCKED|STALL|FATAL` and be woken per event. Arm it BEFORE dropping the baton, and baseline it to the current line count so an earlier run's `COMPLETE` in the same file cannot false-trigger it. When starting the supervisor detached, redirect stdout to some OTHER file, never to `supervisor.run.log`, or lines double.
- **Model discipline** = every leg is launched with an explicit `--model`, never inheriting a session model.
