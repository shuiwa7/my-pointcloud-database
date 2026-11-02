import os
import json
import csv
import numpy as np
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import trimesh

# ================= 配置参数 =================
BASE_DIR = "database"
POINTS_PER_PART = 30000
SCAN_NOISE_SIGMA = 0.005
TESS_TOLERANCE = 0.005

FLYING_POINT_RATIO = 0.02
FLYING_POINT_SCALE = 2.0       
DUST_POINT_COUNT = 300
# ============================================

def process_pointcloud_task(args):
    inst_dir, step_filename = args
    import cadquery as cq
    
    step_path = os.path.join(inst_dir, step_filename)
    inst_id = step_filename.replace(".step", "")
    ply_path = os.path.join(inst_dir, f"{inst_id}_dirty.ply")
    
    if os.path.exists(ply_path):
        return "Skipped"  # 正常情况下不会被提交，这里做二次保险
    
    try:
        shape = cq.importers.importStep(step_path).val()
    except Exception as e:
        return f"❌ 读取STEP失败: {step_path}, {e}"
        
    vertices, triangles = shape.tessellate(TESS_TOLERANCE)
    if not triangles:
        return f"❌ 网格化为空: {step_path}"
        
    verts_array = np.array([[v.x, v.y, v.z] for v in vertices])
    faces_array = np.array(triangles)
    mesh = trimesh.Trimesh(vertices=verts_array, faces=faces_array)
    
    points, face_indices = trimesh.sample.sample_surface(mesh, POINTS_PER_PART)
    
    noise = np.random.normal(0, SCAN_NOISE_SIGMA, points.shape)
    noisy_points = points + noise
    
    n_flying = int(POINTS_PER_PART * FLYING_POINT_RATIO)
    flying_indices = np.random.choice(POINTS_PER_PART, n_flying, replace=False)
    flying_points = points[flying_indices].copy()
    
    normals = mesh.face_normals[face_indices[flying_indices]]
    offsets = np.random.uniform(0.1, FLYING_POINT_SCALE, size=(n_flying, 1))
    flying_noise = normals * offsets
    flying_noise += np.random.normal(0, SCAN_NOISE_SIGMA * 2, (n_flying, 3))
    flying_points += flying_noise
    
    bounds = mesh.bounds
    min_bound = bounds[0] - 2.0 
    max_bound = bounds[1] + 2.0
    dust_points = np.random.uniform(min_bound, max_bound, size=(DUST_POINT_COUNT, 3))
    
    final_points = np.vstack((noisy_points, flying_points, dust_points))
    np.random.shuffle(final_points)
    
    pcd = trimesh.PointCloud(final_points)
    pcd.export(ply_path, encoding='binary')
    
    return f"✅ 成功: {inst_id}"

def main():
    print("🚀 正在扫描所有的 STEP 文件以统计点云生成需求...")
    tasks = []
    families = ["box", "cylinder", "sphere", "stepped_shaft", "hole_plate"]
    
    total_steps_found = 0
    existing_plys = 0
    
    for family in families:
        specs_root = os.path.join(BASE_DIR, family, f"{family}_specs")
        if not os.path.isdir(specs_root):
            continue
            
        design_folders = sorted([d for d in os.listdir(specs_root) if d.startswith(family)])
        for folder in design_folders:
            design_dir = os.path.join(specs_root, folder)
            inst_dir = os.path.join(design_dir, "instances")
            if not os.path.isdir(inst_dir):
                continue
                
            for file in os.listdir(inst_dir):
                if file.endswith(".step"):
                    total_steps_found += 1
                    ply_file = file.replace(".step", "_dirty.ply")
                    
                    if os.path.exists(os.path.join(inst_dir, ply_file)):
                        existing_plys += 1
                    else:
                        tasks.append((inst_dir, file))
                        
    total_tasks = len(tasks)
    
    print("="*50)
    print(f"📊 点云扫描结果:")
    print(f"   - 找到 STEP 总数 : {total_steps_found} 个")
    print(f"   - 已有点云数量 : {existing_plys} 个 ✅")
    print(f"   - 本次需新生成 : {total_tasks} 个 🚀")
    print("="*50 + "\n")
    
    if total_tasks == 0:
        print("✅ 所有点云均已生成，无需重复操作！")
        return

    max_workers = max(1, multiprocessing.cpu_count() - 1)
    print(f"⚡ 启动 {max_workers} 个并行进程执行点云生成...\n")
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_pointcloud_task, task): task for task in tasks}
        for future in tqdm(as_completed(futures), total=total_tasks, desc="新增点云进度", unit="件"):
            try:
                result = future.result()
                if result.startswith("❌"):
                    tqdm.write(result)
            except Exception as e:
                tqdm.write(f"❌ 进程崩溃: {e}")

    print("\n✅ 全部执行完毕！")

if __name__ == "__main__":
    main()