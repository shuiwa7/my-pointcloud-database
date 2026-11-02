"""
hole_plate_spec_sampler.py

为 hole_plate 零件族生成 100 个设计规格（spec.json）。
- 4 个维度：L（长）、W（宽）、H（厚）、D（孔直径）
- 4 种搭配模式：homogeneous / hetero_dims / hetero_form / mixed
  占比 20% / 40% / 20% / 20%
- 强制约束 L, W > H 与 D < min(L, W)：在给定 nominal 池下天然满足，
  代码里做 post-hoc 校验并打印结果
"""

import json
import os
import random
from collections import Counter

# =========================================================
# 常量
# =========================================================

DIM_ORDER = ["L", "W", "H", "D"]
ITS       = ["IT6", "IT7", "IT8"]
FORMS     = ["sym", "plus", "minus", "asym"]

# 每个维度的 nominal 池
DIM_NOMINALS = {
    "L": [60, 80, 100],
    "W": [40, 60, 80],
    "H": [10, 15, 20],
    "D": [10, 20, 30],
}

# (dim, nominal, IT) -> T（mm）
TOL_TABLE = {
    # L: 60/80 落在 >50-80 段；100 落在 >80-120 段
    ("L", 60,  "IT6"): 0.019, ("L", 60,  "IT7"): 0.030, ("L", 60,  "IT8"): 0.046,
    ("L", 80,  "IT6"): 0.019, ("L", 80,  "IT7"): 0.030, ("L", 80,  "IT8"): 0.046,
    ("L", 100, "IT6"): 0.022, ("L", 100, "IT7"): 0.035, ("L", 100, "IT8"): 0.054,

    # W: 40 落在 >30-50 段；60/80 落在 >50-80 段
    ("W", 40,  "IT6"): 0.016, ("W", 40,  "IT7"): 0.025, ("W", 40,  "IT8"): 0.039,
    ("W", 60,  "IT6"): 0.019, ("W", 60,  "IT7"): 0.030, ("W", 60,  "IT8"): 0.046,
    ("W", 80,  "IT6"): 0.019, ("W", 80,  "IT7"): 0.030, ("W", 80,  "IT8"): 0.046,

    # H: 10 落在 >6-10；15 落在 >10-18；20 落在 >18-30
    ("H", 10,  "IT6"): 0.009, ("H", 10,  "IT7"): 0.015, ("H", 10,  "IT8"): 0.022,
    ("H", 15,  "IT6"): 0.011, ("H", 15,  "IT7"): 0.018, ("H", 15,  "IT8"): 0.027,
    ("H", 20,  "IT6"): 0.013, ("H", 20,  "IT7"): 0.021, ("H", 20,  "IT8"): 0.033,

    # D: 10 落在 >6-10；20/30 落在 >18-30
    ("D", 10,  "IT6"): 0.009, ("D", 10,  "IT7"): 0.015, ("D", 10,  "IT8"): 0.022,
    ("D", 20,  "IT6"): 0.013, ("D", 20,  "IT7"): 0.021, ("D", 20,  "IT8"): 0.033,
    ("D", 30,  "IT6"): 0.013, ("D", 30,  "IT7"): 0.021, ("D", 30,  "IT8"): 0.033,
}

# ISO 尺寸段
SIZE_SEGMENT = {
    10:  ">6-10",
    15:  ">10-18",
    20:  ">18-30",
    30:  ">18-30",
    40:  ">30-50",
    60:  ">50-80",
    80:  ">50-80",     # 80 是 >50-80 上界
    100: ">80-120",
}

DIM_DEFINITION = {
    "L": "长方体长度",
    "W": "长方体宽度",
    "H": "长方体厚度",
    "D": "内孔拟合直径",
}

PATTERN_COUNTS = {
    "homogeneous": 20,
    "hetero_dims": 40,
    "hetero_form": 20,
    "mixed":       20,
}

# =========================================================
# 工具函数
# =========================================================

def deviations(tol_form, T):
    if tol_form == "sym":
        return round( T / 2.0, 6), round(-T / 2.0, 6)
    if tol_form == "plus":
        return round( T,       6), 0.0
    if tol_form == "minus":
        return 0.0,               round(-T,       6)
    if tol_form == "asym":
        return round( 0.7 * T, 6), round(-0.3 * T, 6)
    raise ValueError(tol_form)


def build_dimspec(dim, nominal, it_grade, tol_form):
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
    base, rem = divmod(n, len(items))
    pool = []
    for i, item in enumerate(items):
        pool.extend([item] * (base + (1 if i < rem else 0)))
    rng.shuffle(pool)
    return pool


