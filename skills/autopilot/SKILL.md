---
name: autopilot
description: Autonomously drive ONE delivery-grade plan file to completion -- execute each phase via fresh subagents, verify empirically, save plan-file state, and continue across the orchestrator's own context-window boundary, with no human in the loop except pre-defined escalation gates. User-invoked only, NEVER auto-fired. Fires when you say "autopilot this plan", "run this plan to completion", "drive <slug> to done", or "autopilot <slug>".
disable-model-invocation: true
argument-hint: "<theme>/<slug> of the plan file to drive to completion"
---

# Autopilot

> **Which surface?** Related drivers, easy to confuse:
> - `/goal`: one completion condition, run in THIS session (transcript-judged, no delegation).
> - `/autopilot`: drive ONE plan file phase-by-phase via fresh subagents (this skill).
> - `/relay`: drive ONE plan file HEADLESS via supervisor-relaunched fresh CLI legs -- the step-away sibling of autopilot (same precondition gate by reference, external substrate). Watching live -> autopilot; stepping away -> relay.
> - `/loop`: re-run a prompt or command on a recurring interval.

Drive ONE delivery-grade plan file to done, hands-off. Your session is the ORCHESTRATOR: it thinks in goals, phases, and verification, and delegates ALL execution to fresh subagents. The orchestrator stays context-lean so the loop survives its own auto-compaction -- heavy work happens in subagents; only compact summaries return.

This is a composition, not a reinvention. The autonomous run-until-done loop + completion oracle + turn-cap come from native **`/goal`** (a session-scoped prompt-based Stop hook: after each turn a small model judges the condition against what Claude surfaced; "no" = keep going, "yes" = stop). Autopilot WRAPS `/goal`, adding the four things `/goal` structurally lacks: per-phase fresh-subagent delegation, artifact-level verification (the `/goal` evaluator cannot call tools -- it only reads the transcript), the durable plan-file save, and the delivery-gate + escalation safety contract below. `/goal` keeps the session turning; autopilot governs what each turn does. Use bare `/goal` for a simple single-context run-to-condition; reach for autopilot when the plan is multi-phase and you want context-leanness, artifact-level verification, durable plan-file saves, and the escalation-gate safety contract.

## Invocation & resume

- **Start it:** `/autopilot <theme>/<slug>` is the on-switch. A freshly-created skill needs a one-time window reload to register as a command. Autopilot drives a plan FILE on disk -- if you paste raw plan content, first save it to `<your-plans-dir>/<slug>.md`, then run.
- **Permission mode:** the session must be in a leashed auto mode (NOT default, which prompts on every action; NOT a full bypass, which is security-gated and is not the mechanism). The precondition gate checks this -- a leash is what lets it proceed unattended safely.
- **It keeps going by itself (via `/goal`):** Engage sets a native `/goal` whose condition is the plan's done-criteria + a turn cap, so the session keeps taking turns without asking "continue?". The ONLY stops are: `/goal`'s evaluator confirming completion, the turn-cap clause, a phase that failed verification twice, or a pre-defined escalation gate. Those stops are the safety, not a malfunction.
- **Do NOT clear or save between phases.** It self-saves the plan file + commits a checkpoint each phase, and survives its own auto-compaction by re-reading the plan file. Engage the save/clear machinery only when it STOPS.
- **Resume after a stop:** fix whatever it escalated, then re-invoke `/autopilot <slug>` (which re-sets the `/goal`). It re-reads the plan file + `## Autopilot State` block and picks up from Resume Here.

## The one principle that makes unattended runs safe

**Autonomy does NOT come from the permission system allowing risky actions.** A leashed auto mode pauses and prompts a human after repeated classifier blocks (and in headless mode it aborts). So the loop is designed to **never attempt a classifier-blockable action** -- every irreversible or outward-facing step (push, publish, send, delete, sign, deploy, post, email, external API write) is an explicit human-handled ESCALATION GATE, not an autopilot phase. Autopilot does the building (drafting, coding, testing, local file edits, plan-file saves); the human does the committing-to-the-world. If a block is ever hit anyway, the Stall Detector makes it LOUD (never assumed to be "still working").

---

## Precondition Gate (run BEFORE the loop -- refuse if ANY check fails)

Read the target plan and verify all of:

1. **Plan file exists.** If not, list closest matches and ask for the right slug. Never guess.
2. **Delivery-grade, not discovery-grade.** Delivery-grade = passes the spec test: fully decided, no open discovery, a fresh agent could execute it cold from the file alone. REFUSE if any present: an open Question that gates a phase; an undecided fork; a `TBD`/`TODO`/`?`/vague action inside a phase. Refusal:
   > "This plan is still DISCOVERY-grade: [the open question / undecided fork]. Autopilot only drives DELIVERY-grade plans. Finish deciding [X], close the open question, then re-run."
