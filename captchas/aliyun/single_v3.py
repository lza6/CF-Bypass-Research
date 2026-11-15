import os
"""v3 重发实验 — 单号多次发码提升命中率

假设: D1 号池个体抽签 (可收概率 p~10-20%), 单号 300s 窗口内 cooldown 60s 一次
可打 3-4 发, 命中率 1-(1-p)^n
验证: 发码后 61s 再点 Get code → 新滑块 → T001 → 再发码 → 查收
"""
import asyncio, json, sys, os, time, re, base64, math, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 'C:/Users/Administrator.DESKTOP-EGNE9ND/Desktop/逆向产物/SeedanceAI/tools')

import proxy_source
from d1_client import D1Client
from gap_yolo import detect_gap_yolo
from camoufox.async_api import AsyncCamoufox

D1_TOKEN = os.environ.get('D1_TOKEN', '')
BAD_PREFIX = ('162', '165', '166', '167', '170', '171', '190', '192', '197')
REAL_CARD = re.compile(r'^1(3[0-9]|4[5-9]|5[0-3,5-9]|7[0-6,8]|8[0-9]|9[1,3,8])')
_COEF = (0.003552, 0.0769)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'moss_accounts.jsonl')


def _invert(target):
    a, b = _COEF
    return (-b + math.sqrt(b * b + 4 * a * target)) / (2 * a)


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


