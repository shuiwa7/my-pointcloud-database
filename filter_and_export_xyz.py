import os
import numpy as np
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import open3d as o3d

# ================= 配置参数 =================
BASE_DIR = "database"

# 滤波参数 (SOR)
NB_NEIGHBORS = 30          # 考察每个点周围的 30 个邻居
STD_RATIO = 1.5            # 标准差乘数。越小，过滤越狠；越大，保留越宽松。1.5 通常能滤掉飞点。

# 输出格式控制
XYZ_DECIMAL = 6            # 坐标保留的小数位数
# ============================================

def process_xyz_task(args):
    inst_dir, ply_filename = args
    
    ply_path = os.path.join(inst_dir, ply_filename)
    # 输出命名：inst_0001_dirty.ply -> inst_0001_filtered.xyz
    base_name = ply_filename.replace("_dirty.ply", "")
    xyz_path = os.path.join(inst_dir, f"{base_name}_filtered.xyz")
    
    # 1. 读取原始带噪点云
    try:
        pcd = o3d.io.read_point_cloud(ply_path)
    except Exception as e:
        return f"❌ 读取PLY失败: {ply_path}, {e}"
        
    if len(pcd.points) == 0:
        return f"❌ 点云为空: {ply_path}"
        
    # 2. 执行统计滤波 (SOR)
    # 返回的 cl, ind 分别是过滤后的点云和保留点的索引
    cl, ind = pcd.remove_statistical_outlier(nb_neighbors=NB_NEIGHBORS, std_ratio=STD_RATIO)
    
    filtered_points = np.asarray(cl.points)
    
    if len(filtered_points) == 0:
        return f"❌ 滤波后为空: {ply_path}"
        
    # 3. 导出为 XYZ 格式 (只保留 X Y Z，空格分隔)
    # np.savetxt 写入速度非常快，fmt 控制精度
    try:
        np.savetxt(xyz_path, filtered_points, fmt=f"%.{XYZ_DECIMAL}f %.{XYZ_DECIMAL}f %.{XYZ_DECIMAL}f")
    except Exception as e:
        return f"❌ 写入XYZ失败: {xyz_path}, {e}"
        
    return f"✅ 成功: {base_name}"

def main():
    print("🚀 开始扫描 PLY 文件并构建滤波导出任务...")
    tasks = []
    families = ["box", "cylinder", "sphere", "stepped_shaft", "hole_plate"]
    
    total_plys = 0
    existing_xyzs = 0
    
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
                if file.endswith("_dirty.ply"):
                    total_plys += 1
                    base_name = file.replace("_dirty.ply", "")
                    xyz_file = f"{base_name}_filtered.xyz"
                    
                    if os.path.exists(os.path.join(inst_dir, xyz_file)):
                        existing_xyzs += 1
                    else:
                        tasks.append((inst_dir, file))
                        
    total_tasks = len(tasks)
    
    print("="*50)
    print(f"📊 过滤与导出扫描结果:")
    print(f"   - 找到原 PLY 总数 : {total_plys} 个")
    print(f"   - 已有 XYZ 文件数 : {existing_xyzs} 个 ✅")
    print(f"   - 本次需新生成    : {total_tasks} 个 🚀")
    print("="*50 + "\n")
    
    if total_tasks == 0:
        print("✅ 所有 XYZ 文件均已生成，无需重复操作！")
        return

    max_workers = max(1, multiprocessing.cpu_count() - 1)
    print(f"⚡ 启动 {max_workers} 个并行进程执行滤波与导出...\n")
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_xyz_task, task): task for task in tasks}
        for future in tqdm(as_completed(futures), total=total_tasks, desc="滤波导出进度", unit="件"):
            try:
                result = future.result()
                if result.startswith("❌"):
                    tqdm.write(result)
            except Exception as e:
                tqdm.write(f"❌ 进程崩溃: {e}")

    print("\n✅ 全部滤波并导出为 XYZ 完成！")

if __name__ == "__main__":
    main()