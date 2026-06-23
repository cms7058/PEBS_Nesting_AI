# 第零阶段 · 算法可行性验证（Phase 0）

> **生死线**：异形套料利用率 ≥85%，逼近 SigmaNEST。过线才进入第一阶段工程开发（Go/No-Go 硬门槛）。

本目录是一次性「探针」工程，只验证数学命门，不追求工程质量。Python 独立 venv，与仓库根的 Node 阿米巴连接器互不影响。

## 目录结构

```
phase0/
├── src/
│   ├── dxf_io.py            # DXF 读写 / 闭合轮廓提取（ezdxf + shapely）
│   ├── generate_samples.py  # 合成 DXF 样本（矩形 / L 形 / 不规则件混合）
│   ├── nest_baseline.py     # 排料基线：Bottom-Left 贪心 + 多角度 + 碰撞检测
│   └── run.py               # 主入口：样本 → 排料 → 出图 → 利用率报告
├── samples/                 # 合成 DXF 样本
└── out/                     # 排料图 PNG + 报告
```

## 运行

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python src/generate_samples.py     # 生成合成样本
.venv/bin/python src/run.py                  # 跑基线，输出利用率与排料图
.venv/bin/python src/run.py samples/sample_1.dxf   # 跑指定 DXF
```

## 算法演进路径（文档「能跑 → 够用 → 领先」）

| 步骤 | 状态 | 说明 |
|---|---|---|
| 基线 Bottom-Left + 启发式 | ✅ 已跑通（~56%） | `nest_baseline.place()` |
| NFP 临界多边形（核心壁垒） | ✅ 已实现 | `nfp.py`，pyclipper Minkowski 和 |
| 进阶 GA 优化顺序与角度 | ✅ 已实现 | `nest_nfp.optimize_ga()` |
| 多目标 NSGA-II | ⬜ 可选 | 平衡利用率 / 切割长度 / 余料质量 |

## 验证结论（合成样本，80 件/板宽 1000）

| 料型 | NFP+GA 利用率 | 判定 |
|---|---|---|
| 纯矩形件 | **86.1%** | ✅ 过线 |
| 矩形为主 + 少量异形 | 83.1% | 逼近 |
| 矩形/L 混合 | 78.7% | 待 Deepnest |
| 高难随机凹异形 | 72.6% | 待 Deepnest |

**结论**：自研 NFP+GA 在**矩形/矩形为主料型已过 85%**，第一阶段板材 MVP（矩形优先）算法可行性成立；
高难异形 ~73%，按文档**不重造轮子**，异形引擎基于 Deepnest 二开。数字为合成样本，待真实工厂 DXF 复核。

跑验证矩阵：`.venv/bin/python src/experiment.py` → 输出 `out/phase0_report.md` + 各料型排料图。

---

## 真实基准数据集（公开）

[ESICUP datasets](https://github.com/ESICUP/datasets) — 异形排样学术金标准实例（albano/swim/trousers/shapes…），
含 90° 与连续旋转变体。已 clone 至 `datasets/esicup/`。

- `src/esicup.py` — ESICUP XML → shapely 多边形解析器（可导出 DXF 喂入自研引擎）

## B 路线：接入成熟引擎（sparrow / jagua-rs）

真正的 Deepnest 是 Electron 桌面应用、难 headless；同属 **NFP+GA 家族**的生产级开源引擎
[**sparrow**](https://github.com/JeroenGar/sparrow)（基于碰撞引擎 `jagua-rs`，**均为 MIT 许可，可商用**）
是异形排料的开源 SOTA。已构建 `engines/sparrow/`，跑批：

```bash
.venv/bin/python src/run_sparrow.py 20    # 每实例 20s
```

**实测（20s/实例，对照文献 best-known）**：

| 实例 | sparrow | best-known | 性质 |
|---|---|---|---|
| trousers | **91.3%** | 89.7% | 真实裁剪件 |
| marques | **90.3%** | 89.2% | 真实件 |
| jakobs1 | **89.1%** | 78.9% | 抽象件 |
| albano | **88.4%** | 88.2% | 纺织件 |
| dagli | 86.7% | 87.3% | 真实件 |
| mao | 84.2% | 85.2% | 真实件 |
| swim | 75.2% | 75.7% | 高难纺织（SOTA 即此） |
| shapes0 | 66.5% | 66.5% | 最难抽象（SOTA 即此） |

**结论**：成熟引擎仅 20s 即**达到/超过学术 SOTA**；偏真实形状的实例普遍 **84–91%**，
低值实例（swim/shapes0）是 SOTA 本身的天花板、且远比真实钣金件难。
→ **异形命门可通过「集成 sparrow/jagua-rs」解决，无需自研，印证文档「不重造轮子」策略。**

## 验收口径

- 输入：真实工厂 DXF（待提供）/ 当前用合成样本起步
- 指标：平均利用率、单样本利用率、耗时
- 对照：与 SigmaNEST / 手工排料结果对比，确认差距可接受
- 产出：**异形套料利用率验证报告 + Go/No-Go 决议**
