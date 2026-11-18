# CF-Bypass-Research 项目最终状态与待办清单

> **本文件是项目唯一状态源与施工图。** 2026-11-18 基于代码级核验重写，取代并删除旧版《项目总状态与待办清单》（2026-11-13，基线 v6.5.0）与根目录《参考的结果计划指南.md》（2026-11-18 增量对标）。历史版本均可从 git 找回：`git show de81d8d:计划书/CF-Bypass-Research-项目总状态与待办清单.md`、`git show 12e35af:参考的结果计划指南.md`。
>
> **基线**：`master` @ `de81d8d`（tag `v6.5.1`，CI 双绿 @ `e521d13`：`ci` run 44252565570 + `site-ci` run 44252572597）。证据分级：**已验证**（实际运行观察）/ **静态确认**（读代码确认）/ **合理推断** / **待验证**（缺环境或权限）。

---

## 0. 一页速览

文档此前声称的"已落地"经本轮逐项核验**基本属实**：v6.5.1 的 headed 窗口治理（`service.py:434` 注入 `--window-position=-3200` + `service.py:602` 守门线程）、T-07/T-08/T-10、C3/C5、R-3 本地补丁（`PATCHES.json` 5 个补丁全部 `applied`）均有代码与证据支撑；`docs/facts.json`（2026-11-18 实测）与门禁一致。

真实缺口集中在四类：**① geoip 决策反转未收口**（代码 `geoip=True` 与 SKILL.md/旧计划书"已否决"矛盾，`maxminddb` 未进 requirements）；**② 研究线 R-3 仍未闭环**（stage2 断言 6 条 skip，研究断言 3 pass / 0 fail / 6 skip（C 断言已升级闭环））；**③ 待授权项**（R-1 stealth 真机、D-1/D-2/D-3、真机台账 64/80 全停中）；**④ 记录在案的残留**（明文 key 历史、手机号明文、do_POST 行数超标等）。

## 1. 当前基线（已验证，2026-11-18）

| 项 | 值 | 口径 |
|---|---|---|
| 版本 | `6.5.1`（`docs/facts.json`） | 已验证 |
| Python 用例 | **1274 collected**（facts.json 实测；v6.5.1 发版时点 1272 passed / 8 skipped，见 CHANGELOG） | 已验证 |
| 覆盖率 | `solver/` floor **80**（实测 ~90%）· `captchas/` floor **28**（Win 29.17% / Linux CI 28.55%，真机实验脚本已豁免出分母） | 已验证（`docs/coverage-policy.json`） |
| Go | **58 个 `Test*`**，`-race` 全绿 | 已验证 |
| findings / openapi | 54 条三态结论 · 14 操作双向一致 | 已验证 |
| `service.py` | 3243 行（facts.json 实时计数） | 已验证 |
| 四类验收（v6.5.1 终态） | UI 70/70 · realcalls 46/46 · E2E 40/40 · 复审 PASS（8 域空 diff SKIP） | 已验证（`evidence/RELEASE-6.5.1.json`） |
| 真机预算台账 | **64 / 80，累计失败 5/5 → 按纪律全停**（`policy.md` §2） | 已验证 |

## 2. 已落地能力（本轮核验确认）

