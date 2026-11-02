"""
cylinder_spec_sampler.py

为 cylinder 零件族生成 60 个设计规格（spec.json），
覆盖 nominal × IT × form 的 36 种 DimSpec 组合，
按 4 种搭配模式分层抽样，并叠加两条覆盖约束：
  1) nominal 覆盖：每个 nominal 在 D 和 H 上各至少出现 15 次
  2) 尺寸段交叉覆盖：约 50% 设计 D 与 H 落在不同尺寸段，约 50% 同段
"""

import json
import os
import random
from collections import Counter

# =========================================================
# 基础配置
# =========================================================

N_DESIGNS = 60
NOMINALS  = [20, 40, 100]
ITS       = ["IT6", "IT7", "IT8"]
FORMS     = ["sym", "plus", "minus", "asym"]
DIMS      = ["D", "H"]

# ISO 基本公差值（单位 mm）
TOL_TABLE = {
    (20,  "IT6"): 0.013, (20,  "IT7"): 0.021, (20,  "IT8"): 0.033,
    (40,  "IT6"): 0.016, (40,  "IT7"): 0.025, (40,  "IT8"): 0.039,
    (100, "IT6"): 0.022, (100, "IT7"): 0.035, (100, "IT8"): 0.054,
}

SIZE_SEGMENT = {
    20:  ">18-30",
    40:  ">30-50",
    100: ">80-120",
}

DIM_DEFINITION = {
    "D": "外圆柱拟合直径",
    "H": "两端面距离",
}

# =========================================================
# 工具函数
# =========================================================

def deviations(tol_form: str, T: float):
    """根据公差形式返回 (上偏差, 下偏差)。"""
    if tol_form == "sym":         # ±T/2
        return round( T / 2.0, 6), round(-T / 2.0, 6)
    if tol_form == "plus":        # ei=0
        return round( T,       6), 0.0
    if tol_form == "minus":       # es=0（轴的 h）
        return 0.0,               round(-T,       6)
    if tol_form == "asym":        # es=+0.7T, ei=-0.3T
        return round( 0.7 * T, 6), round(-0.3 * T, 6)
    raise ValueError(f"unknown tol_form: {tol_form}")


def build_dimspec(dim: str, nominal: int, it_grade: str, tol_form: str) -> dict:
    """构造单个维度的 DimSpec 字典。"""
    T = TOL_TABLE[(nominal, it_grade)]
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


# =========================================================
# 约束构造：nominal 池 + 尺寸段交叉覆盖
# =========================================================

def build_nominal_pairs(n: int, rng: random.Random):
    """
    生成 n 个 (D_nominal, H_nominal, cross_segment) 三元组。

    构造思路（n 需能被 6 整除，对 n=60 完美平衡）：
      - n/2 个「同段」对：D = H，三档均匀（20/40/100 各 n/6 次）
      - n/2 个「跨段」对：D ≠ H，六种有序组合各 n/12 次
        → 恰好让每个 nominal 在 D 上出现 n/3 次，在 H 上也 n/3 次
        → 满足「每个 nominal 在 D/H 上各 ≥ 15 次」（n=60 时为 20 次）
    """
    assert n % 6 == 0, "n 需能被 6 整除以保证 nominal 均匀覆盖"

    n_same  = n // 2        # 30
    n_cross = n - n_same    # 30
    per_nom_same  = n_same // 3      # 10，同段中每个 nominal 出现次数
    per_pair_cross = n_cross // 6    # 5，跨段中每个有序对出现次数

    pairs = []

    # 同段：D = H
    for nv in NOMINALS:
        for _ in range(per_nom_same):
            pairs.append((nv, nv, False))

    # 跨段：D ≠ H，六个有序对 (20,40) (20,100) (40,20) (40,100) (100,20) (100,40)
    for d_nv in NOMINALS:
        for h_nv in NOMINALS:
            if d_nv != h_nv:
                for _ in range(per_pair_cross):
                    pairs.append((d_nv, h_nv, True))

    rng.shuffle(pairs)
    return pairs


def build_patterns(n: int, rng: random.Random):
    """
    分配 n 个设计的搭配模式：
      homogeneous 20% / hetero_it 40% / hetero_form 20% / mixed 20%
    """
    ratios = [
        ("homogeneous", 0.20),
        ("hetero_it",   0.40),
        ("hetero_form", 0.20),
        ("mixed",       0.20),
    ]
    patterns = []
    for name, r in ratios:
        patterns.extend([name] * int(round(r * n)))
    while len(patterns) < n:
        patterns.append("mixed")
    patterns = patterns[:n]
    rng.shuffle(patterns)
    return patterns


# =========================================================
# 抽样核心
# =========================================================

