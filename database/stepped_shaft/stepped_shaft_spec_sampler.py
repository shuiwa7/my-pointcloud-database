"""
stepped_shaft_spec_sampler.py

为 stepped_shaft 零件族生成 100 个设计规格（spec.json）。
- 4 个维度：D1（大径）、H1（大端高）、D2（小径）、H2（小端高）
- 维度间搭配 4 种模式：homogeneous / hetero_dims / hetero_form / mixed
  （占比 20% / 40% / 20% / 20%）
- 强制约束：D1_nominal > D2_nominal
- nominal 采样采用分层池 + 6 种合法 (D1,D2) 组合均匀化
"""

import json
import os
import random
from collections import Counter

# =========================================================
# 常量
# =========================================================

DIM_ORDER = ["D1", "H1", "D2", "H2"]      # 固定顺序，用于遍历与输出
ITS       = ["IT6", "IT7", "IT8"]
FORMS     = ["sym", "plus", "minus", "asym"]

# 每个维度的 nominal 池
DIM_NOMINALS = {
    "D1": [40, 60, 100],
    "D2": [20, 40, 60],
    "H1": [20, 40, 60],
    "H2": [10, 20, 30],
}

# (dim, nominal, IT) -> T (单位 mm)
TOL_TABLE = {
    ("D1", 40,  "IT6"): 0.016, ("D1", 40,  "IT7"): 0.025, ("D1", 40,  "IT8"): 0.039,
    ("D1", 60,  "IT6"): 0.019, ("D1", 60,  "IT7"): 0.030, ("D1", 60,  "IT8"): 0.046,
    ("D1", 100, "IT6"): 0.022, ("D1", 100, "IT7"): 0.035, ("D1", 100, "IT8"): 0.054,

    ("D2", 20,  "IT6"): 0.013, ("D2", 20,  "IT7"): 0.021, ("D2", 20,  "IT8"): 0.033,
    ("D2", 40,  "IT6"): 0.016, ("D2", 40,  "IT7"): 0.025, ("D2", 40,  "IT8"): 0.039,
    ("D2", 60,  "IT6"): 0.019, ("D2", 60,  "IT7"): 0.030, ("D2", 60,  "IT8"): 0.046,

    ("H1", 20,  "IT6"): 0.013, ("H1", 20,  "IT7"): 0.021, ("H1", 20,  "IT8"): 0.033,
    ("H1", 40,  "IT6"): 0.016, ("H1", 40,  "IT7"): 0.025, ("H1", 40,  "IT8"): 0.039,
    ("H1", 60,  "IT6"): 0.019, ("H1", 60,  "IT7"): 0.030, ("H1", 60,  "IT8"): 0.046,

    ("H2", 10,  "IT6"): 0.009, ("H2", 10,  "IT7"): 0.015, ("H2", 10,  "IT8"): 0.022,
    ("H2", 20,  "IT6"): 0.013, ("H2", 20,  "IT7"): 0.021, ("H2", 20,  "IT8"): 0.033,
    ("H2", 30,  "IT6"): 0.013, ("H2", 30,  "IT7"): 0.021, ("H2", 30,  "IT8"): 0.033,
}

# ISO 尺寸段（含边界归属）
SIZE_SEGMENT = {
    10:  ">6-10",      # over 6 up to 10
    20:  ">18-30",
    30:  ">18-30",     # 30 是 >18-30 的上界
    40:  ">30-50",
    60:  ">50-80",
    100: ">80-120",
}

DIM_DEFINITION = {
    "D1": "大端外圆柱拟合直径",
    "H1": "大端圆柱高度",
    "D2": "小端外圆柱拟合直径",
    "H2": "小端圆柱高度",
}

