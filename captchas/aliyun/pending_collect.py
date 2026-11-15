"""MOSS pending 号补收 — 扫 pending_moss.jsonl, 号收到短信 → 登录 → 建 sk → moss_accounts.jsonl

运行:  python -u -X utf8 pending_collect.py            (单轮)
      while true; do python -u pending_collect.py; sleep 300; done   (循环)
"""
import json
import sys
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, 'C:/Users/Administrator.DESKTOP-EGNE9ND/Desktop/逆向产物/SeedanceAI/tools')
from d1_client import D1Client

D1_TOKEN = os.environ.get('D1_TOKEN', '')
PENDING = os.path.join(HERE, 'pending_moss.jsonl')
ACCOUNTS = os.path.join(HERE, 'moss_accounts.jsonl')


def moss_api(path, body, cookies=None):
    headers = {'Content-Type': 'application/json',
               'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/157',
               'Origin': 'https://platform.moss.cn'}
    if cookies:
        headers['Cookie'] = cookies
    req = urllib.request.Request('https://platform.moss.cn/portal-api' + path,
                                 data=json.dumps(body).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        sc = r.headers.get_all('Set-Cookie') or []
        return json.loads(r.read().decode()), '; '.join(c.split(';')[0] for c in sc)


def main():
    if not os.path.exists(PENDING):
        print('无 pending 文件')
        return
    d1 = D1Client(D1_TOKEN)
    lines = [json.loads(l) for l in open(PENDING, encoding='utf8') if l.strip()]
    print(f'pending 号: {len(lines)}')
    got = []
    for rec in lines:
        phone = rec['phone']
        try:
            text = d1.raw('getMsg', phone=phone, keyWord='mosi')
            if '[尚未收到]' in text:
                print(f'  {phone}: 尚未收到')
                continue
            # 收到短信 → 提取码
            import re
            m = re.search(r'\b(\d{4,8})\b', text)
            if not m:
                print(f'  {phone}: 短信无码: {text[:60]}')
                continue
            code = m.group(1)
            print(f'  {phone}: 码 {code} ✓ 补登录...')
            lr, cookies = moss_api('/auth/account/login',
                                   {'kind': 'phone', 'account': phone, 'code': code})
            kr, _ = moss_api('/api_keys', {'name': '1'}, cookies)
            sk = (kr.get('items') or [{}])[0].get('api_key') or kr.get('api_key')
            out = {'ok': True, 'phone': phone, 'sk': sk, 'is_new': lr.get('is_new_user'),
                   'recovered': True}
            got.append(out)
            with open(ACCOUNTS, 'a', encoding='utf8') as f:
                f.write(json.dumps(out, ensure_ascii=False) + '\n')
            print(f'  {phone}: *** sk={sk[:20]}... ***')
        except Exception as e:
            print(f'  {phone}: err {str(e)[:60]}')
    # 移除已补收的
    if got:
        got_phones = {g['phone'] for g in got}
        remaining = [r for r in lines if r['phone'] not in got_phones]
        with open(PENDING, 'w', encoding='utf8') as f:
            for r in remaining:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'本轮补收: {len(got)}')

if __name__ == '__main__':
    main()
