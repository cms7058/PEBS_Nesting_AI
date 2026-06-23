import { useEffect, useRef, useState } from "react";
import {
  chat,
  createSession,
  exportUrl,
  getLayout,
  runNest,
  uploadDxf,
  type LayoutData,
  type NestInfo,
  type Provider,
} from "./api";
import { BarCutting } from "./BarCutting";
import { InteractiveLayout } from "./InteractiveLayout";
import { LLMConfigModal } from "./LLMConfig";
import AmibaProjectBanner from "./AmibaProjectBanner";
import { SheetNesting } from "./SheetNesting";

interface Msg {
  role: "user" | "assistant" | "system";
  text: string;
}

const PROVIDERS: { id: Provider; label: string }[] = [
  { id: "claude", label: "Claude" },
  { id: "qwen", label: "Qwen3" },
  { id: "minimax", label: "MiniMax 2.7" },
  { id: "glm", label: "GLM 5.2" },
];

export function App() {
  const [sid, setSid] = useState<string>("");
  const [provider, setProvider] = useState<Provider>("claude");
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      role: "assistant",
      text: "你好,我是智能排料 Copilot。直接描述下料需求即可,例如:\n「管材定尺 6 米,切 8 根 1.2 米、12 根 0.85 米,锯缝 3mm,怎么下最省?」\n板材排料请先上传 DXF 图纸。",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [nest, setNest] = useState<NestInfo | null>(null);
  const [svgKey, setSvgKey] = useState(0); // 强制刷新排料图
  const [layout, setLayout] = useState<LayoutData | null>(null);
  const [view, setView] = useState<"interactive" | "static">("interactive");
  const [sheetW, setSheetW] = useState(1500);
  const [hasParts, setHasParts] = useState(false);
  const [partIds, setPartIds] = useState<string[]>([]);
  const [panelMode, setPanelMode] = useState<"single" | "sheets">("single");
  const [matType, setMatType] = useState<"plate" | "profile">("plate");
  const [showConfig, setShowConfig] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    createSession().then(setSid).catch((e) => add("system", "建会话失败:" + e));
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo(0, logRef.current.scrollHeight);
  }, [msgs]);

  function add(role: Msg["role"], text: string) {
    setMsgs((m) => [...m, { role, text }]);
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f || !sid) return;
    try {
      const { loaded_parts: n, diagnostics: d } = await uploadDxf(sid, f);
      setHasParts(n > 0);
      setPartIds(Array.from({ length: n }, (_, i) => `part_${i}`));
      let info = `已载入 ${n} 个零件(${f.name})。`;
      if (d && d.entities_total != null) {
        info += `\n几何预处理:${d.entities_total} 个实体 → 重组 ${d.contours} 条闭合轮廓 → ${d.parts} 个零件`;
        if (d.holes) info += `(含 ${d.holes} 个内孔)`;
        if (d.bend_skipped) info += `;剔除折弯线 ${d.bend_skipped}`;
        if (d.noncurve_skipped) info += `、标注/文字 ${d.noncurve_skipped}`;
      } else if (d && d.mode === "simple") {
        info += "(简单解析:仅闭合多段线)";
      }
      info += "\n单板可点「自动排料」;多板出料表见右侧切换。";
      add("system", info);
    } catch (err) {
      add("system", "上传失败:" + err);
    }
  }

  async function autoNest() {
    if (!sid || !hasParts || busy) return;
    setBusy(true);
    try {
      const data = await runNest(sid, sheetW, 8);
      setLayout(data);
      setNest({ utilization: data.utilization, placed: data.parts.length, used_length_mm: data.used_length });
      setSvgKey((k) => k + 1);
      add("system", `自动排料完成:利用率 ${(data.utilization * 100).toFixed(1)}%，${data.parts.length} 件。可拖动微调。`);
    } catch (err) {
      add("system", "排料失败:" + err);
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || !sid || busy) return;
    add("user", text);
    setInput("");
    setBusy(true);
    try {
      const r = await chat(sid, text, provider);
      add("assistant", r.reply || "(无文本回复)");
      if (r.nest) {
        setNest(r.nest);
        setSvgKey((k) => k + 1);
        try {
          setLayout(await getLayout(sid));
        } catch {
          /* 一维下料无 layout */
        }
      }
    } catch (err) {
      add("system", "对话失败(可能未配置该 provider 的 API key):" + err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <AmibaProjectBanner />
      <header>
        <h1>智能排料 Copilot</h1>
        <span className="tag">板 · 管 · 棒 全料型自动下料</span>
        <div className="sp" />
        <label className="prov">
          对话模型
          <select value={provider} onChange={(e) => setProvider(e.target.value as Provider)}>
            {PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </label>
        <button className="cfgbtn" onClick={() => setShowConfig(true)}>⚙ 模型配置</button>
        <label className="upload">
          上传 DXF
          <input type="file" accept=".dxf" onChange={onUpload} hidden />
        </label>
      </header>

      {showConfig && <LLMConfigModal onClose={() => setShowConfig(false)} onSaved={() => { /* 已保存 */ }} />}

      <main>
        <section className="chat">
          <div className="log" ref={logRef}>
            {msgs.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="bubble">{m.text}</div>
              </div>
            ))}
            {busy && <div className="msg assistant"><div className="bubble">计算中…</div></div>}
          </div>
          <div className="composer">
            <textarea
              value={input}
              placeholder="用自然语言描述下料需求…(Enter 发送，Shift+Enter 换行)"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button onClick={send} disabled={busy}>发送</button>
          </div>
        </section>

        <aside className="panel">
          <div className="mattabs">
            <button className={matType === "plate" ? "on" : ""} onClick={() => setMatType("plate")}>板材</button>
            <button className={matType === "profile" ? "on" : ""} onClick={() => setMatType("profile")}>管材 · 棒材</button>
          </div>

          {matType === "profile" ? (
            <BarCutting sid={sid} />
          ) : (
          <>
          {hasParts && (
            <div className="modetabs">
              <button className={panelMode === "single" ? "on" : ""}
                onClick={() => setPanelMode("single")}>单板交互</button>
              <button className={panelMode === "sheets" ? "on" : ""}
                onClick={() => setPanelMode("sheets")}>多板出料表</button>
            </div>
          )}

          {panelMode === "sheets" ? (
            <SheetNesting sid={sid} partIds={partIds} />
          ) : (
          <>
          <h2>排料结果</h2>

          {hasParts && (
            <div className="nestctl">
              <label>板宽
                <input type="number" value={sheetW} min={100}
                  onChange={(e) => setSheetW(Number(e.target.value))} /> mm
              </label>
              <button onClick={autoNest} disabled={busy}>自动排料</button>
            </div>
          )}

          {nest ? (
            <>
              <div className="kpi">
                <div className="big">{(nest.utilization * 100).toFixed(1)}%</div>
                <div className="sub">最优利用率</div>
              </div>

              {layout && (
                <div className="tabs">
                  <button className={view === "interactive" ? "on" : ""}
                    onClick={() => setView("interactive")}>交互拖拽</button>
                  <button className={view === "static" ? "on" : ""}
                    onClick={() => setView("static")}>排料图</button>
                </div>
              )}

              {layout && view === "interactive" ? (
                <InteractiveLayout data={layout} />
              ) : (
                <div className="layout">
                  <img key={svgKey} src={`${exportUrl(sid, "svg")}?t=${svgKey}`} alt="排料图" />
                </div>
              )}

              <div className="exports">
                <a href={exportUrl(sid, "nc")} download="layout.nc">导出 NC</a>
                <a href={exportUrl(sid, "dxf")} download="layout.dxf">导出 DXF</a>
                <a href={exportUrl(sid, "svg")} download="layout.svg">导出 SVG</a>
              </div>
            </>
          ) : (
            <p className="hint">上传 DXF 后点「自动排料」,或在对话中描述需求。<br />二维结果支持拖拽微调 + 实时利用率;一维下料结果在对话中给出。</p>
          )}
          </>
          )}
          </>
          )}
        </aside>
      </main>
    </div>
  );
}