# 搭配模式数量（100 设计）
PATTERN_COUNTS = {
    "homogeneous": 20,   # 同质型
    "hetero_dims": 40,   # 异质型（IT 至少 3 种不同，form 随机）
    "hetero_form": 20,   # 异质 form 型（form 全排列，IT 随机）
    "mixed":       20,   # 混合型（IT 至少 3 种不同 + form 全排列）
}

# =========================================================
# 工具函数
# =========================================================

def deviations(tol_form, T):
    """返回 (upper_dev, lower_dev)。"""
    if tol_form == "sym":
        return round(T / 2.0, 6), round(-T / 2.0, 6)
    if tol_form == "plus":
        return round(T, 6), 0.0
    if tol_form == "minus":
        return 0.0, round(-T, 6)
    if tol_form == "asym":
        return round(0.7 * T, 6), round(-0.3 * T, 6)
    raise ValueError(tol_form)


def build_dimspec(dim, nominal, it_grade, tol_form):
    """构造单个维度的 DimSpec。"""
    T = TOL_TABLE[(dim, nominal, it_grade)]
    upper, lower = deviations(tol_form, T)
    return {
        "nominal":        float(nominal),
        "it_grade":       it_grade,
        "size_segment":   SIZE_SEGMENT[nominal],
        "T":              T,
        "tol_form":       tol_form,
        "upper_dev":      upper,
        "lower_dev":      lower,
        "LSL":            round(nominal + lower, 6),
        "USL":            round(nominal + upper, 6),
        "dim_definition": DIM_DEFINITION[dim],
    }


def stratified_pool(items, n, rng):
    """把 items 均匀填充到 n 个槽位并打乱（分层）。"""
    base, rem = divmod(n, len(items))
    pool = []
    for i, item in enumerate(items):
        pool.extend([item] * (base + (1 if i < rem else 0)))
    rng.shuffle(pool)
    return pool


def build_d_pairs(n):
    """
    构造 n 个合法的 (D1_nominal, D2_nominal) 对，D1 > D2。
    合法组合共 6 种，均匀轮转，保证每种都出现。
    """
    candidates = [
        (40, 20),
        (60, 20), (60, 40),
        (100, 20), (100, 40), (100, 60),
    ]
    base, rem = divmod(n, len(candidates))
    pairs = []
    for i, p in enumerate(candidates):
        pairs.extend([p] * (base + (1 if i < rem else 0)))
    return pairs


def assign_it(pattern, rng):
    """按 pattern 分配 4 个维度的 IT。"""
    if pattern == "homogeneous":
        it = rng.choice(ITS)
        return {d: it for d in DIM_ORDER}

    if pattern in ("hetero_dims", "mixed"):
        # 三档 IT 全出现（IT6/IT7/IT8 各一次）+ 第 4 个随机
        base  = rng.sample(ITS, 3)          # 3 个不同 IT 的排列
        extra = rng.choice(ITS)             # 第 4 个随机
        its   = base + [extra]
        rng.shuffle(its)
        return dict(zip(DIM_ORDER, its))

    if pattern == "hetero_form":
        return {d: rng.choice(ITS) for d in DIM_ORDER}

    raise ValueError(pattern)


def assign_form(pattern, rng):
    """按 pattern 分配 4 个维度的 form。"""
    if pattern == "homogeneous":
        fm = rng.choice(FORMS)
        return {d: fm for d in DIM_ORDER}

    if pattern == "hetero_dims":
        return {d: rng.choice(FORMS) for d in DIM_ORDER}

    if pattern in ("hetero_form", "mixed"):
        # 4 个 form 全排列，sym/plus/minus/asym 各出现一次
        perm = rng.sample(FORMS, 4)
        return dict(zip(DIM_ORDER, perm))

    raise ValueError(pattern)


# =========================================================
# 抽样核心
# =========================================================

