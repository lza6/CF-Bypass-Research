"""R-1 stealth 注入的离线单测：不依赖浏览器，只验证生成 JS 的确定性内容。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "solver"))

from stealth import stealth_init_script  # noqa: E402


def test_script_contains_core_hooks():
    js = stealth_init_script(persona="windows", egress_id="default")
    assert "getImageData" in js          # canvas 噪声
    assert "UNMASKED_VENDOR_WEBGL" in js or "0x9245" in js
    assert "RTCPeerConnection" in js     # webrtc 防泄漏
    assert "Navigator.prototype" in js   # navigator 一致性
    assert "__STEALTH_SEED__" in js


def test_seed_binds_persona_and_egress():
    a = stealth_init_script(persona="windows", egress_id="egress-1")
    b = stealth_init_script(persona="windows", egress_id="egress-2")
    c = stealth_init_script(persona="windows", egress_id="egress-1")
    assert a != b, "不同出口必须不同噪声种子"
    assert a == c, "同 persona+出口必须可复现"


def test_values_are_json_escaped_not_concatenated():
    # 参数只以 JSON 常量进入，不允许拼接进代码体（防注入面）
    evil = 'x"; alert(1); "'
    js = stealth_init_script(persona=evil, egress_id="e", gl_vendor=evil, egress_ip=evil,
                             navigator={"platform": evil})
    assert evil + '"' not in js.replace('\\"', "")  # 原始引号不得直接出现在常量外
    assert 'const __GL_VENDOR__' in js
