# 独立代码复审

- generated_at: 2026-11-18T13:01:46
- duration_sec: 55.5
- diff_bytes: 137164
- untracked_included: (none)
- exit_code: 0

---



The diff rewrites `tests/test_service.py`, but the substantive changes are small: (1) adds `import os`; (2) adds an `os.name != "nt"` skip guard to `test_family_pids_parses_tasklist_csv`; (3) restructures `test_solver_headed_starts_janitor_thread` so that on non-Windows it only verifies the janitor does *not* start (then skips), while Windows keeps the full launch/exit lifecycle. Everything else is byte-identical to the previous file.

Assessment of the changes:

- Both platform guards are correct fixes for tests that would otherwise fail on Linux/macOS (a `win-janitor` thread and `tasklist` invocation are Windows-only). The skip placement is right: in `test_family_pids_parses_tasklist_csv` the skip happens before any setup; in the janitor test the negative assertion runs *before* `pytest.skip`, so the "does not start on non-NT" contract is still actually verified, not just skipped.
- No resource leaks introduced: both new early paths close the created `Solver` in `finally` before returning/skipping.
- No false assertions or mock-as-integration issues introduced by the change; the loosened `/detect` 413-or-disconnect assertion and the keep-alive/raw-socket tests are pre-existing and unchanged in meaning.

P0: none
P1: none
P2 | tests/test_service.py:1472 | `test_family_pids_parses_tasklist_csv` now skips its entire body on non-Windows, so the tasklist CSV parsing logic (PID extraction, quoted-header handling, localized "no tasks" message) gets zero coverage on Linux CI runners | a regression in the CSV parsing (e.g. a change to how the localized "信息: 没有运行的任务…" line or quoted columns are handled) would pass a Linux-only CI pipeline undetected | extract the parsing into a pure helper (e.g. `_parse_tasklist_pids(stdout: str) -> set[int]`) that is OS-independent and unit-test that helper unconditionally, keeping only the `subprocess.run`/`tasklist` invocation behind the Windows guard

VERDICT: PASS
