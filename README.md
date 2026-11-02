# Point Cloud Tolerance Inverse Dataset Pipeline

本项目旨在为“基于统计分析的逆向公差推理算法”提供具有**绝对真值（Ground Truth）**的测试数据集。流水线从带公差的 2D 图纸参数出发，生成 3D 实体模型，模拟真实加工误差，并最终生成带有物理扫描缺陷（飞点、噪点）的高密度点云数据，最后清洗输出为算法易读的纯坐标文本。

## 📦 数据集规模

本数据集涵盖 **5 个零件族**：
1. 长方体 (Box)
2. 圆柱 (Cylinder)
3. 球体 (Sphere)
4. 阶梯轴 (Stepped Shaft)
5. 带孔板 (Hole Plate)

总计 **396 个设计 (Design)**，每个设计生成 100 个实例，共计 **39,600 个样本**。

> **注意**：为了保持仓库轻量（< 1MB），本项目**不包含**生成的 3D 实体（STEP）和点云（PLY/XYZ）文件。请 clone 本仓库后，按照以下流程一键生成。

---

## 🛠️ 环境依赖

建议使用 Python 3.9+。运行以下命令安装所需的三维处理与科学计算库：

```bash
pip install cadquery numpy trimesh open3d tqdm
```

---

## 🚀 运行流水线

请按以下顺序在根目录下执行脚本：

### 第一步：生成 3D 实体 (STEP)
根据 `database` 目录下的 `spec.json`（图纸真值），对各个维度的尺寸进行截断正态分布抽样，使用 CadQuery 生成高精度 CAD 模型，并记录真实尺寸。

```bash
python generate_step.py
```
* **输入**：`database/*/*/*/spec.json`
* **输出**：`instances/inst_xxxx.step` 与 `instance_metadata.csv`

### 第二步：模拟物理扫描生成点云 (PLY)
将实体网格化，在表面均匀采样 30,000 个点。注入高斯测距噪声、边缘飞点（Flying Pixels）和空间悬浮噪点（Dust）。

```bash
python generate_dirty_pointcloud.py
```
* **输入**：`instances/inst_xxxx.step`
* **输出**：`instances/inst_xxxx_dirty.ply`（二进制格式）

### 第三步：去噪滤波与格式转换 (XYZ)
利用 Open3D 的统计离群点移除 (SOR) 算法清洗飞点和噪点，并导出为纯坐标的无头文本，方便直接用 Numpy 等库读取。

```bash
python filter_and_export_xyz.py
```
* **输入**：`instances/inst_xxxx_dirty.ply`
* **输出**：`instances/inst_xxxx_filtered.xyz`

### 第四步：数据集全量校验
验证生成的文件是否存在缺失，核对实体包围盒尺寸是否与 CSV 记录一致，确保所有实际尺寸都在公差界（LSL~USL）内。

```bash
python check_dataset.py
```

---

## 📂 核心数据说明

### 1. 设计层真值 (`spec.json`)
定义了零件各个维度的公称尺寸、IT 等级、上下偏差、LSL 与 USL。

```json
{
  "design_id": "hole_plate_0042",
  "family": "hole_plate",
  "dims": {
    "D": {
      "nominal": 20.0,
      "it_grade": "IT8",
      "tol_form": "plus",
      "LSL": 20.000,
      "USL": 20.033,
      "dim_definition": "内孔拟合直径"
    }
  }
}
```

### 2. 实例层真值 (`instance_metadata.csv`)
记录了每一个具体零件在“加工”后的绝对真实物理尺寸（保留 6 位小数），供拟合算法进行中间步骤的精度校验。

```csv
instance_id,actual_L,actual_W,actual_H,actual_D
inst_0001,100.01234,60.00123,10.00567,20.01122
```

---

## 📄 算法逻辑详细说明

### 尺寸误差模拟
采用**截断正态分布抽样**。设 \(C_p=1.33\)，标准差 \(\sigma = T / (6 C_p)\)。使用拒绝采样法确保生成的实际尺寸严格落在 \([LSL, USL]\) 区间内，模拟稳定工艺下的真实零件分布。

### 扫描缺陷模拟
1. **边缘飞点**：提取 2% 的表面点，沿面片法线向外平移随机距离（0.1~2.0 mm），模拟激光打在边缘时的反射拖尾。
2. **空间噪点**：在包围盒外围随机生成 300 个悬空点，模拟环境光散射。

### 滤波去噪
使用 Open3D 的统计滤波 (SOR) 算法，计算每个点到其 30 个邻居的平均距离，剔除超过全局均值 1.5 倍标准差的离群点，最大程度保留形貌并剔除飞点。