import os
"""协同排查实验 — 用户指令: 取号→走流程→到验证码那步停下, 用户在 D1 后台查

流程: getPhone → 滑块(代理) → T001 → 原生发码(代理, 200) → 停下
     → 每 10s 轮询 getMsg(keyWord=mosi) + 打印原始响应全文
     → 用户在 D1 软件/后台同时看, 报码给我 → 完成登录
"""
import asyncio, json, sys, os, time, re, base64, math, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 'C:/Users/Administrator.DESKTOP-EGNE9ND/Desktop/逆向产物/SeedanceAI/tools')

import proxy_source
from d1_client import D1Client
import moss_slider_solver as solver

D1_TOKEN = os.environ.get('D1_TOKEN', '')
BAD_PREFIX = ('162', '165', '166', '167', '170', '171', '190', '192', '197')
REAL_CARD = re.compile(r'^1(3[0-9]|4[5-9]|5[0-3,5-9]|7[0-6,8]|8[0-9]|9[1,3,8])')


async def main():
    d1 = D1Client(D1_TOKEN)

    # 1. 取号 (实卡段)
    phone = None
    for _ in range(30):
        try:
            p = d1.get_phone('mosi')
        except Exception:
            continue
        if not p.startswith(BAD_PREFIX) and REAL_CARD.match(p):
            phone = p
            break
    print(f'=== 取号: {phone} ===', flush=True)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'co_test_phone.txt'), 'w') as f:
        f.write(phone or '')

    # 2. 滑块+原生发码 (代理)
    _seen = set()
    info = {}
    for _ in range(10):
        cand = proxy_source.pick('file', 'moss', exclude=_seen)
        if cand and all(x not in cand['url'] for x in ('45000', '45002', '45013', '45001', '10808')):
            info = cand
            break
        if cand:
            _seen.add(cand['url'])
    if not info:
        print('代理池枯', flush=True)
        return
    print(f'代理: {info.get("exit_ip")}', flush=True)
    solver.PROXY = {'server': info['url']}
    r = await asyncio.wait_for(solver.solve_slider(phone=phone), timeout=300)
    if not r.get('solved'):
        print(f'滑块失败: {r.get("error")}', flush=True)
        return
    sms = r.get('sms') or {}
    print(f'T001 {r.get("elapsed")}s 发码={sms.get("status")} body={sms.get("body")}', flush=True)

    # 3. 停下 — 轮询 getMsg 打原始响应, 等用户查后台
    print('=== 发码 200 完成, 现在开始轮询 D1 getMsg (原始响应全文) ===', flush=True)
    print('=== 请你现在去 D1 后台查这个号的短信, 看到了报码给我 ===', flush=True)
    deadline = time.monotonic() + 600
    n = 0
    while time.monotonic() < deadline:
        time.sleep(10)
        n += 1
        try:
            t = d1.raw('getMsg', phone=phone, keyWord='mosi')
        except Exception as e:
            print(f'[{n}] getMsg ERR: {str(e)[:80]}', flush=True)
            continue
        print(f'[{n}] getMsg(mosi) 原始: {t[:120]}', flush=True)
        if '[尚未收到]' not in t:
            m = re.search(r'\b(\d{4,8})\b', t)
            print(f'*** 收到短信! 验证码: {m.group(1) if m else "?"} ***', flush=True)
            print(f'原文: {t[:200]}', flush=True)
            return

asyncio.run(main())
