"""MOSS 批量产号 — 并发版 v2 (200号任务)

用户指令:
  1. 实卡段过滤 (16x/部分19x 超时 → 全跳)
  2. 收码轮询 20s 间隔, 60s 超时丢号换号
  3. 并发提吞吐
  4. 目标 200 号落盘

策略:
  - 每 worker 独立 camoufox + 代理出口 (proxy_source exclude 轮换)
  - 直发捷径(DIRECT)在外部变体, 仓库版强制滑块 (成功码 T001)
  - 收码 60s (20s 间隔轮询) 超时即弃
  - 2 worker 并发 (4 已证触发风控, 2 串行稳定)
  - 无 sleep 间隔 (上一号失败立刻下一号, 收码 60s 已是天然间隔)
"""
import asyncio
import json
import sys
import os
import time
import re
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_AI = 'C:/Users/Administrator.DESKTOP-EGNE9ND/Desktop/逆向产物/SeedanceAI'
sys.path.insert(0, HERE)
sys.path.insert(0, SEED_AI + '/tools')
sys.path.insert(0, SEED_AI)

import proxy_source  # noqa: E402
from d1_client import D1Client, D1Fatal, D1Retryable  # noqa: E402

OUT = os.path.join(HERE, 'moss_accounts.jsonl')
PENDING = os.path.join(HERE, 'pending_moss.jsonl')
D1_TOKEN = os.environ.get('D1_TOKEN', '')

# 实卡段正则 (排除 16x 虚卡 + 部分 19x)
REAL_CARD = re.compile(r'^1(3[0-9]|4[5-7]|5[0-3,5-9]|7[0-6,8]|8[0-9]|9[1,3,8])')
# 黑名单段: 162/165/166/167/170/171 虚卡, 190/192/197 部分超时
BAD_PREFIX = ('162', '165', '166', '167', '170', '171', '190', '192', '197')

_used_proxies = set()
_proxy_lock = asyncio.Lock()
_file_lock = asyncio.Lock()


async def pick_proxy() -> dict:
    async with _proxy_lock:
        for _ in range(15):
            info = proxy_source.pick('file', 'moss', exclude=_used_proxies)
            if info and info.get('url'):
                _used_proxies.add(info['url'])
                return info
    return {}


def get_real_phone(d1) -> str | None:
    """取号直到命中实卡段 (最多 30 次)"""
    for _ in range(30):
        try:
            p = d1.get_phone('mosi')
            if p.startswith(BAD_PREFIX) or not REAL_CARD.match(p):
                print(f'    跳虚卡: {p}')
                continue
            return p
        except D1Retryable:
            continue
    return None


