"""MOSS 批量产号 — 干净版 (先跑 3-4 个成功验证)

用户指令:
  - 发码走海外代理 IP (滑块浏览器原生回调链路, 天然走代理出口)
  - D1 getPhone/getMsg 本机直连
  - 收码 20s 轮询 60s 超时丢号
  - 实卡段过滤
  - 目标: 先 4 号串行, 全链路落盘 moss_accounts.jsonl
"""
import asyncio
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_AI = 'C:/Users/Administrator.DESKTOP-EGNE9ND/Desktop/逆向产物/SeedanceAI'
sys.path.insert(0, HERE)
sys.path.insert(0, SEED_AI + '/tools')

import proxy_source
from d1_client import D1Client

D1_TOKEN = 'c4930f01cc074d2991ccc3ae336c1e4e'
OUT = os.path.join(HERE, 'moss_accounts.jsonl')
BAD_PREFIX = ('162', '165', '166', '167', '170', '171', '190', '192', '197')
REAL_CARD = re.compile(r'^1(3[0-9]|4[5-9]|5[0-3,5-9]|7[0-6,8]|8[0-9]|9[1,3,8])')

# 复用稳定版滑块求解器 (8/10 T001, 含 6 attempt 重试 + 原生回调发码)
import moss_slider_solver as solver


_used = set()


def pick_proxy():
    for _ in range(15):
        info = proxy_source.pick('file', 'moss', exclude=_used)
        if info and info.get('url'):
            _used.add(info['url'])
            return info
    return {}


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


def d1_wait_direct(d1, phone, timeout_s=60, interval_s=20):
    """D1 收码, 本机直连 (D1Client 即直连 urllib)"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(min(interval_s, max(0.5, deadline - time.monotonic())))
        try:
            text = d1.raw('getMsg', phone=phone, keyWord='mosi')
        except Exception:
            continue
        if '[尚未收到]' in text:
            print(f'    等短信... 剩 {int(deadline - time.monotonic())}s')
            continue
        import re
        m = re.search(r'\b(\d{4,8})\b', text)
        if m:
            return m.group(1), text
    return None, None


async def produce_one(d1, proxy_url):
    """单号全链路: 取号→滑块(代理)→原生发码(代理)→D1收码(直连)→登录→key"""
    # 取号 (D1 直连, 实卡过滤)
    phone = None
    for _ in range(30):
        try:
            p = d1.get_phone('mosi')
        except Exception:
            continue
        if not solver_mod_ok(p):
            continue
        phone = p
        break
    if not phone:
        return {'ok': False, 'error': 'no real-card phone'}
    print(f'  号: {phone}')

    # 滑块 + 原生发码 (都走代理浏览器)
    solver.PROXY = {'server': proxy_url}
    t0 = time.monotonic()
    try:
        r = await asyncio.wait_for(solver.solve_slider(phone=phone), timeout=300)
    except asyncio.TimeoutError:
        return {'ok': False, 'phone': phone, 'error': 'solve timeout'}
    if not r.get('solved'):
        return {'ok': False, 'phone': phone, 'error': f'slider: {r.get("error", "?")}'}
    sms = r.get('sms') or {}
    print(f'  T001 ✓ {r.get("elapsed")}s 发码={sms.get("status")}')
    if sms.get('status') != 200:
        return {'ok': False, 'phone': phone, 'error': f'发码未 200: {sms}'}

    # D1 收码 (直连, 20s×3)
    print('  D1 收码 (20s 轮询, 60s 上限)...')
    code, sms_text = d1_wait_direct(d1, phone, timeout_s=60, interval_s=20)
    if not code:
        with open(os.path.join(HERE, 'pending_moss.jsonl'), 'a', encoding='utf8') as f:
            f.write(json.dumps({'phone': phone, 'sent_at': time.time(), 'keyword': 'mosi'}) + '\n')
        return {'ok': False, 'phone': phone, 'error': '收码超时丢号'}
    print(f'  验证码: {code}')

    # 登录 + 建 key (本机直连)
    lr, cookies = direct_post('/auth/account/login', {'kind': 'phone', 'account': phone, 'code': code})
    print(f'  登录: is_new={lr.get("is_new_user")}')
    kr, _ = direct_post('/api_keys', {'name': '1'}, cookies)
    sk = (kr.get('items') or [{}])[0].get('api_key') or kr.get('api_key')
    rec = {'ok': True, 'phone': phone, 'sk': sk, 'is_new': lr.get('is_new_user'),
           'proxy': proxy_url, 'elapsed': round(time.monotonic() - t0, 1), 'ts': time.time()}
    with open(OUT, 'a', encoding='utf8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f'  *** OK *** sk={sk[:28]}...')
    return rec


def solver_mod_ok(p):
    return not p.startswith(BAD_PREFIX) and REAL_CARD.match(p)


async def main(count=4):
    d1 = D1Client(D1_TOKEN)
    ok = 0
    for i in range(count):
        print(f'--- {i+1}/{count} ---')
        info = pick_proxy()
        if not info:
            print('  代理池枯'); break
        proxy_url = info['url']
        print(f'  代理: {info.get("exit_ip")}')
        try:
            r = await produce_one(d1, proxy_url)
        except Exception as e:
            r = {'ok': False, 'error': str(e)[:120]}
        if not r.get('ok') and ('滑块' in str(r.get('error', '')) or 'timeout' in str(r.get('error', ''))):
            proxy_source.mark_bad(proxy_url, 'moss: ' + str(r.get('error', ''))[:40])
        if r.get('ok'):
            ok += 1
        else:
            print(f'  失败: {r.get("error")}')
        await asyncio.sleep(5)

    print(f'\n=== {ok}/{count} 成功 ===')
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf8'):
            if line.strip():
                d = json.loads(line)
                if d.get('ok'):
                    print(f'  {d["phone"]}  {d["sk"][:30]}...')


if __name__ == '__main__':
    asyncio.run(main(4))
