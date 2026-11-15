"""鉴别实验: 直连重放 cvp 发码给 D1 新号

流程: 滑块在代理里过 (T001, 拿 certifyId/securityToken) → 浏览器关闭(原生回调不触发)
→ 本机直连用 cvp 发码 → D1 查短信 90s
用途: 鉴别「海外代理发码短信不到」是 IP 问题还是 D1 号池问题
"""
import asyncio, json, sys, os, time, re, base64, math, random, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 'C:/Users/Administrator.DESKTOP-EGNE9ND/Desktop/逆向产物/SeedanceAI/tools')

import proxy_source
from d1_client import D1Client
import moss_slider_solver as solver

PHONE = '13975512398'


async def main():
    _seen = set()
    info = {}
    for _ in range(8):
        cand = proxy_source.pick('file', 'moss', exclude=_seen)
        if cand and '45000' not in cand['url'] and '45002' not in cand['url'] and '10808' not in cand['url'] and '45013' not in cand['url'] and '45001' not in cand['url']:
            info = cand
            break
        if cand:
            _seen.add(cand['url'])
    if not info:
        raise SystemExit('代理池枯')
    print('proxy:', info.get('exit_ip'), flush=True)
    solver.PROXY = {'server': info['url']}

    from camoufox.async_api import AsyncCamoufox
    from gap_yolo import detect_gap_yolo
    cvp = None
    kw = dict(headless=True, humanize=True, proxy=solver.PROXY)
    async with AsyncCamoufox(**kw) as browser:
        page = await browser.new_page()
        verify_results = []

        async def on_response(resp):
            if 'gu0sj6-verify' in resp.url:
                try:
                    verify_results.append(json.loads(await resp.text()))
                except Exception:
                    pass

        page.on('response', on_response)
        await page.goto('https://platform.moss.cn/login', wait_until='domcontentloaded', timeout=45000)
        await page.wait_for_selector('input[placeholder*="phone number"]', timeout=20000)
        for _try in range(3):
            await page.evaluate('''(ph) => {
                const i = document.querySelector('input[placeholder*="phone number"]');
                const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                s.call(i, ph); i.dispatchEvent(new Event('input', {bubbles: true}));
            }''', PHONE)
            await asyncio.sleep(0.6)
            actual = await page.evaluate('() => document.querySelector(' + chr(39) + 'input[placeholder*="phone number"]' + chr(39) + ')?.value || ""')
            if actual == PHONE:
                break
            print(f'输入重试 {_try}: actual={actual!r}', flush=True)
        await asyncio.sleep(2)
        clicked = False
        for b in await page.query_selector_all('button'):
            t = await b.text_content()
            if t and ('获取验证码' in t or 'Get code' in t):
                box = await b.bounding_box()
                print('按钮 box:', box, flush=True)
                if box:
                    await page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                else:
                    await b.click()
                clicked = True
                break
        print('clicked:', clicked, flush=True)
        btns_before = await page.evaluate("() => [...document.querySelectorAll('button')].map(b => b.textContent.trim()).filter(t=>t).slice(0,6)")
        print('点前按钮:', btns_before, flush=True)
        try:
            await page.wait_for_function(
                "() => (document.getElementById('aliyunCaptcha-window-popup')||{className:''}).className.includes('window-show')",
                timeout=15000, polling=100)
        except Exception:
            st = await page.evaluate('''() => ({
                  popup: document.getElementById('aliyunCaptcha-window-popup')?.className || 'none',
                  btns: [...document.querySelectorAll('button')].map(b => b.textContent.trim()).filter(t=>t).slice(0,6),
              })''')
            print('滑块未弹详情:', st, flush=True)
            return
        await asyncio.sleep(1.5)
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
        dist = solver._invert(g['gap_x'] * geo['bgW'] / geo['nat'])
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
        for _ in range(30):
            await asyncio.sleep(1)
            if verify_results and verify_results[-1].get('Result', {}).get('VerifyCode'):
                break
        r = verify_results[-1] if verify_results else {}
        code = r.get('Result', {}).get('VerifyCode', '')
        print('verify:', code, flush=True)
        if code != 'T001':
            return
        certify_id = r['Result'].get('certifyId', '')
        sec_tok = r['Result'].get('securityToken', '')
        cvp = base64.b64encode(json.dumps({
            'certifyId': certify_id, 'sceneId': 'l6hmxyih', 'isSign': True,
            'securityToken': sec_tok}).encode()).decode()

    # 浏览器已关 — 原生回调没机会发码; 直连重放 cvp 发码
    print('cvp len:', len(cvp), flush=True)
    body = {'kind': 'phone', 'account': PHONE, 'purpose': 'login', 'captcha_verify_param': cvp}
    req = urllib.request.Request('https://platform.moss.cn/portal-api/auth/account/code',
                                 data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Origin': 'https://platform.moss.cn',
                                          'Referer': 'https://platform.moss.cn/login',
                                          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36'},
                                 method='POST')
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print('直连发码:', resp.status, resp.read().decode()[:150], flush=True)
    except urllib.error.HTTPError as e:
        print('直连发码 HTTP', e.code, e.read().decode()[:200], flush=True)
        return
    d1 = D1Client('c4930f01cc074d2991ccc3ae336c1e4e')
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        time.sleep(15)
        t = d1.raw('getMsg', phone=PHONE, keyWord='mosi')
        if '[尚未收到]' not in t:
            print('*** 短信到了 ***', t[:80], flush=True)
            return
        print(f'等... 剩{int(deadline - time.monotonic())}s', flush=True)
    print('90s 超时, 短信未到', flush=True)


asyncio.run(main())
