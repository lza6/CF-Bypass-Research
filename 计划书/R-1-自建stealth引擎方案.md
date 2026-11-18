# R-1 自建 stealth 引擎方案（设计稿 v1）

> 状态：**设计完成，待真机验证**。台账已重置（2026-11-19，新上限 100），R-1 真机验证已获授权（另行报批后执行）。
> 前置事实（2026-11-11 R-E2E-5）：机械链路 PASS——`CLOAKBROWSER_BINARY_PATH` 指向本地 Playwright Chromium 绕过 license，Turnstile 官方测试 sitekey 7.3s 出 token；**这不证明 stealth 有效**（本地 Chromium 无 CloakBrowser C++ 补丁、测试 key 恒通过）。

## 1. 目标

为 CF `managed` 挑战（Clerk Turnstile 升级版）提供一个**不依赖 CloakBrowser 商业 license** 的有头浏览器求解路径，成功率与 camoufox 相当或更高，并保持与现有四后端链（cfsolve → pydoll → camoufox → FlareSolverr）的接入兼容。

## 2. 候选底层对比（选型结论）

| 候选 | 指纹层级 | Windows 可用性 | 与现链集成 | 结论 |
|---|---|---|---|---|
| **camoufox（现有）** | Firefox C++ 层 | ✅ 已验证 | 已集成 | 基线：managed 必开 `--headed` + win-janitor |
| **patchright** | Chromium JS/CDP 层 | ✅ | 引擎工厂已有分支 | 指纹弱于 camoufox；作为对照臂 |
| **camoufox + 自研补丁** | Firefox C++ 层 + 应用层 JS 注入 | ✅ | 走 `_default_browser_factory` 加参数 | **推荐主路线**（增量最小、可复用全部治理） |
| **cloakbrowser** | Chromium C++ 87 处补丁 | 需 license | 已有分支 | 仅作对照，不做依赖 |
| 全新 C++ fork | 最深 | 高成本 | 需新后端 | 否决（换底座已否决） |

## 3. 自研 stealth 增强设计（主路线：camoufox++）

在 camoufox 之上增加**应用层stealth 注入**（不换底座，通过 Playwright `add_init_script` 注入）：

1. **Canvas/WebGL 噪声**：`toDataURL`/`getImageData` 加 per-session 稳定噪声（种子=egress_id 哈希），`getParameter` 对 UNMASKED_VENDOR/RENDERER 返回与 profile 一致的值。
2. **navigator 一致性**：`hardwareConcurrency`/`deviceMemory`/`userAgent`/`platform` 与 camoufox profile 的 OS persona 严格一致（防止 headed 窗口模式下 UA 与窗口环境漂移）。
3. **WebRTC 防泄漏**：禁用非代理 ICE candidate（`RTCPeerConnection` 过滤 `srflx` 非 egress 地址）。
4. **字体/插件枚举一致性**：`navigator.plugins`/`mimeTypes` 长度与 persona 匹配。
5. **时序拟人**：鼠标轨迹已有 `humanize=True`；补充 `pointerdown/move/up` 事件间隔抖动（对 Turnstile 交互检测）。
6. **TLS 层**：保持 curl_cffi 指纹对照实验结论——浏览器原生 TLS 不动。

## 4. 落地改动点（工程）

- `solver/stealth.py`（新增，纯函数+JS 字符串，离线可测）：
  - `stealth_init_script(persona: dict, egress_id: str) -> str`
  - 注入点：`service.py::_default_browser_factory` 的 `kwargs["args"]` 之外，通过 context `add_init_script`；`--stealth` 开关（默认开，`--no-stealth` 关，便于 A/B）。
- 引擎工厂：patchright 分支同步注入 1/2/3（能力允许范围内）。
- 测试：`tests/test_stealth.py` 离线断言 JS 含关键 hook（canvas/webrtc/navigator），不依赖浏览器。

## 5. 验证计划（两段）

**A. 本地靶场（零真机）**
- 用 Turnstile 官方测试 sitekey（恒通过）验证链路连通与注入不破坏页面。
- 用 `docs/challenges/jsd.md` 的本地静态样本验证 JS 注入不报错。

**B. 真机 A/B（已授权批次内）**
- 站点：`scrapingcourse.com/cloudflare-challenge`（R-3 同源，已证实会弹 managed 挑战）。
- 设计：camoufox 基线 vs camoufox+stealth 各 N 次（N=3 起步，失败即停），同出口、串行 ≥30s、独立 `--egress-id`。
- 判定：求解成功率、耗时、`/stats` 故障分类；结果落 `evidence/R-1-stealth-<date>.json`。
- 通过标准：stealth 臂成功率 > 基线且 ≥2/3；不达标则记录并回退（`--no-stealth` 默认）。

## 6. 风险与边界

- CF 对抗是移动靶：任何 stealth 结论只在观测窗口内有效，文档只记实测不宣称长期成功率。
- 注入脚本可能触发 CF 新检测：A/B 失败即回退，不影响主链路。
- 全程遵守 policy.md §2（真机台账、串行、egress-id、CI 离线）。

## 7. 执行顺序

1. `solver/stealth.py` + 注入点 + 离线单测（可立即做，不碰真机）
2. `--stealth/--no-stealth` 开关 + `/solve` 透传（`SolveOptions` 增加字段，openapi 同步）
3. 本地靶场冒烟（Turnstile 测试 key）
4. 真机 A/B（按 §5B，独立报批批次）
