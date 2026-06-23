import { useEffect, useState } from "react";
import { AmibaPush } from "./AmibaPush";
import {
  deleteRemnant,
  listRemnants,
  nestBars,
  registerBarRemnants,
  reportUrl,
  type BarNestResult,
  type Remnant,
} from "./api";

interface Row {
  length: number;
  qty: number;
}

// 一维原料的切割条带可视化(按长度比例)
function BarStrip({ bar, stockMax }: { bar: BarNestResult["bars"][0]; stockMax: number }) {
  const palette = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2", "#edc948", "#b07aa1"];
  const segs = Object.entries(bar.cuts).flatMap(([len, n]) =>
    Array.from({ length: n }, () => Number(len))
  );
  const keys = [...new Set(segs)].sort((a, b) => b - a);
  const colorOf = (l: number) => palette[keys.indexOf(l) % palette.length];
  return (
    <div className="barstrip" style={{ width: `${(bar.stock_length / stockMax) * 100}%` }}>
      {segs.map((l, i) => (
        <div key={i} className="seg" style={{ flex: l, background: colorOf(l) }} title={`${l}mm`}>
          {l}
        </div>
      ))}
      <div className="rem" style={{ flex: Math.max(bar.remnant_length, 1) }}
        title={`余料 ${bar.remnant_length}mm`} />
    </div>
  );
}

