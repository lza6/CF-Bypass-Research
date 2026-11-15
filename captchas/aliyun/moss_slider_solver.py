"""MOSS 平台阿里滑块求解器 (T001 已验证: 2/2 一次过)

用法:
    uv run --active --with camoufox --with numpy --with opencv-python-headless \
        --with onnxruntime python -X utf8 moss_slider_solver.py [手机号]

流程:
    camoufox (反检测 Firefox) 打开 MOSS 登录页 → 输入手机号 → 点获取验证码
    → SDK 原生滑块 → YOLO 缺口检测 → 二次反解拖距 → overshoot-correct 拖动
    → 网络层拦截 gu0sj6-verify 响应 → T001 + securityToken

产出 (返回值):
    {solved: True, code: 'T001', securityToken: '...', phone: '...', elapsed: N}
    securityToken 即 MOSS 发送验证码所需的 captcha 验证凭证 (SDK 内部自动提交)

依赖: camoufox fetch (python -m camoufox fetch), GH_TOKEN (更新检查绕限流)
注意: 同手机号频控 — 上次通过后短时间内重试同号会'滑块未弹', 需换号
"""
import asyncio
import json
import random
import math
import base64
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gap_yolo import detect_gap_yolo
from camoufox.async_api import AsyncCamoufox

_COEF = (0.003552, 0.0769)  # piece = A·m² + B·m (MOSS 实测, 双环境拟合残差 0)


def _invert(target: float) -> float:
    """二次反解: 缺口位置 → 鼠标行程"""
    a, b = _COEF
    return (-b + math.sqrt(b * b + 4 * a * target)) / (2 * a)


def random_phone() -> str:
    return '1' + random.choice(['38', '39', '86', '87', '89']) + str(random.randint(10000000, 99999999))


PROXY = None  # 外部可设: socks5://host:port