def sample_designs(n_designs=100, seed=20241028):
    rng = random.Random(seed)

    # 1) pattern 分配
    patterns = []
    for name, cnt in PATTERN_COUNTS.items():
        patterns.extend([name] * cnt)
    assert len(patterns) == n_designs
    rng.shuffle(patterns)

    # 2) D1/D2 nominal 对（满足 D1 > D2）
    d_pairs = build_d_pairs(n_designs)
    rng.shuffle(d_pairs)

    # 3) H1/H2 nominal 分层池（无约束）
    h1_pool = stratified_pool(DIM_NOMINALS["H1"], n_designs, rng)
    h2_pool = stratified_pool(DIM_NOMINALS["H2"], n_designs, rng)

    designs = []
    for i in range(n_designs):
        pattern = patterns[i]
        d1_nom, d2_nom = d_pairs[i]
        nominals = {
            "D1": d1_nom,
            "H1": h1_pool[i],
            "D2": d2_nom,
            "H2": h2_pool[i],
        }

        it_assign = assign_it(pattern, rng)
        fm_assign = assign_form(pattern, rng)

        dims = {d: build_dimspec(d, nominals[d], it_assign[d], fm_assign[d])
                for d in DIM_ORDER}

        designs.append({
            "design_id": f"stepped_shaft_{i + 1:04d}",
            "family":    "stepped_shaft",
            "dims":      dims,
            "sampling_meta": {
                "pattern": pattern,
                "seed":    seed,
            },
        })

    return designs


# =========================================================
# 写出与统计
# =========================================================

def write_designs(designs, out_root="."):
    for spec in designs:
        folder = os.path.join(out_root, spec["design_id"])
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "spec.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)


