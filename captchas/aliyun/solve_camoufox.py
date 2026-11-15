"""MOSS/通用 阿里滑块求解器 — camoufox 后端 (pydoll/cloakbrowser 替代).

自建 CapMonster 式模板页 (只 scene_id + prefix), camoufox 反检测 Firefox 渲染 SDK,
YOLO 缺口 + 二次反解 + overshoot-correct CDP 拖动, 网络层拦 verify 响应拿 T001/securityToken.

接口对齐 captchas/aliyun/solve.py::solve_aliyun — 返回 {solved, token, verify_code, ...}.
依赖: pip install camoufox playwright numpy opencv-python-headless onnxruntime; camoufox fetch
"""
import asyncio
import json
import random
import math
import base64
import hashlib
import hmac
import urllib.parse
import uuid
import sys
import os
import time
from pathlib import Path

import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gap_yolo import detect_gap_yolo
from camoufox.async_api import AsyncCamoufox

_COEF = (0.003552, 0.0769)  # piece = A·m² + B·m (阿里 V3 通用, 双环境实测残差 0)
_TEMPLATE = Path(__file__).parent / 'template.html'


def _sign(params: dict) -> str:
    s = '&'.join(f'{urllib.parse.quote(k, safe="")}={urllib.parse.quote(str(params[k]), safe="")}'
                 for k in sorted(params))
    sts = f"POST&{urllib.parse.quote('/', safe='')}&{urllib.parse.quote(s, safe='')}"
    return base64.b64encode(
        hmac.new(('YSKfst7GaVkXwZY' + 'vVihJsKF9r89koz' + '&').encode(), sts.encode(), hashlib.sha1).digest()).decode()


def _invert(target: float) -> float:
    a, b = _COEF
    return (-b + math.sqrt(b * b + 4 * a * target)) / (2 * a)


async def verify_in_page(page, tok: dict, scene_id: str, prefix: str, region: str = 'cn') -> dict:
    """VerifyCaptchaV3 from inside page — 同指纹同 IP, 时效内即时提交."""
    ak_id = os.environ.get('ALIYUN_CAPTCHA_AK_ID') or '111jdk439dJJIjd023823201'
    host = f'https://{prefix}-verify.captcha-open{"-southeast" if region == "sgp" else ""}.aliyuncs.com/'
    p = {
        'AaduaneId': ak_id, 'SignatureMethod': 'HMAC-SHA1', 'SignatureVersion': '1.0',
        'Format': 'JSON', 'Timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'Version': '2023-03-05', 'Action': 'VerifyCaptchaV3', 'SceneId': scene_id,
        'SignatureNonce': str(uuid.uuid4()), 'CertifyId': tok['certifyId'],
        'CaptchaVerifyParam': json.dumps({
            'sceneId': tok['sceneId'], 'certifyId': tok['certifyId'],
            'deviceToken': tok['deviceToken'], 'data': tok['data']}),
    }
    p['Signature'] = _sign(p)
    body = urllib.parse.urlencode(p)
    r = await page.evaluate('''async (body) => {
        const res = await fetch(document.baseURI, {method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}, body});
        return await res.json();
    }''', body)
    return r


