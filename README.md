# claude-relay-autopilot

Hands-off, multi-phase plan execution for [Claude Code](https://docs.claude.com/en/docs/claude-code). One engine, two front doors:

- **`/autopilot`** drives one plan file to completion **while you watch**, in your open session, delegating each phase to a fresh subagent.
- **`/relay`** drives one plan file to completion **while you step away**, headless: a small always-on supervisor relaunches fresh CLI sessions ("legs"), one phase per leg, until the plan is done.

Both share one safety gate and one core idea: **a long agent run should not be one tired marathon session that degrades as its context fills. It should be a chain of fresh runners, each reading shared state from disk, doing one bounded chunk, writing state back, and exiting.**

Continuity lives on disk (a Markdown plan file plus a small JSON sidecar), never in a single long-lived context. That is what lets these runs survive context compaction, tab closes, and overnight execution.

---

## Why this exists

Ask Claude Code to execute a big, multi-phase plan in one session and two things eventually go wrong: the context window fills and compacts (reasoning quality drifts), and if the tab or window closes, the run dies. The usual fixes either keep one long session alive (and inherit its degradation) or puppet the UI to spawn new tabs (brittle and easy to break on an editor update).

This project takes the other path. The plan file on disk is the single source of truth. Each unit of work is a **fresh process** that reconstructs everything it needs from that file, does exactly one phase, saves, and exits. Nothing important lives only in a context window, so nothing important is lost when a context window ends.

## The two front doors

| | `/autopilot` | `/relay` |
|---|---|---|
| You are | present, watching live | stepping away |
| Substrate | in-session subagents | external supervisor + headless `claude -p` legs |
| Survives tab close | no (in-session) | yes (runs on disk) |
| Reporting | live in your session | chime + optional in-session watcher wake |
| Same plan-quality bar | yes | yes |
| Same precondition gate | yes (source of truth) | yes (by reference) |

Pick by situation, not by task: watching live, use autopilot; leaving the machine, use relay. The plan file and the gate are identical either way.

## How it works (short version)

1. You author a **delivery-grade plan file**: atomic phases, at least one falsifiable verification criterion, a declared File Territory (the only paths work may touch), and any irreversible/outward step marked as an **escalation gate** rather than an auto-run phase.
2. A **precondition gate** refuses to run anything that is still discovery-grade (open questions, undecided forks, vague phases, human-only verification). This is the single most important safety property: the loop only drives plans that a fresh agent could execute cold.
3. Execution runs **one phase per fresh runner**. The runner reads the plan, executes the current phase, **verifies empirically** (exit code, file diff, command output, never self-reported prose), saves state back to the plan file, commits a checkpoint, and ends.
4. The next runner is a clean context that re-reads the plan and continues. Repeat until every phase is checked and every criterion passes, or the run stops at an escalation gate.

Full architecture in [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md). The key design decisions and why they were made are in [docs/DECISIONS.md](docs/DECISIONS.md). Where this sits relative to prior art is in [docs/PRIOR-ART.md](docs/PRIOR-ART.md).

## Install

These are Claude Code skills plus a small Python engine.

1. **Skills.** Copy `skills/relay/` and `skills/autopilot/` into your Claude Code skills directory (`~/.claude/skills/`). Reload the Claude Code window once so the commands register. Both skills reference paths in angle brackets like `<your-plans-dir>/<slug>.md`. Point those at wherever you keep plan files.
2. **Engine (relay only).** `/autopilot` needs no engine; it runs in-session. `/relay` needs the supervisor:
   - Copy `engine/` somewhere in your project (for example a `scripts/relay/` folder).
   - Start it in a terminal: `python engine/supervisor.py`. It prints `READY` and idles, waiting for a baton file.
   - Optionally auto-start it on folder open with a VS Code task (`runOn: folderOpen`).
3. **Requirements.** Claude Code CLI on your PATH, Python 3.8+. The supervisor as written targets Windows for its chime and process-priority calls; both degrade gracefully on other platforms (see the notes in `engine/supervisor.py`).

## Quickstart: a relay

```bash
# 1. Start the supervisor in a dedicated terminal
python engine/supervisor.py

# 2. In Claude Code, from your project
/relay <your-theme>/<your-slug>
```

The skill runs the precondition gate, confirms the supervisor is up, drops a **baton** (a small JSON file naming your plan), and goes quiet. The supervisor relaunches fresh legs until the plan reaches `COMPLETE` or `BLOCKED`, then chimes. If your session is still open, it wakes and reports.

To start a relay by hand without the skill:

```powershell
$baton = @{ plan = "<path/to/your/plan.md>"; leg_cap = 8 } | ConvertTo-Json
[System.IO.File]::WriteAllText("<path/to>/state/relay/baton.json", $baton)
```

## Safety model

- **The gate, not the permission system, is the safety.** These runs never rely on a permission mode that waves risky actions through. Every irreversible or outward-facing step (push, publish, send, delete, deploy, sign) is an **escalation gate**: the run executes up to it, stops, and hands it to you. Autopilot builds; you commit to the world.
- **File Territory is a wall.** Legs treat the plan's declared File Territory as their only write surface. A plan with vague or missing territory is refused.
- **Empirical verification only.** A phase is never marked done on an agent's say-so. It is proven with evidence a process cannot fabricate: a real exit code, a file diff, test output.
- **Bounded.** A leg cap and a no-progress detector stop runaways. Consider adding a token/cost ceiling for long unattended runs.

## Status and honesty

This is a working personal setup, published as a reference implementation and a design writeup. It has been proven end to end on real multi-phase plans. The known rough edge, called out plainly: the failure rails (a leg that hangs, exits nonzero, or exits clean having done nothing) deserve more deliberate exercising than the happy path has received. See [docs/DECISIONS.md](docs/DECISIONS.md) for the full picture.

## Prior art

This pattern is a recombination of well-established ideas, not a from-scratch invention, and it is stronger for it. It owes an obvious debt to Geoffrey Huntley's [Ralph](https://ghuntley.com/ralph/) loop, Anthropic's autonomous-coding quickstart, the Erlang/OTP supervisor tree, and the blackboard architecture. [docs/PRIOR-ART.md](docs/PRIOR-ART.md) credits each and states exactly where this differs.

## License

MIT. See [LICENSE](LICENSE).
