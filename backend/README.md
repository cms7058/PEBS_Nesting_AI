# Nesting Copilot 后端 · 第一阶段板材 MVP

对话式排料最小闭环:**上传 DXF → 对话排料(LLM + 工具)→ 排料图/NC 导出**。

## 架构(四层解耦,LLM 不碰计算)

```
交互层   app/llm/        provider 适配(Claude/Qwen3/MiniMax2.7/GLM5.2 可切换) + Function Calling 编排
工具层   app/tools/      cut_1d / nest_2d / calc_cost —— 中性 JSON Schema，按 provider 转 Anthropic/OpenAI 格式
求解层   app/engine/     nest_2d 封装 sparrow(jagua-rs)；cut1d 一维 FFD
几何层   app/geometry/   DXF 解析(轮廓提取)
输出     app/output/     SVG / DXF / NC 导出
服务     app/main.py     FastAPI：/session /upload /chat /export
```

> **红线**:LLM 只做意图理解、工具编排、结果解释;排料计算全在求解层(确定、可验证)。

## 运行

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # 填入任一 provider 的 API key
# 需先构建 sparrow 引擎(见 ../phase0/README.md：cargo build --release)
.venv/bin/uvicorn app.main:app --reload
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/session` | 新建会话,返回 session_id |
| POST | `/session/{sid}/upload` | 上传 DXF,载入零件 |
| POST | `/session/{sid}/chat` | 对话(body: `{message, provider?}`),驱动工具排料 |
| GET | `/session/{sid}/export/{svg\|nc\|dxf}` | 导出排料图/切割码 |
| GET | `/health` | 健康检查(含 sparrow 是否就绪) |

## 对话示例(对应设计文档)

```
用户：管材定尺6米，切8根1.2米、12根0.85米，锯缝3mm，怎么下最省？
→ LLM 抽参 → 调 cut_1d → 4 根 6米原料，利用率 82.5% → 解释 + 提示导出
```

二维排料:先 `/upload` 一张 DXF,再对话「板宽 1500,帮我排料」→ LLM 调 `nest_2d`(sparrow)。

## 已验证

- nest_2d(sparrow)/ cut_1d / DXF 解析 / SVG·NC·DXF 导出:全链路跑通(TestClient)
- Function Calling 编排循环:mock provider 验证(抽参→调工具→回灌结果→解释)
- LLM provider 适配:Claude(anthropic SDK)+ Qwen/MiniMax/GLM(OpenAI 兼容),填 key 即用

## 待办(第二阶段起)

- 几何脏数据预处理(非闭合修复、圆弧拟合)独立模块
- cut_1d 升级列生成法;nest_2d 异形带孔/共边
- 余料登记与智能匹配;会话存储换 Redis/PG;接 PEBS 阿米巴成本闭环
