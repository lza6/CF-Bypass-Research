# MOSS (platform.moss.cn) 阿里云验证码 V3 完整逆向报告

日期: 2026-11-13 ~ 2026-11-14
目标: 发送验证码前置的阿里云滑块 (gu0sj6.captcha-open.aliyuncs.com)
结论: 协议 95% 纯算还原, 滑块 data 加密为 64 字节状态自同步 RC4 变体 (VM bytecode), 已完成浏览器自动化兜底并实测通过 (业务端进入"发送中…"状态)

---

## 1. 全链路

```
GET  /portal-api/auth/account/captcha-config
     ← {enabled, region:"cn", prefix:"gu0sj6", scenes:{login,reset,bind}}

[阿里 SDK 三件套]
  AliyunCaptcha.js        (o.alicdn.com)              主 SDK
  pe.0XX.<hash>.js        (g.alicdn.com/dynamicJS/3.29.0/)  动态加密 VM (StaticPath 下发, 版本轮换: 088/089/075...)
  feilin077.<hash>.js     (g.alicdn.com/FeiLin/1.5.4/)      设备指纹 → deviceToken

POST gu0sj6.captcha-open.aliyuncs.com        Action=InitCaptchaV3   ← CertifyId + 拼图 URL + DeviceConfig
POST gu0sj6-verify.captcha-open.aliyuncs.com Action=VerifyCaptchaV3 ← VerifyResult + securityToken
POST upload.captcha-open.aliyuncs.com        Action=UploadLog       (埋点, 不参与验证)
POST cloudauth-device-dualstack.cn-shanghai.aliyuncs.com  Log1/Log2/Log3 (设备指纹)

POST /portal-api/auth/account/code
     body: {kind:"phone"|"email", account, purpose, captcha_verify_param}
     captcha_verify_param = base64(JSON{certifyId, sceneId, isSign:true, securityToken})
     ↑ 注意: 不是完整 CaptchaVerifyParam! verify 通过后 SDK onBizSuccess 只回传 4 字段
```

## 2. 已 100% 还原并实测验证的密码学常量

### 2.1 captcha-open API 签名 (HMAC-SHA1) ✅
```
KEY_ID   (AaduaneId) = 111jdk439dJJIjd023823201
KEY_SECRET           = 222aiJodos2938JDdosko2djd82sf0
KEY_ID 密文    = MQECT2fv9RPHHlaKkKNWZP0vS4BJe7J1XY8H7v7s27M=
KEY_SECRET 密文 = EYKxcWbB1W70XKzyYLOt12LQ9EFXzV0OvPKeOPWhABg=

签名算法:
  1. 删除 Signature; 其余参数按 key ASCII 升序
  2. qs = "k1=v1&k2=v2..."  (Se: encodeURIComponent + '+'→%20, '*'→%2A, %7E→~)
  3. stringToSign = "POST&%2F&" + Se(qs)
  4. Signature = Base64(HMAC-SHA1(key=KEY_SECRET+"&", msg=stringToSign))
实测: HAR 中 UploadLog / VerifyCaptchaV3 两条真实请求复算一致 ✅
```

### 2.2 AES 常量封装 (AES-128-CBC / PKCS7) ✅
```
KEY_WRAP_KEY = FqJB6iRNVYdEGpwb
KEY_WRAP_IV  = 0123456789ABCDEF    (源码 hex 串 d35db7e39ebbf3d001083105
                                    经 Hex.parse→Base64.stringify→Utf8.parse 得到)
```
| 密文 (base64) | 解密明文 | 用途 |
|---|---|---|
| EYKxcWbB1W70…ABg= | 222aiJodos2938JDdosko2djd82sf0 | API KEY_SECRET |
| kvqU4wg9JqUy…kkq4= | DuanemHmyeE6LXCC46sJEDUw5DTlSZ | 设备指纹 KEY_SECRET |
| tK5X1r3E65gc…Pns= | DuaneAprqkYsF3nt1yjK29Bf | 设备指纹 KEY_ID |
| 8KmHIQsc5+LZ…ss0= | 45f8ac1e1de14397 | Yt.REQ — DeviceData 外层 key |
| k+1RW0cz3iDi…Gas= | c175a358550d02e2 | Yt.FLAG — captcha-front Data key |
| 9NhnQQ+LRrKC…grM= | 87f879f135f27da7 | Yt.RES |
| +fR9tYzlKFr0…MfA= | a549a55c60a39aa0 | Yt.UPLOAD |
| xLLw/t15vkI7…2B0= | 75ae5c150d235802 | Yt.PREID |
| DNsKKPRHfOTu…Ez2k= | (32B raw) 0cdb0a28…4cf69 | feilin 上报 AES-256 key |