async def solve_aliyun_camoufox(scene_id: str, prefix: str, region: str = 'cn',
                                proxy: str = None, timeout_s: int = 120,
                                max_attempts: int = 10) -> dict:
    t0 = time.monotonic()
    page_html = (_TEMPLATE.read_text()
                 .replace('__SCENE__', scene_id)
                 .replace('__PREFIX__', prefix)
                 .replace('__REGION__', region))
    # camoufox: 本地 HTML 用 data/set_content; route 拦截对 Firefox 可靠性差 → set_content
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        page = await browser.new_page()
        verify_results = []

        async def on_response(response):
            try:
                url = response.url
                if f'{prefix}-verify' in url or ('verify' in url and 'captcha' in url):
                    body = json.loads(await response.text())
                    verify_results.append(body)
            except Exception:
                pass

        page.on('response', on_response)
        await page.set_content(page_html, wait_until='domcontentloaded', timeout=45000)
        # SDK ready
        for _ in range(60):
            ready = await page.evaluate('() => window.__ready === true')
            if ready:
                break
            await asyncio.sleep(0.5)
        else:
            return {'solved': False, 'error': 'SDK never ready', 'elapsed': round(time.monotonic() - t0, 1)}

        for attempt in range(1, max_attempts + 1):
            # 点按钮 → 弹滑块
            await page.evaluate("() => { window.__verify = null; document.getElementById('btn').click(); }")
            try:
                await page.wait_for_function(
                    "() => (document.getElementById('aliyunCaptcha-window-popup')||{className:''}).className.includes('window-show')",
                    timeout=15000)
            except Exception:
                print(f'attempt {attempt}: popup not shown')
                continue
            await asyncio.sleep(1.5)
            # 图片
            back_src = shadow_src = None
            for _ in range(24):
                back_src = await page.evaluate("()=>{const i=document.getElementById('aliyunCaptcha-img');return i?i.src:null}")
                shadow_src = await page.evaluate("()=>{const i=document.getElementById('aliyunCaptcha-puzzle');return i?i.src:null}")
                if back_src and back_src.startswith('data:image') and len(back_src) > 1000:
                    break
                await asyncio.sleep(0.5)
            if not back_src or not back_src.startswith('data:image'):
                print(f'attempt {attempt}: img not ready')
                continue
            back_bytes = base64.b64decode(back_src.split(',', 1)[1])
            shadow_bytes = base64.b64decode(shadow_src.split(',', 1)[1])
            g = detect_gap_yolo(back_bytes, shadow_bytes)
            if not g:
                print(f'attempt {attempt}: yolo miss, refresh')
                await page.evaluate("()=>document.getElementById('aliyunCaptcha-btn-refresh')?.click()")
                await asyncio.sleep(2)
                continue
            gap_x = g['gap_x']
            geo = await page.evaluate('''() => {
                const img = document.getElementById('aliyunCaptcha-img');
                const slider = document.getElementById('aliyunCaptcha-sliding-slider');
                const r = slider.getBoundingClientRect();
                return { bgW: img.getBoundingClientRect().width, nat: img.naturalWidth,
                         sx: r.x + r.width/2, sy: r.y + r.height/2 };
            }''')
            target = gap_x * geo['bgW'] / geo['nat']
            dist = _invert(target)
            print(f'attempt {attempt}: gap={gap_x} dist={dist:.1f}')
            sx, sy = geo['sx'], geo['sy']
            await page.mouse.move(sx, sy)
            await page.mouse.down()
            over = dist + random.uniform(6, 11)
            n = 42
            for i in range(1, n + 1):
                t = i / n
                ease = 1 - (1 - t) ** 3
                await page.mouse.move(sx + over * ease, sy + math.sin(t * 5) * 1.2)
                await asyncio.sleep(0.011 + (i % 4) * 0.004)
            cn = 10
            for j in range(1, cn + 1):
                t = j / cn
                await page.mouse.move(sx + over + (dist - over) * t, sy + random.uniform(-0.6, 0.6))
                await asyncio.sleep(0.02 + random.uniform(0, 0.015))
            await page.mouse.move(sx + dist, sy)
            await asyncio.sleep(0.16 + random.uniform(0, 0.1))
            await page.mouse.up()
            # 等 verify (SDK 回调 __verify 或 网络层)
            tok = None
            for _ in range(12):
                await asyncio.sleep(1)
                tok = await page.evaluate('() => window.__verify')
                if tok or verify_results:
                    break
            if not tok:
                print(f'attempt {attempt}: no callback')
                continue
            tok = json.loads(tok) if isinstance(tok, str) else tok
            r = await verify_in_page(page, tok, scene_id, prefix, region)
            code = (r or {}).get('Result', {}).get('VerifyCode', '')
            print(f'attempt {attempt}: {code}')
            if code == 'T001':
                return {'solved': True, 'verify_code': 'T001', 'token': tok,
                        'verify_result': r, 'gap_x': gap_x, 'dist': dist,
                        'attempts': attempt,
                        'elapsed': round(time.monotonic() - t0, 1)}
            # 失败 → 刷新换题
            await page.evaluate("()=>document.getElementById('aliyunCaptcha-btn-refresh')?.click()")
            await asyncio.sleep(2)
        return {'solved': False, 'error': 'max attempts', 'attempts': max_attempts,
                'last': verify_results[-1] if verify_results else None,
                'elapsed': round(time.monotonic() - t0, 1)}


if __name__ == '__main__':
    scene = sys.argv[1] if len(sys.argv) > 1 else 'l6hmxyih'
    prefix = sys.argv[2] if len(sys.argv) > 2 else 'gu0sj6'
    region = sys.argv[3] if len(sys.argv) > 3 else 'cn'
    r = asyncio.run(solve_aliyun_camoufox(scene, prefix, region))
    print(json.dumps(r, ensure_ascii=False, default=str)[:500])
