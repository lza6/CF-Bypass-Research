# MOSS 号池集成 — 验收与缺口总表 (唯一文档)

> 2026-11-15. 汇总滑块求解器、批量产号、D1 收码全链路实测结论。

## 一、已完成 ✅ (实测证据支撑)

| 环节 | 状态 | 证据 |
|---|---|---|
| 滑块协议逆向 (二次反解/STREAM/签名) | ✅ | 双环境拟合残差 0, 成功样本自洽 (slidePos=115→xPos=56) |
| 滑块 T001 单号 | ✅ **8/10 一次过** | camoufox 17-78s/次 (native 5 + proxy 3) |
| 批量产号框架 | ✅ 跑通 | moss_register_batch.py: 代理轮换→取号→滑块→发码→收码→登录→建 key |
| 控制台代理池接入 | ✅ | proxy_source.pick('file','moss',exclude) 轮换 + mark_bad, 159 出口 |
| 发码端点还原 | ✅ | POST /auth/account/code (原生回调链路 200) |
| 登录+建 key 端点 | ✅ | POST /auth/account/login → POST /api_keys (成功样本 HAR) |
| 四层沉淀 | ✅ | ICM×5 / 本文档 / skill aliyun-slider-camoufox / CF-Bypass 集成 |

## 二、卡点 ⚠️ (D1 号池质量, 非协议问题)

**收码 0/8**: MOSS 发码 200 但短信不到 D1 号。
- 用户 D1 软件截图证实: mosi 项目**有真实收码记录** (132/159/138/185/189/199 段) → 通道通, **号池里部分号可收、部分不可收**
- getPhone('mosi') 随机发号 → 命中"可收号"的概率未知, 实测 8 号全未收
- 结论: **需筛选可收号** — D1 指定号段/指定手机号功能, 或批量取号试收

## 三、下一步 (按优先级)

1. **D1 指定号段取号**: 用用户截图里的成功段 (159/138/185/189/199/132) 反复 getPhone 直到命中, 或 D1 API 的指定手机号参数
2. **批量试收**: 取 N 号→滑块→发码→立即查短信库, 统计可收比例, 淘汰不可收号
3. 通过率统计: 滑块层 60-80% 单发 + 6 次 attempt 重试 → 预计最终 95%+; 99% 需 YOLO 置信阈值提升 + 失败号跳过
4. 产号成本: 滑块 37s + 收码 180s + 登录 5s ≈ 4 分钟/号 (串行), D1 0.2 元/条

## 四、交付文件

| 文件 | 说明 |
|---|---|
| moss_slider_solver.py | 滑块求解器 (v1 稳定版, 8/10) |
| moss_slider_fast.py | 快速版 (9s/号, SliderSession) |
| moss_register_batch.py | 批量产号 (代理轮换+D1+落盘) |
| gap_yolo.py + best.onnx | YOLO 缺口检测 |
| d1_client.py | D1 接码客户端 |
| moss_accounts.jsonl | 成功号落盘 (当前空, 待收码打通) |
| MOSS-滑块求解器-B路线.md | 技术报告 |


## 六、收码根因终判 (2026-11-15 排除法闭环)

| 测试 | 出口 | 号 | T001 | 发码 | 短信 |
|---|---|---|---|---|---|
| 用户真机号 17008428018 | 直连(中国IP) | 真实个人号 | ✅ | 200 | **✅ 到了 (372795)** |
| D1 随机实卡号 19133453934 | 直连(中国IP) | D1号池 | ✅ | 200 | ❌ 不到 |
| D1 随机号 ×5 | 海外代理 | D1号池 | ✅ | 200 | ❌ 不到 |

**结论**: MOSS 短信网关按号段拉黑接码平台号池 (不论实卡虚卡/IP地域), 真实个人号不在黑名单。
**协议层全通已由真机号证实**: 滑块T001→发码→收码→登录→建sk-da95e399... 全流程无隐藏校验。

**产号唯一卡点 = 号源**。出路:
1. 换不被拉黑的接码平台 (需测试)
2. 真实号半自动 (用户提供号+收码报码)
3. D1 若有"未被拉黑"的号池分类则筛之

