# 独立代码复审

- generated_at: 2026-11-18T12:39:59
- duration_sec: 37.2
- diff_bytes: 27677
- untracked_included: (none)
- exit_code: 0

---



**Review scope:** the diff only rewrites `tests/test_runpy.py`. Lines 1–306 are carried over verbatim (likely line-ending normalization); the net new material is two tests: `test_review_skip_domains_do_not_gate` and `test_review_diff_empty_diff_short_circuits`. No production code changes, so no P0 surface.

Findings:

P2 | tests/test_runpy.py:308 | `test_review_skip_domains_do_not_gate` never exercises the real aggregation logic — it loads `run.py` (`mod` is unused) and then asserts on a locally re-implemented `classify()` function, so it is tautological | If `cmd_review` regresses and starts counting EMPTY-DIFF/SKIP domains as FAIL (or drops the last-match VERDICT rule), this test still passes, giving false confidence that the invariant is locked | Extract the real verdict-aggregation helper from `run.py` and test it directly, or drive `cmd_review` with stubbed report files and assert the aggregated verdict treats EMPTY-DIFF as SKIP

P2 | tests/test_runpy.py:331 | `test_review_diff_empty_diff_short_circuits` is not hermetic: it stubs `subprocess.run` but lets the real `git diff` execute, so the "empty diff" precondition depends on live repository state for `solver/detect.py` | Any branch/PR that legitimately modifies `solver/detect.py` (or whatever base `review_diff.py` diffs against), or a pytest run from a cwd where the pathspec resolves differently, makes `main()` proceed past the short-circuit; the spy then raises `AssertionError("空 diff 不应调用 claude")` and the test fails for reasons unrelated to the code under test | Stub the git invocation (patch the module's git call to return an empty diff deterministically) so the empty-diff premise is guaranteed, and keep the spy only for asserting claude is not called

P2 | tests/test_runpy.py:331 | The claude guard assumes claude is invoked exclusively via `subprocess.run` (the spy checks `a[0][0] == "claude"` there only); if `review_diff.py` invokes claude via `subprocess.check_output`/`Popen`, the test would neither detect nor block it | A future refactor of `review_diff.py` to `check_output` would silently turn this into a false-positive test, and could invoke the real `claude` binary from the test suite | Guard all subprocess entry points (`run`, `check_output`, `Popen`) in the spy, or patch a single abstraction/`shutil.which`-level seam used by `review_diff.py`

P0: none
P1: none

VERDICT: PASS