- **服务面**（`solver/` + `gocfsolve/`）：求解链 cfsolve → pydoll → Camoufox → FlareSolverr，`route=auto`；回落最多 2 跳、`ip-blocked` 不换后端；SQLite(WAL) 缓存热路径零 Python 参与；`/health /stats /metrics /audit` + `X-Request-Id`；`/createTask` `/getTaskResult` 兼容层；按域令牌桶（`solver/ratelimit.py`，默认 `--rate-per-host 1/30`，只对冷求解计数）。
- **Go 客户端**：`SolveWithOptions`（`cfsolve.go:495`）透传 `Want/Route/Sitekey`；240s 探活 client；rate-limited failover 不摘节点（契约用例锁定）。
- **两页 UI**（`/`、`/console`）：共享令牌 `solver/ui_tokens.py`；E-4 五条不变量测试锁死；42 单测（console 21 + statuspage 21）+ 35 真浏览器 E2E。
- **公开站**（`site/`）：14 路由中英双语、axe 0、Lighthouse 桌面 100×4、CSP hash 门禁、移动档 Lighthouse 已接 CI。
- **研究台**：`scripts/corpus.py` / `scripts/research.py` / `run.py`；6 类 stage2 断言 + 3 条 source 假设，合成样本永不 skip。
- **MCP stdio**：`python run.py mcp`，5 工具（`docs/MCP.md`）。
- **v6.5.1 headed 窗口治理**：出生即屏外（`service.py:434`）+ 300ms `win-janitor` 守门线程（`service.py:602`，juggler 忽略命令行参数的兜底）+ 4 条离线单测；8892 实例实测 12s 后屏内大窗口 0。
- **MOSS 阿里滑块实验链**（`captchas/aliyun/moss_*`）：纯协议 E2E 打通 + camoufox 批量产号 + 刷新绕滑块冷却，9 张截图证据；`moss_accounts.jsonl` 的 key 已脱敏为 `sk-<REDACTED>`。
- **R-3 本地补丁**：`tools/cfsolve-patches/cfsolve-call-depth-limit-20261113.patch`（Run 深度上限 256，挂点变结构化失败并报告 pc），`PATCHES.json` 登记 `applied`，`cargo test --lib` 245 passed。

## 3. 真实未完成 / 未完整闭环清单（交付执行方的任务卡）

> 执行纪律：红灯先行 → 改 → 定向验证；一卡一 commit；证据落 `plans/证据/` 或 `evidence/`；L3 卡须独立 Critic；不许为过门禁放宽断言。**真机动作在台账重置（用户批准）前一律不做。**

### 3.1 工程收口（可离线做，L1）——v6.5.1→v6.6.0 已全部落地

> W1–W4 十五卡对应关系：N1–N4=T02–T04；本版《下一步改进指南 v6.5.1→v6.6.0》
> 的 T05–T15 落点：数字刷新 1bded3e/9525728、NOT-REVIEWED 钉死 1298f3e、
> coverage selftest 6a93ea5、moss NameError 修复 0e2b5d0、ruff 清零 c2bb713、
> run-pool/run.ps1 参数 b5fd04e、运维实证入主文档 215c1f8、phone 脱敏 c94342e、
> 断言证据入库 6f8660c、上游路径恢复 bf6fde8。

| # | 级别 | 做什么 | 精确落点 | 验收 |
|---|---|---|---|---|
| **N1** ✅ b6407c4 | P2 | geoip 决策反转收口：SKILL.md §6.5 仍写"geoip 已被否决…保持 geoip=False"，与代码矛盾；`maxminddb` 是 `camoufox[geoip]` extra 但未列入 requirements.txt（本机靠环境巧合可用）；MMDB 首次下载 116MB 无任何提示 | `.claude/skills/cf-bypass-methods/SKILL.md:138-142`（改为与 `service.py:426` 一致：geoip=True 已于 ff36cc3 启用 + 理由）；`requirements.txt` 补 `maxminddb`（或 `camoufox[geoip]` 声明）；启动日志或 `/health` 提示首次 116MB MMDB 下载 | `pip install -r requirements.txt` 幂等；`validate-doc-commands` 不受影响；SKILL.md 与代码零矛盾 |
| **N2** ✅ 2d2b9e6 | P3 | engines 工厂 geoip 死分支：`engines.py:114` 仍 `geoip=False`，而 camoufox 实际走 `service.py:426` 的 `geoip=True` 工厂；若未来复用该工厂会静默退回 False | `solver/engines.py:114`：对齐 geoip=True，或加注释标明"camoufox 走 service 工厂，此分支仅 cloakbrowser/patchright" | `tests/test_engines_factories.py` 相应更新后绿 |
| **N3** ✅ 2d2b9e6 | P3 | `--headed` 帮助文本过时：仍写"有头模式（调试用）"，与 CHANGELOG 运维实证"managed 站生产必开"矛盾 | `solver/bootstrap.py:91` | 文本更新；`test_bootstrap` 绿 |
| **N4** ✅ eb57871 | P3 | cfsolve 上游跟踪：`PATCHES.json` 的 `upstream_ref` 仍写 "master@2026-10-29 + **4** local patches"，实际已有 **5** 个补丁；上游 `chris124567/cfsolve` 已出现 `profiles/safari-26-ios.json` 新 persona 与 capture-proxy 录制流，主项目未对齐 | `tools/cfsolve-patches/PATCHES.json` 修正计数；在本文件 §3.2 R-3 行维护上游版本锚点 | PATCHES.json 自洽；R-3 行含上游最新 release 锚点 |