async def drag_and_verify(page, verify_results):
    """拖滑块直到 T001 (单次), 返回 bool"""
    await asyncio.sleep(1.5)
    back = shadow = None
    for _ in range(24):
        back = await page.evaluate("()=>document.getElementById('aliyunCaptcha-img')?.src||null")
        shadow = await page.evaluate("()=>document.getElementById('aliyunCaptcha-puzzle')?.src||null")
        if back and back.startswith('data:image') and len(back) > 1000:
            break
        await asyncio.sleep(0.5)
    if not back or not back.startswith('data:image'):
        return False
    g = detect_gap_yolo(base64.b64decode(back.split(',', 1)[1]),
                        base64.b64decode(shadow.split(',', 1)[1]))
    if not g or g.get('confidence', 0) < 0.3:
        return False
    geo = await page.evaluate('''() => {
        const img = document.getElementById('aliyunCaptcha-img');
        const s = document.getElementById('aliyunCaptcha-sliding-slider');
        const r = s.getBoundingClientRect();
        return {bgW: img.getBoundingClientRect().width, nat: img.naturalWidth,
                sx: r.x+r.width/2, sy: r.y+r.height/2};
    }''')
    dist = _invert(g['gap_x'] * geo['bgW'] / geo['nat'])
    sx, sy = geo['sx'], geo['sy']
    await page.mouse.move(sx, sy)
    await page.mouse.down()
    over = dist + random.uniform(6, 11)
    for i in range(1, 43):
        t = i / 42
        ease = 1 - (1 - t) ** 3
        await page.mouse.move(sx + over * ease, sy + math.sin(t * 5) * 1.2)
        await asyncio.sleep(0.011 + (i % 4) * 0.004)
    for j in range(1, 11):
        t = j / 10
        await page.mouse.move(sx + over + (dist - over) * t, sy + random.uniform(-0.6, 0.6))
        await asyncio.sleep(0.02 + random.uniform(0, 0.015))
    await page.mouse.move(sx + dist, sy)
    await asyncio.sleep(0.18)
    await page.mouse.up()
    n0 = len(verify_results)
    for _ in range(30):
        await asyncio.sleep(1)
        if len(verify_results) > n0 and verify_results[-1].get('Result', {}).get('VerifyCode'):
            break
    if not verify_results or verify_results[-1].get('Result', {}).get('VerifyCode') != 'T001':
        return False
    return True


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

    async with AsyncCamoufox(headless=True, humanize=True,
                              proxy={'server': info['url']}) as browser:
        page = await browser.new_page()
        verify_results = []
        code_calls = []

        async def on_response(resp):
            if 'gu0sj6-verify' in resp.url:
                try:
                    verify_results.append(json.loads(await resp.text()))
                except Exception:
                    pass
            if '/auth/account/code' in resp.url:
                try:
                    code_calls.append({'status': resp.status, 'body': (await resp.text())[:120]})
                except Exception:
                    code_calls.append({'status': resp.status})

        page.on('response', on_response)
        await page.goto('https://platform.moss.cn/login', wait_until='domcontentloaded', timeout=45000)
        await page.wait_for_selector('input[placeholder*="phone number"]', timeout=20000)

        for attempt in range(1, 5):  # 最多 4 发
            print(f'=== 发送第 {attempt} 次 ===', flush=True)
            # 输入手机号 (每次都设, 防页面状态)
            await page.evaluate('''(ph) => {
                const i = document.querySelector('input[placeholder*="phone number"]');
                const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                s.call(i, ph); i.dispatchEvent(new Event('input', {bubbles: true}));
            }''', phone)
            await asyncio.sleep(0.8)
            actual = await page.evaluate('() => document.querySelector(\'input[placeholder*="phone number"]\')?.value || ""')
            if actual != phone:
                print(f'输入失败 actual={actual!r}, 等待重试', flush=True)
                await asyncio.sleep(3)
                continue

            # 点 Get code
            clicked = False
            for b in await page.query_selector_all('button'):
                t = await b.text_content()
                if t and ('获取验证码' in t or 'Get code' in t):
                    await b.click()
                    clicked = True
                    break
            if not clicked:
                # 按钮冷却 — 等 61s 再来
                print('按钮冷却, 等 65s', flush=True)
                await asyncio.sleep(65)
                continue

            # 等滑块弹
            try:
                await page.wait_for_function(
                    "() => (document.getElementById('aliyunCaptcha-window-popup')||{className:''}).className.includes('window-show')",
                    timeout=15000, polling=100)
            except Exception:
                # 直发或冷却
                btns = await page.evaluate("()=>[...document.querySelectorAll('button')].map(b=>b.textContent.trim()).slice(0,6)")
                print(f'滑块未弹, 按钮: {btns}', flush=True)
                if any('Sending' in x for x in btns):
                    await asyncio.sleep(12)  # 等直发结果
                else:
                    await asyncio.sleep(65)
                continue

            ok = await drag_and_verify(page, verify_results)
            if not ok:
                print('滑块未过, 刷新重试', flush=True)
                await page.evaluate("()=>document.getElementById('aliyunCaptcha-btn-refresh')?.click()")
                await asyncio.sleep(2)
                continue
            # 等 MOSS 原生发码
            for _ in range(15):
                await asyncio.sleep(1)
                if code_calls:
                    break
            cc = code_calls[-1] if code_calls else {}
            print(f'T001 ✓ 发码={cc.get("status")} {cc.get("body")}', flush=True)
            if cc.get('status') != 200:
                continue

            # 查收 75s (覆盖到下一轮 cooldown)
            t0 = time.monotonic()
            got = None
            while time.monotonic() - t0 < 75:
                time.sleep(10)
                try:
                    t = d1.raw('getMsg', phone=phone, keyWord='mosi')
                except Exception:
                    continue
                if '[尚未收到]' not in t:
                    m = re.search(r'\b(\d{4,8})\b', t)
                    if not m:
                        print(f'  非验证码文本: {t[:90]}', flush=True)
                        continue
                    got = m.group(1)
                    break
            if got:
                el = int(time.monotonic() - t0)
                print(f'*** 第 {attempt} 发命中! {got} (发码后{el}s) ***', flush=True)
                lr, cookies = direct_post('/auth/account/login', {'kind': 'phone', 'account': phone, 'code': got})
                print(f'登录: is_new={lr.get("is_new_user")}', flush=True)
                kr, _ = direct_post('/api_keys', {'name': '1'}, cookies)
                sk = (kr.get('items') or [{}])[0].get('api_key') or kr.get('api_key')
                rec = {'ok': True, 'phone': phone, 'sk': sk, 'is_new': lr.get('is_new_user'),
                       'proxy': info.get('exit_ip'), 'attempts': attempt, 'ts': time.time()}
                with open(OUT, 'a', encoding='utf8') as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                print(f'*** OK sk={sk[:28]}... ***', flush=True)
                return
            print(f'第 {attempt} 发 75s 未收, 继续下一发', flush=True)

        print('4 发全空, 放弃该号', flush=True)


asyncio.run(main())
