# Prior art and honest lineage

This pattern is a recombination of well-established ideas, not novel primitives. That is a strength: it stands on several independently battle-tested patterns. This document credits them and states exactly where the relay differs from each. If you know a closer precedent, a pull request correcting this page is welcome.

## The closest three

### 1. The Ralph loop (Geoffrey Huntley, 2025)

The canonical "agent in a loop": [`ghuntley.com/ralph`](https://ghuntley.com/ralph/). At its core, `while :; do cat PROMPT.md | claude-code ; done`, with all state persisting only through on-disk files that each fresh iteration re-reads. Anthropic later packaged a version as an official plugin, and shipped supported loop-style commands.

**Same as the relay:** a dumb loop, fresh context per iteration, disk-only state.

**Where the relay differs:** Ralph re-runs the *same prompt continuously* against a monolithic goal. The relay is **baton-gated** (event-driven, not a tight `while` loop) and **phase-sequenced** (each leg does a *different* bounded phase driven by a structured plan file), and it treats `BLOCKED` and empirical per-phase verification as first-class.

### 2. Anthropic's autonomous-coding quickstart

A coding agent that starts each session from scratch and reconstructs everything from immutable disk state (a feature list, a progress file, git history), then exits. No memory between sessions; all context reconstructed from files.

**Same as the relay:** fresh process per step reading durable disk state, git as the handoff.

**Where the relay differs:** the quickstart is re-kicked by a human or a simple script. The relay adds the external **supervisor** (a dumb baton-poller) and completion-triggered relaunch, plus the optional watcher wake for in-session reporting.

### 3. The Erlang/OTP supervisor tree

Decades-old fault-tolerance design: a [supervisor](https://adoptingerlang.org/docs/development/supervision_trees/) whose only job is to monitor and restart child workers per a fixed strategy. Deliberately dumb; push logic to the leaf workers; "let it crash".

**Same as the relay:** a deliberately dumb supervisor plus restartable workers, with logic pushed to the leaves.

**Where the relay differs:** OTP restarts on **crash for fault tolerance**, and its workers are commonly stateful (state rebuilt from a store). The relay relaunches on **clean completion to advance the work and defeat context rot**, and its workers are stateless by mandate.

## Runner-up: the blackboard architecture

A classic AI pattern: independent knowledge sources read and write a shared knowledge store, activated when the store reaches a relevant state. The relay's plan-plus-sidecar *is* a blackboard and the legs *are* the knowledge sources.

**Where the relay differs:** classic blackboard has an *intelligent control shell* that decides which knowledge source runs next. The relay deliberately moves that intelligence *out* of the coordinator and *into the plan file that each worker reads*. That is the distinguishing move (see [DECISIONS.md](DECISIONS.md#2-the-supervisor-holds-no-domain-judgment-there-is-no-persistent-smart-coordinator)).

## The instructive contrast: smart coordinators

Some contemporary multi-agent systems do the opposite of the relay: they centralize coordination in a *smart, persistent* manager agent, with all state in a shared tracker. Steve Yegge's [Gas Town](https://github.com/steveyegge/gastown) is the loudest example, many agent instances coordinated by a persistent smart "Mayor", state in a git-backed issue tracker.

This is a genuine design fork, worth naming rather than assuming. The relay's position: a long-lived smart coordinator has the exact context-rot problem the whole design exists to eliminate, so the relay refuses to have one. A smart-coordinator design has to solve coordinator context-rot some other way (Gas Town offloads it to the external tracker). The trade is real, not obviously one-sided; the relay picks "no persistent smart component" on purpose.

## Framework state-persistence, for comparison

Most agent frameworks keep state in one long-lived process or conversation, not a fresh process per step. LangGraph's [checkpointers](https://docs.langchain.com/oss/python/langgraph/persistence) persist graph state to a store after each node, which separates compute from memory, but the graph still runs in one process; critics note that if that process dies, the run dies with it. That is a save-point model, not a fresh-process durable-execution model. The relay's process-per-phase is closer to true durable execution at the cost of a full context re-boot each phase.

## Documented failure modes (why the open edges in DECISIONS matter)

Writeups on agent loops converge on a few risks, all of which apply here and shape the safety model:

- **Marching broken work forward.** Without tests, a type checker, or an empirical judge, a loop marks broken work "finished" and agents declare victory too early. This is why the relay verifies empirically and treats a no-progress clean exit as a stop condition. See, for example, ["The Ralph Loop Is Not Enough"](https://dev.to/entire/the-ralph-loop-is-not-enough-2kc9).
- **Cost multiplication.** Re-reading the full context every iteration is intentionally inefficient; at scale the loop becomes the expensive part. Hence the note to add a spending ceiling.
- **Failing unattended.** A loop running unattended is also a loop failing unattended; debugging moves into runs you were never watching. Hence loud failure logging and the watcher wake.
- **Consensus mitigations:** a max-iteration cap, no-progress detection, and a dollar ceiling. The relay ships the first two; the third is a recommended addition.

## Verdict

A **known-but-recombined folk pattern**. The individual primitives are all established. The specific assembly, an event-gated supervisor that relaunches on completion to advance one distinct phase per leg, with a deliberately stateless coordinator and disk-only continuity, is an uncommon combination. The one meaningfully against-the-grain choice is the refusal to have any persistent smart coordinator, which is worth stress-testing rather than taking on faith.