### 3.2 研究线（部分依赖真机/上游）

| # | 现状 | 剩余动作 |
|---|---|---|
| **R-3** | 本地 call-depth 补丁已入库（挂死→结构化失败）；**stage2 变体仍未收敛**，6 条 stage2 结构断言维持 skip；研究断言 2026-11-19 升级后实测（`plans/证据/research-assertions-2026-11-19.json`）：**3 pass / 0 fail / 6 skip** —— `C_encoder_shape` 已按 jsd.md 实证升级为运行时构造特征（charCodeAt/fromCharCode/atob），旧 fail 定性为断言过时并闭环；样本 `2026-11-04-6c02e277` 仍未走到 stage2 | ① ~~向上游提 call-depth PR~~ → **上游 2026-11-07 起明确不收 PR**（README Contributions 政策，作者建议 fork）——补丁与 MB 级回归单测已推到 fork 分支 `lza6/cfsolve@fix/vm-call-depth-limit`（commit a33082b，可直接 diff/ cherry-pick）；主项目继续以本地 patch 形式维护（`PATCHES.json` 已登记）；② 补一份走到 stage2 的真实会话快照（需真机预算重置）；③ ~~处置 C_encoder_shape fail~~ ✅ 已升级断言语义闭环（2026-11-19）；④ 任何回放/构建必须走 `scripts/run_limited.py --max-mb 2048`（峰值 ~5GB，已有 40GB 打满事故） |
| **R-1** | 机械链路 PASS（本地 Chromium 绕过 license，Turnstile 测试 key 7.3s），**stealth 有效性未验证**；用户方向为自建 stealth 引擎，未启动 | 自建 stealth 引擎方案 + 真机验证（等台账重置） |

### 3.3 待授权（外部凭证 / 真机出站 / 人工，未执行）

| # | 项 | 阻塞点 |
|---|---|---|
| **R-2** | ~~真实 CF 站复验~~ **CLOSED**（2026-11-11 udemy 端到端：出口一致、6.03s 拿 clearance、回放 200、审计读回，`evidence/R-2-20261111.json`） | 无 |
| **台账** | 真机预算 64/80、累计失败 5/5 → **全停**；任何真机动作先等用户批准重置 | 用户批准 |
| **D-1** | 公开站部署（Cloudflare Pages）+ 域名绑定 | 域名 + API token（用户决定） |
| **D-2** | Search Console / Bing / 百度验证 + sitemap 提交 + 关键词 volume 回填 | 三平台账号 + DNS/HTML 验证不在本机 |
| **D-3** | 英文母语审校签字（`site/content/EN-REVIEW.md` Sign-off 仍 pending） | 需人工，AI 不可代签 |
| **依赖 D-1** | 根 README 顶部公开站链接 + `llms.txt`（现在加会指向不存在的站点） | D-1 落地后一并做 |

### 3.4 已知残留（记录在案，按需处置）

