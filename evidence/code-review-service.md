# v6.5.1 → v6.6.0 发布 diff 评审

**结论：无阻断性缺陷。** 核心语义改动只有 geoip 一处，其余是死代码清理与格式化，且有 F401/F841/F821 兜底。以下是 ruff（E/F, line-length 120）覆盖不到的点，按严重度排列。

## 中

**1. `geoip=True` 是行为变更，且本轮零真机未验证（engines.py `_camoufox_factory` + bootstrap.py 新增提示）**
- 工厂从 `geoip: False` 硬编码改为 `geoip: True`，意味着**每次 camoufox 首次启动都要联网下载 ~116MB**；离线/受限网络环境下 Camoufox 启动可能直接失败或挂起。本工厂被"直接复用"的场景（脚本、未来调用方）都会继承这个行为。
- bootstrap 新增的 `"[cfsolve] geoip 已启用…"` 提示要成立，前提是**所有** camoufox 路径都是 geoip=True。注释声称 `service._default_browser_factory` 自 ff36cc3 起就是 True，但本 diff 里看不到该函数——建议核对一次，避免提示与实际行为不一致。
- 建议：真机冒烟一次 camoufox 启动（验证下载、`%LOCALAPPDATA%` 缓存路径、二次启动离线可用）；并考虑给离线部署留一个环境变量开关（如 `CFSOLVE_GEOIP=0`），否则气隙环境无法用 bootstrap 起 camoufox。

## 低

**2. 本 diff 未包含 CHANGELOG 勘误注记和版本号变更。** 上下文约定 v6.6.0 要"只加勘误注记"，但这里只有 6 个代码文件。若勘误/版本号在别的提交里，忽略此条；否则发布内容缺一块。

**3. `--headed` help 文案与默认值存在张力。** help 说"Clerk/CF managed 挑战无头全部解不出，生产批量必开"，但默认仍是 headless（opt-in）。对 managed 挑战场景，默认值就是已知不可用的模式。若有意保留默认（非 managed 场景 headless 仍可用），建议 help 补一句"默认无头"，避免运维误读。

**4. geoip 提示的触发条件与平台文案。** `engine_enum.value == "camoufox"` 依赖枚举字面量精确匹配（大小写），不匹配则提示静默不打印——顺手核对一下。`%LOCALAPPDATA%/...` 写死 Windows 路径，跨平台跑 script-mode 时会误导（项目 Windows 优先，可不改）。

## nit

**5.** engines.py 新注释"本工厂是 bootstrap 对**非 camoufox** 引擎的统一入口"与事实相反——`_camoufox_factory` 就是 camoufox 的工厂。疑似笔误，建议改为"对 camoufox 引擎"。

**6.** metrics.py 拆分后的首段 `f'cfsolve_host_failures_total'` 不含占位符，`f` 前缀可去掉（隐式拼接下 F541 不会报，纯洁癖）。

## 已核对、无问题（不动）

- **bootstrap 双臂 import 删除完全对称**（`MAX_URL_LEN`/`MIN_TTL`/`parse_proxy_url` 两臂同步删除），属性面一致性保持。唯一残余风险：若有测试直接 `from solver.bootstrap import parse_proxy_url` 这类引用会爆——跑一遍测试即可确认。
- `cb(h, l, …)` → `cb(h, hwnd, …)`：第二参是 EnumWindows 的 LPARAM，函数体未使用，纯改名，无语义影响。
- probe.py 保留 `import json  # noqa: F401` 的兼容面、service.py 头部 re-export 面均按既定取舍未动。
- metrics.py host_failures 与 service.py hint 两处 f-string 拆分，输出与原实现逐字节一致（尾随空格、"的 "后接 `{TOKEN_LINE_PREFIX}` 均保留）；`{{host=…}}` 转义正确；行宽均在 120 内。
- proxypool.py 删除的 `now = time.time()` 为死变量，`time` 模块其他处仍在用。

**发版前建议**：除常规测试外，补一次真机 camoufox 冷启动冒烟（覆盖 geoip 下载/缓存/提示文案），这是本轮唯一未经验证的行为变更点。


VERDICT: PASS
