import os
"""单号验证 v2 — 成功变量定位实验

上次协同成功 (17503344415 → 766930), 这次无人工干预完整自动跑:
取号 → 滑块(代理) → 原生发码 → 10s 间隔轮询 getMsg (120s)
若也收到 → 之前 run_4 失败是轮询间隔/时序问题 → 可批量
若不收 → 需要进一步定位 (预约行为/时段/号池)
"""
import asyncio, json, sys, os, time, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 'C:/Users/Administrator.DESKTOP-EGNE9ND/Desktop/逆向产物/SeedanceAI/tools')

import proxy_source
from d1_client import D1Client
import moss_slider_solver as solver

D1_TOKEN = os.environ.get('D1_TOKEN', '')
BAD_PREFIX = ('162', '165', '166', '167', '170', '171', '190', '192', '197')
REAL_CARD = re.compile(r'^1(3[0-9]|4[5-9]|5[0-3,5-9]|7[0-6,8]|8[0-9]|9[1,3,8])')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'moss_accounts.jsonl')


def direct_post(path, body, cookies=None):
    import urllib.request
    headers = {'Content-Type': 'application/json',
               'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36',
               'Origin': 'https://platform.moss.cn',
               'Referer': 'https://platform.moss.cn/login'}
    if cookies:
        headers['Cookie'] = cookies
    req = urllib.request.Request('https://platform.moss.cn/portal-api' + path,
                                 data=json.dumps(body).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        sc = r.headers.get_all('Set-Cookie') or []
        return json.loads(r.read().decode()), '; '.join(c.split(';')[0] for c in sc)


async def main():
    d1 = D1Client(D1_TOKEN)
    phone = None
    for _ in range(30):
        try:
            p = d1.get_phone('mosi')
        except Exception:
            continue
        if not p.startswith(BAD_PREFIX) and REAL_CARD.match(p):
            phone = p
            break
    print(f'号: {phone}', flush=True)

    seen = set()
    info = {}
    for _ in range(10):
        cand = proxy_source.pick('file', 'moss', exclude=seen)
        if cand and all(x not in cand['url'] for x in ('45000', '45002', '45013', '45001', '10808')):
            info = cand
            break
        if cand:
            seen.add(cand['url'])
    print(f'代理: {info.get("exit_ip")}', flush=True)
    solver.PROXY = {'server': info['url']}
    r = await asyncio.wait_for(solver.solve_slider(phone=phone), timeout=300)
    if not r.get('solved'):
        print(f'滑块失败: {r.get("error")}', flush=True)
        return
    sms = r.get('sms') or {}
    print(f'T001 {r.get("elapsed")}s 发码={sms.get("status")}', flush=True)

    t_sent = time.monotonic()
    deadline = t_sent + 120
    n = 0
    while time.monotonic() < deadline:
        time.sleep(10)
        n += 1
        el = int(time.monotonic() - t_sent)
        try:
            t = d1.raw('getMsg', phone=phone, keyWord='mosi')
        except Exception as e:
            print(f'[{n}/{el}s] ERR {str(e)[:60]}', flush=True)
            continue
        if '[尚未收到]' in t:
            print(f'[{n}/{el}s] 尚未收到', flush=True)
            continue
        m = re.search(r'\b(\d{4,8})\b', t)
        code = m.group(1)
        print(f'[{n}/{el}s] *** 收到! {code} ***', flush=True)
        lr, cookies = direct_post('/auth/account/login', {'kind': 'phone', 'account': phone, 'code': code})
        print(f'登录: is_new={lr.get("is_new_user")}', flush=True)
        kr, _ = direct_post('/api_keys', {'name': '1'}, cookies)
        sk = (kr.get('items') or [{}])[0].get('api_key') or kr.get('api_key')
        rec = {'ok': True, 'phone': phone, 'sk': sk, 'is_new': lr.get('is_new_user'),
               'proxy': info.get('exit_ip'), 'ts': time.time()}
        with open(OUT, 'a', encoding='utf8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        print(f'*** OK sk={sk[:28]}... 落盘 ***', flush=True)
        return
    print('120s 超时未收到', flush=True)


asyncio.run(main())