| # | 内容 | 位置 | 处置建议 |
|---|---|---|---|
| S-1 | git 历史 `835723e` 含明文 key（工作树已脱敏，公开仓库历史可见） | git history | 彻底清除需 history rewrite（用户知情，待拍板） |
| S-2 | MOSS 账号台账手机号明文（key/token 已脱敏，phone 未脱敏） | `captchas/aliyun/moss_accounts.jsonl:1` | 若对外公开仓库，脱敏 phone 字段 |
| S-3 | `do_POST` 200 行，超出项目自定 50 行标准（剩余为状态机本体，拆=重写） | `solver/service.py` | 维持 P3 记录（`docs/项目规格.md` L7），不强行拆 |
| S-4 | geoip 收益无同站双臂 A/B 数据；ff36cc3 的"万号实证"未留仓库证据 | `evidence/` 无 geoip 记录 | 真机预算全停，只能标注"决策依据为运维实证"（N1 落地时在 SKILL.md 写明） |
| S-5 | v6.4.1 独立审查记录不修的 2 条 P3：主链"握手后"许可证拒绝 → 500；cloakbrowser 二进制下载失败 → 500（都需可用许可证才能真机触发） | `计划书` 旧版 §4.4（git 历史） | 保持记录不修，遇真机再归位 `not-configured` |
| S-6 | 未跟踪文件：`local_solver.err.log`、`plans/证据/research-assertions-2026-11-18.json` | 工作树 | 断言 JSON 已入库（11-18 与 11-19 两份）；err.log 按用户既定决策不处理 |

### 3.5 v7.0 十二卡 × B0–B15 参考对标对账（2026-11-13 完成态，保留备查）

> v7.0 指南（`git show 9dbb3ab:计划书/下一步改进指南.md` 可找回）与参考对标审计（原根目录《参考的结果计划指南.md》，`git show 12e35af:参考的结果计划指南.md` 可找回）的处置结果。全部闭环，仅 R-3 上游修复受阻（见 §3.2）。

| 卡 | 内容 | 状态 | 落点/证据 |
|---|---|---|---|
| T-01 | smoke 默认鉴权必红（P1-01） | ✅ 12e35af | `run.py` `_smoke_get` 带 Bearer；`tests/test_runpy.py` |
| T-02 | SSRF 断言假阳性（P1-02） | ✅ 12e35af | 精确断言 400+`invalid-request`；负向用例在 `test_runpy.py` |
| T-03 | verify 纳入 smoke + doctor `--gate` | ✅ | verify 14 步（含 `doctor-gate(环境快照)`）；`scripts/doctor.py --gate`（仅 FAIL 非 0）；`tests/test_doctor_proxypool.py` 锁行为 |
| T-04 | 版本锚点盲区（P2-02） | ✅ 12e35af | `validate-docs.mjs:66` 查项目规格版本行 |
| T-05 | 文档命令对账 | ✅ | `scripts/validate-doc-commands.mjs`（正负双向验证过）；进 CI |
| T-06 | 前端三类交互 E2E（P2-03） | ✅ 12e35af | `site.spec.ts:177-215`（theme 持久化 / 语言双向 / 移动菜单） |
| T-07 | cfsolve-setup 装配向导（B2） | ✅ | `scripts/cfsolve_setup.py` + `run.py cfsolve-setup` + run.ps1 ValidateSet 同步；15 条单测 |
| T-08 | 按域令牌桶限流（P2-05） | ✅ 12e35af + 本轮 | `solver/ratelimit.py`（默认 `--rate-per-host 1/30`，只对冷求解计数）；Go 契约用例 `TestPoolRateLimitedFailsOverWithoutBlamingNode` |
| T-09 | captchas 离线回放测试（P2-04） | ✅ 12e35af + 本轮 | `tests/test_captcha_pure.py`（8 家纯函数）；arkose 门禁依赖 pycryptodome（CI 红灯根因，已修） |
| T-10 | 故障注入测试 | ✅ | `tests/conftest.py::fault_inject` + `tests/test_fault_injection.py` 7 条 |
| T-11 | 未覆盖行逐段标注（P3-01/02） | ✅ 12e35af | `docs/覆盖率盲区标注.md` |
| T-12 | 移动档 Lighthouse + 发版 | ✅ | 移动档已接 CI；v6.5.0 已发版（tag 推送、双绿、`evidence/RELEASE-6.5.0.json`） |
| B0 | Go 5s 探活超时（P0-01） | ✅ 12e35af | `cfsolve.go:592` 用 240s `hc`；慢 solver 用例 |
| B11/B12/B13 | prewarm force / token 竞态 / want 缓存键（P1-05/06/07） | ✅ 12e35af | `prewarm.py:156`、`.env.lock`、`service.py` cache_key 含 want |
| B1 | 验收链 | ✅ 12e35af | 同 T-01/02/03 |
| B14 | detect 移植丢信号（P2-10） | ✅ 12e35af | `detect.py` 重写 + `tests/fixtures/detect/cases.json` + CI 特征表自检 |
| B15 及其余 P2 | Go fail-open/共享切片/ErrNoChallenge、合规 NOTICE 等 | ✅ 12e35af | CHANGELOG `[Unreleased]` 全清单 |
| P1-03/04 | 许可证合规（NPOSL-3.0 / captcha-solver 无 LICENSE） | ✅ 12e35af | `NOTICE` 记录 + `docs/检测-防护识别.md` 更正 + detect 自有整理 |
| **R-3 上游修复** | cfsolve `PreparedSession::try_new` call_plan 挂住 | ⏸ 受阻 | 本地补丁已入库（见 §3.2 R-3 行）；上游 PR + stage2 真实样本待办 |

