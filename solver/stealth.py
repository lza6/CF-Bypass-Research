"""R-1 自建 stealth 注入（应用层，叠加在 camoufox 之上，不换底座）。

设计稿：`计划书/R-1-自建stealth引擎方案.md`。注入通过 Playwright
`context.add_init_script` 在每个求解 context 建立时执行（文档开始前），
因此对 managed 挑战的入口脚本同样生效。

边界（S-4/方案 §6）：注入是否提升成功率只能靠真机 A/B 判定；本模块只保证
"注入内容确定、可离线测试、可一键关闭"。
"""

from __future__ import annotations

import hashlib

# 与 persona/出口绑定的稳定噪声种子——同一 (persona, egress) 组合噪声恒定，
# 跨次求解可复现；不同出口噪声不同，避免跨出口指纹关联。
_NOISE_HOOK = """
(function () {
  var seedHex = __STEALTH_SEED__;
  function prng(tag) {
    var h = 0;
    var s = seedHex + ':' + tag;
    for (var i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) >>> 0; }
    return function () { h = (h * 1664525 + 1013904223) >>> 0; return h / 4294967296; };
  }
  // Canvas 2D：读回像素时加稳定噪声
  try {
    var origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function () {
      var data = origGetImageData.apply(this, arguments);
      var rnd = prng('canvas');
      for (var i = 0; i < data.data.length; i += 97) { data.data[i] = (data.data[i] + (rnd() * 3 | 0)) & 255; }
      return data;
    };
  } catch (e) {}
  // WebGL：厂商/型号与 persona 一致（由 Python 侧注入常量）
  try {
    var glProto = WebGLRenderingContext.prototype;
    var origGetParameter = glProto.getParameter;
    var vendor = __GL_VENDOR__, renderer = __GL_RENDERER__;
    glProto.getParameter = function (p) {
      if (p === 0x9245) return vendor;      // UNMASKED_VENDOR_WEBGL
      if (p === 0x9246) return renderer;    // UNMASKED_RENDERER_WEBGL
      return origGetParameter.apply(this, arguments);
    };
  } catch (e) {}
})();
"""

_NAVIGATOR_HOOK = """
(function () {
  var defs = __NAVIGATOR_OVERRIDES__; // {"hardwareConcurrency": 8, ...}
  for (var key in defs) {
    try {
      Object.defineProperty(Navigator.prototype, key, {
        get: (function (v) { return function () { return v; }; })(defs[key]),
        configurable: true,
      });
    } catch (e) {}
  }
})();
"""

_WEBRTC_HOOK = """
(function () {
  // 只放行 egress 侧候选；主机候选保留（本地回环采集是正常行为）。
  var egressPrefix = __EGRESS_IP__;
  var OrigPC = window.RTCPeerConnection;
  if (!OrigPC) return;
  function Patched(cfg) {
    var pc = new OrigPC(cfg);
    var origAdd = pc.addIceCandidate.bind(pc);
    pc.addEventListener('icecandidate', function (ev) {
      var c = ev && ev.candidate;
      if (c && c.candidate && c.candidate.indexOf('srflx') >= 0
          && egressPrefix && c.candidate.indexOf(egressPrefix) < 0) {
        // 吞掉非出口 IP 的 srflx 候选（防止 WebRTC 泄漏真实线路）
        return;
      }
    });
    pc.addIceCandidate = function (c) { return origAdd(c); };
    return pc;
  }
  Patched.prototype = OrigPC.prototype;
  window.RTCPeerConnection = Patched;
})();
"""


def _seed(persona: str, egress_id: str) -> str:
    return hashlib.sha256(f"{persona}|{egress_id}".encode()).hexdigest()[:16]


def _js_const(name: str, value: str) -> str:
    import json
    return f"const {name} = {json.dumps(value)};"


def stealth_init_script(persona: str = "", egress_id: str = "",
                        gl_vendor: str = "", gl_renderer: str = "",
                        egress_ip: str = "", navigator: dict | None = None) -> str:
    """生成注入 JS。全部参数做字符串化，防注入面（参数只进常量，不拼接代码）。"""
    seed = _seed(persona, egress_id)
    nav = navigator or {}
    import json
    return (
        f"const __STEALTH_SEED__ = {json.dumps(seed)};\n"
        f"const __GL_VENDOR__ = {json.dumps(gl_vendor)};\n"
        f"const __GL_RENDERER__ = {json.dumps(gl_renderer)};\n"
        f"const __EGRESS_IP__ = {json.dumps(egress_ip)};\n"
        f"const __NAVIGATOR_OVERRIDES__ = {json.dumps(nav)};\n"
        + _NOISE_HOOK + "\n" + _NAVIGATOR_HOOK + "\n" + _WEBRTC_HOOK
    )