export function BarCutting({ sid }: { sid: string }) {
  const [profile, setProfile] = useState<"tube" | "bar">("tube");
  const [od, setOd] = useState(60);
  const [thickness, setThickness] = useState(3);
  const [stockLen, setStockLen] = useState(6000);
  const [count, setCount] = useState(50);
  const [kerf, setKerf] = useState(3);
  const [material, setMaterial] = useState("20#钢");
  const [rows, setRows] = useState<Row[]>([{ length: 1200, qty: 8 }, { length: 850, qty: 12 }]);
  const [useRemnants, setUseRemnants] = useState(false);
  const [res, setRes] = useState<BarNestResult | null>(null);
  const [remnants, setRemnants] = useState<Remnant[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function refresh() {
    try { setRemnants(await listRemnants("1d")); } catch { /* */ }
  }
  useEffect(() => { refresh(); }, []);

  // 仅同牌号 + 同规格余料可复用(同料型、同外径,管材还需同壁厚)
  const specMatch = (r: Remnant) =>
    r.material === material && r.profile_type === profile &&
    Math.abs((r.od ?? -1) - od) < 0.5 &&
    (profile !== "tube" || Math.abs((r.thickness ?? -1) - thickness) < 0.5);

  async function run() {
    setBusy(true); setErr("");
    try {
      setRes(await nestBars(sid, rows.map((r) => ({ length_mm: r.length, qty: r.qty })),
        stockLen, count, kerf, useRemnants,
        { profile_type: profile, od_mm: od, thickness_mm: profile === "tube" ? thickness : 0, material }));
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  async function doRegister() {
    if (!res) return;
    const n = await registerBarRemnants(sid);
    await refresh();
    setErr(n ? "" : "无可登记余料(各料余长均 <200mm)");
  }

  const stockMax = Math.max(stockLen, ...(res?.bars.map((b) => b.stock_length) ?? [stockLen]));
  const avail = remnants.filter((r) => r.status === "available" && specMatch(r)).length;
  const specLabel = profile === "tube" ? `Ø${od}×${thickness}` : `Ø${od}`;

  return (
    <div className="sheetnest">
      <div className="subtabs">
        <button className={profile === "tube" ? "on" : ""} onClick={() => setProfile("tube")}>管材</button>
        <button className={profile === "bar" ? "on" : ""} onClick={() => setProfile("bar")}>棒材</button>
        <span className="spectag">规格 {specLabel}</span>
      </div>

      <div className="form">
        <label>牌号
          <input list="bar-grades" value={material} onChange={(e) => setMaterial(e.target.value)} style={{ width: 90 }} />
          <datalist id="bar-grades">
            {(profile === "tube" ? ["20#钢", "Q235", "304不锈钢", "316不锈钢", "6061铝"]
              : ["45#钢", "Q235", "40Cr", "304不锈钢", "6061铝"]).map((g) => <option key={g} value={g} />)}
          </datalist>
        </label>
        <label>外径<input type="number" value={od} onChange={(e) => setOd(+e.target.value)} />mm</label>
        {profile === "tube" && (
          <label>壁厚<input type="number" value={thickness} onChange={(e) => setThickness(+e.target.value)} />mm</label>
        )}
        <label>定尺<input type="number" value={stockLen} onChange={(e) => setStockLen(+e.target.value)} />mm</label>
        <label>根数<input type="number" value={count} onChange={(e) => setCount(+e.target.value)} /></label>
        <label>锯缝<input type="number" value={kerf} onChange={(e) => setKerf(+e.target.value)} />mm</label>
        <label className="chk">
          <input type="checkbox" checked={useRemnants} onChange={(e) => setUseRemnants(e.target.checked)} />
          优先用余料({avail})
        </label>
        <button onClick={run} disabled={busy}>{busy ? "下料中…" : "生成切割单"}</button>
      </div>

      <table className="cutlist">
        <thead><tr><th>零件长(mm)</th><th>数量</th><th></th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td><input type="number" value={r.length} onChange={(e) => {
                const n = [...rows]; n[i] = { ...n[i], length: +e.target.value }; setRows(n);
              }} /></td>
              <td><input type="number" value={r.qty} onChange={(e) => {
                const n = [...rows]; n[i] = { ...n[i], qty: +e.target.value }; setRows(n);
              }} /></td>
              <td><button className="del" onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="addrow" onClick={() => setRows([...rows, { length: 1000, qty: 1 }])}>+ 加一行零件</button>

      {err && <p className="err">{err}</p>}

      {res && (
        <>
          <div className="summary">
            总利用率 <b>{(res.overall_utilization * 100).toFixed(1)}%</b> ·
            用新料 <b>{res.bars_used}</b> ·
            用余料 <b style={{ color: res.remnants_used ? "#59a14f" : undefined }}>{res.remnants_used}</b> ·
            缺口 <b style={{ color: res.total_shortfall ? "#e15759" : "#59a14f" }}>{res.total_shortfall}</b>
            <button className="reg" onClick={doRegister}>登记余料入库</button>
          </div>

          {res.accounting && (
            <div className="acct">
              规格 {specLabel} · 截面 {res.accounting.section_area_mm2}mm² · {res.accounting.weight_kg_per_m}kg/m ·
              净产品 <b>{res.accounting.product_weight_kg}kg</b> ·
              投入新料 <b>{res.accounting.input_weight_kg}kg</b> ·
              可回收余料 <b style={{ color: "#59a14f" }}>{res.accounting.remnant_weight_kg}kg</b>
            </div>
          )}

          <h3>切割出料表
            <a className="exp" href={reportUrl(sid, "bar", "xlsx")} download>导出 Excel</a>
            <button className="exp" onClick={() => window.open(reportUrl(sid, "bar", "pdf"), "_blank")}>导出 PDF</button>
          </h3>
          <table className="cutlist">
            <thead><tr><th>料号</th><th>切割明细</th><th>利用率</th><th>余料</th></tr></thead>
            <tbody>
              {res.bars.map((b) => (
                <tr key={b.bar_code} className={b.is_remnant ? "rem-row" : ""}>
                  <td>{b.is_remnant ? "♻ " : ""}{b.bar_code}</td>
                  <td>{Object.entries(b.cuts).map(([l, n]) => `${l}×${n}`).join(", ")}</td>
                  <td>{(b.utilization * 100).toFixed(0)}%</td>
                  <td>{b.remnant_length}mm</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>切割图</h3>
          <div className="bars">
            {res.bars.map((b) => (
              <div key={b.bar_code} className="barline">
                <span className="barlbl">{b.is_remnant ? "♻" : ""}{b.bar_code}</span>
                <BarStrip bar={b} stockMax={stockMax} />
              </div>
            ))}
          </div>

          {res.accounting && <AmibaPush sid={sid} kind="bar" />}
        </>
      )}

      <div className="remboard">
        <h3>余料库 · 管/棒({avail} 段可复用 / 共 {remnants.filter((r) => r.status === "available").length} 段)</h3>
        {remnants.length === 0 ? (
          <p className="hint">下料后点「登记余料入库」,把余料段(含规格/牌号/重量)建档,下次同牌号同规格可勾选「优先用余料」复用。</p>
        ) : (
          <table className="cutlist">
            <thead><tr><th>余料号</th><th>牌号</th><th>规格</th><th>长度</th><th>重量</th><th>来源/日期</th><th></th></tr></thead>
            <tbody>
              {remnants.map((r) => (
                <tr key={r.id} className={r.status !== "available" ? "rem-used" : (specMatch(r) ? "" : "rem-nomatch")}>
                  <td>{r.id}</td>
                  <td>{r.material}</td>
                  <td>{r.profile_type === "tube" ? `Ø${r.od}×${r.thickness}` : `Ø${r.od}`}</td>
                  <td>{r.length}mm</td>
                  <td>{r.weight_kg ?? "-"}kg</td>
                  <td>{r.source} · {r.date}</td>
                  <td><button className="del" onClick={async () => { await deleteRemnant(r.id); refresh(); }}>×</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
