# MOSS 阿里滑块 — 纯协议 E2E 实战打通 + 号池批量产号

> 2026-11-15. camoufox 反检测 Firefox + YOLOv8n 缺口检测 + 二次反解拖距 + overshoot 拖动 = **T001 8/10 一次过**。
> E2E 全链路已由真实号证实: 滑块T001 → 原生发码 → 短信到 → 纯协议登录 → 建 API key `sk-da95e399...`。
> **发码必须走未频控的中国大陆 IP** (海外代理 T001 过但 MOSS 短信网关不发)。

## E2E 全链路 (已打通)

```
camoufox 打开登录页 → YOLO 缺口 → 二次反解 → overshoot 拖动
→ gu0sj6-verify → T001 → MOSS 原生回调 → /portal-api/auth/account/code (200)
→ 短信 → /auth/account/login {is_new_user:true} → /portal-api/api_keys → sk-xxx
```

## 核心结论

1. **二次反解** (F015 唯一解): `piece = 0.003552×m² + 0.0769×m`, 反解 m = (-B+√(B²+4Atarget))/(2A)
2. **判定码分流**: F015=位置 (反解修), F001=行为 (反检测修), F002=过期 (60s 内发码), F017=token 无效
3. **环境要求**: camoufox (反检测 Firefox) 必须; jsdom/puppeteer 均 F001; headless 可用
4. **缺口检测**: YOLO (best.onnx) 必须; cv2 Sobel 在 AIGC 背景误检率高
5. **发码 IP**: 必须中国大陆未频控 IP; 海外代理 T001 过但短信不发
6. **D1 接码**: 关键词 `mosi` (小写); getPhone 随机号可能不在可收池 → 需实卡过滤/pending 补收

## 文件清单

| 文件 | 说明 |
|---|---|
| solve_camoufox.py | 通用求解器 (scene_id+prefix 即可跑) |
| moss_slider_fast.py | MOSS 快速版 (9s/号, SliderSession) |
| moss_slider_solver.py | 稳定版 (8/10 T001) |
| moss_batch_200.py | 200 号批量 (2 worker, 实卡过滤, 60s 收码) |
| pending_collect.py | pending 号补收循环 |
| d1_client.py | D1 接码客户端 |
| gap_yolo.py + best.onnx | YOLO 缺口检测 |
| moss_coef.json | 二次反解系数 |
| trackGen.js | 真人轨迹生成器 |
| string_table.json | SDK 字符串全表 |
| MOSS-号池集成-验收与缺口总表.md | 验收+缺口唯一文档 |
| MOSS-滑块求解器-B路线.md | 技术报告 |
| e2e_result.json | E2E 实战结果 (sk-da95e399...) |

## 快速跑

```bash
# 单号 E2E
uv run --active --with camoufox --with numpy --with opencv-python-headless --with onnxruntime \
  python -u -X utf8 moss_slider_fast.py

# 200 号批量
uv run --active --with camoufox --with numpy --with opencv-python-headless --with onnxruntime \
  python -u -X utf8 moss_batch_200.py --count 200 --workers 2

# pending 补收
uv run --active python -u -X utf8 pending_collect.py
```

## 坑速查

- camoufox proxy 必传 dict `{server: url}`
- python 重定向必须 `-u` (否则缓冲吞日志)
- D1 关键词 = `mosi` (小写)
- `wait_code` 必须关键字参数 `timeout_s=` (位置参数会被当正则)
- T001 后 60s 内必须发码, 发码后 300s 内必须登录
- 并发 4 worker 触发风控聚合全拒 (2 worker + 错峰可用)
- Firefox 空页宿主被 SDK 静默拒 (必须真页面)
- 手动拼 captcha_verify_param 发码 → 400 captcha_failed (必须原生回调链路)
- 同 IP 20+ 次滑块后频控 (滑块不弹/发码不发), 冷却后恢复
- GitHub 限流带 GH_TOKEN
