import { useEffect, useState } from "react";
import { Layer, Line, Rect, Stage } from "react-konva";
import { AmibaPush } from "./AmibaPush";
import {
  deleteRemnant,
  listRemnants,
  nestSheets,
  registerRemnants,
  reportUrl,
  type Remnant,
  type SheetNestResult,
  type SheetOut,
} from "./api";

const PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
  "#edc948", "#b07aa1", "#ff9da7", "#9c755f"];

function SheetThumb({ sheet, colorOf }: { sheet: SheetOut; colorOf: (id: string) => string }) {
  const VIEW = 220;
  const scale = VIEW / Math.max(sheet.width, sheet.height);
  return (
    <div className="thumb">
      <div className="thumb-h">
        {sheet.sheet_code} · {(sheet.utilization * 100).toFixed(1)}%
      </div>
      <Stage width={sheet.width * scale} height={sheet.height * scale} scaleX={scale} scaleY={scale}>
        <Layer>
          <Rect x={0} y={0} width={sheet.width} height={sheet.height}
            fill="#fff" stroke="#333" strokeWidth={2 / scale} />
          {sheet.items.map((it, i) => (
            <Line key={i} points={it.points.flat()} closed
              fill={colorOf(it.part_id) + "cc"} stroke="#222" strokeWidth={0.5 / scale} />
          ))}
        </Layer>
      </Stage>
    </div>
  );
}