def sample_designs(n_designs: int = N_DESIGNS, seed: int = 20241028):
    rng = random.Random(seed)

    patterns     = build_patterns(n_designs, rng)
    nominal_pairs = build_nominal_pairs(n_designs, rng)

    designs = []
    for i in range(n_designs):
        pattern = patterns[i]
        d_nom, h_nom, cross = nominal_pairs[i]

        # ---- 按 pattern 生成 IT / form 分配 ----
        if pattern == "homogeneous":
            # D 与 H 同一 IT、同一 form
            it  = rng.choice(ITS)
            fm  = rng.choice(FORMS)
            it_a = {"D": it,   "H": it}
            fm_a = {"D": fm,   "H": fm}

        elif pattern == "hetero_it":
            # D 与 H 的 IT 不同（从 3 档里取 2 个不同的）；form 自由
            two_it = rng.sample(ITS, 2)
            it_a = {"D": two_it[0], "H": two_it[1]}
            fm_a = {"D": rng.choice(FORMS), "H": rng.choice(FORMS)}

        elif pattern == "hetero_form":
            # D 与 H 的 form 不同（从 4 档里取 2 个不同的）；IT 自由
            it_a = {"D": rng.choice(ITS), "H": rng.choice(ITS)}
            two_fm = rng.sample(FORMS, 2)
            fm_a = {"D": two_fm[0], "H": two_fm[1]}

        elif pattern == "mixed":
            # IT 和 form 都不同
            two_it = rng.sample(ITS, 2)
            two_fm = rng.sample(FORMS, 2)
            it_a = {"D": two_it[0], "H": two_it[1]}
            fm_a = {"D": two_fm[0], "H": two_fm[1]}

        else:
            raise ValueError(pattern)

        dims = {
            "D": build_dimspec("D", d_nom, it_a["D"], fm_a["D"]),
            "H": build_dimspec("H", h_nom, it_a["H"], fm_a["H"]),
        }

        designs.append({
            "design_id": f"cylinder_{i + 1:04d}",
            "family":    "cylinder",
            "dims":      dims,
            "sampling_meta": {
                "pattern":        pattern,
                "cross_segment":  cross,
                "seed":           seed,
            },
        })

    return designs


# =========================================================
# 写出与统计
# =========================================================

def write_designs(designs, out_root: str = "."):
    for spec in designs:
        folder = os.path.join(out_root, spec["design_id"])
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "spec.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)


def print_summary(designs):
    n = len(designs)
    pattern_c = Counter(d["sampling_meta"]["pattern"]        for d in designs)
    cross_c   = Counter(d["sampling_meta"]["cross_segment"]  for d in designs)

    d_nom_c, h_nom_c = Counter(), Counter()
    it_c, form_c     = Counter(), Counter()
    ni_d, ni_h       = Counter(), Counter()   # (nominal, IT) 分布
    same_it = same_fm = both = 0
    for d in designs:
        for dim in DIMS:
            s = d["dims"][dim]
            it_c[s["it_grade"]]   += 1
            form_c[s["tol_form"]] += 1
            if dim == "D":
                d_nom_c[s["nominal"]] += 1
                ni_d[(s["nominal"], s["it_grade"])] += 1
            else:
                h_nom_c[s["nominal"]] += 1
                ni_h[(s["nominal"], s["it_grade"])] += 1
        its = {d["dims"][k]["it_grade"] for k in DIMS}
        fms = {d["dims"][k]["tol_form"] for k in DIMS}
        if len(its) == 1: same_it += 1
        if len(fms) == 1: same_fm += 1
        if len(its) == 1 and len(fms) == 1: both += 1

    print("=" * 68)
    print(f"设计数量: {n}   DimSpec 总数: {n * len(DIMS)}")
    print("=" * 68)

    print(f"\n[1] 搭配模式    : {dict(pattern_c)}")
    print(f"[2] 跨段标记    : cross=True -> {cross_c[True]}, "
          f"cross=False -> {cross_c[False]}")

    print(f"\n[3] D 的 nominal : {dict(sorted(d_nom_c.items()))}")
    print(f"    H 的 nominal : {dict(sorted(h_nom_c.items()))}")

    print(f"\n[4] IT 边缘分布 : {dict(it_c)}")
    print(f"    form 边缘   : {dict(form_c)}")

    print("\n[5] (nominal, IT) 分布 —— D 侧:")
    print(f"    {'nominal':>8} | {'IT6':>5} {'IT7':>5} {'IT8':>5} | 行和")
    for nv in NOMINALS:
        row = [ni_d[(nv, g)] for g in ITS]
        print(f"    {nv:>6}mm | {row[0]:>5} {row[1]:>5} {row[2]:>5} | {sum(row)}")

    print("\n[6] (nominal, IT) 分布 —— H 侧:")
    print(f"    {'nominal':>8} | {'IT6':>5} {'IT7':>5} {'IT8':>5} | 行和")
    for nv in NOMINALS:
        row = [ni_h[(nv, g)] for g in ITS]
        print(f"    {nv:>6}mm | {row[0]:>5} {row[1]:>5} {row[2]:>5} | {sum(row)}")

    print("\n[7] 维度间多样性检查:")
    print(f"    D 与 H 同 IT          : {same_it}")
    print(f"    D 与 H 同 form        : {same_fm}")
    print(f"    同 IT 且同 form       : {both}  (预期 = homogeneous 数量 = 12)")

    # 覆盖约束硬检查
    print("\n[8] 覆盖约束检查:")
    ok = True
    for nv in NOMINALS:
        if d_nom_c[nv] < 15:
            print(f"    ✗ D 侧 nominal={nv} 出现 {d_nom_c[nv]} 次 < 15")
            ok = False
        if h_nom_c[nv] < 15:
            print(f"    ✗ H 侧 nominal={nv} 出现 {h_nom_c[nv]} 次 < 15")
            ok = False
    print(f"    nominal ≥ 15 次         : {'✓ 通过' if ok else '✗ 失败'}")
    print(f"    cross_segment 两种都出现: "
          f"{'✓' if cross_c[True] > 0 and cross_c[False] > 0 else '✗'}  "
          f"(cross={cross_c[True]}, same={cross_c[False]})")


# =========================================================
# Main
# =========================================================

if __name__ == "__main__":
    OUT_ROOT = "cylinder_specs"   # 输出根目录；想输出到当前目录改成 "."
    os.makedirs(OUT_ROOT, exist_ok=True)

    designs = sample_designs(n_designs=N_DESIGNS, seed=20241028)
    write_designs(designs, out_root=OUT_ROOT)
    print_summary(designs)
    print(f"\n完成：{len(designs)} 个 spec.json 已写入 '{OUT_ROOT}/cylinder_XXXX/'")