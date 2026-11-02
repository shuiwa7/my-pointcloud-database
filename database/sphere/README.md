# Sphere 零件族全枚举 —— 完整规格说明书

> 本文件描述 Sphere 零件族 36 个设计的**配置池**、**配置池语义**、**全枚举顺序规则**、**JSON 输出格式**，以及**完整的 36 条枚举映射表**。
> Sphere 只有 1 个维度，因此**不做抽样**，直接对 36 种 DimSpec 做全枚举，每种恰好 1 次。

---

## 目录

1. [概述](#1-概述)
2. [配置池定义](#2-配置池定义)
3. [配置池语义](#3-配置池语义)
4. [全枚举顺序规则](#4-全枚举顺序规则)
5. [JSON 输出格式](#5-json-输出格式)
6. [完整 36 条枚举映射表](#6-完整-36-条枚举映射表)
7. [校验清单](#7-校验清单)
8. [与 box / cylinder 的差异](#8-与-box--cylinder-的差异)
9. [附录](#9-附录)

---

## 1. 概述

一个 Sphere 零件由 **唯一维度 D** 描述：

- **D**：球面拟合直径

每个设计只持有一个 **DimSpec**（尺寸规格），由三元组构成：

$$
\text{DimSpec} = (\text{nominal},\ \text{IT},\ \text{form})
$$

- **nominal**：名义直径（3 档）
- **IT**：公差等级（3 档）
- **form**：公差形式 / 偏差分配方式（4 档）

候选空间 = 3 × 3 × 4 = **36 种**。

本零件族**不做抽样**，直接**全枚举**这 36 种 DimSpec，每种出一个设计，共 **36 个** `spec.json`。

> **设计意图**：Sphere 只有一个维度，维度间搭配模式（同质 / 异质 IT / 异质 form / 混合）在单维度下没有意义。因此采用**全枚举**，保证 36 种 DimSpec **逐一出现恰好 1 次**，可作为「完整覆盖」的基准数据集，用于算法单元测试或训练集的最小子集。

---

## 2. 配置池定义

### 2.1 nominal 池（3 档）

| 值 | 单位 | 说明 |
|---|---|---|
| `20`  | mm | 小尺寸 |
| `40`  | mm | 中尺寸 |
| `100` | mm | 大尺寸 |

> 三档均**避开 ISO 尺寸段边界**（18、30、50、80、120），保证每档落在段内、T 值稳定。

### 2.2 IT 池（3 档）

| 值 | 说明 |
|---|---|
| `IT6` | 精密 |
| `IT7` | 中等 |
| `IT8` | 一般 |

### 2.3 form 池（4 档）

| 值 | 中文名 | 偏差特征 | 对应 ISO 基本偏差 |
|---|---|---|---|
| `sym`   | 对称公差 | upper = +T/2, lower = −T/2 | 类似 `js` |
| `plus`  | 单向正公差 | ei = 0，upper = +T, lower = 0 | 类似 `H`（孔） |
| `minus` | 单向负公差 | es = 0，upper = 0, lower = −T | 类似 `h`（轴） |
| `asym`  | 非对称公差 | es = +0.7T, ei = −0.3T | 非标准，自定义 |

### 2.4 DimSpec 完整取值空间（36 种）

| nominal \ IT | IT6 | IT7 | IT8 |
|---|---|---|---|
| **20 mm**  | 4 种 form | 4 种 form | 4 种 form |
| **40 mm**  | 4 种 form | 4 种 form | 4 种 form |
| **100 mm** | 4 种 form | 4 种 form | 4 种 form |

每个格子内 form ∈ {sym, plus, minus, asym}，故共 3 × 3 × 4 = **36** 种。

---

## 3. 配置池语义

### 3.1 nominal 的语义：尺寸段映射

每个 nominal 落在 ISO 尺寸段的**内部**（非边界），用于查 IT 公差表：

| nominal | size_segment | 段内位置 |
|---|---|---|
| 20 mm  | `>18-30`   | 段内 |
| 40 mm  | `>30-50`   | 段内 |
| 100 mm | `>80-120`  | 段内 |

### 3.2 IT 的语义：基本公差值 T（单位 mm）

$$
T = \text{TOL\_TABLE}[\text{nominal}][\text{IT}]
$$

| nominal \ IT | IT6 | IT7 | IT8 |
|---|---:|---:|---:|
| **20 mm**  | 0.013 | 0.021 | 0.033 |
| **40 mm**  | 0.016 | 0.025 | 0.039 |
| **100 mm** | 0.022 | 0.035 | 0.054 |

> 表中数值取自 ISO 286 / GB/T 1800 基本公差表，是 DimSpec 中 `T` 字段的直接来源。

### 3.3 form 的语义：偏差分配规则

设该维度的基本公差为 `T`，则 form 决定上下偏差 `upper_dev` / `lower_dev` 的分配：

| form | upper_dev | lower_dev | 含义 |
|---|---|---|---|
| `sym`   | `+T/2`  | `−T/2`  | 以公称为中心对称分布 |
| `plus`  | `+T`    | `0`     | 基本偏差 ei = 0，只上不下的单向公差 |
| `minus` | `0`     | `−T`    | 基本偏差 es = 0，只下不上的单向公差 |
| `asym`  | `+0.7T` | `−0.3T` | 以公称为中心非对称，上偏大下偏小（偏心比 7:3） |

> 4 种 form 下 `USL − LSL` 恒等于 `T`：form 只决定「公差带相对公称的位置」，不改变带宽。

### 3.4 派生字段（由 3.2 + 3.3 唯一确定）

一旦 `nominal`、`T`、`upper_dev`、`lower_dev` 确定，以下字段自动得出：

| 字段 | 公式 |
|---|---|
| `LSL`（下限） | `nominal + lower_dev` |
| `USL`（上限） | `nominal + upper_dev` |
| `size_segment` | 见 §3.1 |
| `dim_definition` | 固定 `"球面拟合直径"` |

**维度定义文案（Sphere 唯一维）**：

| 维度 | dim_definition |
|---|---|
| D | `球面拟合直径` |

---

## 4. 全枚举顺序规则

由于 Sphere 只有 1 个维度，不存在「维度间搭配模式」。全枚举采用**固定三重循环**：

- **外层**：nominal，升序 `20 → 40 → 100`
- **中层**：IT，升序 `IT6 → IT7 → IT8`
- **内层**：form，按 §2.3 定义顺序 `sym → plus → minus → asym`

**编号公式**：

$$
\text{idx} = (\text{nominal 位置}) \times 12 + (\text{IT 位置}) \times 4 + (\text{form 位置}) + 1
$$

其中：

- nominal 位置 ∈ {0, 1, 2}
- IT 位置 ∈ {0, 1, 2}
- form 位置 ∈ {0, 1, 2, 3}

**具体编号区间**：

| nominal 位置 | 编号范围 | 个数 |
|---|---|---:|
| 20 mm（pos 0）  | `sphere_0001` – `sphere_0012` | 12 |
| 40 mm（pos 1）  | `sphere_0013` – `sphere_0024` | 12 |
| 100 mm（pos 2） | `sphere_0025` – `sphere_0036` | 12 |

**每个 nominal 块内**：

| IT 位置 | 编号范围（相对块内） | 个数 |
|---|---|---:|
| IT6（pos 0） | 块内 01 – 04 | 4 |
| IT7（pos 1） | 块内 05 – 08 | 4 |
| IT8（pos 2） | 块内 09 – 12 | 4 |

**每个 (nominal, IT) 块内**：4 个 form 依次为 `sym → plus → minus → asym`。

> **关于示例 ID 的说明**：你给的示例里 `sphere_0007` 对应 `40 / IT8 / sym`。按本方案的编号规则，`sphere_0007` 实际是 `20 / IT7 / minus`；`40 / IT8 / sym` 对应 `sphere_0021`。示例 ID 只是展示 JSON 字段结构，编号本身不严格对应某一顺序。若确实需要 `sphere_0007 = 40 / IT8 / sym`，需把顺序改成「IT 外层 → nominal 中层 → form 内层」或你指定的任何顺序，本方案默认采用最直观的「nominal → IT → form」。

---

## 5. JSON 输出格式

### 5.1 目录结构

```
<输出根目录>/
├── sphere_0001/
│   └── spec.json
├── sphere_0002/
│   └── spec.json
├── ...
└── sphere_0036/
    └── spec.json
```

每个设计一个子文件夹，命名规则 `sphere_XXXX`（4 位补零，从 0001 到 0036）。

### 5.2 `spec.json` 顶层结构

| 字段 | 类型 | 含义 |
|---|---|---|
| `design_id` | string | 设计 ID，等于所在文件夹名，格式 `sphere_XXXX` |
| `family` | string | 零件族，固定 `"sphere"` |
| `dims` | object | 唯一维度 DimSpec，键仅为 `"D"` |
| `sampling_meta` | object | 采样元数据，见 §5.4 |

### 5.3 `dims.D` 字段

| 字段 | 类型 | 单位 | 含义 |
|---|---|---|---|
| `nominal` | float | mm | 名义直径 |
| `it_grade` | string | — | 公差等级，`IT6` / `IT7` / `IT8` |
| `size_segment` | string | — | 所在 ISO 尺寸段标签 |
| `T` | float | mm | 基本公差值，由 `(nominal, it_grade)` 查表 |
| `tol_form` | string | — | 公差形式，`sym` / `plus` / `minus` / `asym` |
| `upper_dev` | float | mm | 上偏差（可为 0） |
| `lower_dev` | float | mm | 下偏差（可为 0 或负） |
| `LSL` | float | mm | 下限 = `nominal + lower_dev` |
| `USL` | float | mm | 上限 = `nominal + upper_dev` |
| `dim_definition` | string | — | 固定 `"球面拟合直径"` |

**字段间的恒等式（可用于校验）**：

$$
\text{USL} - \text{LSL} = \text{upper\_dev} - \text{lower\_dev} = T
$$

对 4 种 form，span 均为 `T`。

### 5.4 `sampling_meta` 字段

| 字段 | 类型 | 含义 |
|---|---|---|
| `pattern` | string | 固定 `"full_enum"`（本族不做抽样，全枚举） |
| `seed` | int | 全局种子，仅做追溯用（全枚举不依赖随机，因此不影响结果） |

> Sphere 的 `sampling_meta` **只有 2 个字段**，比 box / cylinder 少了 `cross_segment`——因为只有 1 个维度，不存在「跨尺寸段」的概念。

### 5.5 完整示例（单个 design）

```json
{
  "design_id": "sphere_0007",
  "family": "sphere",
  "dims": {
    "D": {
      "nominal": 40.0,
      "it_grade": "IT8",
      "size_segment": ">30-50",
      "T": 0.039,
      "tol_form": "sym",
      "upper_dev": 0.0195,
      "lower_dev": -0.0195,
      "LSL": 39.9805,
      "USL": 40.0195,
      "dim_definition": "球面拟合直径"
    }
  },
  "sampling_meta": {
    "pattern": "full_enum",
    "seed": 20241028
  }
}
```

> 上例使用你原始 prompt 中的示例 ID 与数值；实际运行时 `sphere_0007` 对应 `20 / IT7 / minus`（见 §6 表格第 7 行）。此示例仅用于展示 JSON 字段结构。

### 5.6 字段约束速查

| 字段 | 合法取值 / 约束 |
|---|---|
| `design_id` | `^sphere_\d{4}$`，取值 `sphere_0001` – `sphere_0036` |
| `family` | 固定 `"sphere"` |
| `dims` 的键 | 必须且仅含 `D` |
| `nominal` | `∈ {20.0, 40.0, 100.0}` |
| `it_grade` | `∈ {"IT6","IT7","IT8"}` |
| `tol_form` | `∈ {"sym","plus","minus","asym"}` |
| `size_segment` | 由 `nominal` 唯一确定（§3.1） |
| `T` | 由 `(nominal, it_grade)` 唯一确定（§3.2） |
| `upper_dev` / `lower_dev` | 由 `(tol_form, T)` 唯一确定（§3.3） |
| `LSL` / `USL` | 由 `nominal` 与 `lower_dev` / `upper_dev` 唯一确定 |
| `pattern` | 固定 `"full_enum"` |
| `seed` | 全局固定，本数据集为 `20241028`（对结果无影响） |

---

## 6. 完整 36 条枚举映射表

按 **nominal → IT → form** 顺序列出全部 36 个设计。这张表就是最终输出，`spec.json` 里 `dims.D` 的内容与表中一一对应。

| ID | nominal | IT | form | T | upper_dev | lower_dev | LSL | USL |
|---|---|---|---:|---:|---:|---:|---:|---:|
| sphere_0001 | 20 | IT6 | sym   | 0.013 | +0.0065 | −0.0065 | 19.9935 | 20.0065 |
| sphere_0002 | 20 | IT6 | plus  | 0.013 | +0.0130 | 0.0000  | 20.0000 | 20.0130 |
| sphere_0003 | 20 | IT6 | minus | 0.013 | 0.0000  | −0.0130 | 19.9870 | 20.0000 |
| sphere_0004 | 20 | IT6 | asym  | 0.013 | +0.0091 | −0.0039 | 19.9961 | 20.0091 |
| sphere_0005 | 20 | IT7 | sym   | 0.021 | +0.0105 | −0.0105 | 19.9895 | 20.0105 |
| sphere_0006 | 20 | IT7 | plus  | 0.021 | +0.0210 | 0.0000  | 20.0000 | 20.0210 |
| sphere_0007 | 20 | IT7 | minus | 0.021 | 0.0000  | −0.0210 | 19.9790 | 20.0000 |
| sphere_0008 | 20 | IT7 | asym  | 0.021 | +0.0147 | −0.0063 | 19.9937 | 20.0147 |
| sphere_0009 | 20 | IT8 | sym   | 0.033 | +0.0165 | −0.0165 | 19.9835 | 20.0165 |
| sphere_0010 | 20 | IT8 | plus  | 0.033 | +0.0330 | 0.0000  | 20.0000 | 20.0330 |
| sphere_0011 | 20 | IT8 | minus | 0.033 | 0.0000  | −0.0330 | 19.9670 | 20.0000 |
| sphere_0012 | 20 | IT8 | asym  | 0.033 | +0.0231 | −0.0099 | 19.9901 | 20.0231 |
| sphere_0013 | 40 | IT6 | sym   | 0.016 | +0.0080 | −0.0080 | 39.9920 | 40.0080 |
| sphere_0014 | 40 | IT6 | plus  | 0.016 | +0.0160 | 0.0000  | 40.0000 | 40.0160 |
| sphere_0015 | 40 | IT6 | minus | 0.016 | 0.0000  | −0.0160 | 39.9840 | 40.0000 |
| sphere_0016 | 40 | IT6 | asym  | 0.016 | +0.0112 | −0.0048 | 39.9952 | 40.0112 |
| sphere_0017 | 40 | IT7 | sym   | 0.025 | +0.0125 | −0.0125 | 39.9875 | 40.0125 |
| sphere_0018 | 40 | IT7 | plus  | 0.025 | +0.0250 | 0.0000  | 40.0000 | 40.0250 |
| sphere_0019 | 40 | IT7 | minus | 0.025 | 0.0000  | −0.0250 | 39.9750 | 40.0000 |
| sphere_0020 | 40 | IT7 | asym  | 0.025 | +0.0175 | −0.0075 | 39.9925 | 40.0175 |
| sphere_0021 | 40 | IT8 | sym   | 0.039 | +0.0195 | −0.0195 | 39.9805 | 40.0195 |
| sphere_0022 | 40 | IT8 | plus  | 0.039 | +0.0390 | 0.0000  | 40.0000 | 40.0390 |
| sphere_0023 | 40 | IT8 | minus | 0.039 | 0.0000  | −0.0390 | 39.9610 | 40.0000 |
| sphere_0024 | 40 | IT8 | asym  | 0.039 | +0.0273 | −0.0117 | 39.9883 | 40.0273 |
| sphere_0025 | 100 | IT6 | sym   | 0.022 | +0.0110 | −0.0110 | 99.9890 | 100.0110 |
| sphere_0026 | 100 | IT6 | plus  | 0.022 | +0.0220 | 0.0000  | 100.0000 | 100.0220 |
| sphere_0027 | 100 | IT6 | minus | 0.022 | 0.0000  | −0.0220 | 99.9780 | 100.0000 |
| sphere_0028 | 100 | IT6 | asym  | 0.022 | +0.0154 | −0.0066 | 99.9934 | 100.0154 |
| sphere_0029 | 100 | IT7 | sym   | 0.035 | +0.0175 | −0.0175 | 99.9825 | 100.0175 |
| sphere_0030 | 100 | IT7 | plus  | 0.035 | +0.0350 | 0.0000  | 100.0000 | 100.0350 |
| sphere_0031 | 100 | IT7 | minus | 0.035 | 0.0000  | −0.0350 | 99.9650 | 100.0000 |
| sphere_0032 | 100 | IT7 | asym  | 0.035 | +0.0245 | −0.0105 | 99.9895 | 100.0245 |
| sphere_0033 | 100 | IT8 | sym   | 0.054 | +0.0270 | −0.0270 | 99.9730 | 100.0270 |
| sphere_0034 | 100 | IT8 | plus  | 0.054 | +0.0540 | 0.0000  | 100.0000 | 100.0540 |
| sphere_0035 | 100 | IT8 | minus | 0.054 | 0.0000  | −0.0540 | 99.9460 | 100.0000 |
| sphere_0036 | 100 | IT8 | asym  | 0.054 | +0.0378 | −0.0162 | 99.9838 | 100.0378 |

> 该表由 §3.2 + §3.3 **完全确定**，与脚本运行结果**逐位一致**（脚本的 `print_enum_table()` 打印相同内容）。

---

## 7. 校验清单

跑完脚本后对照输出确认（或直接对 §6 表逐行核对）：

| 检查项 | 期望值 | 说明 |
|---|---|---|
| 输出文件夹数 | **36** | `sphere_0001` – `sphere_0036` |
| 每个 nominal 出现次数 | **12** | 36 / 3 |
| 每个 IT 出现次数 | **12** | 36 / 3 |
| 每个 form 出现次数 | **9** | 36 / 4 |
| 每个 (nominal, IT) 组合 | **4** | 含 4 种 form 各 1 次 |
| 每个 (nominal, form) 组合 | **3** | 含 3 种 IT 各 1 次 |
| 每个 (IT, form) 组合 | **3** | 含 3 种 nominal 各 1 次 |
| **每个 (nominal, IT, form) 组合** | **1（精确）** | 全枚举的定义性质 |
| `USL − LSL = T` | 全部成立 | 恒等式 |
| `pattern` 字段 | 全部 `"full_enum"` | — |
| `dim_definition` 字段 | 全部 `"球面拟合直径"` | — |

**核心验收点**：36 种 `(nominal, IT, form)` 组合**逐一出现恰好 1 次**——这是全枚举的定义性质。打开任一 `spec.json` 对照 §6 表核对行号与内容一致，即通过。

---

## 8. 与 box / cylinder 的差异

| 项目 | box | cylinder | **sphere** |
|---|---|---|---|
| 维度数 | 3（L / W / H） | 2（D / H） | **1（D）** |
| 设计数 | 100 | 60 | **36** |
| 生成方式 | 分层 + 4 种搭配模式 | 分层 + 4 种搭配模式 + 覆盖约束 | **全枚举** |
| `pattern` 字段 | 4 种取值 | 4 种取值 | **固定 `"full_enum"`** |
| `cross_segment` 字段 | — | 有 | **无**（单维无跨段概念） |
| 每 (nominal, IT, form) 期望计数 | ≈ 8.3 | ≈ 3.3 | **1（精确）** |
| 每 IT 期望总数 | 100 | 40 | **12** |
| 每 form 期望总数 | 75 | 30 | **9** |

> Sphere 因为维度只有 1，所有「维度间搭配」的机制全部退化，数据集的用途从「训练算法学到多尺寸差异」变为「**完整覆盖的基准集**」——适合作为单元测试、schema 校验、或算法训练的参照系。

---

## 9. 附录

### 附录 A：T 值速查表（同 §3.2）

| nominal \ IT | IT6 | IT7 | IT8 |
|---|---:|---:|---:|
| 20  | 0.013 | 0.021 | 0.033 |
| 40  | 0.016 | 0.025 | 0.039 |
| 100 | 0.022 | 0.035 | 0.054 |

### 附录 B：form 偏差速查表（乘 T）

| form | upper_dev | lower_dev | 对应 ISO |
|---|---|---|---|
| `sym`   | +0.5T | −0.5T | 类似 `js` |
| `plus`  | +1.0T | 0     | 类似 `H`（孔） |
| `minus` | 0     | −1.0T | 类似 `h`（轴） |
| `asym`  | +0.7T | −0.3T | 自定义 |

### 附录 C：枚举顺序总结

```
sphere_0001 → 20 / IT6 / sym      ← 起点
sphere_0002 → 20 / IT6 / plus
sphere_0003 → 20 / IT6 / minus
sphere_0004 → 20 / IT6 / asym
sphere_0005 → 20 / IT7 / sym
...
sphere_0012 → 20 / IT8 / asym     ← 20mm 块结束
sphere_0013 → 40 / IT6 / sym      ← 40mm 块开始
...
sphere_0024 → 40 / IT8 / asym     ← 40mm 块结束
sphere_0025 → 100 / IT6 / sym     ← 100mm 块开始
...
sphere_0036 → 100 / IT8 / asym    ← 终点
```

### 附录 D：单条 spec.json 的生成算法（伪代码）

```
for nominal in [20, 40, 100]:
    for it_grade in [IT6, IT7, IT8]:
        for tol_form in [sym, plus, minus, asym]:
            idx += 1
            T         = TOL_TABLE[(nominal, it_grade)]
            upper, low = deviations(tol_form, T)
            LSL       = nominal + low
            USL       = nominal + upper
            write(f"sphere_{idx:04d}/spec.json",
                  design_id = f"sphere_{idx:04d}",
                  dims.D    = {nominal, it_grade, T, tol_form,
                               upper, low, LSL, USL,
                               size_segment, dim_definition})
```