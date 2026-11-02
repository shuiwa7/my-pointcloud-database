import os
import json
import csv
import numpy as np
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

# ================= 配置参数 =================
BASE_DIR = "database"
NUM_INSTANCES = 100
CP_TARGET = 1.33          
BASE_SEED = 20241028      
# ============================================

def sample_truncated_normal(lsl, usl, cp, rng):
    T = usl - lsl
    mu = (usl + lsl) / 2.0
    sigma = T / (6.0 * cp)
    while True:
        val = rng.normal(mu, sigma)
        if lsl <= val <= usl:
            return val

def process_design_task(args):
    design_dir, family, design_seed = args
    import cadquery as cq 
    
    spec_path = os.path.join(design_dir, "spec.json")
    if not os.path.exists(spec_path):
        return {"id": "", "created": 0, "skipped": 0}
        
    with open(spec_path, 'r', encoding='utf-8') as f:
        spec = json.load(f)
        
    dims = spec["dims"]
    inst_dir = os.path.join(design_dir, "instances")
    os.makedirs(inst_dir, exist_ok=True)
    csv_path = os.path.join(inst_dir, "instance_metadata.csv")
    metadata_rows = []
    
    rng = np.random.default_rng(design_seed)
    
    created_cnt = 0
    skipped_cnt = 0
    
    for i in range(1, NUM_INSTANCES + 1):
        inst_id = f"inst_{i:04d}"
        step_path = os.path.join(inst_dir, f"{inst_id}.step")
        
        actual_dims = {}
        for dim_name, dim_spec in dims.items():
            actual_dims[dim_name] = sample_truncated_normal(
                dim_spec["LSL"], dim_spec["USL"], cp=CP_TARGET, rng=rng
            )
            
        row = {"instance_id": inst_id}
        for k, v in actual_dims.items():
            row[f"actual_{k}"] = round(v, 6) 
        metadata_rows.append(row)
        
        # 检查是否存在
        if os.path.exists(step_path):
            skipped_cnt += 1
            continue
            
        # 建模
        if family == "box":
            part = cq.Workplane("XY").box(actual_dims["L"], actual_dims["W"], actual_dims["H"])
        elif family == "cylinder":
            part = cq.Workplane("XY").circle(actual_dims["D"] / 2.0).extrude(actual_dims["H"])
        elif family == "sphere":
            part = cq.Workplane("XY").sphere(actual_dims["D"] / 2.0)
        elif family == "stepped_shaft":
            part = cq.Workplane("XY").circle(actual_dims["D1"] / 2.0).extrude(actual_dims["H1"])
            part = part.faces(">Z").workplane().circle(actual_dims["D2"] / 2.0).extrude(actual_dims["H2"])
        elif family == "hole_plate":
            part = cq.Workplane("XY").box(actual_dims["L"], actual_dims["W"], actual_dims["H"])
            part = part.faces(">Z").workplane().hole(actual_dims["D"])
        else:
            raise ValueError(f"Unknown family: {family}")
            
        cq.exporters.export(part, step_path, exportType="STEP")
        created_cnt += 1
        
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=metadata_rows[0].keys())
        writer.writeheader()
        writer.writerows(metadata_rows)
        
    return {"id": spec['design_id'], "created": created_cnt, "skipped": skipped_cnt}

def main():
    print("🚀 正在扫描设计图纸并构建并行任务列表...")
    tasks = []
    families = ["box", "cylinder", "sphere", "stepped_shaft", "hole_plate"]
    
    for family in families:
        specs_root = os.path.join(BASE_DIR, family, f"{family}_specs")
        if not os.path.isdir(specs_root):
            continue
            
        design_folders = sorted([d for d in os.listdir(specs_root) if d.startswith(family)])
        for folder in design_folders:
            design_dir = os.path.join(specs_root, folder)
            try:
                design_num = int(folder.split('_')[-1])
            except:
                design_num = 0
            design_seed = BASE_SEED + design_num
            tasks.append((design_dir, family, design_seed))
            
    total_designs = len(tasks)
    total_expected_files = total_designs * NUM_INSTANCES
    
    print("="*50)
    print(f"📊 设计层扫描结果:")
    print(f"   - 发现设计总数 : {total_designs} 个")
    print(f"   - 理论模型总数 : {total_expected_files} 个 STEP")
    print("⏳ 脚本正在后台静默核验哪些文件已存在，请稍候...")
    
    # 预先计算现有文件数
    existing_files = 0
    for design_dir, _, _ in tasks:
        inst_dir = os.path.join(design_dir, "instances")
        if os.path.isdir(inst_dir):
            existing_files += sum(1 for f in os.listdir(inst_dir) if f.endswith(".step"))
            
    to_generate = total_expected_files - existing_files
    print(f"   - 已有文件数量 : {existing_files} 个 ✅")
    print(f"   - 本次需新生成 : {to_generate} 个 🚀")
    print("="*50 + "\n")
    
    if to_generate == 0:
        print("✅ 所有 STEP 文件均已存在，无需重复操作！")
        return

    max_workers = max(1, multiprocessing.cpu_count() - 1)
    print(f"⚡ 启动 {max_workers} 个并行进程执行生成任务...\n")
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_design_task, task): task for task in tasks}
        for future in tqdm(as_completed(futures), total=total_designs, desc="生成进度", unit="设计"):
            try:
                future.result()
            except Exception as e:
                tqdm.write(f"❌ 任务出错: {e}")

    print("\n✅ 全部执行完毕！")

if __name__ == "__main__":
    main()