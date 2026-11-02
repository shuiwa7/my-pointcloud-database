import os
import json
import csv
import random
import cadquery as cq
from tqdm import tqdm

BASE_DIR = "database"
EXPECTED_INSTANCES = 100
TOLERANCE = 1e-5  # 浮点数比较容差

def check_all():
    print("🕵️ 开始全量检查数据集 (包含 5 个零件族)...\n")
    
    # 【修改点 1】：加入新增的 2 个零件族
    families = ["box", "cylinder", "sphere", "stepped_shaft", "hole_plate"]
    total_designs = 0
    
    # 统计变量
    missing_folders = 0
    missing_files = 0
    empty_files = 0
    csv_errors = 0
    out_of_bounds = 0
    geom_mismatches = 0
    
    for family in families:
        specs_root = os.path.join(BASE_DIR, family, f"{family}_specs")
        if not os.path.isdir(specs_root):
            continue
            
        design_folders = sorted([d for d in os.listdir(specs_root) if d.startswith(family)])
        
        for folder in tqdm(design_folders, desc=f"检查 {family}"):
            total_designs += 1
            design_dir = os.path.join(specs_root, folder)
            
            # --- 1. 读取 spec.json ---
            spec_path = os.path.join(design_dir, "spec.json")
            with open(spec_path, 'r', encoding='utf-8') as f:
                spec = json.load(f)
            
            # --- 2. 检查 instances 文件夹和 CSV ---
            inst_dir = os.path.join(design_dir, "instances")
            if not os.path.isdir(inst_dir):
                tqdm.write(f"❌ 缺失 instances 文件夹: {design_dir}")
                missing_folders += 1
                continue
                
            csv_path = os.path.join(inst_dir, "instance_metadata.csv")
            if not os.path.exists(csv_path):
                tqdm.write(f"❌ 缺失 CSV 文件: {csv_path}")
                csv_errors += 1
                continue
                
            # 读取 CSV
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                if len(rows) != EXPECTED_INSTANCES:
                    tqdm.write(f"❌ CSV 行数错误 {folder}: 预期 {EXPECTED_INSTANCES}, 实际 {len(rows)}")
                    csv_errors += 1
            
            # --- 3. 遍历 CSV 每一行，检查 STEP 文件和公差边界 ---
            for row in rows:
                inst_id = row["instance_id"]
                step_path = os.path.join(inst_dir, f"{inst_id}.step")
                
                # 检查 STEP 是否存在且非空
                if not os.path.exists(step_path):
                    missing_files += 1
                    continue
                if os.path.getsize(step_path) < 1024:  # 小于 1KB 的通常有问题
                    empty_files += 1
                    
                # 检查尺寸是否越界 (这个逻辑对 5 个族都通用)
                for dim_name, dim_spec in spec["dims"].items():
                    val = float(row[f"actual_{dim_name}"])
                    lsl = dim_spec["LSL"]
                    usl = dim_spec["USL"]
                    
                    if val < lsl - TOLERANCE or val > usl + TOLERANCE:
                        tqdm.write(f"❌ 尺寸越界: {folder}/{inst_id} 维度 {dim_name} 实际={val}, 范围=[{lsl}, {usl}]")
                        out_of_bounds += 1

    # --- 4. 抽取 5 个文件做物理几何校验 ---
    print("\n🔬 正在随机抽取 5 个 STEP 文件进行物理几何尺寸校验...")
    all_step_files = []
    for root, dirs, files in os.walk(BASE_DIR):
        for file in files:
            if file.endswith(".step"):
                all_step_files.append(os.path.join(root, file))
    
    if len(all_step_files) > 5:
        samples = random.sample(all_step_files, 5)
    else:
        samples = all_step_files
        
    for sample in samples:
        inst_dir = os.path.dirname(sample)
        design_dir = os.path.dirname(inst_dir)
        family = os.path.basename(os.path.dirname(os.path.dirname(design_dir)))
        inst_id = os.path.basename(sample).replace(".step", "")
        
        csv_path = os.path.join(inst_dir, "instance_metadata.csv")
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["instance_id"] == inst_id:
                    expected_dims = row
                    break
                    
        try:
            shape = cq.importers.importStep(sample)
            bbox = shape.val().BoundingBox()
            
            # 【修改点 2】：加入新族的三维包围盒校验逻辑
            if family == "box":
                vols = sorted([bbox.xlen, bbox.ylen, bbox.zlen])
                expected = sorted([float(expected_dims["actual_L"]), 
                                   float(expected_dims["actual_W"]), 
                                   float(expected_dims["actual_H"])])
                for e, v in zip(expected, vols):
                    if abs(e - v) > 1e-4:
                        tqdm.write(f"❌ 几何校验失败: {sample} 预期 {expected} 实际 {vols}")
                        geom_mismatches += 1
                        break
                        
            elif family == "cylinder":
                expected_D = float(expected_dims["actual_D"])
                expected_H = float(expected_dims["actual_H"])
                if abs(bbox.xlen - expected_D) > 1e-4 or abs(bbox.zlen - expected_H) > 1e-4:
                    tqdm.write(f"❌ 几何校验失败: {sample} 预期 D={expected_D}, H={expected_H} 实际 X={bbox.xlen}, Z={bbox.zlen}")
                    geom_mismatches += 1
                    
            elif family == "sphere":
                expected_D = float(expected_dims["actual_D"])
                if abs(bbox.xlen - expected_D) > 1e-4:
                    tqdm.write(f"❌ 几何校验失败: {sample} 预期 D={expected_D} 实际 X={bbox.xlen}")
                    geom_mismatches += 1
                    
            elif family == "stepped_shaft":
                # 阶梯轴：X 和 Y 长度等于大径 D1，Z 长度等于两段高度之和
                expected_D1 = float(expected_dims["actual_D1"])
                expected_total_H = float(expected_dims["actual_H1"]) + float(expected_dims["actual_H2"])
                
                # 容忍 1e-4 的浮点误差
                if abs(bbox.xlen - expected_D1) > 1e-4 or abs(bbox.zlen - expected_total_H) > 1e-4:
                    tqdm.write(f"❌ 几何校验失败: {sample} 预期 D1={expected_D1}, Total_H={expected_total_H} 实际 X={bbox.xlen}, Z={bbox.zlen}")
                    geom_mismatches += 1
                    
            elif family == "hole_plate":
                # 带孔板：外包围盒依然是 L, W, H
                vols = sorted([bbox.xlen, bbox.ylen, bbox.zlen])
                expected = sorted([float(expected_dims["actual_L"]), 
                                   float(expected_dims["actual_W"]), 
                                   float(expected_dims["actual_H"])])
                for e, v in zip(expected, vols):
                    if abs(e - v) > 1e-4:
                        tqdm.write(f"❌ 几何校验失败: {sample} 预期 {expected} 实际 {vols}")
                        geom_mismatches += 1
                        break
            else:
                tqdm.write(f"✅ 抽检通过: {inst_id}")
                
        except Exception as e:
            tqdm.write(f"❌ 几何校验崩溃: {sample}, 错误: {e}")
            geom_mismatches += 1

    # --- 总结 ---
    print("\n" + "="*40)
    print("📊 检查结果汇总")
    print("="*40)
    print(f"总计扫描设计: {total_designs} 个")
    print(f"缺失文件夹: {missing_folders}")
    print(f"缺失 STEP 文件: {missing_files}")
    print(f"空/损坏 STEP 文件: {empty_files}")
    print(f"CSV 数据错误: {csv_errors}")
    print(f"尺寸越界错误: {out_of_bounds}")
    print(f"几何物理校验错误: {geom_mismatches}")
    print("="*40)
    
    if missing_files == 0 and empty_files == 0 and csv_errors == 0 and out_of_bounds == 0 and geom_mismatches == 0:
        print("🎉 完美！全量 39600 个数据集完全合规！")
    else:
        print("⚠️ 发现异常，请根据上方日志排查具体文件。")

if __name__ == "__main__":
    check_all()