### 3.6 工程线九项（v6.4.x，全部闭环）

| # | 项 | 状态 | 落地内容 | 验证证据 |
|---|---|---|---|---|
| **A1** | 文档数字漂移 + 模块指标进单一事实源 | ✅ | `docs/facts.json` 增 `module_coverage` 与 `service_py_lines`；`validate-docs.mjs` 增锚点规则 | `validate-docs.mjs` 一致；负向注入 → exit 1 且指名模块 |
| **A2** | 两份同名状态文件合并 | ✅ | 根与 `plans/状态/` 两处已删；2026-11-18 重写版为当前唯一状态源 | `git show 12e35af:参考的结果计划指南.md` 可找回 |
| **C1** | 幻影参数 `--max-body-bytes` | ✅ | 413 `hint` 改为"上限固定 65536 字节（没有可调参数）"；`docs/API.md`、`openapi.json` 同步 | `rg max-body-bytes` 只剩 CHANGELOG 历史条目与归档 |
| **C2** | `/detect` 写审计 | ✅ | 成功/缓存命中/失败各一行；`GET /audit` 读得到 | 新增 3 条用例断言审计真落盘且可读回 |
| **C3** | 404 进 `ErrorCode` + HEAD/OPTIONS/405 语义 | ✅ | `NOT_FOUND`/`METHOD_NOT_ALLOWED` 入码表；`do_HEAD`/`do_OPTIONS`(204)；其余方法 405+`Allow` 且先读掉 body | 新增 9 条用例（keep-alive 错位、204 无 Content-Length 等） |
| **C4** | `openapi.json` 补服务端错误分支 | ✅ | `/solve` `/detect` 补 500/502/503/504；404 在 `info.description` 整体说明（逐操作声明不可达）；`validate-openapi.mjs` 规则 4 | 负向注入 418 → 红并指名；selftest 覆盖 |
| **C5** | Go 客户端补 `Want`/`Route`/`Sitekey` | ✅ | `SolveOptions` + `SolveWithOptions()`；`Clearance` 补 `Token`/`AWSWAFToken`，产物校验按 want 选字段 | 6 条 Go 用例（透传 + 产物解析）；`-race` 全绿 |
| **D1** | 两页公共 JS 去重 | ✅ | `solver/_page_common.py`（`__COMMON_JS__` 占位注入）；`getJSON`/`setKV` 行为统一 | 36 条两页单测 + 真浏览器 E2E 35/35；`_page_common.py` 100% |
| **D2** | `do_POST` 下沉嫁接层旁路 | ✅（部分） | 旁路 60 行搬 `solver/multicaptcha.py::handle_compat_bypass()`（纯函数）；`do_POST` 227→200 行 | 17 条纯函数边界用例；**残留**：仍 200 行（状态机本体，拆=重写，S-3 记录在案） |

### 3.7 UI/UX 残留五项（v6.4.x，全部处理完毕）

| # | 问题 | 实测位置 | 处理 |
|---|---|---|---|
| **V-1** | 死 npm 脚本 `"og": "node scripts/og.mjs"` | `site/package.json` | ✅ 已删（scripts 17 条，无 og） |
| **V-2** | 文档"18 hash" vs 实际 20 | 原 V1 指南 | 已随旧文档删除消解 |
| **V-3** | `ui-v1/phase0-baseline.md` 不存在 | `plans/证据/ui-v1/` | 不补——`bundle.json` 已覆盖同一批数字 |
| **V-4** | 空目录 `site/public/fonts/`、`site/public/og/`、`site/styles/` | `site/` | ✅ 已删除 |
| **V-5** | 证据 README 引 v6.3.1 CI run | `ui-v1/README.md:27` | ✅ 已更新为 v6.3.2 双 run |

