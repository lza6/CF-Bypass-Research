import os
"""UI 截图验证实验 — 用户要求: 实际截图浏览器验证滑块过掉+发码真的发生了

流程: 取号 → 滑块 → 每个关键节点截图 (滑块弹窗/拖动后/T001后/发码请求后/登录页状态)
     → 截图存 screenshots/ 目录 → 用户可肉眼核对
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
SS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'screenshots')
os.makedirs(SS, exist_ok=True)


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
        req_bodies = []

        async def on_response(resp):
            if 'gu0sj6-verify' in resp.url:
                try:
                    verify_results.append(json.loads(await resp.text()))
                except Exception:
                    pass
            if '/auth/account/code' in resp.url:
                try:
                    code_calls.append({'status': resp.status, 'body': (await resp.text())[:150]})
                except Exception:
                    code_calls.append({'status': resp.status})

        async def on_request(req):
            if '/auth/account/code' in req.url:
                try:
                    req_bodies.append(req.post_data[:300] if req.post_data else None)
                except Exception:
                    pass

        page.on('response', on_response)
        page.on('request', on_request)
        await page.goto('https://platform.moss.cn/login', wait_until='domcontentloaded', timeout=45000)
        await page.wait_for_selector('input[placeholder*="phone number"]', timeout=20000)
        await page.screenshot(path=os.path.join(SS, '01_login_page.png'))

        # 输入手机号
        for t in range(4):
            await page.evaluate('''(ph) => {
                const i = document.querySelector('input[placeholder*="phone number"]');
                const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                s.call(i, ph); i.dispatchEvent(new Event('input', {bubbles: true}));
            }''', phone)
            await asyncio.sleep(0.8)
            actual = await page.evaluate('() => document.querySelector(\'input[placeholder*="phone number"]\')?.value || ""')
            if actual == phone:
                break
        await page.screenshot(path=os.path.join(SS, '02_phone_input.png'))
        print(f'输入确认: {actual}', flush=True)

        # 点 Get code
        for b in await page.query_selector_all('button'):
            t = await b.text_content()
            if t and ('获取验证码' in t or 'Get code' in t):
                await b.click()
                break
        await asyncio.sleep(2)
        await page.screenshot(path=os.path.join(SS, '03_after_click.png'))

        # 等滑块
        popped = False
        try:
            await page.wait_for_function(
                "() => (document.getElementById('aliyunCaptcha-window-popup')||{className:''}).className.includes('window-show')",
                timeout=15000, polling=100)
            popped = True
        except Exception:
            pass
        if not popped:
            btns = await page.evaluate("()=>[...document.querySelectorAll('button')].map(b=>b.textContent.trim()).slice(0,6)")
            print(f'滑块未弹: {btns}', flush=True)
            await page.screenshot(path=os.path.join(SS, '04_no_popup.png'))
            return
        await asyncio.sleep(2)
        await page.screenshot(path=os.path.join(SS, '04_slider_popup.png'))

        # YOLO + 反解 + 拖动
        back = shadow = None
        for _ in range(24):
            back = await page.evaluate("()=>document.getElementById('aliyunCaptcha-img')?.src||null")
            shadow = await page.evaluate("()=>document.getElementById('aliyunCaptcha-puzzle')?.src||null")
            if back and back.startswith('data:image') and len(back) > 1000:
                break
            await asyncio.sleep(0.5)
        g = detect_gap_yolo(base64.b64decode(back.split(',', 1)[1]),
                            base64.b64decode(shadow.split(',', 1)[1]))
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
        await asyncio.sleep(0.15)
        await page.screenshot(path=os.path.join(SS, '05_before_release.png'))
        await page.mouse.up()
        await asyncio.sleep(2)
        await page.screenshot(path=os.path.join(SS, '06_after_drag.png'))

        # 等 verify
        for _ in range(30):
            await asyncio.sleep(1)
            if verify_results and verify_results[-1].get('Result', {}).get('VerifyCode'):
                break
        code = verify_results[-1].get('Result', {}).get('VerifyCode', '') if verify_results else ''
        print(f'verify: {code}', flush=True)
        await page.screenshot(path=os.path.join(SS, '07_after_verify.png'))
        if code != 'T001':
            print('滑块未过', flush=True)
            return

        # T001 → 前端原生发码
        for _ in range(15):
            await asyncio.sleep(1)
            if code_calls:
                break
        cc = code_calls[-1] if code_calls else {}
        print(f'发码: {cc}', flush=True)
        print(f'发码请求体: {req_bodies[-1] if req_bodies else None}', flush=True)
        await page.screenshot(path=os.path.join(SS, '08_after_code_request.png'))
        # 页面最终状态 (前端应显示倒计时/Sending成功)
        btns = await page.evaluate("()=>[...document.querySelectorAll('button')].map(b=>b.textContent.trim()).slice(0,6)")
        print(f'按钮状态: {btns}', flush=True)
        await page.screenshot(path=os.path.join(SS, '09_final_state.png'))

        if cc.get('status') != 200:
            print('发码非200', flush=True)
            return

    # 浏览器外: D1 查收
    t0 = time.monotonic()
    while time.monotonic() - t0 < 120:
        time.sleep(10)
        try:
            t = d1.raw('getMsg', phone=phone, keyWord='mosi')
        except Exception:
            continue
        el = int(time.monotonic() - t0)
        if '[尚未收到]' in t:
            print(f'[{el}s] 尚未收到', flush=True)
            continue
        m = re.search(r'\b(\d{4,8})\b', t)
        if not m:
            print(f'[{el}s] 非验证码文本: {t[:80]}', flush=True)
            continue
        got = m.group(1)
        print(f'[{el}s] *** 收到! {got} ***', flush=True)
        lr, cookies = direct_post('/auth/account/login', {'kind': 'phone', 'account': phone, 'code': got})
        print(f'登录: is_new={lr.get("is_new_user")}', flush=True)
        kr, _ = direct_post('/api_keys', {'name': '1'}, cookies)
        sk = (kr.get('items') or [{}])[0].get('api_key') or kr.get('api_key')
        rec = {'ok': True, 'phone': phone, 'sk': sk, 'is_new': lr.get('is_new_user'), 'ts': time.time()}
        with open('moss_accounts.jsonl', 'a', encoding='utf8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        print(f'*** OK sk={sk[:28]}... ***', flush=True)
        return
    print('120s 超时', flush=True)


asyncio.run(main())
