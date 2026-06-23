# 智能排料 Copilot · PEBS Nesting AI

> 用对话完成工业排料,让材料利用率最大化。

面向中小钣金 / 机械加工厂的**板材 · 管材 · 棒材全料型自动下料系统**:以对话式智能体为统一入口,覆盖二维异形/矩形套料与一维下料,自动生成出料表、切割单、NC,并把材料成本/工时喂入 PEBS 阿米巴经营核算。

与传统套料软件最大的不同:用户无需掌握复杂 CAD 排版,只需自然语言描述需求或上传 DXF,系统自动完成解析、排料优化、出图与成本核算。

---

## 核心能力

| 能力 | 说明 |
|---|---|
| 🗣 **对话式排料** | LLM 理解意图、抽参、编排工具(可切换 Claude / Qwen3 / MiniMax / GLM),求解器封装为可调用工具,LLM 不碰计算 |
| 🟦 **板材二维排料** | 固定尺寸板 + 多张 + 按需求量装箱(自研 Rust `bin_nester`,基于 jagua-rs BPP),单板利用率 92–95% |
| 🎯 **交互拖拽** | Konva 画布拖动零件、实时利用率、重叠/越界检测 |
| 🟫 **管/棒一维下料** | 多根定尺 + 库存限制 + 锯缝 + 余料优先,带规格(外径/壁厚)与重量核算 |
| ♻ **余料资产管理** | 每张板/每根料的余料自动建档(规格+牌号+重量),下次按牌号+规格匹配优先复用——数据飞轮 |
| ⚖ **材料牌号 + 重量核算** | 三料型均带牌号,按截面/面积×密度算重量(净产品/投入/可回收余料 kg) |
| 🧹 **几何脏数据预处理** | 真实 CAD 展开图:散乱 LINE/ARC/样条重组为闭合轮廓、修复缺口、剔除折弯线/标注、识别内孔 |
| 📊 **PEBS 阿米巴成本闭环** | 排料结果折算成本/工时,以料/机要素指标 + 浪费归因上报阿米巴单元核算(独有壁垒) |
| 📄 **导出** | 出料表/切割单导出 Excel(.xlsx)+ PDF(打印友好) |

---

## 系统架构(四层解耦)

```
交互层    frontend/         React + TS + Konva:对话、交互拖拽、出料表、余料看板、模型配置
应用服务  backend/app/      FastAPI:任务编排、LLM 多模型适配、会话、导出、阿米巴上报
几何处理  backend/app/geometry/   DXF 脏数据预处理(ezdxf + shapely):轮廓重组、缺口修复、识孔
求解引擎  backend/app/engine/     2D 装箱(Rust bin_nester / sparrow)、1D 下料(FFD)
算法验证  phase0/           第零阶段:sparrow/jagua-rs 异形验证 + 自研 bin_nester Rust 求解器
集成      src/              阿米巴 Node 连接器(子工具接入主系统)
```

> 红线:**LLM 绝不直接参与排料计算**,只做意图理解、工具编排、结果解释,确保结果确定可验证。

### 技术栈
- **前端**:React 18 · TypeScript · Vite · react-konva
- **后端**:FastAPI · Python 3.9+ · shapely · ezdxf · openpyxl · anthropic / openai SDK
- **求解引擎**:Rust(`bin_nester` 自研固定板装箱;`sparrow`/`jagua-rs` 异形 strip-packing)
- **LLM**:Claude(Anthropic)/ Qwen3 / MiniMax / GLM(OpenAI 兼容),页面可配置

---

## 目录结构

```
.
├── frontend/              React 前端(对话 + 交互排料 + 出料表 + 余料看板)
│   └── src/               App / SheetNesting / BarCutting / InteractiveLayout / AmibaPush / LLMConfig …
├── backend/               FastAPI 后端
│   └── app/
│       ├── main.py        路由:/session /upload /chat /nest_sheets /nest_bars /report /push_amiba …
│       ├── engine/        bin_nester(2D 装箱)· bar_cutting(1D 下料)· sparrow 封装
│       ├── geometry/      clean_dxf(脏数据预处理)· dxf(简单解析)
│       ├── llm/           providers(多模型适配)· orchestrator(Function Calling 循环)
│       ├── tools/         工具注册表(中性 Schema → Anthropic/OpenAI)
│       ├── output/        SVG / NC / DXF 导出
│       ├── export_report  出料表/切割单 Excel + PDF
│       └── amiba / remnant / materials / llm_config …
├── phase0/                算法验证 + Rust 求解器
│   ├── src/               合成样本、NFP+GA 基线、sparrow 批跑、ESICUP 解析
│   └── engines/           bin_nester(自研)· sparrow(克隆,gitignored)
├── src/                   阿米巴 Node 连接器
└── 智能排料智能体系统 项目设计文档.docx
```

---

## 快速开始

### 1. 求解引擎(Rust,首次必装)
```bash
# 安装 Rust(若无):curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cd phase0/engines
git clone --depth 1 https://github.com/JeroenGar/sparrow.git   # 异形 strip-packing(可选)
( cd sparrow && cargo build --release )
( cd bin_nester && cargo build --release )                     # 固定板装箱(必需)
```

### 2. 后端
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 9100 --reload
# LLM key:在前端「⚙ 模型配置」页填,或 cp .env.example .env 填写
```

### 3. 前端
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173,/api 代理到后端 9100
```

打开 http://localhost:5173 →「上传 DXF」或直接对话下料。

---

## 主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/session` | 新建会话 |
| POST | `/session/{sid}/upload` | 上传 DXF(默认脏数据预处理,返回诊断) |
| POST | `/session/{sid}/chat` | 对话(LLM + 工具排料) |
| POST | `/session/{sid}/nest` · `/nest_sheets` | 二维排料 / 固定板多张装箱 |
| POST | `/session/{sid}/nest_bars` | 管/棒一维下料 |
| POST | `/session/{sid}/register_remnants` · `register_bar_remnants` | 登记余料 |
| GET | `/remnants?kind=2d\|1d` | 余料库 |
| POST | `/session/{sid}/push_amiba` | 折算成本/工时上报阿米巴 |
| GET | `/session/{sid}/report?kind=&fmt=xlsx\|pdf` | 导出出料表/切割单 |
| GET·POST | `/config/llm` | LLM 页面配置 |

---

## 项目状态

设计文档全部模块已落地:算法验证 → 板材 MVP → 交互排料 → 固定板装箱 → 一维下料 →
材料牌号/规格/重量核算 → 余料资产管理 → LLM 页面配置 → 阿米巴成本闭环 → Excel/PDF 导出 →
几何脏数据预处理。**三条护城河(AI 对话 + 余料数据飞轮 + PEBS 成本闭环)+ 几何入口质量全部完成。**

> 注:阿米巴上报接口(`app/amiba.py`)将按「阿米巴智能体构建方案」定稿后对齐;当前独立模式下休眠,不影响排料功能。
