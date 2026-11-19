"""R-1 stealth 真机 A/B 批次（2026-11-19，用户已批准，台账重置后首批之一）。

设计：计划书/R-1-自建stealth引擎方案.md §5B
  - 目标：https://www.scrapingcourse.com/cloudflare-challenge（公开 CF 练习页，managed 挑战）
  - 臂A 基线：camoufox headed，无 stealth 注入，2 次
  - 臂B 注入：camoufox headed + stealth 注入，3 次
  - 出口：http://127.0.0.1:10808（v2rayN），同站串行 >=30s
  - 判定：每臂成功数、耗时；结果落 evidence/R-1-stealth-20261119.json

纪律：policy.md §2 —— 失败即停（本批任一臂连续 2 次失败停止该臂），不许超次。
运行：python scripts/r1_stealth_ab.py   （前台跑约 10-25 分钟）
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = "https://www.scrapingcourse.com/cloudflare-challenge"
SITEKEY = ""  # managed 挑战无需 sitekey
PORT = 8978
PROXY = "http://127.0.0.1:10808"
SOLVE_TIMEOUT = 300
GAP = 32  # 同站串行间隔（>30s）
TOKEN = (ROOT / ".env").read_text(encoding="utf-8").split("=", 1)[1].strip()


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def start_solver(stealth: bool, port: int) -> subprocess.Popen:
    args = [sys.executable, "solver/service.py", "--port", str(port), "--headed",
            "--proxy", PROXY, "--token-file", ".env"]
    if not stealth:
        args.append("--no-stealth")
    log(f"启动 solver port={port} stealth={stealth}")
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)


def wait_ready(port: int, timeout: float = 90) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            body = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5))
            if body.get("state") == "ready":
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def solve_once(port: int) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/solve",
        data=json.dumps({"url": TARGET, "want": "clearance", "timeout": 110}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {TOKEN}"})
    t0 = time.monotonic()
    try:
        body = json.load(urllib.request.urlopen(req, timeout=SOLVE_TIMEOUT))
        body["_elapsed"] = round(time.monotonic() - t0, 1)
        return body
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        return {"ok": False, "http": e.code, "body": detail,
                "_elapsed": round(time.monotonic() - t0, 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}",
                "_elapsed": round(time.monotonic() - t0, 1)}


def run_arm(name: str, stealth: bool, times: int, port: int) -> list[dict]:
    results = []
    proc = start_solver(stealth, port)
    try:
        if not wait_ready(port):
            log(f"{name}: solver 未就绪，本臂记 0/{times}")
            return [{"arm": name, "ok": False, "error": "solver-not-ready"}]
        for i in range(1, times + 1):
            log(f"{name} 第 {i}/{times} 次求解…")
            r = solve_once(port)
            r["arm"] = name
            r["stealth"] = stealth
            r["n"] = i
            results.append(r)
            log(f"{name} #{i}: ok={r.get('ok')} elapsed={r.get('_elapsed')}s")
            if i < times:
                time.sleep(GAP)
            # 纪律：本臂连续 2 次失败即停
            if not r.get("ok") and i >= 2 and all(not x.get("ok") for x in results[-2:]):
                log(f"{name}: 连续 2 次失败，按纪律停止本臂")
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:  # noqa: BLE001
            proc.kill()
    return results


def main() -> int:
    all_results = []
    log("=== 臂A 基线（无 stealth）x2 ===")
    all_results += run_arm("baseline", False, 2, PORT)
    time.sleep(GAP)
    log("=== 臂B stealth 注入 x3 ===")
    all_results += run_arm("stealth", True, 3, PORT + 1)

    summary = {
        "task_id": "R-1-stealth-AB",
        "date": "2026-11-19",
        "target": TARGET,
        "egress": PROXY,
        "results": all_results,
        "baseline_ok": sum(1 for r in all_results if r.get("arm") == "baseline" and r.get("ok")),
        "baseline_n": sum(1 for r in all_results if r.get("arm") == "baseline"),
        "stealth_ok": sum(1 for r in all_results if r.get("arm") == "stealth" and r.get("ok")),
        "stealth_n": sum(1 for r in all_results if r.get("arm") == "stealth"),
    }
    out = ROOT / "evidence" / "R-1-stealth-20261119.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"结论: 基线 {summary['baseline_ok']}/{summary['baseline_n']} | "
        f"stealth {summary['stealth_ok']}/{summary['stealth_n']} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