def print_summary(designs):
    n = len(designs)
    print("=" * 78)
    print(f"设计数量: {n}")
    print("=" * 78)

    # [1] pattern
    pat = Counter(d["sampling_meta"]["pattern"] for d in designs)
    print("\n[1] Pattern 分布:")
    for k in ["homogeneous", "hetero_dims", "hetero_form", "mixed"]:
        print(f"    {k:14s}: {pat.get(k, 0):3d}")

    # [2] nominal
    print("\n[2] Nominal 分布（每维度）:")
    for dim in DIM_ORDER:
        c = Counter(d["dims"][dim]["nominal"] for d in designs)
        s = "  ".join(f"{int(k)}mm:{c[k]:2d}" for k in sorted(c))
        print(f"    {dim:3s}: {s}")

    # [3] IT
    print("\n[3] IT 分布（每维度）:")
    for dim in DIM_ORDER:
        c = Counter(d["dims"][dim]["it_grade"] for d in designs)
        s = "  ".join(f"{k}:{c[k]:2d}" for k in ITS)
        print(f"    {dim:3s}: {s}")
    total_it = Counter()
    for d in designs:
        for dim in DIM_ORDER:
            total_it[d["dims"][dim]["it_grade"]] += 1
    print(f"    合计: {dict(total_it)}  (总 DimSpec = {n * 4})")

    # [4] form
    print("\n[4] Form 分布（每维度）:")
    for dim in DIM_ORDER:
        c = Counter(d["dims"][dim]["tol_form"] for d in designs)
        s = "  ".join(f"{k}:{c[k]:2d}" for k in FORMS)
        print(f"    {dim:3s}: {s}")
    total_fm = Counter()
    for d in designs:
        for dim in DIM_ORDER:
            total_fm[d["dims"][dim]["tol_form"]] += 1
    print(f"    合计: {dict(total_fm)}")

    # [5] 强制约束
    print("\n[5] 强制约束检查:")
    bad = [d["design_id"] for d in designs
           if not (d["dims"]["D1"]["nominal"] > d["dims"]["D2"]["nominal"])]
    print(f"    D1_nominal > D2_nominal : "
          f"{'✓ 全部满足' if not bad else f'✗ {len(bad)} 个违反: {bad}'}")

    # [6] (D1, D2) 组合覆盖
    print("\n[6] (D1, D2) 组合覆盖:")
    pair_c = Counter((d["dims"]["D1"]["nominal"], d["dims"]["D2"]["nominal"])
                     for d in designs)
    for p in [(40.0, 20.0), (60.0, 20.0), (60.0, 40.0),
              (100.0, 20.0), (100.0, 40.0), (100.0, 60.0)]:
        mark = "✓" if pair_c.get(p, 0) > 0 else "✗"
        print(f"    {mark} (D1={int(p[0]):3d}, D2={int(p[1]):3d}) : {pair_c.get(p, 0):3d}")

    # [7] 多样性检查
    print("\n[7] 维度间多样性检查:")
    same_it = same_fm = both = 0
    for d in designs:
        its = {d["dims"][k]["it_grade"] for k in DIM_ORDER}
        fms = {d["dims"][k]["tol_form"] for k in DIM_ORDER}
        if len(its) == 1: same_it += 1
        if len(fms) == 1: same_fm += 1
        if len(its) == 1 and len(fms) == 1: both += 1
    print(f"    4 维全同 IT            : {same_it:3d}")
    print(f"    4 维全同 form          : {same_fm:3d}")
    print(f"    4 维全同 IT 且全同 form: {both:3d}  (应 = 20，仅 homogeneous)")

    # [8] (nominal, IT) 交叉表（每维度）
    print("\n[8] (nominal, IT) 交叉表（每维度）:")
    for dim in DIM_ORDER:
        cross = Counter()
        for d in designs:
            s = d["dims"][dim]
            cross[(s["nominal"], s["it_grade"])] += 1
        print(f"\n    {dim}:")
        print(f"    {'nom\\IT':>8} | " + " ".join(f"{g:>5}" for g in ITS) + " |  合计")
        for nv in DIM_NOMINALS[dim]:
            row = [cross[(float(nv), g)] for g in ITS]
            row_s = " ".join(f"{v:>5}" for v in row)
            print(f"    {nv:>6}mm | {row_s} | {sum(row):>5}")

    # [9] form x IT 交叉表（全维度合计）
    print("\n[9] (form, IT) 交叉表（全维度合计）:")
    cross_fi = Counter()
    for d in designs:
        for dim in DIM_ORDER:
            s = d["dims"][dim]
            cross_fi[(s["tol_form"], s["it_grade"])] += 1
    print(f"    {'form\\IT':>8} | " + " ".join(f"{g:>5}" for g in ITS) + " |  合计")
    for fv in FORMS:
        row = [cross_fi[(fv, g)] for g in ITS]
        row_s = " ".join(f"{v:>5}" for v in row)
        print(f"    {fv:>8} | {row_s} | {sum(row):>5}")

    # [10] pattern 内的 IT / form 语义核查（抽样前 10 个设计示例）
    print("\n[10] Pattern 语义核查（抽样示例）:")
    for d in designs[:6]:
        its = " ".join(f"{k}={d['dims'][k]['it_grade']}" for k in DIM_ORDER)
        fms = " ".join(f"{k}={d['dims'][k]['tol_form']}" for k in DIM_ORDER)
        n_its = len({d["dims"][k]["it_grade"] for k in DIM_ORDER})
        n_fms = len({d["dims"][k]["tol_form"] for k in DIM_ORDER})
        print(f"    {d['design_id']} ({d['sampling_meta']['pattern']:11s}): "
              f"#IT={n_its} #form={n_fms}")
        print(f"        {its}")
        print(f"        {fms}")


# =========================================================
# Main
# =========================================================

if __name__ == "__main__":
    OUT_ROOT = "stepped_shaft_specs"
    os.makedirs(OUT_ROOT, exist_ok=True)

    designs = sample_designs(n_designs=100, seed=20241028)
    write_designs(designs, out_root=OUT_ROOT)
    print_summary(designs)
    print(f"\n完成：{len(designs)} 个 spec.json 已写入 '{OUT_ROOT}/stepped_shaft_XXXX/'")