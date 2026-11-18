# 独立代码复审

- generated_at: 2026-11-18T12:20:07
- duration_sec: 30.3
- diff_bytes: 0
- untracked_included: (none)
- exit_code: 0

---

**Note:** the diff body between `DIFF START/END` is empty — only the prose change summary was provided. This is therefore a design-level review of the described changes (headed `--window-position` injection + 300ms window-janitor thread killing family PIDs + 4 unit tests), not a line-level review. Findings below are concrete risks inherent to the described design that should be verified against the actual code.

P2 | solver/service.py:_family_pids | Janitor records/kills browser "family PIDs" on a 300ms tick, but PIDs are recycled by the OS | Parent chrome exits; before the next tick the OS reuses its PID (or a child's) for an unrelated process, and the janitor kills that unrelated process — or kills a freshly restarted browser launched by the same Solver | Record (pid, create_time) pairs when capturing the family and re-validate create_time/name/ppid immediately before kill; swallow NoSuchProcess/RaceError per target

P2 | solver/service.py:_start_window_janitor | Thread lifecycle and per-tick exception handling are the classic failure points for a 300ms janitor | If the loop has no stop Event checked each tick, or lets psutil.AccessDenied/NoSuchProcess escape, the janitor either silently dies (orphan protection lost) or one thread leaks per Solver instance across restarts/tests | Daemon thread with a stop Event set in Solver.close()/stop(); catch and log exceptions per tick; join with a short timeout on close

P2 | solver/service.py:_default_browser_factory | Headed mode injects `--window-position` — if appended unconditionally it can duplicate/override a user-supplied flag (Chromium honors the last occurrence) | Caller passes custom launch args containing `--window-position=100,100`; the injected value silently wins, placing the window contrary to caller intent | Only inject when args contain no existing `--window-position`; validate the computed x/y are sane (non-negative, on-screen) before injecting

P2 | tests/test_service.py | 4 unit tests around a 300ms real-time janitor thread are prone to timing flakiness or real process spawning | On a loaded CI runner, a fixed-sleep assertion ("wait 300ms then assert kill happened") intermittently misses, producing flaky failures; or tests launch a real browser process | Make the janitor interval/clock injectable, use a fake process registry, synchronize via events/`wait_for`-style polling instead of fixed sleeps, and assert the stop Event is set on close

P0: none
P1: none

VERDICT: PASS