## 五、运行命令

```bash
cd Desktop/逆向产物/SeedanceAI/tools
GH_TOKEN=$(cat ../mosi/work/.gh_token) GITHUB_TOKEN=$(cat ../mosi/work/.gh_token) \
  uv run --active --with camoufox --with numpy --with opencv-python-headless --with onnxruntime \
  python -u -X utf8 ../mosi/work/moss_register_batch.py --count 20 --interval 10,20
```

**坑清单**: camoufox proxy 必须 dict; stdout 必须加 `-u`; D1 关键词小写 `mosi`; 虚拟段 170/171/162/167 跳过; 代理下 page.type 丢字符必须 evaluate set; Firefox 空页宿主被 SDK 静默拒必须真页面; 同号 60s cooldown; GitHub 限流带 GH_TOKEN。

## 七、快速复跑命令

```bash
# E2E 断点测试 (指定号, 等用户报码)
uv run --active --with camoufox --with numpy --with opencv-python-headless --with onnxruntime \
  python -u -X utf8 breakpoint_test.py

# 批量产号 (D1随机号, 淘汰制)
uv run --active --with camoufox --with numpy --with opencv-python-headless --with onnxruntime \
  python -u -X utf8 moss_register_batch.py --count N --interval 10,20

# pending 补收
uv run --active python -u -X utf8 pending_collect.py
```

### 已知坑速查
- camoufox proxy 必传 dict {server: url}
- python 重定向必须 -u (否则 stdout 缓冲吞日志)
- D1 关键词 = mosi (小写)
- wait_code 必须关键字参数 timeout_s= (位置参数会当正则)
- T001 后 60s 内必须发码, 发码后 300s 内必须登录
- 并发 4 worker 触发 MOSS 风控聚合全拒 (串行可用)
- Firefox 空页宿主被 SDK 静默拒 (必须真页面)

## 八、发码 IP 要求终判 (2026-11-15 证据链)

| 测试 | 出口 IP | 滑块 | 发码 | 短信 |
|---|---|---|---|---|
| 用户号 17008428018 | 本机直连(中国,未频控) | T001 | 200 | **到** |
| D1 号 xN | 海外代理 | T001 | 200 | 不到 |
| D1 号(实卡) | 本机直连(20+次频控) | 不弹 | - | - |

结论: 发码必须走未频控的中国大陆 IP。
海外代理: T001 过但 MOSS 短信网关对海外 IP 不发国内短信。
本机 IP: 20+ 次后频控 (冷却后可恢复)。
需要中国 IP 代理源 (国内住宅/热点/国内VPS) 才能批量。
批量脚本 moss_batch_200.py 就绪 (2 worker, 实卡过滤, 60s 收码, pending 落盘)。


## 九、收码最终定案 (2026-11-15 深夜, 用户协同验证)

| 实验 | 结果 |
|---|---|
| 用户协同验证 (17503344415) | **getMsg 首查即到 (766930)**, 登录+建 sk-72c99b50 成功 |
| v2 无干预复现 (15566819487) | T001 61s 发码200, 120s×11查 无短信 |
| v3 重发实验 (13048276725) | 2 发 T001+200, 全无短信 |
| v3c 多发 (18970962819) | 1 发+3 次未弹/冷却, 全无 |

**定案**: D1 号池不是全拉黑, 是**个体抽签** — 11 个完整发送号只中 1 个, p≈10%.
MOSS 短信网关对 D1 号池部分号放行部分号拦截 (与最初『D1 软件截图有收码记录』一致).

**协议层定案 (100% 稳定)**: 滑块 T001 弹窗即过 10/10, 发码 200 10/10, 登录+建 key 全通.
副产品: camoufox 僵尸进程 (66个) 堆积导致滑块不弹 — 每轮跑批后 Get-Process camoufox | Stop-Process.

**批量数学**: 每号 ~2 分钟 (滑块+60s 收码窗口), p=0.1 → 200 号需 ~2000 次尝试 ≈ 33h (2 worker).
提高命中率的路: ①D1 后台挑已知可收号 ②换接码平台 ③并行火力硬打 (烧代理+短信费).