## 4. 决策与风险存档（仍有约束力）

### 4.1 风险登记（仍有约束力）

| 编号 | 内容 | 约束 |
|---|---|---|
| **R9b** | glassdoor.co.uk 出口疑似被提分：同站当天连打 12 次后 60s 解不出 | 同一出口不反复打同一站；换出口必须换 `--egress-id`（被 `policy.md` §2 引用） |
| **R13** | WAL 切换竞态未确定性复现（同进程/跨进程持锁、90 次裸构造均未稳定命中） | 已有有界重试把概率压到观察不到，**不能宣称"不可能再发生"**；回归只覆盖重试逻辑（被 `solver/cache.py:401` 引用） |
| **R14** | 测试侧 `ResourceWarning: unclosed database` | 已修（v6.3 B4）：根因是 conftest 只钩了 `solver.cache`、漏了脚本模式 `cache` 模块 |
| **批次 C 抖动** | 超大 body 客户端写一半收到 RST，约 **1/30** 读不到 413 | `DRAIN_MAX_BYTES`/`DRAIN_TIMEOUT` 有界读；用例同守"拿到 413"与"秒级收尾"两个边界（被 `tests/test_service.py:916` 引用） |
| **R10/R15** | 缓存命中路径 32 并发 p99 ≈1s；读路径串行进锁 | 单进程建议 ≤16 并发；实测无退化（hot 5959.6 QPS / p99 2.72ms） |

### 4.2 决策记录

| 编号 | 决策 / 风险 |
|---|---|
| **geoip（更新版）** | 早期结论曾否决 geoip（运行期 MMDB 下载 + 隐私面）。**2026-11-13 起 ff36cc3 反转为 `geoip=True, humanize=True`**（`service.py:426`）：万号运维实证指纹与出口 IP 地理脱钩是 CF 提分输入之一。代价：首次下载 116MB MMDB 到 `AppData/Local/camoufox/`，`maxminddb` 依赖未显式声明（见 N1）。本表以代码为准 |
| **真机纪律** | 台账 64/80、失败 5/5 全停；同站串行 ≥30s；换出口必须换 `--egress-id`；CI 永远离线（`policy.md` §2） |
| **依赖取舍** | 生产不引 `prometheus_client`；dev 引 `hypothesis`+`ruff`；不引 `mypy`、FastAPI/pydantic（零新依赖） |
| **405 而非 501** | 该资源不支持的方法回 405+`Allow`（501 语义是"服务不认识方法"，且 501 不在 `STATUS_BY_CODE` 契约内） |
| **`SolveWithOptions` 不碰本地缓存** | 本地缓存键=域+出口，前提是产物恒为 clearance；`want=turnstile` 一次性 token 混入会污染整个 TTL，要求调用方显式单次使用 |
| **明确不做** | captchas 11 求解器全量真机验证；captchas 升主链路；换浏览器底座（含 lightpanda）；在线 demo/账号/支付；全站 3D/滚动劫持/粒子雨；用评分表做高数字 |

### 4.3 参考库结论（2026-11-05 重分类后复核；2026-11-11 全库对标后增补）

- `captcha-solver` 系已以 `captchas/` 形式接入；`ohmycaptcha`/`cipherwire__disarm`/`FlareSolverr` 已在 v6.2 整合；双档门禁/流量录制思路已落地。
- `lightpanda-io__browser`（Zig 无头浏览器）：**P3 观察**，JS 覆盖面与反检测能力未知，不建议换底座。
- 纯协议复现类（`CaptchaFoxChallengeSolver`、`CloudFlareInvisibleSolver`）与本项目 cfsolve 同族，无新增工程手段。
- 付费 API 客户端（`nonecap`/`nopecha`/`cf-turnstile-token`）违反 `policy.md` 红线，排除。

