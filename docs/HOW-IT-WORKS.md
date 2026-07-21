# How it works

This document explains the architecture of the relay (the headless engine) and how autopilot (the in-session sibling) shares its ideas. Read the [README](../README.md) first for the one-paragraph version.

## The core problem

A single long agent session degrades. As its context window fills, it compacts, and the compacted summary is lower fidelity than the original reasoning. It also dies if its host (a terminal tab, an editor window) closes. Any approach that keeps one session alive for a long multi-phase task inherits both problems.

The relay's answer: **do not keep one session alive.** Run a chain of fresh sessions, each of which reconstructs its world from disk, does one bounded phase, writes the result back to disk, and exits. The plan file is the memory; the sessions are disposable.

## The pieces (vocabulary)

- **Baton** — the go signal. A small JSON file dropped on disk. Its presence means "start", its content names the plan file and a leg cap.
- **Supervisor** — a short Python loop in one always-open terminal. It idles polling for the baton; when the baton appears it relaunches legs, watches their exit codes and the on-disk state, and chimes when the plan reaches a terminal state. It carries **zero domain judgment** by design (more on this below).
- **Leg** — one fresh headless CLI session (`claude -p ...`). It reads state from disk, does exactly one phase, saves state to disk, and exits. Every leg is pinned to a specific model so it never inherits whatever model the launching session happened to use.
- **Plan file** — the canonical, human-readable ledger (Markdown). Phases, verification criteria, File Territory, decisions. Legs read it in full and update it as they go.
- **Sidecar** — a small JSON file next to the plan (`<plan>.relay.json`) holding machine state: `status` (`IN_PROGRESS` / `COMPLETE` / `BLOCKED`), `legs_run`, `leg_cap`, `last_leg`, `blocked_reason`. This exists so the supervisor never has to parse Markdown; it reads only JSON and stays dumb.
- **Watcher** — an optional reporting channel. An open session arms a background monitor on the supervisor's log; the harness wakes that session on each transition and on completion. This is the same mechanism that reports background subagents back to a session, which is why it feels native.

## The flow

```
open session (optional)          plan file  <---- canonical ledger ---->  sidecar (JSON)
   arms watcher, gets woken            ^                                     ^  ^
   reports, never coordinates          |  read in full / saved each leg     |  | dumb JSON only
        |                              |                                     |  |
   baton.json (drop = go)              |                                     |  |
        v                              |                                     |  |
   supervisor loop  --launches-->  leg 1  -->  leg 2  -->  ...  -->  COMPLETE --> chime
   (idle poll, relaunch,          each leg = fresh context, model-pinned,
    exit-code + progress rails)    may dispatch its own subagents mid-phase
```

1. A baton is dropped naming a plan.
2. The supervisor picks it up, reads the sidecar, and launches leg 1.
3. Leg 1 reads the plan, finds the first unchecked non-gate phase, executes it, verifies empirically, saves the plan file and sidecar, commits a checkpoint, and exits.
4. The supervisor checks: did the leg exit 0? Did the plan or sidecar actually change (no-progress guard)? Is the leg cap reached? If all clear and status is still `IN_PROGRESS`, it launches leg 2.
5. Repeat until the sidecar says `COMPLETE` (chime, stop) or `BLOCKED` (chime, stop, wait for a human to clear it and re-drop the baton).

## The most important design choice: no persistent smart coordinator

It is tempting to describe the supervisor as a "dumb supervisor". That is true of the Python process, but it misdescribes the system, and the distinction matters.

The intelligence in this system did not disappear. It **relocated** to two places:

- **The plan file** holds the cross-phase judgment (the sequence, the verification criteria, the File Territory), authored by a capable session at plan time. Think of it as frozen intelligence.
- **Each leg is a full orchestrator.** A leg is not a dumb executor. It is a complete agent session that reasons about its phase, can dispatch its own subagents, and verifies its own work.

So there are three levels:

```
supervisor (a judgment-free relauncher)      <- dumb on purpose
    |
    leg / orchestrator (fresh, capable, ephemeral)   <- the intelligence
        |
        subagents dispatched by the leg      <- workers
```

Two different relationships hide inside the word "nested":

- **Between legs it is a sequential chain, not nesting.** Leg 1 does not spawn leg 2; the supervisor does. They are siblings in a relay, handed off through disk state and the baton.
- **Within a leg it is genuine nesting.** A leg dispatches its own subagents.

The supervisor is kept judgment-free deliberately, and the real reason is subtle. It is not "dumb beats smart". It is that **a long-lived smart coordinator would have the exact context-rot problem the relay exists to eliminate.** A supervisor that accumulated understanding across the whole run would itself be a degrading long-lived context. So the design refuses to have any long-lived smart component at all. Coordination is re-derived from the plan file by each fresh leg, every time.

(One honest caveat: the optional watcher session is a long-lived smart component. It is exempt from the claim because it is optional — the relay completes without it — and because it only observes and reports; it never decides what a leg does. So it does not reintroduce coordinator context-rot.)

## The leg contract

Every leg receives the same prompt (see [engine/leg-contract.md](../engine/leg-contract.md)), with the plan path and leg number substituted in. In essence:

1. Read the plan file in full. Its File Territory is your only write surface.
2. The current phase is the first unchecked, non-gate Status Board item.
3. If no unchecked items remain, re-verify every criterion empirically. All pass, set the sidecar to `COMPLETE`. Any fail, set `BLOCKED` with the exact gap.
4. If the phase is an escalation gate, needs a human, needs a tool you lack, or is not fully decided, set `BLOCKED` with the reason. Never fabricate success. A transparent `BLOCKED` is correct; a fake pass is the cardinal failure.
5. Otherwise execute that one phase, verify empirically, save the plan file (flip the checkbox, rewrite the resume pointer, append any decision), update the sidecar.
6. Commit only the files you touched, by pathspec. Never push.
7. Exit. One phase per leg is the law.

The "one phase per leg" rule is what keeps every leg's context small and fresh. A leg that greedily did three phases would be halfway back to the long-degrading-session problem.

## Failure semantics

The supervisor stops the relay plainly on any of these, with a single log line carrying a stable keyword so a watcher can catch it:

- `LEG n FAILED` — nonzero exit. No silent retry; the leg's output is kept as a black-box log for diagnosis.
- `LEG n TIMEOUT` — exceeded the per-leg timeout. The plan may have a half-finished phase; review before retrying.
- `LEG n NO-PROGRESS` — clean exit but neither the plan nor the sidecar changed. This catches a leg that "declared victory" without doing work.
- `STALL` — the leg cap was reached without `COMPLETE`. Prevents runaways.
- `RELAY BLOCKED` — a leg hit something only a human can clear. Fix it, re-drop the baton to retry from current state.

`BLOCKED` is a first-class, healthy outcome, not an error. It is how the system refuses to guess.

## Autopilot: the same ideas, in-session

`/autopilot` is the sibling for when you are watching. Instead of an external supervisor relaunching CLI legs, the open session is the orchestrator and delegates each phase to a fresh in-session subagent. It stays context-lean (heavy work happens in subagents; only compact summaries return) so the loop survives its own auto-compaction by re-reading the plan file each iteration. It uses the same precondition gate, the same empirical-verification discipline, the same escalation-gate safety contract, and the same per-phase save-and-checkpoint.

The shared rule: **the orchestrator thinks; it does not grind.** Whether the orchestrator is an external Python loop (relay) or your open session (autopilot), the actual work happens in fresh, disposable runners, and all continuity lives in the plan file.
