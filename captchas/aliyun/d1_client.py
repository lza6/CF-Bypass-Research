#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D1 接码平台客户端（api.d1jiema.com）纯文本协议。

返回约定（无 JSON）：
  成功  -> 直接返回内容（手机号 / 短信正文 / 余额数字）
  未到  -> 文本包含「[尚未收到]」
  失败  -> ERROR:错误信息
信任模型：token 不依赖出口 IP，直连即可（Loomy 项目已验证）。
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.d1jiema.com/zc/data.php"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"


class D1Fatal(Exception):
    """token 错 / 封号 / 余额不足，重试无用。"""


class D1Retryable(Exception):
    """网络错误 / 临时失败，可退避重试。"""


class D1Client:
    def __init__(self, token: str, timeout: int = 25):
        self.token = token
        self.timeout = timeout

    def raw(self, code: str, **params) -> str:
        qs = {"code": code, "token": self.token}
        qs.update({k: v for k, v in params.items() if v})
        url = BASE + "?" + urllib.parse.urlencode(qs)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                text = r.read().decode("utf-8", errors="replace").strip()
        except urllib.error.HTTPError as e:
            if e.code in (500, 502, 503, 504):
                raise D1Retryable(f"HTTP {e.code}（平台抖动，可重试）") from e
            raise D1Retryable(f"HTTP {e.code}: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise D1Retryable(f"{type(e).__name__}: {e}") from e
        if text.startswith("ERROR"):
            if any(k in text for k in ("token错误", "封禁", "封号", "余额不足", "请充值")):
                raise D1Fatal(text)
            raise D1Retryable(text)
        return text

    def balance(self) -> float:
        return float(self.raw("leftAmount"))

    def get_phone(self, keyword: str) -> str:
        text = self.raw("getPhone", keyWord=keyword)
        if not text.isdigit() or len(text) != 11:
            raise D1Retryable(f"getPhone 返回异常: {text[:80]}")
        return text

    def get_msg(self, phone: str, keyword: str) -> str | None:
        """返回短信原文；尚未收到返回 None。"""
        text = self.raw("getMsg", phone=phone, keyWord=keyword)
        if "[尚未收到]" in text:
            return None
        return text

    def wait_code(self, phone: str, keyword: str, pattern: str = r"\b(\d{4,8})\b",
                  timeout_s: int = 150, interval_s: int = 6) -> tuple[str, str]:
        """轮询取码，返回 (验证码, 短信原文)。超时抛 D1Retryable。"""
        import re
        deadline = time.time() + timeout_s
        last = None
        while time.time() < deadline:
            try:
                last = self.get_msg(phone, keyword)
            except D1Retryable as e:
                last = f"[poll-err] {e}"
            if last and "[尚未收到]" not in last and not last.startswith("[poll-err]"):
                m = re.search(pattern, last)
                if m:
                    return m.group(1), last
            time.sleep(interval_s)
        raise D1Retryable(f"收码超时 {timeout_s}s，最后响应: {str(last)[:120]}")