async def solve_slider(phone: str = None, max_attempts: int = 6, headless: bool = True) -> dict:
    """过滑块, 返回 {solved, code, securityToken, ...}"""
    phone = phone or random_phone()
    print('手机号:', phone)
    t0 = time.monotonic()
    verify_results = []

    kw = dict(headless=headless, humanize=True)
    if PROXY:
        kw['proxy'] = PROXY
    async with AsyncCamoufox(**kw) as browser:
        page = await browser.new_page()
        verify_results = []
        portal_code_calls = []

        async def on_response(response):
            try:
                if 'gu0sj6-verify' in response.url:
                    body = json.loads(await response.text())
                    verify_results.append(body)
                    r = body.get('Result', {})
                    print('verify:', r.get('VerifyCode'),
                          '+TOKEN' if r.get('VerifyResult') else '')
                if '/auth/account/code' in response.url:
                    try:
                        portal_code_calls.append({'status': response.status,
                                                  'body': (await response.text())[:200]})
                    except Exception:
                        portal_code_calls.append({'status': response.status})
            except Exception:
                pass

        page.on('response', on_response)
        await page.goto('https://platform.moss.cn/login', wait_until='domcontentloaded', timeout=45000)
        await page.wait_for_selector('input[placeholder*="phone number"]', timeout=20000)
        await page.type('input[placeholder*="phone number"]', phone, delay=30)
        await asyncio.sleep(0.6)

        for attempt in range(1, max_attempts + 1):
            print(f'--- attempt {attempt} ---')
            clicked = False
            for b in await page.query_selector_all('button'):
                t = await b.text_content()
                if t and ('获取验证码' in t or 'Get code' in t):
                    await b.click()
                    clicked = True
                    break
            if not clicked:
                # 按钮可能还在"发送中"冷却 — 频控表现
                return {'solved': False, 'error': '按钮冷却/频控 (同号短期重试)', 'phone': phone}
            try:
                await page.wait_for_function(
                    "() => (document.getElementById('aliyunCaptcha-window-popup')||{className:''}).className.includes('window-show')",
                    timeout=15000)
            except Exception:
                st = await page.evaluate('''() => ({
                  popup: document.getElementById('aliyunCaptcha-window-popup')?.className || 'none',
                  btn: [...document.querySelectorAll('button')].map(b => b.textContent.trim()).filter(t=>t&&t.length<20).slice(0,8),
                  body: document.body.innerText.slice(0, 200),
                })''')
                print('滑块未弹详情:', st)
                return {'solved': False, 'error': '滑块未弹', 'phone': phone}
            await asyncio.sleep(1.5)
            # 图片 (SDK XHR → data URI)
            back_src = shadow_src = None
            for _ in range(24):
                back_src = await page.evaluate("()=>{const i=document.getElementById('aliyunCaptcha-img');return i?i.src:null}")
                shadow_src = await page.evaluate("()=>{const i=document.getElementById('aliyunCaptcha-puzzle');return i?i.src:null}")
                if back_src and back_src.startswith('data:image') and len(back_src) > 1000:
                    break
                await asyncio.sleep(0.5)
            if not back_src or not back_src.startswith('data:image'):
                print('图未就绪')
                continue
            back_bytes = base64.b64decode(back_src.split(',', 1)[1])
            shadow_bytes = base64.b64decode(shadow_src.split(',', 1)[1])
            # YOLO 缺口
            g = detect_gap_yolo(back_bytes, shadow_bytes)
            if not g or g.get('confidence', 0) < 0.3:
                print('YOLO 低置信, 刷新')
                await page.evaluate("()=>document.getElementById('aliyunCaptcha-btn-refresh')?.click()")
                await asyncio.sleep(2)
                continue
            gap_x = g['gap_x']
            # 几何 + 二次反解
            geo = await page.evaluate('''() => {
                const img = document.getElementById('aliyunCaptcha-img');
                const slider = document.getElementById('aliyunCaptcha-sliding-slider');
                const r = slider.getBoundingClientRect();
                return { bgW: img.getBoundingClientRect().width, nat: img.naturalWidth,
                         sx: r.x + r.width/2, sy: r.y + r.height/2 };
            }''')
            target = gap_x * geo['bgW'] / geo['nat']
            dist = _invert(target)
            print(f'gap={gap_x} target={target:.0f} dist={dist:.1f}')
            # overshoot-correct 拖动 (isTrusted=true, humanize 平滑)
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
            await asyncio.sleep(0.16 + random.uniform(0, 0.1))
            await page.mouse.up()
            print('拖动完成')
            # 等 verify
            for _ in range(12):
                await asyncio.sleep(1)
                if verify_results and verify_results[-1].get('Result', {}).get('VerifyCode'):
                    break
            if verify_results:
                last = verify_results[-1]
                code = last.get('Result', {}).get('VerifyCode', '')
                if code == 'T001':
                    elapsed = round(time.monotonic() - t0, 1)
                    print(f'*** T001 通过 *** {elapsed}s')
                    certify_id = last.get('Result', {}).get('certifyId', '')
                    security_token = last['Result'].get('securityToken', '')
                    # MOSS 页面原生回调链路自己发码 — 等待 /portal-api/auth/account/code 请求
                    sms_resp = None
                    for _ in range(15):
                        await asyncio.sleep(1)
                        if portal_code_calls:
                            sms_resp = portal_code_calls[-1]
                            break
                    print('MOSS 原生发码:', sms_resp)
                    return {'solved': True, 'code': 'T001', 'phone': phone, 'certifyId': certify_id,
                            'securityToken': security_token, 'sms': sms_resp,
                            'elapsed': elapsed, 'attempts': attempt,
                            'full': last}
                # 失败 → 刷新换题重试
                await page.evaluate("()=>document.getElementById('aliyunCaptcha-btn-refresh')?.click()")
                await asyncio.sleep(2)
        return {'solved': False, 'error': 'max attempts',
                'last_codes': [r.get('Result', {}).get('VerifyCode') for r in verify_results]}


if __name__ == '__main__':
    ph = sys.argv[1] if len(sys.argv) > 1 else None
    r = asyncio.run(solve_slider(phone=ph))
    print(json.dumps(r, ensure_ascii=False, default=str)[:600])
