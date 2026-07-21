# Design decisions

The choices that shaped this system, why each was made, and what was rejected. Distilled from the working design notes.

## 1. Continuity lives only on disk; runners are disposable

**Decision.** The plan file (plus a JSON sidecar) is the single source of truth. Each phase runs in a fresh process that reconstructs its world from disk and exits. Anything a runner does not write to disk is lost at the process boundary, by design.

**Why.** This is the whole point. A process boundary is a fresh context window. Forcing one between phases means no phase ever inherits a degraded, compacted context, and the run survives any host closing.

**Rejected.** One long-lived session (inherits context degradation and dies on tab close). UI puppeting to spawn new tabs (brittle: rides undocumented editor deep links and keystroke automation, breakable by any editor update, and piles up dead tabs).

## 2. The supervisor holds no domain judgment; there is no persistent smart coordinator

**Decision.** The supervisor is a judgment-free relauncher. It polls, launches, checks exit codes, and stops on terminal states. All intelligence lives in the plan file (frozen at authoring time) and in each leg (a full, fresh orchestrator).

**Why.** A long-lived *smart* coordinator would itself be a degrading long-lived context, which is exactly the problem being solved. So the design refuses to have any long-lived smart component. Coordination is re-derived from the plan file by each fresh leg.

**Nuance.** "Dumb supervisor" is accurate about the Python process but misleading about the system. The intelligence did not vanish; it relocated. The honest framing is "stateless coordinator": no long-lived smart component, coordination re-read from disk each leg. See [HOW-IT-WORKS.md](HOW-IT-WORKS.md#the-most-important-design-choice-no-persistent-smart-coordinator).

**Rejected.** A smart, persistent supervisor that accumulates understanding across the run (reintroduces context rot in the coordinator). This is a deliberate fork away from orchestration designs that centralize coordination in a long-lived "manager" agent.

## 3. Legs are orchestrator-grade, not dumb executors

**Decision.** Each leg is a complete agent session: it reads the plan, executes the phase, dispatches its own subagents when warranted, and verifies its own work. The orchestrator role lives *inside* the legs, not in a visible tab and not in the supervisor.

**Why.** A headless CLI session is a full session (project rules, skills, subagent dispatch). Nothing about being the orchestrator requires a visible window. Putting the orchestrator in disposable legs gives fresh context every phase for free.

**Rejected.** Dumb single-purpose executor legs driven by a smarter external planner (that planner would have to hold cross-phase state, recreating the long-context problem).

## 4. Two front doors, one gate

**Decision.** `/autopilot` (watched, in-session) and `/relay` (headless, step-away) are separate commands but share one precondition gate. The relay runs the autopilot gate *by reference*, so there is a single source of truth for what counts as a runnable plan.

**Why.** The two serve genuinely different situations (present vs away) and deserve their own verbs. But duplicating the gate would let the two drift apart. By-reference keeps one gate.

**Rejected.** A single command with a mode flag (the two situations are distinct enough to name). Copy-pasting the gate into both (drift).

## 5. Reporting back to an open session is a watcher wake, not UI puppeting

**Decision.** When a session is open during a relay, it learns of progress and completion by arming a background watcher on the supervisor's log. The harness wakes the session to announce, the same channel that reports background subagents.

**Why.** It is native, documented machinery, so the experience matches how subagent results already surface. Zero puppeting, and it wakes the existing session rather than spawning a new tab.

**Rejected.** Background-agent surfaces that register in a separate list with no wire into an open chat (a completed run there is invisible unless you go look). Deep-link injection (puppeting again).

## 6. Permission posture is bypass; confinement comes from File Territory, not the permission prompt

**Decision.** Relay legs run with permissions bypassed for a smooth unattended run. Confinement comes from the plan's declared File Territory and the leg contract, not from per-action permission prompts.

**Why.** An unattended run cannot answer permission prompts, and a permission mode that pauses after repeated blocks looks identical to "still working" in a headless run. So the plan, not the prompt, is the boundary.

**Honest tradeoff.** This is the sharpest risk in the design. Confinement by contract is prose, not a hardened mechanism. A leg that misreads a vague File Territory can write outside it, unwatched. Mitigations: the gate refuses plans without concrete File Territory; every phase is scoped to a named write set; consider narrowing the leg's tool surface or add-dir for extra-sensitive runs. **`/autopilot` deliberately does not bypass** — it runs in a leashed permission mode precisely because a human is present. Choose relay's bypass consciously.

## 7. Done is proven empirically, never self-reported

**Decision.** A phase is never marked complete on an agent's prose ("I did it"). It is proven with evidence a process cannot fabricate: an exit code, a file diff, test output, file-exists-with-content. Completion re-runs every criterion.

**Why.** Agents declare victory too early and can fabricate plausible "verified" success. The single most documented failure mode of agent loops is marching broken work forward. Evidence, not belief.

**Rejected.** Trusting the implementer's summary (the fabrication vector). A human-only verification criterion (the loop cannot prove it, so such a plan is refused for unattended runs).

## Known open edges (stated plainly)

Honesty over polish:

- **Failure rails are under-exercised.** The happy path is proven repeatedly. The failure paths (a leg that hangs, exits nonzero, or exits clean having done nothing) exist in code and should be deliberately triggered and confirmed, not just trusted. The "exit-0-but-did-nothing" case is the one a judgment-free supervisor is blindest to; the no-progress guard is the defense, and it deserves a real test.
- **No cost ceiling yet.** Fresh context per leg means each leg re-boots its full rule and tool context from zero, so an N-phase plan is N cold boots, not one warm session. That multiplies token cost. Every serious agent-loop writeup converges on a spending ceiling; a leg cap bounds count but not dollars. Consider adding one to the supervisor for long unattended runs.
- **Delivery-grade only.** Because everything not written to a structured plan field dies at the leg boundary, this pattern is wrong for exploratory work where a session's accumulated, unstructured context *is* the artifact. The gate enforces delivery-grade on purpose. Use a normal single session for discovery.
