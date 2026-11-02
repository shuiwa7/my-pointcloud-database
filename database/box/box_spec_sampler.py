"""
box_spec_sampler.py

为 box 零件族生成 100 个设计规格（spec.json），
覆盖 nominal × IT × form 的 36 种 DimSpec 组合，
并按 4 种搭配模式做分层 + 随机抽样。
"""

import json
import os
import random
from collections import Counter

# =========================================================
# 基础配置
# =========================================================

NOMINALS = [20, 40, 100]
ITS      = ["IT6", "IT7", "IT8"]
FORMS    = ["sym", "plus", "minus", "asym"]
DIMS     = ["L", "W", "H"]

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
    "L": "两平行端面距离",
    "W": "两平行侧面距离",
    "H": "上下两面距离",
}

# =========================================================
# 工具函数
# =========================================================

def deviations(tol_form: str, T: float):
    """根据公差形式返回 (上偏差, 下偏差)。"""
    if tol_form == "sym":         # ±T/2
        upper, lower =  T / 2.0, -T / 2.0
    elif tol_form == "plus":      # ei=0
        upper, lower =  T,       0.0
    elif tol_form == "minus":     # es=0
        upper, lower =  0.0,    -T
    elif tol_form == "asym":      # es=+0.7T, ei=-0.3T
        upper, lower =  0.7 * T, -0.3 * T
    else:
        raise ValueError(f"unknown tol_form: {tol_form}")
    return round(upper, 6), round(lower, 6)


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


def make_stratified_pool(items, n, rng):
    """把 items 均匀填充到 n 个槽位并打乱（分层）。"""
    pool = []
    base, rem = divmod(n, len(items))
    for j, item in enumerate(items):
        pool.extend([item] * (base + (1 if j < rem else 0)))
    rng.shuffle(pool)
    return pool


# =========================================================
# 抽样核心
# =========================================================

def sample_designs(n_designs: int = 100, seed: int = 20241028):
    rng = random.Random(seed)

    # ---- 1. 搭配模式分配（20% / 40% / 20% / 20%）----
    mode_counts = [
        ("homogeneous", 0.20),
        ("hetero_it",   0.40),
        ("hetero_form", 0.20),
        ("mixed",       0.20),
    ]
    patterns = []
    for name, ratio in mode_counts:
        patterns.extend([name] * int(round(ratio * n_designs)))
    # 修正累计误差
    while len(patterns) < n_designs:
        patterns.append("mixed")
    patterns = patterns[:n_designs]
    rng.shuffle(patterns)

    # ---- 2. 名义尺寸分层池（每个维度位置独立）----
    nominal_pools = {d: make_stratified_pool(NOMINALS, n_designs, rng) for d in DIMS}

    # ---- 3. 逐设计生成 ----
    designs = []
    for i in range(n_designs):
        pattern = patterns[i]
        nominal = {d: nominal_pools[d][i] for d in DIMS}

        if pattern == "homogeneous":
            # 三个维度同一 IT、同一 form
            shared_it   = rng.choice(ITS)
            shared_form = rng.choice(FORMS)
            it_assign   = {d: shared_it   for d in DIMS}
            form_assign = {d: shared_form for d in DIMS}

        elif pattern == "hetero_it":
            # 三个维度 IT 各不相同（3 档 IT 全用），form 自由
            shuffled_it = ITS[:]
            rng.shuffle(shuffled_it)
            it_assign   = dict(zip(DIMS, shuffled_it))
            form_assign = {d: rng.choice(FORMS) for d in DIMS}

        elif pattern == "hetero_form":
            # 三个维度 form 各不相同（从 4 档里挑 3 档），IT 自由
            it_assign   = {d: rng.choice(ITS) for d in DIMS}
            chosen_forms = rng.sample(FORMS, len(DIMS))
            form_assign  = dict(zip(DIMS, chosen_forms))

        elif pattern == "mixed":
            # IT 和 form 都各不相同
            shuffled_it = ITS[:]
            rng.shuffle(shuffled_it)
            it_assign   = dict(zip(DIMS, shuffled_it))
            chosen_forms = rng.sample(FORMS, len(DIMS))
            form_assign  = dict(zip(DIMS, chosen_forms))

        else:
            raise ValueError(pattern)

        dims = {
            d: build_dimspec(d, nominal[d], it_assign[d], form_assign[d])
            for d in DIMS
        }

        designs.append({
            "design_id": f"box_{i + 1:04d}",
            "family":    "box",
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

def write_designs(designs, out_root: str = "."):
    for spec in designs:
        folder = os.path.join(out_root, spec["design_id"])
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "spec.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)


def print_summary(designs):
    pattern_c = Counter(d["sampling_meta"]["pattern"] for d in designs)
    it_c, form_c, combo_c, nom_c = Counter(), Counter(), Counter(), Counter()
    for d in designs:
        for dim in DIMS:
            s = d["dims"][dim]
            nom_c[s["nominal"]]          += 1
            it_c[s["it_grade"]]          += 1
            form_c[s["tol_form"]]        += 1
            combo_c[(s["nominal"], s["it_grade"])] += 1

    print(f"设计数量     : {len(designs)}")
    print(f"模式分布     : {dict(pattern_c)}")
    print(f"nominal 分布 : {dict(sorted(nom_c.items()))}")
    print(f"IT      分布 : {dict(it_c)}")
    print(f"form    分布 : {dict(form_c)}")
    print("(nominal, IT) 组合分布：")
    for k in sorted(combo_c):
        print(f"    {k}: {combo_c[k]}")


# =========================================================
# Main
# =========================================================

if __name__ == "__main__":
    OUT_ROOT = "box_specs"     # 输出根目录，可按需修改
    os.makedirs(OUT_ROOT, exist_ok=True)

    designs = sample_designs(n_designs=100, seed=20241028)
    write_designs(designs, out_root=OUT_ROOT)
    print_summary(designs)
    print(f"\n完成：{len(designs)} 个 spec.json 已写入 '{OUT_ROOT}/box_XXXX/'")