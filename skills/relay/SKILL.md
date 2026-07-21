---
name: relay
description: Start a supervisor relay -- drive ONE delivery-grade plan file to completion HEADLESS while you step away. Fresh `claude -p` legs (one phase per leg, full rules + MCP), state on disk, completion wakes your open session. Fires when you say "relay <slug>", "start a supervisor relay", "run this plan headless", "drive this while I'm away". User-invoked only, NEVER auto-fired. Attended-and-watching runs use /autopilot instead.
disable-model-invocation: true
argument-hint: "<theme>/<slug> of the delivery-grade plan file to relay"
---

# /relay -- supervisor relay front door

Hand ONE delivery-grade plan file to the supervisor relay: an always-open terminal
loop that relaunches fresh headless `claude -p` legs (model-pinned, one phase per
leg, full rules chain, MCP via deferred loading) until the plan is COMPLETE or
BLOCKED. Continuity lives ONLY on disk (plan file + sidecar). The invoking session
becomes the reporting surface: it arms a watcher, goes quiet, and gets woken by the
harness on progress and completion.

Architecture, vocabulary (baton / supervisor / relay / leg / watcher), and the design
rationale live in the project docs (`docs/HOW-IT-WORKS.md`, `docs/DECISIONS.md`).
Engine internals: `engine/README.md`.

## Relay vs autopilot (siblings, same gate, different substrate)

- **/autopilot** -- you are present, watching live in-session; the session drives via subagents.
- **/relay** -- you are stepping away; headless legs grind, the session only reports.
- Same plan-file quality bar for both. MCP-heavy phases are fine in either (legs reach the full MCP roster via deferred loading).

## Precondition gate (run BEFORE anything -- by reference, do not duplicate)

Run the EXACT gate from the `autopilot` skill ("Precondition Gate", checks 1-9):
plan exists; delivery-grade not discovery-grade; at least one falsifiable
Verification Criterion; atomic Status Board; every phase machine-verifiable;
irreversible/outward actions flagged as escalation gates, not phases; permission
posture; one upfront greenlight (the invocation); drift check against reality.
Refuse with autopilot's refusal messages on any failure.

Two relay-specific additions:
1. **File Territory is load-bearing:** legs treat it as their ONLY write surface.
   If the plan's territory is vague or missing, refuse until it is declared.
2. **Mid-plan human-only steps:** any phase needing your eyes/hands must be
   marked an escalation gate -- the relay will BLOCK there by design (chime +
   stop), which is correct behavior, but tell the user up front where it will stop.

## Engage (steps, in order)

1. **Gate** (above). On pass, announce the plan, leg cap, and any gates it will
   stop at.
2. **Confirm the supervisor is running:** the supervisor tees every line to
   `<state>/relay/supervisor.run.log` (truncated fresh per supervisor session) --
   recent lines there, or the process itself (`python .../engine/supervisor.py`),
   mean it is up. If not running, start it (a dedicated terminal, or a
   `runOn: folderOpen` VS Code task). When starting detached, redirect stdout to a
   DIFFERENT file (e.g. `supervisor.stdout.log`, never `supervisor.run.log`, lines
   would double). Do not proceed until READY/IDLE is observed.
3. **Arm the watcher** (this is what makes THIS session report by itself; armed
   BEFORE the baton so its baseline predates every transition -- otherwise the
   first lines, or a very fast relay's terminal line, land in history it ignores).
   A background monitor polling `<state>/relay/supervisor.run.log`. HISTORY-SAFE:
   baseline to the current line count at arm time and judge only NEW lines, so an
   earlier relay's COMPLETE in the same file cannot false-trigger it:
   ```bash
   log="<state>/relay/supervisor.run.log"
   seen=$(wc -l < "$log" 2>/dev/null | tr -d ' '); seen=${seen:-0}
   while true; do
     if [ -f "$log" ]; then
       total=$(wc -l < "$log" | tr -d ' ')
       if [ "$total" -gt "$seen" ]; then
         new=$(tail -n +"$((seen+1))" "$log")
         echo "$new" | grep -E 'BATON|LEG|RELAY COMPLETE|RELAY BLOCKED|STALL|FATAL|RESUME'
         echo "$new" | grep -qE 'RELAY COMPLETE|RELAY BLOCKED|STALL|FATAL|FAILED|TIMEOUT|NO-PROGRESS' && exit 0
         seen=$total
       fi
     fi
     sleep 5
   done
   ```
   (Monitor timeout: generous -- real legs are long; use a persistent monitor for overnight.)
4. **Drop the baton** (no-BOM writer):
   ```powershell
   $b = @{ plan = "<path/to/your/plan.md>"; leg_cap = 8 } | ConvertTo-Json
   [System.IO.File]::WriteAllText("<state>\relay\baton.json", $b)
   ```
5. **Announce and go quiet:** "Relay engaged on `<slug>`, cap N legs. This session
   will report each leg and announce the end state." Then END THE TURN. Do not
   poll, do not sleep.

## On wake

- **RELAY COMPLETE:** do NOT take the sidecar's word -- re-verify the plan's
  Verification Criteria yourself (run the commands, check the artifacts), then
  report: legs run, per-criterion evidence, leg commits (`git log`), black-box
  logs (`<state>/relay/leg-N-*.log`).
- **RELAY BLOCKED:** surface the `blocked_reason` verbatim + the exact fix
  needed; after it is cleared, re-drop a baton (that IS the retry mechanism).
- **STALL / FAILED / TIMEOUT / NO-PROGRESS:** report plainly with the black-box
  log path. Never rescue by faking state; diagnose before any retry.

## What this does NOT do

Does not run discovery-grade plans (refuses, same as autopilot). Does not touch
plans mid-relay from the reporting session (legs own the plan file while a relay
runs). Does not push, publish, or cross escalation gates -- legs BLOCK there.
Does not let legs inherit the session model (the model is pinned in the engine).
