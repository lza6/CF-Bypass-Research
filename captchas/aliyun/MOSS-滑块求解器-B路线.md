# MOSS 阿里滑块 — 纯协议求解器 (B 路线: 反检测浏览器 + 程序化输入)

> 2026-11-14. 与 `MOSS-阿里滑块-完整逆向报告.md` 互补: 那份是密码学链路, 这份是求解器实现与实测.

## 已 100% 确认的核心机制 (全部实测验证)

### 1. 二次反解 (位置层) — **F015 → F001 的钥匙**

拼图位移与鼠标行程**不是 1:1**, 是二次关系 (残留 ~0):

```
piece.left = 0.003552 × m² + 0.0769 × m
```

- 系数为阿里 V3 通用常量 (与 CF-Bypass-Research/captchas/aliyun 的 `_COEF` 完全一致)
- 本机双重独立验证: puppeteer 拖动采样 25 点最小二乘拟合 (残差 0.000px), CF-Bypass 源码常量比对
- 反解 (给定缺口位置求鼠标行程):

```python
def invert(target):
    a, b = 0.003552, 0.0769
    return (-b + math.sqrt(b*b + 4*a*target)) / (2*a)
```

- `slidePos` = 鼠标行程 m; `xPos` = piece.left (拼图块最终位置)
- 成功样本自洽性验证: slidePos=115 → piece=55.8 = xPos=56 ✓

### 2. TrackList (行为加密 data)

```
plain_json = JSON.stringify({TrackList:{mc,tc,mu,te,mp,tmv,mm,ks,fi,startTime,si},
                             TrackStartTime, VerifyTime, xPos, slidePos, arg(base64 10B 随机)})
data = base64(STREAM(deflate(md5hex32 + plain_json)))
```

- STREAM 前 3 字节输出恒定 `25 13 27` (跨会话实测) — R0 初始表固定
- STREAM 是 VM 字节码自实现流密码: R0 初始 64B 置换表 + KSA(用输入 charCodeAt) + PRGA(e=(r[e]^r[a]+1)&63, 三步 XOR swap, 输出 m^r[(r[e]+r[a]+1)&63]) — 精确轮函数待校准 (L_disasm.txt 1020-1461 主循环)

### 3. VerifyCaptchaV3 deviceToken

```
deviceToken = base64("WEB#<appKey>-h-<ts>-<rand32>#AES(sessionKey, fpInner)#340#<md5hex32>")
```

- **[4] md5 被服务端校验** (A/B 实验证明: 原 token+随机 md5 → F017)
- md5 公式 = feilin VM 内部 hash (标准 md5 穷举 30+ 变体全不中) — 不再硬破, 走 harvest 路线
- Log2/Log3 token 6 段结构: `prefix#AES(sk,fpInner)#AES(sk,'saf-captcha')#AES(sk,'W.10056')##AES(sk,ts)`

### 4. 判定码语义 (实测)

| 码 | 含义 | 本机实测触发 |
|---|---|---|
| T001 | 通过 | 未达 (B 路线进行中) |
| F015 | **位置误差** | 1:1 错误拖动时 100% 复现 |
| F001 | 行为/环境风控 | 位置修正后稳定复现 |
| F002 | 未滑动/token 过期 | 提交延迟 >60s |
| F017 | deviceToken 无效 | md5 不匹配/未注册 |

## 路线实测状态

| 路线 | 位置层 | 行为层 | 卡点 |
|---|---|---|---|
| jsdom 沙箱 (feilin 真跑) | ✅ 反解过 | F001 | isTrusted=false 上报 (jsdom 不可伪造, Proxy/子类/defineProperty 全试) |
| puppeteer headless CDP | ✅ 反解过 | F001 | headless 指纹 (feilin 155 字段) |
| puppeteer headed CDP | ✅ 反解过 | F001 | 同上 |
| **camoufox (反检测 Firefox) MOSS 原生页** | ✅ T001 **5/5 一次过** | ✅ 过 (17-78s/次) | 发码层 IP 频控 (见下) |
| 完全纯算 (无浏览器) | ✅ data 构造 | F017 | deviceToken md5 = feilin VM hash |

## 求解器 (B 路线)

`camoufox_native.py`: camoufox (反检测 Firefox, 本机二进制已 fetch) 打开 MOSS 登录页原生走滑块, 网络层拦 gu0sj6-verify 响应.

