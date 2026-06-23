// 后端 API 封装。开发时经 Vite 代理 /api → http://localhost:8000

export type Provider = "claude" | "qwen" | "minimax" | "glm";

export interface NestInfo {
  utilization: number;
  placed: number;
  used_length_mm: number;
}

export async function createSession(): Promise<string> {
  const r = await fetch("/api/session", { method: "POST" });
  return (await r.json()).session_id;
}

export interface UploadResult {
  loaded_parts: number;
  diagnostics?: {
    entities_total?: number; by_type?: Record<string, number>;
    bend_skipped?: number; noncurve_skipped?: number; contours?: number;
    parts?: number; holes?: number; mode?: string; error?: string;
  };
}

export async function uploadDxf(sid: string, file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`/api/session/${sid}/upload`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function chat(
  sid: string,
  message: string,
  provider: Provider
): Promise<{ reply: string; nest?: NestInfo }> {
  const r = await fetch(`/api/session/${sid}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, provider }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function exportUrl(sid: string, fmt: "svg" | "nc" | "dxf"): string {
  return `/api/session/${sid}/export/${fmt}`;
}

export function reportUrl(sid: string, kind: "sheet" | "bar", fmt: "xlsx" | "pdf"): string {
  return `/api/session/${sid}/report?kind=${kind}&fmt=${fmt}`;
}

export interface LayoutData {
  sheet_width: number;
  used_length: number;
  utilization: number;
  parts: { id: string; points: [number, number][]; area: number }[];
}

export async function runNest(sid: string, sheetWidth: number, timeSec?: number): Promise<LayoutData> {
  const r = await fetch(`/api/session/${sid}/nest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sheet_width_mm: sheetWidth, time_sec: timeSec }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getLayout(sid: string): Promise<LayoutData> {
  const r = await fetch(`/api/session/${sid}/layout`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ---- 固定板材多张装箱 + 出料表(方案乙)----

export interface SheetItem {
  part_id: string;
  points: [number, number][];
}
export interface SheetOut {
  sheet_code: string;
  is_remnant: boolean;
  utilization: number;
  width: number;
  height: number;
  part_counts: Record<string, number>;
  items: SheetItem[];
}
export interface PerPart {
  part_id: string;
  demand: number;
  placed: number;
  shortfall: number;
}
export interface SheetAccounting {
  thickness_mm: number;
  weight_kg_per_m2: number;
  product_weight_kg: number;
  input_weight_kg: number;
}
export interface SheetNestResult {
  overall_utilization: number;
  sheets_used: number;
  remnants_used: number;
  sheets_available: number;
  total_placed: number;
  total_shortfall: number;
  per_part: PerPart[];
  sheets: SheetOut[];
  spec?: { material: string; thickness: number };
  accounting?: SheetAccounting;
}

export async function nestSheets(
  sid: string,
  sheetLength: number,
  sheetWidth: number,
  sheetCount: number,
  demands: Record<string, number>,
  useRemnants: boolean,
  material: string,
  thicknessMm: number
): Promise<SheetNestResult> {
  const r = await fetch(`/api/session/${sid}/nest_sheets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sheet_length_mm: sheetLength,
      sheet_width_mm: sheetWidth,
      sheet_count: sheetCount,
      demands,
      use_remnants: useRemnants,
      material,
      thickness_mm: thicknessMm,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ---- 余料库 ----

export interface Remnant {
  id: string;
  kind?: "2d" | "1d";
  source: string;
  material: string;
  date: string;
  status: string;
  free_ratio: number;
  weight_kg?: number;
  thickness?: number;
  // 2D
  sheet_w?: number;
  sheet_h?: number;
  free_area?: number;
  largest_rect?: { x: number; y: number; w: number; h: number };
  // 1D
  length?: number;
  profile_type?: "tube" | "bar";
  od?: number;
}

export async function listRemnants(kind?: "2d" | "1d"): Promise<Remnant[]> {
  const r = await fetch(`/api/remnants${kind ? `?kind=${kind}` : ""}`);
  return (await r.json()).remnants;
}

export async function registerRemnants(sid: string): Promise<number> {
  const r = await fetch(`/api/session/${sid}/register_remnants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ min_free_ratio: 0.15 }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()).registered;
}

export async function deleteRemnant(id: string): Promise<void> {
  await fetch(`/api/remnants/${id}`, { method: "DELETE" });
}

// ---- 管材/棒材一维下料(1D)----

export interface BarOut {
  bar_code: string;
  is_remnant: boolean;
  stock_length: number;
  used_length: number;
  remnant_length: number;
  utilization: number;
  cuts: Record<string, number>;
}
export interface BarAccounting {
  section_area_mm2: number;
  weight_kg_per_m: number;
  product_weight_kg: number;
  input_weight_kg: number;
  remnant_weight_kg: number;
}
export interface BarSpec {
  profile_type: "tube" | "bar";
  od: number;
  thickness: number;
}
export interface BarNestResult {
  overall_utilization: number;
  bars_used: number;
  remnants_used: number;
  total_shortfall: number;
  per_piece: { length: number; demand: number; placed: number; shortfall: number }[];
  bars: BarOut[];
  kerf: number;
  spec?: BarSpec;
  accounting?: BarAccounting;
}

export async function nestBars(
  sid: string,
  pieces: { length_mm: number; qty: number }[],
  stockLength: number,
  stockCount: number,
  kerf: number,
  useRemnants: boolean,
  spec: { profile_type: "tube" | "bar"; od_mm: number; thickness_mm: number; material: string }
): Promise<BarNestResult> {
  const r = await fetch(`/api/session/${sid}/nest_bars`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pieces, stock_length_mm: stockLength, stock_count: stockCount,
      kerf_mm: kerf, use_remnants: useRemnants, ...spec,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function registerBarRemnants(sid: string): Promise<number> {
  const r = await fetch(`/api/session/${sid}/register_bar_remnants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ min_remnant_mm: 200 }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()).registered;
}

// ---- LLM 页面配置 ----

export interface LLMConfig {
  provider: string;
  providers: Record<string, { model: string; base_url: string; key_set: boolean }>;
}

// ---- 阿米巴成本闭环上报 ----

export interface AmibaMetric { factor: string; label: string; value: number; unit: string; benchmark?: number; }
export interface AmibaWaste { costAccount: string; description: string; annualCost: number; attributionRule?: string; }
export interface AmibaPushResult {
  envelope: { source: string; enterpriseId: string; batchId: string; metrics: AmibaMetric[]; wasteItems: AmibaWaste[] };
  push_result: { skipped?: boolean; reason?: string; pushed?: boolean; error?: string; response?: unknown };
  amiba_enabled: boolean;
}

export async function pushAmiba(
  sid: string, kind: "sheet" | "bar", unitPricePerKg: number, benchmark: number
): Promise<AmibaPushResult> {
  const r = await fetch(`/api/session/${sid}/push_amiba`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, unit_price_per_kg: unitPricePerKg, benchmark }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getLLMConfig(): Promise<LLMConfig> {
  return (await fetch(`/api/config/llm`)).json();
}

export async function setLLMConfig(
  provider: string | null,
  configs: Record<string, { api_key?: string; model?: string; base_url?: string }> | null
): Promise<LLMConfig> {
  const r = await fetch(`/api/config/llm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, configs }),
  });
  return r.json();
}

// ---- 阿米巴对接（平台令牌登录 + 按产品计时项目 + 提交回传工时）----
// 注意：阿米巴端点在 /amiba/*（vite 原样代理到后端），不走 /api 前缀。

export interface AmibaProject {
  id: string; enterpriseName?: string; partNo?: string; productName?: string;
  status: string; totalSeconds: number; manHours: number; laborCost: number; laborRate: number;
  tasks: { id: string; running: boolean; status: string }[];
  report?: { ok: boolean; error?: string } | null;
}

async function amibaPost(path: string, body?: unknown): Promise<any> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || d.error || `请求失败 ${r.status}`);
  return d;
}

export const amibaRegister = (body: Record<string, unknown>) => amibaPost("/amiba/register", body);
export const amibaPlatformLogin = (body: Record<string, unknown>) => amibaPost("/amiba/platform-login", body);
export const amibaLaunch = (body: Record<string, unknown>) => amibaPost("/amiba/launch", body);
export async function amibaProject(id: string): Promise<AmibaProject> {
  const r = await fetch(`/amiba/projects/${id}`);
  if (!r.ok) throw new Error("加载失败");
  return r.json();
}
export const amibaProjectTask = (id: string, taskId: string, action: string): Promise<AmibaProject> =>
  amibaPost(`/amiba/projects/${id}/tasks/${taskId}/${action}`);
export const amibaProjectSubmit = (id: string): Promise<AmibaProject> =>
  amibaPost(`/amiba/projects/${id}/submit`);
