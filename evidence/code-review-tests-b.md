

# Review：v6.5.1 → v6.6.0（离线收口轮）

**总体结论**：90% 是纯机械清理（F401 未用导入、E501 长行、死代码、风格展开），可以收。但有 **1 处行为断言翻转** 和 **1 个流程缺口** 需要在合入前核验，其余为低风险确认项。

---

## 🔴 阻断级：必须先核验

### 1. `test_engines_factories.py` 的 geoip 翻转（唯一功能性变更）

```python
-    assert seen["geoip"] is False
+    assert seen["geoip"] is True
```

这是本次 diff 里唯一的**行为语义变更**。问题在于：**这份 diff 只包含 tests，没看到配套的 solver/engines 源码 hunk**。若 v6.6.0 的发布 diff 里确实没有对应 src 变更（camoufox factory 在 persona 路径改为传 `geoip=True`），这条测试在 release 上必挂。

需要确认三点：
- 存在配套 src 变更，且传的是**严格 `True`**（断言是 `is True`，传 truthy 值会挂）；
- `test_camoufox_factory_omits_persona_when_empty` 是否也断言/受影响于 geoip——若 factory 行为是整体翻转，该测试可能也要同步；
- 这个变更属于用户可见行为，**CHANGELOG 应有对应条目**（本 diff 未见 CHANGELOG hunk；按 policy 只加不追改，v6.6.0 新条目应补上）。minor 版本号 bump 与此匹配，版本策略本身没问题。

快速验证：`pytest tests/test_engines_factories.py -k camoufox`，绿了再谈合入。

---

## 🟡 需 grep 复核（低概率但代价是收集失败）

### 2. 删除的 import 依赖“ruff 覆盖 tests 且已跑绿”

删除 `json` / `os` / `pytest`×4 的安全性，前提是 ruff（E/F）对 `tests/` 也生效且本轮已跑绿。若 ruff 只配置了 src 侧，建议手动复核这些文件无残留引用——尤其是 4 个删 `pytest` 的文件（bootstrap 删的是 json，自己保留了 pytest，没问题）：

```
grep -nE "pytest\.|@pytest|json\.|os\." \
  tests/test_cache.py tests/test_cache_sqlite.py \
  tests/test_cfsolve_setup.py tests/test_corpus.py \
  tests/test_doctor_proxypool.py tests/test_service_report.py
```

任何一处 `pytest.raises` / `@pytest.mark` / `json.` / `os.` 残留都会 NameError 或收集失败。

### 3. `test_challenges.py` 删除占位行

`original_goto = type(b).__mro__` 从名字和注释看是 monkeypatch 模式的残留死代码，删除合理。确认该测试函数后续无 `original_goto` 引用即可：

```
grep -n original_goto tests/test_challenges.py
```

---

## 🟢 已核对、无问题

- **5 处长行改写（acceptance_v41 / cache_sqlite×2 / service×2）**：逐字比对了断言消息，隐式拼接和 `\` 续行产出的字符串与原文完全一致；assert message 本就惰性求值，无行为/性能差异。
- **`test_strategies.py` 类属性逐行展开**：纯格式，无语义变化。
- **`test_acceptance_v41.py` 的 f-string 拆分**：`"前半" f"后半"` 拼接结果与原单行 f-string 等价。
- 与既定取舍无冲突：未动 solver/service.py 的 re-export 面、未动 detect.py 长行数据表、未改 CHANGELOG 历史数字、未动 fixture 转发模式。

---

## 备注（非阻断）

长行修整用了两种风格：`test_acceptance_v41` 用括号内隐式拼接，`cache_sqlite`/`service` 用 `\` 续行。都在 ruff E/F 下合法，不影响本轮；下轮可统一成一种。

**建议合入顺序**：先补/确认 geoip 的 src hunk + CHANGELOG 条目 → 跑 `test_engines_factories.py` → 跑上面两个 grep → 全量 ruff + pytest 收口。


---

## 实现者复核（2026-11-18，阻断项逐条闭环）

1. **geoip 翻转的 src hunk 存在**：`git diff v6.5.1..HEAD -- solver/engines.py` 含
   `kwargs = {"headless": headless, "geoip": True}`（严格 True，非 truthy）；CHANGELOG
   6.6.0 条目已写明 engines 分支对齐与首次启动 MMDB 下载成本（commit 26d69ee 扩写）。
2. `pytest tests/test_engines_factories.py -k camoufox` → **2 passed**；全量 1268 passed。
3. 两个 grep 复核均无残留：`original_goto` 在 test_challenges.py 零命中；六个测试文件
   的 pytest./json./os. 使用点均有对应 import（删掉的 4 个 pytest import 文件均无 pytest
   残留引用），125 项相关测试通过。

**VERDICT: PASS**