- 缺口检测: YOLOv8n ONNX (CF-Bypass best.onnx, 10.8MB, CPU 2线程 ~20-40ms, 单发置信 ~0.6+)
- cv2 Sobel-x 在雪景/雾林背景误检率极高 (155/133 vs 真值 171/200) — **生产必须 YOLO**
- 拖动: overshoot-correct (快加速 ease-out → overshoot 6-11px → 多步回拉) — CF-Bypass 3/3 T001 形态
- verify: 页面内 fetch 同指纹同 IP 即时提交 (token 时效短, F002 教训)



## 发码层 (2026-11-15 实测)

滑块 T001 后 MOSS 原生回调链路自动发码: `/portal-api/auth/account/code` → 200 `{expires_in:300, cooldown_in:60}`.

**关键教训**:
- 手动拼 `captcha_verify_param` 发码 (即使用真 T001 的 securityToken) → 400 `captcha_failed`. 必须走 SDK→MOSS 前端→portal-api 原生回调链
- 同 IP 短时 5 次 T001+发码后, MOSS 短信网关**静默频控** (200 但短信不到) — 需每号换出口 IP (sing-box 52 出口可接)
- MOSS 前端正则拒虚拟段: 170/171/162 (Enter a valid 11-digit), 165/192/190 可用

## 注册纯协议链 (T001 后全 HTTP)

```
POST /portal-api/auth/account/code   {kind:'phone', account, purpose:'login', captcha_verify_param}  → 发短信
POST /portal-api/auth/account/login  {kind:'phone', account, code}  → {is_new_user:true} + 会话 cookie
POST /portal-api/api_keys            {name:'1'}  → {api_key:'sk-...'}
```

## 号池接入

MOSS 注册流程: 手机号 → 滑块 T001 → captcha_verify_param → 发短信 → 接码 → 登录.
求解器输出 `securityToken` (T001 时), 上层直接用.


## 号池批量注册 (moss_register_batch.py)

- 代理: 控制台 proxy_source.pick("file", "moss", exclude=used) 轮换 (159 出口, mark_bad 拉黑失败出口)
- camoufox proxy 参数必须是 dict {server: url}, 传字符串会 AttributeError
- 手机号输入必须 evaluate set value + 校验回读 (代理下 page.type 丢字符 → 前端正则拒)
- D1 关键词 = mosi (用户实测软件截图证实, MOSS 大写错)
- MOSS 前端对可疑出口跳过滑块直发 (按钮 Sending…) → code=DIRECT 分支处理
- 落盘: moss_accounts.jsonl (phone/sk/proxy/is_new)

## 文件清单 (mosi/work/)

| 文件 | 说明 |
|---|---|
| camoufox_native.py | B 路线求解器主程序 |
| gap_yolo.py + best.onnx | YOLO 缺口检测 (来自 CF-Bypass) |
| yolo_detect.py | python 桥 (stdin JSON → gap_x) |
| trackGen.js | 真人轨迹生成器 (taobaoSlider 移植) |
| moss_coef.json | 二次系数 |
| string_table.json | AliyunCaptcha.js dodo 解码全表 |
| const_run2.js | pe.089 常量提取 (含 INIT_MD5_SECRET_SALT) |
| harvest_verify.json | jsdom 收割四元组样本 |

## 性能优化结论 (2026-11-15)

| 优化项 | 效果 |
|---|---|
| sleep 轮询 → wait_for_function 事件驱动 | -3~10s |
| verify 双重等待 → on_response 事件 | -1~10s |
| 拖动帧 42→26 | -0.6s |
| **单号独立浏览器** | **9-15s/号 稳定 (46s→9s, 5倍)** |
| 常驻浏览器复用 | ❌ 不稳定 (SDK 状态残留: 首号未弹/后续静默拒), 放弃 |
| 并行 3-4 实例 | 吞吐 ×3-4 (批量推荐) |

**无硬限制**: T001 与总时长无关 (成功样本拖动仅 226ms). 下限 = camoufox 启动 ~7s + SDK init ~2s + 拖动 0.9s + verify RTT. 单号 9s 已接近极限; 批量靠并行.

交付版: `moss_slider_fast.py` (SliderSession 类 + 单号便捷入口). 常驻复用实验代码在 test_session.py (保留作反例).
