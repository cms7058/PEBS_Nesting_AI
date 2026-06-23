// Nesting Copilot —— 排料/套料优化子智能体入口（占位实现）。
// 把这里换成真正的套料算法（板材/型材排样、共边/共线、余料调用等）。
// 演示：启动时 hello 上报能力，产出排料结果后 push 现场要素数据到主阿米巴（接入模式下）。

import { hello, push, amibaEnabled } from "./amiba-connector.js";

const SOURCE = process.env.AMIBA_SOURCE || "nesting";

// 占位：真实实现里这里会读入 BOM/板材规格/订单，跑套料算法得到利用率等结果。
function runNesting() {
  return {
    nestingYield: 78.4,   // 套料利用率 %
    benchmarkYield: 88,   // 行业基准 %
    sheetArea: 12000,     // 投入板材面积（占位单位）
    partArea: 9408,       // 零件占用面积
    remnantReusable: 1320,// 可再利用余料面积
    materialUnitCost: 0.045, // 元/面积单位（占位）
  };
}

async function main() {
  console.log("[nesting] 启动。阿米巴接入：", amibaEnabled() ? "已开启" : "独立模式");

  // 能力发现：让主系统「工具接入」页点亮「料」要素相关能力
  await hello(["nesting_yield", "remnant_reuse", "material_cost_loss"], "0.1.0");

  const r = runNesting();

  const metrics = [
    {
      factor: "material",
      key: "nesting_yield",
      label: "套料利用率",
      value: r.nestingYield,
      unit: "%",
      benchmark: r.benchmarkYield,
      source: SOURCE,
      capturedAt: new Date().toISOString(),
    },
  ];

  // 利用率低于基准的差额折算成材料浪费（年化口径在主系统成本归因引擎里完善）
  const lossArea = r.sheetArea * (r.benchmarkYield - r.nestingYield) / 100;
  const wasteItems = lossArea > 0 ? [
    {
      factor: "material",
      threeProps: "rationality",
      description: `套料利用率 ${r.nestingYield}% 低于基准 ${r.benchmarkYield}%，存在排样浪费`,
      annualCost: Math.round(lossArea * r.materialUnitCost),
      costAccount: "材料利用率损失",
      attributionRule: "排料利用率差额归制造阿米巴",
      source: SOURCE,
    },
  ] : [];

  const result = await push({ metrics, wasteItems, batchId: `nesting_${Date.now()}` });
  console.log("[nesting] 上报结果：", result);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