export function SheetNesting({ sid, partIds }: { sid: string; partIds: string[] }) {
  const [len, setLen] = useState(2500);
  const [wid, setWid] = useState(1250);
  const [count, setCount] = useState(50);
  const [qty, setQty] = useState<Record<string, number>>(
    () => Object.fromEntries(partIds.map((p) => [p, 5]))
  );
  const [res, setRes] = useState<SheetNestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [useRemnants, setUseRemnants] = useState(false);
  const [remnants, setRemnants] = useState<Remnant[]>([]);
  const [material, setMaterial] = useState("Q235");
  const [thickness, setThickness] = useState(3);

  // 仅同牌号 + 同板厚余料可复用
  const specMatch = (r: Remnant) =>
    r.material === material && Math.abs((r.thickness ?? -1) - thickness) < 0.05;

  async function refreshRemnants() {
    try {
      setRemnants(await listRemnants("2d"));
    } catch {
      /* ignore */
    }
  }
  useEffect(() => {
    refreshRemnants();
  }, []);

  async function doRegister() {
    if (!res) return;
    const n = await registerRemnants(sid);
    await refreshRemnants();
    setErr(n ? "" : "无可登记余料(各板自由率均 <15%)");
  }
  async function doDelete(id: string) {
    await deleteRemnant(id);
    await refreshRemnants();
  }

  const colorIdx: Record<string, string> = {};
  partIds.forEach((p, i) => (colorIdx[p] = PALETTE[i % PALETTE.length]));
  const colorOf = (id: string) => colorIdx[id] ?? "#888";

  async function run() {
    setBusy(true);
    setErr("");
    try {
      setRes(await nestSheets(sid, len, wid, count, qty, useRemnants, material, thickness));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="sheetnest">
      <div className="form">
        <label>牌号
          <input list="plate-grades" value={material} onChange={(e) => setMaterial(e.target.value)} style={{ width: 90 }} />
          <datalist id="plate-grades">
            {["Q235", "Q355", "SPCC", "304不锈钢", "316不锈钢", "6061铝", "5052铝"].map((g) => <option key={g} value={g} />)}
          </datalist>
        </label>
        <label>板厚<input type="number" value={thickness} onChange={(e) => setThickness(+e.target.value)} />mm</label>
        <label>板长<input type="number" value={len} onChange={(e) => setLen(+e.target.value)} />mm</label>
        <label>板宽<input type="number" value={wid} onChange={(e) => setWid(+e.target.value)} />mm</label>
        <label>板数<input type="number" value={count} onChange={(e) => setCount(+e.target.value)} /></label>
        <label className="chk">
          <input type="checkbox" checked={useRemnants} onChange={(e) => setUseRemnants(e.target.checked)} />
          优先用余料({remnants.filter((r) => r.status === "available" && specMatch(r)).length})
        </label>
        <button onClick={run} disabled={busy}>{busy ? "排版中…" : "生成出料表"}</button>
      </div>

      <div className="qty-grid">
        {partIds.map((p) => (
          <label key={p}>
            <span style={{ background: colorOf(p) }} className="swatch" />
            {p}
            <input type="number" min={0} value={qty[p] ?? 0}
              onChange={(e) => setQty({ ...qty, [p]: +e.target.value })} />
          </label>
        ))}
      </div>

      {err && <p className="err">{err}</p>}

      {res && (
        <>
          <div className="summary">
            总利用率 <b>{(res.overall_utilization * 100).toFixed(1)}%</b> ·
            用新板 <b>{res.sheets_used}</b> ·
            用余料 <b style={{ color: res.remnants_used ? "#59a14f" : undefined }}>{res.remnants_used}</b> ·
            已排 <b>{res.total_placed}</b> ·
            缺口 <b style={{ color: res.total_shortfall ? "#e15759" : "#59a14f" }}>{res.total_shortfall}</b>
            <button className="reg" onClick={doRegister}>登记余料入库</button>
          </div>

          {res.accounting && (
            <div className="acct">
              {material} · 板厚 {res.accounting.thickness_mm}mm · {res.accounting.weight_kg_per_m2}kg/m² ·
              净产品 <b>{res.accounting.product_weight_kg}kg</b> ·
              投入新板 <b>{res.accounting.input_weight_kg}kg</b>
            </div>
          )}

          <h3>出料表
            <a className="exp" href={reportUrl(sid, "sheet", "xlsx")} download>导出 Excel</a>
            <button className="exp" onClick={() => window.open(reportUrl(sid, "sheet", "pdf"), "_blank")}>导出 PDF</button>
          </h3>
          <table className="cutlist">
            <thead><tr><th>板料编码</th><th>零件号 × 数量</th><th>利用率</th></tr></thead>
            <tbody>
              {res.sheets.map((s) => (
                <tr key={s.sheet_code} className={s.is_remnant ? "rem-row" : ""}>
                  <td>{s.is_remnant ? "♻ " : ""}{s.sheet_code}</td>
                  <td className="counts">
                    {Object.entries(s.part_counts).map(([pid, n]) => (
                      <span key={pid}><i className="swatch" style={{ background: colorOf(pid) }} />{pid}×{n}</span>
                    ))}
                  </td>
                  <td>{(s.utilization * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>

          {res.total_shortfall > 0 && (
            <table className="cutlist">
              <thead><tr><th>零件号</th><th>需求</th><th>已排</th><th>缺口</th></tr></thead>
              <tbody>
                {res.per_part.filter((p) => p.shortfall > 0).map((p) => (
                  <tr key={p.part_id}><td>{p.part_id}</td><td>{p.demand}</td><td>{p.placed}</td>
                    <td style={{ color: "#e15759" }}>{p.shortfall}</td></tr>
                ))}
              </tbody>
            </table>
          )}

          <h3>各板排版图</h3>
          <div className="thumbs">
            {res.sheets.map((s) => <SheetThumb key={s.sheet_code} sheet={s} colorOf={colorOf} />)}
          </div>

          {res.accounting && <AmibaPush sid={sid} kind="sheet" />}
        </>
      )}

      <div className="remboard">
        <h3>余料库 · 板材({remnants.filter((r) => r.status === "available" && specMatch(r)).length} 块可复用 / 共 {remnants.filter((r) => r.status === "available").length} 块)</h3>
        {remnants.length === 0 ? (
          <p className="hint">排版后点「登记余料入库」,把各板边角料(含牌号/板厚/最大矩形/重量)建档,下次同牌号同板厚可勾选「优先用余料」复用。</p>
        ) : (
          <table className="cutlist">
            <thead><tr><th>余料号</th><th>牌号</th><th>板厚</th><th>最大可用矩形</th><th>重量</th><th>来源/日期</th><th></th></tr></thead>
            <tbody>
              {remnants.map((r) => (
                <tr key={r.id} className={r.status !== "available" ? "rem-used" : (specMatch(r) ? "" : "rem-nomatch")}>
                  <td>{r.id}</td>
                  <td>{r.material}</td>
                  <td>{r.thickness ?? "-"}mm</td>
                  <td>{r.largest_rect ? `${r.largest_rect.w}×${r.largest_rect.h}` : "-"}</td>
                  <td>{r.weight_kg ?? "-"}kg</td>
                  <td>{r.source} · {r.date}</td>
                  <td><button className="del" onClick={() => doDelete(r.id)}>×</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