### 2.3 appKey 映射 ✅
```
verifyType "3.0", region cn:
  appKey   = ab034ec0643f91399eb33e062dc7fae1
  appName  = saf-captcha
  设备端点 = https://cloudauth-device-dualstack.cn-shanghai.aliyuncs.com
```

## 3. 请求报文 (全部还原 ✅)

### 3.1 InitCaptchaV3
```
公共参数: AaduaneId, SignatureMethod=HMAC-SHA1, SignatureVersion=1.0, Format=JSON,
          Timestamp=<UTC Z>, Version=2023-03-05, SignatureNonce=<uuid4>, Signature
专有: Action=InitCaptchaV3, SceneId=l6hmxyih, Language=cn, Mode=popup, DeviceData=<enc>

DeviceData = AES( key=45f8ac1e1de14397, join('#', [
    appKey, "W",
    AES( key=c175a358550d02e2, "WEB#saf-captcha#l6hmxyih#captcha-front#gu0sj6#cn" ),
    "W20220202", "CLOUD", "" ]))
实测: 构造值与真实请求解密逐字段一致 ✅

响应: {CertifyId, Image, PuzzleImage, StaticPath, CaptchaType:"PUZZLE",
       DeviceConfig:<240B 加密>, LimitFlow, Success}
```

### 3.2 VerifyCaptchaV3
```
专有: Action=VerifyCaptchaV3, SceneId, CertifyId,
      CaptchaVerifyParam = JSON{sceneId, certifyId, deviceToken, data}
响应: {Result:{VerifyCode:"T001", VerifyResult:true, securityToken}}

deviceToken 结构 = base64("WEB#<appKey>-h-<ts>-<rand32>#<AES-256 指纹>#<480/340>#<md5hex32>")
```

### 3.3 data 字段 (滑块行为加密)
```
plain_json = JSON.stringify({
  TrackList: {
    mc: "x,y,time,button,isTrusted|…",   # mousedown/up
    tc: "",                              # click
    mu: "115,0,3422, ,0",                # mouseup 汇总
    te: "", tmv: "", ks: "", fi: "",
    mp: "dx,dy,t,isTrusted|…",           # mousemove 轨迹 (相对增量)
    mm: "x,y,t,isTrusted|…",             # 合并轨迹 (首点 0,0)
    startTime: <ms>,
    si: "innerWidth,innerHeight,clientWidth,innerHeight,outerHeight,screenHeight,fps,?,outerWidth"
  },
  TrackStartTime: <ms>, VerifyTime: <ms>,
  xPos: "<滑块最终x>", slidePos: "<位移>",
  arg: "<base64(10B 随机)>"              # 每次随机 (服务端 nonce)
})

加密链 (TextEncoder/pako/deflate/base64 全部 hook 实测确认 ✅):
  1. payload = <32hex md5> + plain_json      (md5 源含 INIT_MD5_SECRET_SALT)
  2. zlib    = pako.deflate(payload)          # 78 9C 头, ~500B
  3. b64     = base64(zlib)                   # ~672-680 ASCII
  4. cipher  = STREAM(b64)                    # 等长, VM bytecode 自实现
  5. data    = base64(cipher)
```