async def save_result(rec: dict):
    async with _file_lock:
        with open(OUT, 'a', encoding='utf8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()


async def register_one(worker_id: int, seq: int, d1: D1Client) -> dict | None:
    import moss_slider_solver as solver_mod
    solver_mod.PROXY = None  # reset before pick
    t0 = time.monotonic()  # 每号独立计时（elapsed 用；原版引用 main() 的 t0 必 NameError）

    info = await pick_proxy()
    if not info:
        print(f'[W{worker_id}#{seq}] 代理池枯竭')
        return None
    proxy_url = info['url']
    # solver 的 PROXY 是模块全局 — 用 threading.local 不行, 直接赋值 (串行 await 内安全)
    solver_mod.PROXY = {'server': proxy_url} if isinstance(proxy_url, str) else proxy_url
    print(f'[W{worker_id}#{seq}] proxy={info.get("exit_ip")}')

    phone = get_real_phone(d1)
    if not phone:
        return {'ok': False, 'error': 'no real-card phone'}

    try:
        r = await asyncio.wait_for(solver_mod.solve_slider(phone=phone), timeout=300)
    except asyncio.TimeoutError:
        print(f'[W{worker_id}#{seq}] solve 超时')
        proxy_source.mark_bad(proxy_url, 'solve timeout')
        return None

    # 直发捷径(DIRECT)只存在于外部工作目录的 slider 变体；仓库版强制过滑块，
    # 成功码恒为 T001。这里不再保留永不成立的 direct 分支。
    sms = r.get('sms')
    if not r.get('solved'):
        proxy_source.mark_bad(proxy_url, 'slider: ' + str(r.get('error', ''))[:40])
        print(f'[W{worker_id}#{seq}] 滑块失败: {r.get("error")}')
        return None
    if not sms or sms.get('status') != 200:
        proxy_source.mark_bad(proxy_url, 'sms 400')
        print(f'[W{worker_id}#{seq}] 发码 400')
        return None

    # 收码: 20s 间隔轮询, 60s 超时丢号
    code = None
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        await asyncio.sleep(20)
        try:
            text = d1.raw('getMsg', phone=phone, keyWord='mosi')
        except D1Retryable:
            continue
        if '[尚未收到]' in text:
            continue
        import re as _re
        m = _re.search(r'\b(\d{4,8})\b', text)
        if m:
            code = m.group(1)
            break
    if not code:
        print(f'[W{worker_id}#{seq}] 收码 60s 超时, 丢号 {phone}')
        # pending 记录 (短信可能延迟到)
        async with _file_lock:
            with open(PENDING, 'a', encoding='utf8') as f:
                f.write(json.dumps({'phone': phone, 'sent_at': time.time(), 'keyword': 'mosi'}) + '\n')
        return None

    print(f'[W{worker_id}#{seq}] 验证码: {code}')
    # 登录 + key (同代理)
    def _login_key():
        import urllib.request
        proxy_handler = urllib.request.ProxyHandler({
            'http': proxy_url.replace('socks5://', 'socks5h://'),
            'https': proxy_url.replace('socks5://', 'socks5h://'),
        })
        opener = urllib.request.build_opener(proxy_handler)
        hdrs = {'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/157',
                'Origin': 'https://platform.moss.cn'}
        req1 = urllib.request.Request('https://platform.moss.cn/portal-api/auth/account/login',
            data=json.dumps({'kind': 'phone', 'account': phone, 'code': code}).encode(),
            headers=hdrs, method='POST')
        with opener.open(req1, timeout=30) as resp1:
            lr = json.loads(resp1.read().decode())
            sc = resp1.headers.get_all('Set-Cookie') or []
            cookies = '; '.join(c.split(';')[0] for c in sc)
        req2 = urllib.request.Request('https://platform.moss.cn/portal-api/api_keys',
            data=json.dumps({'name': '1'}).encode(),
            headers={**hdrs, 'Cookie': cookies}, method='POST')
        with opener.open(req2, timeout=30) as resp2:
            kr = json.loads(resp2.read().decode())
        return lr, kr

    try:
        lr, kr = await asyncio.to_thread(_login_key)
        sk = (kr.get('items') or [{}])[0].get('api_key') or kr.get('api_key')
        rec = {'ok': True, 'phone': phone, 'sk': sk, 'proxy': info.get('exit_ip'),
               'is_new': lr.get('is_new_user'), 'worker': worker_id,
               'elapsed': round(time.monotonic() - t0, 1)}
        await save_result(rec)
        print(f'[W{worker_id}#{seq}] *** OK *** {phone} sk={sk[:22]}... {rec["elapsed"]}s')
        return rec
    except Exception as e:
        print(f'[W{worker_id}#{seq}] login/key err: {str(e)[:80]}')
        return None


async def worker_loop(worker_id: int, target: int, done_counter: dict):
    d1 = D1Client(D1_TOKEN)
    produced = 0
    seq = 0
    while produced < target:
        # 检查全局是否已完成
        async with _file_lock:
            pass  # done_counter 检查在外层
        if done_counter.get('total', 0) >= target:
            break
        seq += 1
        try:
            r = await register_one(worker_id, seq, d1)
        except Exception as e:
            print(f'[W{worker_id}] 异常: {str(e)[:100]}')
            r = None
        if r and r.get('ok'):
            produced += 1
            async with _file_lock:
                done_counter['total'] = done_counter.get('total', 0) + 1
        else:
            await asyncio.sleep(3)  # 失败短歇


async def main(target: int = 200, workers: int = 2):
    print(f'=== MOSS 批量产号: 目标 {target}, {workers} worker 并发 ===')
    done_counter = {'total': 0}
    t0 = time.monotonic()
    tasks = []
    for wid in range(workers):
        per = target // workers + (1 if wid < target % workers else 0)
        tasks.append(_staggered_worker(wid + 1, per, done_counter, wid * 30))
    await asyncio.gather(*tasks)
    elapsed = round(time.monotonic() - t0, 1)
    # 读结果
    ok_lines = []
    if os.path.exists(OUT):
        ok_lines = [json.loads(l) for l in open(OUT, encoding='utf8') if l.strip() and json.loads(l).get('ok')]
    print(f'\n=== 完成: {len(ok_lines)}/{target} 用时 {elapsed}s ===')
    for r in ok_lines[-5:]:
        print(f'  {r["phone"]} sk={r["sk"][:25]}')


async def _staggered_worker(wid: int, target: int, done_counter: dict, delay: float):
    if delay:
        await asyncio.sleep(delay)
    return await worker_loop(wid, target, done_counter)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--count', type=int, default=200)
    ap.add_argument('--workers', type=int, default=2)
    a = ap.parse_args()
    asyncio.run(main(a.count, a.workers))
