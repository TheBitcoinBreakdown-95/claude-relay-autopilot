#!/usr/bin/env python3
"""Relay supervisor: drive a Markdown PLAN FILE to completion via fresh headless
Claude Code legs.

One always-open terminal runs this loop. It idles on a baton file; a dropped
baton names a plan file; the supervisor relaunches fresh `claude -p` legs (one
phase per leg, model-pinned, full rules + deferred MCP) until the plan's sidecar
says COMPLETE or BLOCKED, then chimes and returns to idle.

Expected layout (override with env vars, see below):

    <project>/
      scripts/relay/supervisor.py   <- this file
      scripts/relay/leg-contract.md <- the leg prompt template
      state/relay/                  <- runtime state (baton, logs, consumed batons)

Env overrides:
    RELAY_PROJECT_DIR   base project dir (default: two levels up from this file)
    RELAY_ADD_DIR       the --add-dir write root handed to each leg
                        (default: the parent of the project dir)
    RELAY_STATE_DIR     where baton.json + logs live (default: <project>/state/relay)

Disk contract (the supervisor never parses Markdown -- it reads only JSON):
  baton   <state>/baton.json
          {"plan": "<abs or relative path>", "leg_cap": 8}
  sidecar <plan>.relay.json -- the machine ledger legs update:
          {"status": "IN_PROGRESS|COMPLETE|BLOCKED", "legs_run": N,
           "leg_cap": N, "last_leg": {"n": N, "note": "..."},
           "blocked_reason": "..."}
  The plan file itself stays the human/canonical ledger (legs save state on it);
  the sidecar exists so this loop can stay dumb.

Semantics: BLOCKED -> chime + stop; fixing the blocker and re-dropping a baton
retries (sidecar flips back to IN_PROGRESS). COMPLETE at pickup -> no-op (reset
or delete the sidecar to re-run). Every stop condition is one log line with a
stable keyword (BATON / LEG n START|DONE|FAILED|TIMEOUT|NO-PROGRESS / RELAY
COMPLETE / RELAY BLOCKED / STALL / FATAL) so a watcher can stream it.

Guardrails: every leg names its model explicitly (never inherits a session
model); the supervisor holds zero judgment -- all intelligence is in the legs,
all continuity on disk; a failed/timed-out/no-progress leg stops the relay
plainly (no silent retry, no rescue).

Platform note: the chime uses winsound and process priority uses the Windows
API; both fall back gracefully to no-ops on other platforms.
"""

import ctypes
import json
import os
import subprocess
import sys
import shutil
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))              # scripts/relay
PROJECT_DIR = os.environ.get(
    "RELAY_PROJECT_DIR", os.path.dirname(os.path.dirname(HERE)))  # the project dir
ADD_DIR = os.environ.get("RELAY_ADD_DIR", os.path.dirname(PROJECT_DIR))  # leg write root
STATE_DIR = os.environ.get("RELAY_STATE_DIR", os.path.join(PROJECT_DIR, "state", "relay"))
BATON = os.path.join(STATE_DIR, "baton.json")
CONTRACT = os.path.join(HERE, "leg-contract.md")

POLL_SECONDS = 3
IDLE_HEARTBEAT_EVERY = 20        # heartbeat every ~60s while idle
LEG_TIMEOUT_SECONDS = 3600       # real phases can be long; timeout stops the relay
DEFAULT_LEG_CAP = 8
MAX_LEG_CAP = 25
LEG_MODEL = os.environ.get("RELAY_LEG_MODEL", "opus")  # model discipline: legs never inherit
RUN_LOG = os.path.join(STATE_DIR, "supervisor.run.log")  # tee target: the watcher's poll surface


def log(state, detail=""):
    """One transition line to stdout (the terminal panel) AND the run log file
    (what an in-session watcher polls). Tee is fail-open. When launching
    detached, do NOT redirect stdout to RUN_LOG -- lines would double."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {state}"
    if detail:
        line += f" -> {detail}"
    print(line, flush=True)
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def set_below_normal_priority():
    """Windows only; keeps the editor responsive. No-op elsewhere."""
    try:
        BELOW_NORMAL = 0x00004000
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(handle, BELOW_NORMAL)
        return True
    except Exception:
        return False


def chime():
    try:
        import winsound
        winsound.Beep(880, 250)
        winsound.Beep(1175, 350)
    except Exception:
        sys.stdout.write("\a")
        sys.stdout.flush()


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:  # BOM-tolerant
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def resolve_claude():
    exe = shutil.which("claude")
    if exe:
        return exe
    fallback = os.path.join(os.environ.get("USERPROFILE", ""), ".local", "bin", "claude.exe")
    return fallback if os.path.exists(fallback) else None


def resolve_plan(p):
    if not p:
        return None
    if os.path.isabs(p):
        return p if os.path.exists(p) else None
    for base in (ADD_DIR, PROJECT_DIR):
        cand = os.path.normpath(os.path.join(base, p))
        if os.path.exists(cand):
            return cand
    return None


def leg_prompt(plan, sidecar, n, cap):
    with open(CONTRACT, "r", encoding="utf-8-sig") as f:
        text = f.read()
    return (text.replace("{{PLAN_PATH}}", plan)
                .replace("{{SIDECAR_PATH}}", sidecar)
                .replace("{{LEG_N}}", str(n))
                .replace("{{LEG_CAP}}", str(cap))
                .replace("{{TODAY}}", datetime.now().strftime("%Y-%m-%d")))


def run_leg(claude_exe, plan, sidecar, n, cap):
    """One fresh headless leg. Returns exit code, or None on timeout.
    The leg's final output is kept as a black-box log next to the state dir."""
    cmd = [
        claude_exe, "-p", leg_prompt(plan, sidecar, n, cap),
        "--model", LEG_MODEL,
        "--permission-mode", "bypassPermissions",
        "--add-dir", ADD_DIR,
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=PROJECT_DIR, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=LEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(STATE_DIR, f"leg-{n}-{stamp}.log"), "w", encoding="utf-8") as f:
            f.write(proc.stdout or "")
            if proc.stderr:
                f.write("\n--- stderr ---\n" + proc.stderr)
    except OSError:
        pass
    return proc.returncode