3. **At least one falsifiable Verification Criterion**, of the form *"Done = [observable artifact] at [path] and [command] returns [output]"*. Self-reported "done" is not a criterion.
4. **Atomic Status Board.** Items are bite-sized (one edit / one tool call / one check). If vague ("Implement the X subsystem"), refuse and ask for a breakdown.
5. **Every criterion and phase is machine/subagent-verifiable.** Scan for steps a cold subagent CANNOT do or check: "read the value off the live UI", "listen for the sound", "confirm by eye". Each such step is NOT an autopilot phase -- mark it an escalation gate. If a *Verification Criterion* itself is human-only, REFUSE (the loop can't prove done).
6. **Irreversible/outward actions are flagged as escalation gates, not phases.** Scan every phase for push/publish/send/delete/sign/deploy/post/email/external-write. Each is an escalation gate handled by a human, unless the plan EXPLICITLY pre-authorizes it in writing. The run executes up to each gate, then pauses.
7. **Permission posture is a leashed auto mode** (not a full bypass -- that is security-gated and is not the mechanism).
8. **One upfront greenlight** -- the invocation IS the greenlight for this slug.
9. **Plan still matches reality (drift check).** Diff the plan's File Territory and Verification Criteria against the current repo state (do the claimed files exist, do referenced paths and commands still resolve). If reality drifted, STOP and surface the deltas before engaging.

## Engage (write the contract to disk -- chat boundaries die on compaction)

Before looping, APPEND an `## Autopilot State` block to the plan file (this survives the orchestrator's own compaction; a constraint left only in chat does NOT):

```
## Autopilot State
- engaged: YYYY-MM-DD
- slug: <theme>/<slug>
- iteration: 0
- max_iterations: 25
- pre-authorized outward actions: <none | the exact ones the plan authorizes>
- escalation gates (phases NOT to auto-run): <list from gate checks 5-6>
- boundaries: <any "don't touch X / don't publish until I see it" stated -- written here, never left in chat>
```

Then SET THE NATIVE `/goal` that drives the loop. The condition = the plan's overall Verification Criteria, written so Claude's own surfaced tool output proves them (the evaluator does NOT call tools), PLUS a turn cap:

```
/goal Every Status Board item in <theme>/<slug> is checked AND every Verification Criterion passes when re-run -- surface each phase's verifier command output in the conversation as proof -- OR stop and report if an escalation gate / undecided fork / twice-failed phase is reached. Stop after <MAX_TURNS, default 25> turns.
```

Announce: *"Autopilot engaged on `<theme>/<slug>` under `/goal`. Running unattended to the first escalation gate or completion. I stop only for: `/goal` confirming done, the turn cap, a repeated failure, a stall, or a listed escalation gate."*

---

## The Loop (one pass per `/goal` turn)

`/goal` makes the session repeat and STOPS it when the condition holds -- this skill does NOT hand-roll a `while` loop, a turn counter, or a final completion check. Each turn, do exactly ONE pass of Steps 1-5 (one phase), then end the turn having surfaced the verifier output.

### Step 1 -- Re-read plan file + Autopilot State FRESH from disk
At the TOP of every iteration, `Read` the plan file again -- both the `## Autopilot State` block (recovers loop intent + iteration + boundaries after a compaction) and the Status Board. NEVER trust in-context memory of plan or loop state. Determine **current phase** = first unchecked Status Board item that is NOT an escalation gate. If the next unchecked item IS an escalation gate -> Escalate-and-Pause (clear the goal). If no unchecked items remain, surface the full re-run verifier output and end the turn -- `/goal`'s evaluator confirms completion.

### Step 2 -- Dispatch a FRESH subagent for that ONE phase
Self-contained brief (it boots cold, inherits nothing): **Task** (the one phase's concrete action) - **Files** (its file territory; code phases run in the project folder) - **Pattern** (the reference the plan names; "copy patterns, don't invent"; if a tool seems missing, STOP and report) - **Verify** (the phase's slice of the criteria) - **Return contract (4 fields)**: sources / findings+paths / snippet locations / confidence+gaps. One phase per dispatch -- never bundle. Specify the model tier explicitly (mechanical -> cheap; integration -> standard; architecture -> most capable). Do NOT paste prior summaries into the brief. **Project rooting (code phases):** a code subagent must work IN the project folder -- set its cwd there and BEGIN its brief with "Read `<project>/CLAUDE.md` and follow it" if one exists.

### Step 3 -- Treat the summary as a CLAIM
Unverified until Step 4. Never flip a checkbox on "I did it."

### Step 4 -- Verify EMPIRICALLY against un-fabricable evidence
Dispatch a fresh read-only verifier (or run the check inline if it's one cheap command). Verification must rest on evidence a subagent CANNOT fabricate -- actual command exit code, file diff, test output, file-exists+content -- NOT the implementer's prose. For a phase whose output feeds an irreversible/outward gate, run the verifier in a **different model family**.
- PASS -> Step 5.
- FAIL -> retry the phase ONCE with the verifier's concrete failure note. Same failure twice -> Repeated-Failure Escalation (never a third silent retry).
- CANNOT EVALUATE -> Escalate-and-Pause. Never guess a pass.

### Step 5 -- Save + integrity check + checkpoint
On the plan file:
1. **Status Board:** flip the phase to `[x]` with `(done YYYY-MM-DD)`.
2. **Resume Here:** rewrite (file path + verb) to the next unchecked phase.
3. **Autopilot State:** bump `iteration`.
4. **Locked Decisions:** if the phase made a strategic decision, append an entry (Decision/Context/Alternatives/Rationale/**Rejected**/Consequences). Append-only.
5. **Integrity check (anti-self-poisoning):** after writing, re-read and confirm the plan file still parses -- all sections intact, no structure dropped. If the write mangled structure, STOP and escalate (the loop re-reads this file as truth; a corrupt write is self-poisoning).
6. **Checkpoint commit:** `git commit` the plan file + this phase's LOCAL artifacts (stage by name, never `git add -A`) -- `autopilot(<slug>): phase <N> -- <one line>`. Do NOT push (push is an escalation gate).

### Completion (owned by `/goal`, not hand-rolled)
There is NO hand-rolled completion step. When the last non-gate phase is done, surface the full verifier output -- every Verification Criterion re-run, with command output. `/goal`'s evaluator reads that transcript and, when the condition holds, stops the session; then emit the Completion Report. If the board says done but a criterion fails, the evaluator returns "no" and feeds the gap back as next-turn guidance.

---

## Safety Rails

- **Stall Detector (LOUD).** A leashed auto mode pauses-to-prompt on repeated classifier blocks -- in an unattended run that looks identical to "still working." So: if a permission prompt appears, or no phase has advanced in a reasonable number of tool calls, treat it as an ESCALATION (not progress) and fire a notification immediately. A silent stall is the worst failure; make it loud.
- **Turn cap (via `/goal`, not a hand-rolled counter).** The cap lives in the `/goal` condition as a "Stop after N turns" clause (default 25). Bounds runaway token burn.
- **Stop-on-repeated-failure** -- same phase fails verification twice -> escalate.
- **Escalate-and-pause -- do NOT guess -- on:** a listed escalation gate; a genuine discovery/fork the plan didn't pre-decide; any un-pre-authorized irreversible/outward action; an un-evaluable criterion; a file-territory conflict between phases. On escalation: clear the native goal, write state to Resume Here + Autopilot State, notify, and surface: phase reached, exact blocker, the specific decision/authorization needed.
- **Re-read plan + Autopilot State each iteration** -- the single most important rail; what makes the loop survive the orchestrator's own auto-compaction.
- **Orchestrator stays lean** -- all heavy reads/edits in subagents; hold only the freshly-read state + the last compact summary; hand artifacts to subagents as paths, not pasted text.

---

## Reports (each ends the run)

**Completion** -- DONE `<slug>`; phases N/M with dates; per-criterion artifact path + proving command/output; Locked Decisions added; checkpoint SHAs; anything held back at a gate.
**Cap-Hit** -- STOPPED at cap (not done); phases done vs remaining; current Resume Here; recommend raise-cap-and-rerun or inspect non-convergence.
**Escalation** -- PAUSED + the trigger; exact phase + concrete blocker; the specific decision/authorization needed; confirmation Resume Here + Autopilot State on disk reflect the paused state for a clean re-run.

## What this does NOT do
Does NOT decide discovery questions (refuses discovery-grade plans). Does NOT push/publish/deploy/delete unless the plan pre-authorizes it in writing. Does NOT use a full permission bypass. Does NOT let the orchestrator do the work -- every phase is a fresh subagent. Does NOT hand-roll the loop, the turn-counter, or the completion check -- those are native `/goal` (autopilot wraps it).

## Fallback for laptop-closed overnight runs
This in-session skill is the DEFAULT (keeps live MCP/tool access, essential for phases that need it). For a run where you close the laptop, the more robust driver is `/relay`: an OS-detached external loop that runs `claude -p` per phase (fresh context each phase -> zero compaction risk; loop state lives on disk, not a model context). Tradeoff: `-p` aborts on repeated classifier blocks. Reach for relay when the need is genuinely unattended/overnight; this skill covers attended-but-hands-off.