**2026-11-11 全库对标（原根目录《参考的结果计划指南.md》，1736 个项目枚举后）的存档结论**：

- **Kasada**（`B00H0O__kasada-solver`，MIT）：唯一可落地形态是"浏览器 mint sidecar"（Node 20 + 真实 Chrome + 隔离 context mint `x-kpsdk-ct/cd/h/v`），像 FlareSolverr 一样做新 `BackendId`——**不是纯协议**；与零依赖/单进程定位冲突，成本高。真要做先过 `.claude/skills/cf-bypass-methods/SKILL.md` 的新增方法判定。
- `scrapfly/Antibot-Detector`（NPOSL-3.0）与 `captcha-solver`（无 LICENSE）：许可结论已进 `NOTICE`，detect 特征表已改为自有整理（12e35af）。
- 参考库中其余反爬/浏览器/代理项目均未产生新的可落地工程手段；完整逐项结论在 git 历史（`git show 12e35af:参考的结果计划指南.md` §附录 A）。

### 4.4 审查记录

| 轮次 | 范围 | 结论 |
|---|---|---|
| v6.0 独立复审 ×3 | 研究工程化 | 修 7 条真缺陷（研究指标 schema 错配/三态伪造、脱敏闸门失效、diff 判据回退等） |
| v6.3.1 收口 | 公开站 + 两页 UI | 门禁补齐（check-env/check-out/OG/og:image 12 页）；CI 全绿 |
| v6.3.2 独立审查 | `74c72db..928ab6a` | 3 Critical + 7 Should-fix，逐条核实全部成立并修复（idle E2E 恒真、窄屏遮挡、视差失效、标签数值、版本漂移、门禁自测未接 CI、`importorskip` 缺依赖、裸导入扫描可绕过、覆盖率命令形式、占位符边界） |
| v6.4 独立审查 | 工作树全部改动（C1–C5、D1–D2、A1、V-1/V-4/V-5、三道门禁脚本） | 1 P1 + 1 P2 + 6 P3，逐条核实全部成立并已修：**P1** Go 客户端只认 `cf_clearance`，`want=turnstile` 永远报错 → `Clearance` 补 `Token`/`AWSWAFToken`、校验按 want 选字段；**P2** 405/OPTIONS 不读 body → 同连接下一条请求被残留字节顶成 501 HTML → 两处先 `_read_body_raw()`；**P3** 逐操作 404 不可达 → `info.description` 整体说明；204 带 `Content-Length` 违反 RFC 9110 §8.6 → 删；状态页空态丢 `chips` class → 补回；`CONNECT` 并入 405；detect 早退审计 `elapsed` 恒 0 → 入口取时间戳；`toleranceFor` 注释与实现不符 → 补 ±2 容差 |
| v6.4.1 真进程 E2E + 独立审查（2026-11-10） | `scripts/e2e_local.py` 全 40 条；独立审查员只读核 `git diff` + `cloakbrowser` 包源码 | **1 P1 已修**：`cloakbrowser` 装上但无许可证时，`multicaptcha.solve_async` 只接 `ImportError`，`CloakBrowserLicenseError` 落到 `INTERNAL` → HTTP 500。修法：按"依赖不可用"归 `NOT_CONFIGURED`(503) + 登录提示、不打 traceback；补 1 条单测（先红后绿）。**Verdict: Approve**。另 2 条**记录不修**（P3，见 §3.4 S-5）：主链"握手后"许可证拒绝 → 500；二进制下载失败 → 500（都需可用许可证才能真机触发） |
| v6.4.2 站点同步（2026-11-10） | v6.4.1 的 `site-ci` 失败日志 | **1 P2 已修**：站点 `/changelog` 头条停在 6.4.0、`tests.python` 仍是 1065，与 facts 的 6.4.1 / 1066 不一致——版本号只在仓库侧同步，漏了站点内容。修法：中英 `/changelog` 补条目、benchmark 同步；`test:content` 11/11、`verify:site` 14 路由 axe 0、`test:e2e` 19/19 |
| v6.4.3 全量验收复核（2026-11-11） | 发布候选：五处版本号 / 站点版本页 / 状态文档 / 验收证据 | 首轮 **Request Changes**（1 P1 + 1 P2 + 4 P3，逐条核实成立并修复）：P1 证据文件未入库 → 补齐验收报告与 RELEASE 证据；P2 LCP 数字与实测不符 → 修正；P3 UI E2E 文本证据、压测 manifest、CHANGELOG 证据段 → 已补。修复后 **Verdict: Approve**；CI：`ci` 42942791503 / `site-ci` 42942797220 全绿 |