def plan_snapshot(plan):
    try:
        st = os.stat(plan)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def raw_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return ""


def run_relay(claude_exe):
    baton = read_json(BATON) or {}
    plan = resolve_plan(str(baton.get("plan", "")))
    if not plan:
        log("BATON INVALID", f"plan not found: {baton.get('plan')!r}")
        return False
    slug = os.path.splitext(os.path.basename(plan))[0]
    try:
        cap = int(baton.get("leg_cap") or DEFAULT_LEG_CAP)
    except (TypeError, ValueError):
        cap = DEFAULT_LEG_CAP
    cap = max(1, min(cap, MAX_LEG_CAP))
    sidecar = plan + ".relay.json"

    s = read_json(sidecar)
    if not s or s.get("status") not in ("IN_PROGRESS", "BLOCKED", "COMPLETE"):
        s = {"status": "IN_PROGRESS", "legs_run": 0, "leg_cap": cap, "plan": plan}
    if s.get("status") == "COMPLETE":
        log("RELAY ALREADY COMPLETE", f"'{slug}' -- reset or delete the sidecar to re-run")
        return True
    if s.get("status") == "BLOCKED":
        log("RESUME", f"'{slug}' was BLOCKED ({s.get('blocked_reason', '?')}); re-drop = retry")
        s["status"] = "IN_PROGRESS"
        s.pop("blocked_reason", None)
    s["leg_cap"] = cap
    write_json(sidecar, s)
    log("BATON", f"detected -> relaying plan '{slug}' (leg cap {cap})")

    while True:
        s = read_json(sidecar) or {}
        status = s.get("status")
        if status == "COMPLETE":
            log("RELAY COMPLETE", f"'{slug}' after {s.get('legs_run', '?')} legs (chime)")
            return True
        if status == "BLOCKED":
            log("RELAY BLOCKED",
                f"'{slug}': {s.get('blocked_reason', 'no reason recorded')} "
                "(chime; fix it, then re-drop a baton to retry)")
            return False
        try:
            legs_run = int(s.get("legs_run", 0) or 0)
        except (TypeError, ValueError):
            legs_run = 0
        if legs_run >= cap:
            log("STALL", f"leg cap {cap} reached without COMPLETE -> stopping (no runaway)")
            return False

        n = legs_run + 1
        log(f"LEG {n} START", f"plan '{slug}'")
        before_plan = plan_snapshot(plan)
        before_sidecar = raw_text(sidecar)

        code = run_leg(claude_exe, plan, sidecar, n, cap)
        if code is None:
            log(f"LEG {n} TIMEOUT", f"exceeded {LEG_TIMEOUT_SECONDS}s -> stopping; "
                "review the plan file for a half-finished phase before retrying")
            return False
        if code != 0:
            log(f"LEG {n} FAILED", f"exit code {code} -> stopping (no silent retry); "
                f"black box: {STATE_DIR}/leg-{n}-*.log")
            return False

        if plan_snapshot(plan) == before_plan and raw_text(sidecar) == before_sidecar:
            log(f"LEG {n} NO-PROGRESS", "plan and sidecar unchanged after clean exit -> stopping")
            return False

        s = read_json(sidecar) or {}
        s["legs_run"] = n
        write_json(sidecar, s)
        note = str((s.get("last_leg") or {}).get("note") or "")[:70]
        log(f"LEG {n} DONE", f"exit 0, status={s.get('status')}" + (f", note: {note}" if note else ""))


def consume_baton():
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        os.replace(BATON, os.path.join(STATE_DIR, f"baton.consumed-{stamp}"))
    except OSError:
        pass


def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        open(RUN_LOG, "w").close()  # fresh run log per supervisor session
    except OSError:
        pass
    lowered = set_below_normal_priority()
    claude_exe = resolve_claude()
    log("SUPERVISOR START",
        f"relay (plan-file mode); polling {BATON} every {POLL_SECONDS}s "
        f"(priority={'below-normal' if lowered else 'default'})")
    if not claude_exe:
        log("FATAL", "claude CLI not found on PATH or at %USERPROFILE%/.local/bin")
        return
    if not os.path.exists(CONTRACT):
        log("FATAL", f"leg-contract.md missing at {CONTRACT}")
        return
    log("READY", f"claude={claude_exe}, legs={LEG_MODEL}. "
        "Drop a baton naming a plan file to start a relay.")

    polls = 0
    idle_announced = False
    while True:
        if os.path.exists(BATON):
            idle_announced = False
            polls = 0
            run_relay(claude_exe)
            consume_baton()
            chime()
            log("IDLE", "relay stopped; waiting for the next baton")
        else:
            if not idle_announced:
                log("IDLE", "waiting for baton")
                idle_announced = True
            polls += 1
            if polls % IDLE_HEARTBEAT_EVERY == 0:
                log("IDLE", f"still waiting (poll #{polls})")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("SUPERVISOR STOP", "interrupted")
