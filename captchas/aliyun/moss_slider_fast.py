"""MOSS 平台阿里滑块求解器 v2 — 快速版 (常驻浏览器 + 事件驱动)

单号 12-15s, 常驻复用 4-6s/号.

用法:
    # 单号 (临时浏览器)
    uv run --active --with camoufox --with numpy --with opencv-python-headless \
        --with onnxruntime python -X utf8 moss_slider_fast.py 139xxxxxxxx

    # 常驻模式 (批量): import 后用 SliderSession
    async with SliderSession(proxy=...) as s:
        for phone in phones:
            r = await s.solve(phone)

关键优化 vs v1 (46s → 12s / 复用 4-6s):
  1. 浏览器常驻 SliderSession (启动 8-10s 摊销为 0)
  2. 登录页预载: session 启动时完成 goto+选号输入, 每号只点按钮
  3. 所有 sleep 轮询 → wait_for_function 事件驱动 (100ms 检查粒度)
  4. verify 等待: on_response 事件置 Event, 无轮询
  5. 拖动帧 42→26 (形态保持, 时长 ~0.9s)
  6. T001 判定即时返回 (removeEventListener 防泄漏)

无硬限制证据: T001 响应与总时长无关 (成功样本拖动仅 226ms 也过; 时长敏感的是
轨迹形态不是总耗时). 下限约束 = SDK init (~2s) + 发码 RTT, 4-5s/号可达.
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

_COEF = (0.003552, 0.0769)


def _invert(target: float) -> float:
    a, b = _COEF
    return (-b + math.sqrt(b * b + 4 * a * target)) / (2 * a)


def random_phone() -> str:
    return '1' + random.choice(['38', '39', '86', '87', '89']) + str(random.randint(10000000, 99999999))


PROXY = None


class SliderSession:
    """常驻浏览器会话: 一次启动, 多号复用 (批量场景 4-6s/号)"""

    def __init__(self, proxy: str = None, headless: bool = True):
        self.proxy = proxy or PROXY
        self.headless = headless
        self.browser = None
        self.page = None
        self.verify_event = None
        self.verify_results = []
        self.code_calls = []
        self._on_resp = None

    async def start(self):
        kw = dict(headless=self.headless, humanize=True)
        if self.proxy:
            kw['proxy'] = self.proxy
        self._cm = AsyncCamoufox(**kw)
        self.browser = await self._cm.__aenter__()
        self.page = await self.browser.new_page()
        self.verify_event = asyncio.Event()
        self.verify_results = []
        self.code_calls = []

        async def on_response(response):
            try:
                u = response.url
                if 'gu0sj6-verify' in u:
                    body = json.loads(await response.text())
                    self.verify_results.append(body)
                    r = body.get('Result', {})
                    code = r.get('VerifyCode', '')
                    print('verify:', code, '+TOKEN' if r.get('VerifyResult') else '')
                    if code:
                        self.verify_event.set()
                if '/auth/account/code' in u:
                    try:
                        self.code_calls.append({'status': response.status,
                                                'body': (await response.text())[:200]})
                    except Exception:
                        self.code_calls.append({'status': response.status})
                    self.verify_event.set()
            except Exception:
                pass

        self._on_resp = on_response
        self.page.on('response', on_response)
        await self.page.goto('https://platform.moss.cn/login', wait_until='domcontentloaded', timeout=45000)
        await self.page.wait_for_selector('input[placeholder*="phone number"]', timeout=20000)
        return self

    async def stop(self):
        try:
            await self._cm.__aexit__(None, None, None)
        except Exception:
            pass

    async def solve(self, phone: str = None, max_attempts: int = 6) -> dict:
        phone = phone or random_phone()
        print('手机号:', phone)
        t0 = time.monotonic()
        self.verify_results.clear()
        self.code_calls.clear()
        self.verify_event.clear()
        # 输入手机号 (输入框可能已有旧值)
        await self.page.evaluate('''(ph) => {
            const i = document.querySelector('input[placeholder*="phone number"]');
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(i, ph);
            i.dispatchEvent(new Event('input', {bubbles: true}));
        }''', phone)
        await asyncio.sleep(0.3)
        for attempt in range(1, max_attempts + 1):
            print(f'--- attempt {attempt} ---')
            # 弹窗可能上一轮残留 window-show — 先关
            await self.page.evaluate("() => document.getElementById('aliyunCaptcha-btn-close')?.click()")
            await asyncio.sleep(0.4)
            clicked = False
            for b in await self.page.query_selector_all('button'):
                t = await b.text_content()
                if t and ('Get code' in t or '获取验证码' in t):
                    await b.click()
                    clicked = True
                    break
            if not clicked:
                # 按钮冷却 — 等 cooldown 再试
                await asyncio.sleep(10)
                continue
            # 弹窗 (事件驱动 100ms 粒度)
            try:
                await self.page.wait_for_function(
                    "() => (document.getElementById('aliyunCaptcha-window-popup')||{className:''}).className.includes('window-show')",
                    timeout=15000, polling=100)
            except Exception:
                st = await self.page.evaluate('''() => ({
                    popup: document.getElementById('aliyunCaptcha-window-popup')?.className || 'none',
                    body: document.body.innerText.slice(0, 150)})''')
                print('未弹:', st['body'][:80])
                # 重试点击 (SDK init 偶发慢)
                await asyncio.sleep(2)
                continue
            # 图 (事件驱动)
            back_src = shadow_src = None
            for _ in range(60):
                back_src = await self.page.evaluate("()=>{const i=document.getElementById('aliyunCaptcha-img');return i?i.src:null}")
                if back_src and back_src.startswith('data:image') and len(back_src) > 1000:
                    shadow_src = await self.page.evaluate("()=>{const i=document.getElementById('aliyunCaptcha-puzzle');return i?i.src:null}")
                    if shadow_src and shadow_src.startswith('data:image'):
                        break
                await asyncio.sleep(0.15)
            if not back_src or not back_src.startswith('data:image'):
                continue
            back_bytes = base64.b64decode(back_src.split(',', 1)[1])
            shadow_bytes = base64.b64decode(shadow_src.split(',', 1)[1])
            g = detect_gap_yolo(back_bytes, shadow_bytes)
            if not g or g.get('confidence', 0) < 0.3:
                await self.page.evaluate("()=>document.getElementById('aliyunCaptcha-btn-refresh')?.click()")
                await asyncio.sleep(1)
                continue
            gap_x = g['gap_x']
            geo = await self.page.evaluate('''() => {
                const img = document.getElementById('aliyunCaptcha-img');
                const s = document.getElementById('aliyunCaptcha-sliding-slider');
                const r = s.getBoundingClientRect();
                return { bgW: img.getBoundingClientRect().width, nat: img.naturalWidth,
                         sx: r.x + r.width/2, sy: r.y + r.height/2 };
            }''')
            dist = _invert(gap_x * geo['bgW'] / geo['nat'])
            print(f'gap={gap_x} dist={dist:.1f}')
            # 拖动 26 帧 (~0.9s)
            sx, sy = geo['sx'], geo['sy']
            await self.page.mouse.move(sx, sy)
            await self.page.mouse.down()
            over = dist + random.uniform(6, 11)
            n = 26
            for i in range(1, n + 1):
                t = i / n
                ease = 1 - (1 - t) ** 3
                await self.page.mouse.move(sx + over * ease, sy + math.sin(t * 5) * 1.2)
                await asyncio.sleep(0.012 + (i % 4) * 0.004)
            for j in range(1, 8):
                t = j / 7
                await self.page.mouse.move(sx + over + (dist - over) * t, sy + random.uniform(-0.5, 0.5))
                await asyncio.sleep(0.018 + random.uniform(0, 0.012))
            await self.page.mouse.move(sx + dist, sy)
            await asyncio.sleep(0.15)
            await self.page.mouse.up()
            # verify 事件驱动等待 (最长 10s, 实际 RTT 即回)
            try:
                await asyncio.wait_for(self.verify_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
            if self.verify_results:
                last = self.verify_results[-1]
                res = last.get('Result', {})
                code = res.get('VerifyCode', '')
                if code == 'T001':
                    elapsed = round(time.monotonic() - t0, 1)
                    print(f'*** T001 *** {elapsed}s')
                    return {'solved': True, 'code': 'T001', 'phone': phone,
                            'certifyId': res.get('certifyId', ''),
                            'securityToken': res.get('securityToken'),
                            'elapsed': elapsed, 'attempts': attempt}
                # 失败刷新
                await self.page.evaluate("()=>document.getElementById('aliyunCaptcha-btn-refresh')?.click()")
                self.verify_event.clear()
                await asyncio.sleep(1.5)
        return {'solved': False, 'error': 'max attempts',
                'last_codes': [r.get('Result', {}).get('VerifyCode') for r in self.verify_results]}


async def solve_slider(phone: str = None, max_attempts: int = 6, headless: bool = True) -> dict:
    """单号便捷入口 (临时浏览器) — 兼容 v1 接口"""
    s = SliderSession(headless=headless)
    await s.start()
    try:
        return await s.solve(phone=phone, max_attempts=max_attempts)
    finally:
        await s.stop()


if __name__ == '__main__':
    ph = sys.argv[1] if len(sys.argv) > 1 else None
    r = asyncio.run(solve_slider(phone=ph))
    print(json.dumps(r, ensure_ascii=False, default=str)[:500])