**Approve 语义**：严格审查后未发现阻塞性问题，不是"代码完美"。新节点标 Done 前必须有 Approve 记录（写进本节，`policy.md` §3 引用）。

## 5. 文档地图

| 想知道什么 | 看哪里 |
|---|---|
| **状态 / 待办 / 决策 / 风险** | **本文件** |
| 系统边界与承诺 | `docs/项目规格.md`（冲突以它为准） |
| 接口契约 | `docs/API.md` + `docs/openapi.json` |
| MCP 接入 | `docs/MCP.md` |
| 质量门禁数值 | `policy.md` |
| 测试数/覆盖率/版本单一事实源 | `docs/facts.json`（`validate-docs.mjs` 把关） |
| 覆盖率盲区逐模块理由 | `docs/覆盖率盲区标注.md` + `docs/coverage-policy.json` |
| 结论库 | `docs/findings.json`（`validate-findings.mjs`） |
| 历史施工图（v1.1→v5.0） | `plans/archive/`（结论勿再引用） |
| 验收证据 | `plans/证据/` + `evidence/` |
| cfsolve 构建/装配 | `docs/纯协议-cfsolve.md`；`python run.py cfsolve-setup` |
| 过盾方法选型 | `.claude/skills/cf-bypass-methods/SKILL.md` |
| 版本变更史 | `CHANGELOG.md` |

## 6. 验证命令速查

```text
python -m pytest tests/ -q                                         # 全量（1274 收集）
python -m pytest tests/test_console.py tests/test_statuspage.py -q # 两页 UI（36）
python scripts/verify_ui_e2e.py                                    # 两页真浏览器 35/35（需 CHROME_PATH）
cd gocfsolve && go test -race ./...                                # Go 58
node scripts/validate-docs.mjs --coverage-json=coverage.json       # 文档数字一致
node scripts/validate-findings.mjs; node scripts/validate-openapi.mjs
node scripts/gates.selftest.mjs                                    # 门禁自测 24/24
python scripts/check_repo_hygiene.py
cd site && npm run build && npm run csp && npm run verify:csp && npm run verify:site && npm run test:e2e && npm run test:content
```

---

*2026-11-18：基于 `de81d8d`（v6.5.1）代码级核验重写。旧版（2026-11-13，基线 v6.5.0）与根目录《参考的结果计划指南.md》（2026-11-18 增量对标，ANALYSIS_ONLY）删除，有约束力内容已并入本文件；git 历史可查。*
*2026-11-18：**v6.6.0 发版**——W1–W4 十五卡全落地（geoip 收口/计划书补全/数字刷新/NOT-REVIEWED+coverage selftest 钉死/moss NameError/ruff 清零/run-pool 参数/运维实证/phone 脱敏/上游路径），四类验收 UI 70/70 · realcalls 46/46 · E2E 40/40 · 发布 diff 复审 4 域 PASS（`evidence/acceptance.json` overall=passed），site 全门禁绿，tag `v6.6.0` 推送，**CI 双绿**（`ci` run 44308924245 + `site-ci` 44308806961/44308806993）；全程零真机（台账 64/80 不变）。
*2026-11-18 补全：恢复 §3.5–3.7 对账表（v7.0 十二卡 × B0–B15 / 工程线九项 / UI 五项）、§4.1 风险登记（R9b/R13/R14/批次 C/R10/R15）、§4.3 参考库结论与全库对标存档、§4.4 审查记录七轮 + Approve 语义——这些内容仍被 `policy.md` §3、`solver/cache.py:401`、`tests/test_service.py:916` 引用；旧版全文 `git show de81d8d:...` 可查。*
