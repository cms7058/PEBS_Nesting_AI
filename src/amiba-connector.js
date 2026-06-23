// 阿米巴连接器（薄客户端）。子项目对主阿米巴零硬依赖：
// 不配 AMIBA_ENDPOINT 就完全休眠，子项目行为不变；配上就把结果旁路推送给主系统。
// 推送失败只记日志/进重试队列，绝不影响子项目自身功能。

const ENV = process.env;

export function amibaEnabled() {
  return Boolean(ENV.AMIBA_ENDPOINT) && (ENV.AMIBA_SYNC_MODE || "off") === "push";
}

/**
 * 上报一批现场要素数据。
 * @param {{metrics?: object[], wasteItems?: object[], batchId: string}} payload
 */
export async function push({ metrics = [], wasteItems = [], batchId }) {
  if (!amibaEnabled()) return { skipped: true };
  const body = {
    source: ENV.AMIBA_SOURCE || "subproject-template",
    enterpriseId: ENV.AMIBA_ENTERPRISE_ID,
    batchId,
    schemaVersion: "v2",
    metrics,
    wasteItems,
  };
  try {
    const res = await fetch(`${ENV.AMIBA_ENDPOINT}/api/ingest`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${ENV.AMIBA_TOKEN}`,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) throw new Error(`ingest ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn("[amiba] push failed (queued for retry):", err.message);
    // TODO: 落本地重试队列
    return { error: err.message };
  }
}

/** 启动时上报能力清单（能力发现），让主系统点亮对应诊断界面。 */
export async function hello(capabilities = [], version = "0.1.0") {
  if (!amibaEnabled()) return { skipped: true };
  try {
    await fetch(`${ENV.AMIBA_ENDPOINT}/api/connectors/hello`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${ENV.AMIBA_TOKEN}`,
      },
      body: JSON.stringify({ version, capabilities }),
      signal: AbortSignal.timeout(5000),
    });
  } catch (err) {
    console.warn("[amiba] hello failed:", err.message);
  }
}