def assign_it(pattern, rng):
    if pattern == "homogeneous":
        it = rng.choice(ITS)
        return {d: it for d in DIM_ORDER}
    if pattern in ("hetero_dims", "mixed"):
        # IT6/IT7/IT8 各一次 + 第 4 个随机 ⇒ 至少 3 种不同
        base  = rng.sample(ITS, 3)
        extra = rng.choice(ITS)
        its = base + [extra]
        rng.shuffle(its)
        return dict(zip(DIM_ORDER, its))
    if pattern == "hetero_form":
        return {d: rng.choice(ITS) for d in DIM_ORDER}
    raise ValueError(pattern)


def assign_form(pattern, rng):
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

    patterns = []
    for name, cnt in PATTERN_COUNTS.items():
        patterns.extend([name] * cnt)
    assert len(patterns) == n_designs
    rng.shuffle(patterns)

    nominal_pools = {d: stratified_pool(DIM_NOMINALS[d], n_designs, rng)
                     for d in DIM_ORDER}

    designs = []
    for i in range(n_designs):
        pattern = patterns[i]
        nominals = {d: nominal_pools[d][i] for d in DIM_ORDER}

        it_assign = assign_it(pattern, rng)
        fm_assign = assign_form(pattern, rng)

        dims = {d: build_dimspec(d, nominals[d], it_assign[d], fm_assign[d])
                for d in DIM_ORDER}

        designs.append({
            "design_id": f"hole_plate_{i + 1:04d}",
            "family":    "hole_plate",
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


def check_geometry(design):
    """校验两条几何约束：
    (1) L_nom > H_nom 且 W_nom > H_nom
    (2) D_nom < min(L_nom, W_nom)
    另外：检查 D 考虑公差后是否仍能放在 L×W 内部（宽松条件：D.USL < min(L.LSL, W.LSL)）
    """
    n = {d: design["dims"][d]["nominal"] for d in DIM_ORDER}
    ok1 = n["L"] > n["H"] and n["W"] > n["H"]
    ok2 = n["D"] < min(n["L"], n["W"])

    d_usl   = design["dims"]["D"]["USL"]
    l_lsl   = design["dims"]["L"]["LSL"]
    w_lsl   = design["dims"]["W"]["LSL"]
    ok3 = d_usl < min(l_lsl, w_lsl)
    return ok1, ok2, ok3


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
    print("\n[3] IT 分布（每维度 + 合计）:")
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
    print("\n[4] Form 分布（每维度 + 合计）:")
    for dim in DIM_ORDER:
        c = Counter(d["dims"][dim]["tol_form"] for d in designs)
        s = "  ".join(f"{k}:{c[k]:2d}" for k in FORMS)
        print(f"    {dim:3s}: {s}")
    total_fm = Counter()
    for d in designs:
        for dim in DIM_ORDER:
            total_fm[d["dims"][dim]["tol_form"]] += 1
    print(f"    合计: {dict(total_fm)}")

    # [5] 几何约束校验
    print("\n[5] 强制几何约束校验:")
    ok1 = ok2 = ok3 = 0
    bad = []
    for d in designs:
        a, b, c = check_geometry(d)
        ok1 += a; ok2 += b; ok3 += c
        if not (a and b):
            bad.append(d["design_id"])
    print(f"    L_nom > H_nom 且 W_nom > H_nom        : {ok1}/{n} "
          f"{'✓' if ok1 == n else '✗'}")
    print(f"    D_nom < min(L_nom, W_nom)             : {ok2}/{n} "
          f"{'✓' if ok2 == n else '✗'}")
    print(f"    D_USL < min(L_LSL, W_LSL) [严格]      : {ok3}/{n} "
          f"{'✓' if ok3 == n else '⚠ 部分违反（语义仍成立）'}")
    if bad:
        print(f"    ✗ 违反约束的设计: {bad[:5]}...")

    # [6] 多样性检查
    print("\n[6] 维度间多样性检查:")
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

    # [7] (nominal, IT) 交叉表（每维度）
    print("\n[7] (nominal, IT) 交叉表（每维度）:")
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

    # [8] (form, IT) 交叉表（全维度合计）
    print("\n[8] (form, IT) 交叉表（全维度合计）:")
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


# =========================================================
# Main
# =========================================================

if __name__ == "__main__":
    OUT_ROOT = "hole_plate_specs"
    os.makedirs(OUT_ROOT, exist_ok=True)

    designs = sample_designs(n_designs=100, seed=20241028)
    write_designs(designs, out_root=OUT_ROOT)
    print_summary(designs)
    print(f"\n完成：{len(designs)} 个 spec.json 已写入 '{OUT_ROOT}/hole_plate_XXXX/'")