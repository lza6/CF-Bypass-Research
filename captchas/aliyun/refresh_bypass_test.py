import os
"""刷新绕过冷却验证 — 用户提示: 刷新网站就不会出现冷却

实验: 同一号
  第 1 轮: 滑块→T001→发码(看 200)
  刷新页面 → 立即重新输入同号 → 点 Get code
  第 2 轮: 看滑块是否立即弹 + 发码是否立即 200 (不被 cooldown 卡)
若通过 → 批量脚本去掉所有 65s 等待, 失败重试成本 65s→8s
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


def _invert(target):
    a, b = _COEF
    return (-b + math.sqrt(b * b + 4 * a * target)) / (2 * a)


async def round_flow(page, phone, verify_results, code_calls, tag):
    """一轮完整: 输入→点→滑块→T001→发码. 返回 (ok, detail)"""
    t0 = time.monotonic()
    # 输入
    for t in range(4):
        await page.evaluate('''(ph) => {
            const i = document.querySelector('input[placeholder*="phone number"]');
            const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            s.call(i, ph); i.dispatchEvent(new Event('input', {bubbles: true}));
        }''', phone)
        await asyncio.sleep(0.7)
        actual = await page.evaluate('() => document.querySelector(\'input[placeholder*="phone number"]\')?.value || ""')
        if actual == phone:
            break
    if actual != phone:
        return False, f'{tag} 输入失败'

    # 点 Get code
    n_calls = len(code_calls)
    clicked = False
    for b in await page.query_selector_all('button'):
        t = await b.text_content()
        if t and ('获取验证码' in t or 'Get code' in t):
            await b.click()
            clicked = True
            break
    if not clicked:
        btns = await page.evaluate("()=>[...document.querySelectorAll('button')].map(b=>b.textContent.trim()).slice(0,6)")
        return False, f'{tag} 无可用按钮: {btns}'

    # 等滑块
    try:
        await page.wait_for_function(
            "() => (document.getElementById('aliyunCaptcha-window-popup')||{className:''}).className.includes('window-show')",
            timeout=15000, polling=100)
    except Exception:
        btns = await page.evaluate("()=>[...document.querySelectorAll('button')].map(b=>b.textContent.trim()).slice(0,6)")
        return False, f'{tag} 滑块未弹: {btns}'
    await asyncio.sleep(1.5)

    # 图
    back = shadow = None
    for _ in range(24):
        back = await page.evaluate("()=>document.getElementById('aliyunCaptcha-img')?.src||null")
        shadow = await page.evaluate("()=>document.getElementById('aliyunCaptcha-puzzle')?.src||null")
        if back and back.startswith('data:image') and len(back) > 1000:
            break
        await asyncio.sleep(0.5)
    if not back:
        return False, f'{tag} 图未就绪'

    g = detect_gap_yolo(base64.b64decode(back.split(',', 1)[1]),
                        base64.b64decode(shadow.split(',', 1)[1]))
    if not g or g.get('confidence', 0) < 0.3:
        return False, f'{tag} YOLO 低置信'
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

    # 等 verify
    n_v = len(verify_results)
    for _ in range(30):
        await asyncio.sleep(1)
        if len(verify_results) > n_v and verify_results[-1].get('Result', {}).get('VerifyCode'):
            break
    code = verify_results[-1].get('Result', {}).get('VerifyCode', '') if len(verify_results) > n_v else ''
    if code != 'T001':
        return False, f'{tag} verify={code}'

    # 等原生发码
    for _ in range(15):
        await asyncio.sleep(1)
        if len(code_calls) > n_calls:
            break
    if len(code_calls) <= n_calls:
        return False, f'{tag} T001 但无发码请求'
    cc = code_calls[-1]
    el = round(time.monotonic() - t0, 1)
    return cc.get('status') == 200, f'{tag} T001+发码{cc.get("status")} body={cc.get("body")} {el}s'


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

        # 第 1 轮
        ok1, d1_ = await round_flow(page, phone, verify_results, code_calls, '第1轮')
        print(d1_, flush=True)
        if not ok1:
            return

        # 刷新页面 — 用户说冷却就没了
        print('--- 刷新页面 (不等 60s 冷却) ---', flush=True)
        await page.reload(wait_until='domcontentloaded')
        await page.wait_for_selector('input[placeholder*="phone number"]', timeout=20000)
        t_refresh = time.monotonic()

        # 第 2 轮 — 立即
        ok2, d2 = await round_flow(page, phone, verify_results, code_calls, '第2轮')
        el = round(time.monotonic() - t_refresh, 1)
        print(f'{d2} (刷新后{el}s内完成)', flush=True)

        if ok2:
            print('*** 刷新绕过冷却验证通过 — 批量脚本可去掉全部冷却等待 ***', flush=True)
        else:
            print('*** 刷新未绕过 (后端仍冷却) — 保留等待逻辑 ***', flush=True)


asyncio.run(main())
