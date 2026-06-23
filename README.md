# Nesting Copilot · 排料/套料优化子智能体

阿米巴「料」要素的现场子智能体：分析板材/型材**套料利用率**、共边共线优化、**余料调用**，
把利用率损失折算成材料浪费成本上报阿米巴。既可独立使用，也可插拔接入主阿米巴。

- 数据来源标识（source）：`nesting`
- 对应 5M1E 要素：**料（material）**
- 主要能力：`nesting_yield`（套料利用率）、`remnant_reuse`（余料再利用）、`material_cost_loss`（利用率损失成本）

## 运行（独立模式）

```bash
cp .env.example .env   # 不填 AMIBA_ENDPOINT 即独立模式
npm run dev
```

## 接入主阿米巴

1. 把本子项目登记进 [`../../app/src/lib/tools-registry.ts`](../../app/src/lib/tools-registry.ts)
   的 `TOOLS`（`id: "nesting"`），主系统「工具接入」页就会出现它。
2. 在「工具接入」页为目标企业生成连接器令牌，把
   `amiba_endpoint / amiba_token / enterprise_id / source` 写入 `.env`，并设 `AMIBA_SYNC_MODE=push`。
3. 产出排料结果后自动 `POST /api/ingest` 上传 `FactorMetric` 与 `WasteItem`。

> 当前 `src/index.js` 为占位实现（`runNesting()` 返回示例数据）。
> 真实落地时替换为套料算法，输入可对接 [BOM 子系统](../../../PEBS_BOM) 的标准用量与余料 BOM。

连接器实现见 `src/amiba-connector.js`，数据契约见
[`../../app/src/lib/factory-types.ts`](../../app/src/lib/factory-types.ts) 与 [`../README.md`](../README.md)。