### 3.4 流密码 STREAM —— 结构已确认, 精确轮函数见 §5
```
反汇编确认 (L_disasm.txt):
  - 初始状态 r = 64 字节置换表 (0..63 的排列, 已提取):
    [32,50,10,51,6,44,37,16,46,11,62,19,43,25,23,30,60,33,53,34,7,26,12,48,5,2,20,4,
     61,13,47,49,18,29,27,22,1,17,39,56,41,38,55,31,15,58,52,40,8,57,45,35,59,36,42,54,63,3,24,28,14,9,0,21]
  - 两个索引 e, a (RC4 的 i/j), 循环掩码 = r.length-1 = 63
  - 轮结构: a = ((r[e]^r[a])+1) & 63 → r[e] ^= r[a] (swap, 出现 3 次 XOR) →
            m = o.charCodeAt(n) → out += fromCharCode(m ^ r[...])
  - 自同步: 状态由已处理明文驱动; 相同明文前缀 'eJztl' → 相同输出前缀 '2513275f0f' (跨会话实测)
  - 两次同会话采样 keystream 前缀相同至输入分叉点, 之后不同 → 状态依赖明文 ✅
```

## 4. 实测通过记录 ✅
```
2026-11-14 Chrome 157 (CDP 驱动):
  - 缺口识别: canvas 边缘检测 (Sobel 列密度峰值), 成功率高
  - 拖动轨迹: 20 点 ease (0.6 前 90% 加速段), 每点 6-15ms
  - VerifyCaptchaV3 → VerifyResult:true (业务端进入"发送中…", 验证码发出)
  - 完整 captchaVerifyParam 已捕获: success_cvp_final.json
```

## 5. 纯算路线剩余工作 (1 步)
```
流密码精确轮函数: VM bytecode (L_true.json 1498 项 + q_true.json 常量池) 已完整提取
  + 反汇编 (L_disasm.txt 782 行) + 解释器 (pe.075 R=function t(n,e,r,i,a,o))
  + 主循环 1020-1461 已逐指令导出 (loop_body.txt)
阻塞点: VM 解释器需要完整模块 scope 链 (tS/em/y 等混淆函数), 单独执行缺上下文。
可行解: ① 对 pe.075 打补丁 (已验证 patch 点: c=y.P(R,0,[],L,q,N,ti) @276811,
        语法已修正) 在真实浏览器暴露 VM → 直接以纯 JS 调用加密函数 (无需理解轮函数);
        ② 或继续翻译 242 条循环体指令 (约 1-2 天工作量)。
注意: pe 版本轮换 (088→089→075), bytecode 与混淆名随版本变, 常量与结构不变。
```

## 6. 兜底方案 (已实测) ✅
```
Playwright/CDP 自动化:
  1. 打开 /login, 填账号, 点"获取验证码"
  2. 等滑块 popup → 截拼图 back.png → canvas 边缘检测找缺口 x
  3. dispatchEvent mousedown/mousemove(+ease)/mouseup 拖动
  4. 拦截 XHR VerifyCaptchaV3 响应 → onBizSuccess 的 4 字段 JSON 即 captcha_verify_param
  5. 直接 POST /auth/account/code
单次耗时 3-5s, 本报告随附的 CDP 脚本片段可直接复用。
```

## 7. 关键文件索引
```
L_true.json          加密 VM bytecode (1498 项)
q_true.json          VM 常量池 (135 项)
L_disasm.txt         VM 反汇编 (782 行, XOR/主循环清晰可见)
loop_body.txt        主加密循环 242 条指令
ks_pair.json         (z64, cipher) 精确配对样本 + 672B keystream
two_pairs.json       同会话两组配对 (差分分析用)
success_cvp_final.json  实测通过的完整 captchaVerifyParam
```


---

## 求解器交付 (2026-11-15)

滑块 T001 已实战打通 (camoufox + YOLO + 二次反解, 5/5 一次过): 见 [work/MOSS-滑块求解器-B路线.md](work/MOSS-滑块求解器-B路线.md). 主求解器 [work/moss_slider_solver.py](work/moss_slider_solver.py).
