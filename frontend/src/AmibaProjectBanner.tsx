import { useCallback, useEffect, useRef, useState } from "react";
import { amibaProject, amibaProjectTask, amibaProjectSubmit, type AmibaProject } from "./api";

function hms(sec: number): string {
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const z = (n: number) => (n < 10 ? "0" : "") + n;
  return `${z(h)}:${z(m)}:${z(s)}`;
}

// 阿米巴模式：从「重新接入/换令牌（带产品）」进入排料工具时，操作页顶部内嵌该产品的
// 计时横幅——计时随你在排料系统里实际作业而走；开始/暂停可控；提交回传工时到阿米巴该产品。
export default function AmibaProjectBanner() {
  const [ctx] = useState<{ projectId?: string; productName?: string; partNo?: string; enterpriseName?: string } | null>(() => {
    try { return JSON.parse(localStorage.getItem("nesting-amiba-project") || "null"); } catch { return null; }
  });
  const [proj, setProj] = useState<AmibaProject | null>(null);
  const fetchedAt = useRef<number>(Date.now());
  const [, setTick] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    if (!ctx?.projectId) return;
    try { const d = await amibaProject(ctx.projectId); setProj(d); fetchedAt.current = Date.now(); }
    catch { /* ignore */ }
  }, [ctx]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), 1000); return () => clearInterval(t); }, []);

  if (!ctx?.projectId) return null;
  const running = !!proj && proj.status !== "submitted" && proj.tasks.some((t) => t.running);
  const liveTotal = (proj?.totalSeconds || 0) + (running ? (Date.now() - fetchedAt.current) / 1000 : 0);
  const submitted = proj?.status === "submitted";

  const act = async (action: "start" | "stop") => {
    const t = proj?.tasks[0]; if (!t) return;
    try { const d = await amibaProjectTask(ctx.projectId!, t.id, action); setProj(d); fetchedAt.current = Date.now(); }
    catch { /* ignore */ }
  };
  const submit = async () => {
    if (!confirm("提交本产品的排料作业工时？将停止计时并回传到阿米巴。")) return;
    setSubmitting(true);
    try {
      const d = await amibaProjectSubmit(ctx.projectId!);
      setProj(d); fetchedAt.current = Date.now();
      localStorage.removeItem("nesting-amiba-project");
    } catch (e) { alert((e as Error).message); }
    finally { setSubmitting(false); }
  };

  return (
    <div style={bar}>
      <span style={{ fontSize: 18 }}>🔗</span>
      <div>
        <div style={{ fontSize: 13, fontWeight: 700 }}>阿米巴项目 · {ctx.enterpriseName || proj?.enterpriseName || ""}</div>
        <div style={{ fontSize: 12, opacity: 0.85 }}>
          {ctx.productName || proj?.productName} <span style={{ fontFamily: "monospace" }}>{ctx.partNo || proj?.partNo}</span>
          {" · 排料作业计时"}{submitted ? " · 已提交" : (running ? " · 计时中" : "")}
        </div>
      </div>
      <div style={{ marginLeft: "auto", textAlign: "right" }}>
        <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace" }}>{hms(liveTotal)}</div>
        <div style={{ fontSize: 11, opacity: 0.85 }}>{(liveTotal / 3600).toFixed(2)}h{proj ? ` · 估 ¥${Math.round(liveTotal / 3600 * proj.laborRate).toLocaleString("zh-CN")}` : ""}</div>
      </div>
      {!submitted && proj && (
        running
          ? <button onClick={() => act("stop")} style={{ ...btn, background: "#f59e0b", color: "#1c1207" }}>暂停计时</button>
          : <button onClick={() => act("start")} style={{ ...btn, background: "#10b981", color: "#fff" }}>开始计时</button>
      )}
      {!submitted ? (
        <button disabled={submitting} onClick={submit} style={{ ...btn, background: "#2563eb", color: "#fff" }}>
          {submitting ? "提交中…" : "提交并回传工时"}
        </button>
      ) : (
        <span style={{ fontSize: 12, color: proj?.report?.ok ? "#16a34a" : "#f59e0b" }}>
          {proj?.report?.ok ? `已回传 ${proj.manHours}h` : `回传失败：${proj?.report?.error || ""}`}
        </span>
      )}
    </div>
  );
}

const bar: React.CSSProperties = {
  display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "10px 16px",
  background: "linear-gradient(135deg,#064e3b,#0f172a)", color: "#d1fae5", borderBottom: "1px solid #065f46",
};
const btn: React.CSSProperties = { border: "none", borderRadius: 8, padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
