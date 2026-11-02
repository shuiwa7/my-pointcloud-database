"""
sphere_spec_enum.py

对 Sphere 零件族（唯一维度 D）做 36 种 DimSpec 的全枚举，
按固定顺序 nominal → IT → form 依次输出 36 个设计，
每个设计写到 sphere_XXXX/spec.json。
"""

import json
import os

# =========================================================
# 基础配置
# =========================================================

NOMINALS = [20, 40, 100]                 # 外层循环
ITS      = ["IT6", "IT7", "IT8"]         # 中层循环
FORMS    = ["sym", "plus", "minus", "asym"]  # 内层循环

DIMS = ["D"]                              # 球只有 1 个维度

TOL_TABLE = {
    (20,  "IT6"): 0.013, (20,  "IT7"): 0.021, (20,  "IT8"): 0.033,
    (40,  "IT6"): 0.016, (40,  "IT7"): 0.025, (40,  "IT8"): 0.039,
    (100, "IT6"): 0.022, (100, "IT7"): 0.035, (100, "IT8"): 0.054,
}

SIZE_SEGMENT = {20: ">18-30", 40: ">30-50", 100: ">80-120"}

DIM_DEFINITION = {"D": "球面拟合直径"}

# =========================================================
# 工具函数
# =========================================================

def deviations(tol_form: str, T: float):
    """根据公差形式返回 (上偏差, 下偏差)。"""
    if tol_form == "sym":
        return round( T / 2.0, 6), round(-T / 2.0, 6)
    if tol_form == "plus":
        return round( T,       6), 0.0
    if tol_form == "minus":
        return 0.0,               round(-T,       6)
    if tol_form == "asym":
        return round( 0.7 * T, 6), round(-0.3 * T, 6)
    raise ValueError(f"unknown tol_form: {tol_form}")


def build_dimspec(dim: str, nominal: int, it_grade: str, tol_form: str) -> dict:
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
# 全枚举核心
# =========================================================

def enumerate_all_designs(seed: int = 20241028):
    """
    按 nominal → IT → form 的固定顺序全枚举 36 种 DimSpec。
    顺序编号规则：
      idx = (nominal 位置) × 12 + (IT 位置) × 4 + (form 位置)
    """
    designs = []
    idx = 0
    for nominal in NOMINALS:
        for it_grade in ITS:
            for tol_form in FORMS:
                idx += 1
                dims = {"D": build_dimspec("D", nominal, it_grade, tol_form)}
                designs.append({
                    "design_id": f"sphere_{idx:04d}",
                    "family":    "sphere",
                    "dims":      dims,
                    "sampling_meta": {
                        "pattern": "full_enum",
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
        with open(os.path.join(folder, "spec.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)


def print_enum_table(designs):
    """打印 36 行完整映射表，方便核对顺序。"""
    print("=" * 78)
    print(f"{'design_id':<14}{'nominal':>8}  {'IT':>5}  {'form':>6}    "
          f"{'T':>7}  {'upper':>8}  {'lower':>8}  {'LSL':>10}  {'USL':>10}")
    print("=" * 78)
    for d in designs:
        s = d["dims"]["D"]
        print(f"{d['design_id']:<14}{s['nominal']:>8.1f}  {s['it_grade']:>5}  "
              f"{s['tol_form']:>6}    {s['T']:>7.3f}  {s['upper_dev']:>+8.4f}  "
              f"{s['lower_dev']:>+8.4f}  {s['LSL']:>10.4f}  {s['USL']:>10.4f}")
    print("=" * 78)
    print(f"总数：{len(designs)} 个设计")


# =========================================================
# Main
# =========================================================

if __name__ == "__main__":
    OUT_ROOT = "sphere_specs"     # 输出根目录；如要输出到当前目录改为 "."
    os.makedirs(OUT_ROOT, exist_ok=True)

    designs = enumerate_all_designs(seed=20241028)
    write_designs(designs, out_root=OUT_ROOT)
    print_enum_table(designs)
    print(f"\n完成：{len(designs)} 个 spec.json 已写入 '{OUT_ROOT}/sphere_XXXX/'")