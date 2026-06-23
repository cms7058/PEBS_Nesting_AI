import { useState } from "react";
import { pushAmiba, type AmibaPushResult } from "./api";

// 排料结果 → 阿米巴成本闭环上报(料要素)。独立模式显示预览,push 模式显示上报结果。
export function AmibaPush({ sid, kind }: { sid: string; kind: "sheet" | "bar" }) {
  const [price, setPrice] = useState(kind === "bar" ? 6.5 : 5.0);
  const [benchmark, setBenchmark] = useState(88);
  const [res, setRes] = useState<AmibaPushResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function go() {
    setBusy(true); setErr("");
    try { setRes(await pushAmiba(sid, kind, price, benchmark)); }
    catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }

  return (
    <div className="amiba">
      <h3>PEBS 阿米巴成本闭环</h3>
      <div className="form">
        <label>单价<input type="number" value={price} onChange={(e) => setPrice(+e.target.value)} />元/kg</label>
        <label>基准利用率<input type="number" value={benchmark} onChange={(e) => setBenchmark(+e.target.value)} />%</label>
        <button onClick={go} disabled={busy}>{busy ? "上报中…" : "折算成本并上报阿米巴"}</button>
      </div>
      {err && <p className="err">{err}</p>}
      {res && (
        <>
          <p className={`pushstat ${res.push_result.pushed ? "ok" : ""}`}>
            {res.amiba_enabled
              ? (res.push_result.pushed ? "✅ 已上报主阿米巴(料要素 ingest 成功)" : `⚠ 上报失败:${res.push_result.error}`)
              : "ℹ 独立模式预览(未配置 AMIBA_ENDPOINT;下方为将上报的数据)"}
          </p>
          <table className="cutlist">
            <thead><tr><th>要素</th><th>指标</th><th>数值</th><th>基准</th></tr></thead>
            <tbody>
              {res.envelope.metrics.map((m, i) => (
                <tr key={i}>
                  <td>{m.factor === "material" ? "料" : m.factor === "machine" ? "机" : m.factor}</td>
                  <td>{m.label}</td>
                  <td>{m.value}{m.unit}</td>
                  <td>{m.benchmark != null ? `${m.benchmark}%` : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {res.envelope.wasteItems.length > 0 && (
            <table className="cutlist">
              <thead><tr><th>成本科目</th><th>浪费描述</th><th>成本</th><th>归因</th></tr></thead>
              <tbody>
                {res.envelope.wasteItems.map((w, i) => (
                  <tr key={i}>
                    <td>{w.costAccount}</td><td>{w.description}</td>
                    <td style={{ color: "#e15759" }}>¥{w.annualCost}</td>
                    <td>{w.attributionRule}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="hint">批次 {res.envelope.batchId} · 上传 {res.envelope.metrics.length} 项指标 + {res.envelope.wasteItems.length} 项浪费,喂入阿米巴单元成本核算。</p>
        </>
      )}
    </div>
  );
}
