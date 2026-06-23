import { useEffect, useRef, useState } from "react";
import { amibaRegister, amibaLaunch, amibaPlatformLogin } from "./api";

// 阿米巴「重新接入/换令牌」→ 浏览器跳到 /register，携带：
//   连接器令牌(amiba_token)+企业+source（数据回填通道）
//   平台登录令牌(platform_token)+用户名（登录凭证）
//   选定的产品(product_id/part_no/product_name/enterprise_name)
// 本页：① 登记连接器(hello) ② 平台登录核验 ③ 带产品则按产品建排料计时项目
//   → 存项目上下文 → 直接进入真正的排料操作页（顶部内嵌该产品计时横幅）。
export default function AmibaRegister() {
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [msg, setMsg] = useState("");
  const once = useRef(false);

  useEffect(() => {
    if (once.current) return;
    once.current = true;
    (async () => {
      const q = new URLSearchParams(window.location.search);
      const amiba_endpoint = q.get("amiba_endpoint") || "";
      const amiba_token = q.get("amiba_token") || "";
      const enterprise_id = q.get("enterprise_id") || "";
      const source = q.get("source") || "nesting";
      const platform_token = q.get("platform_token") || "";
      const username = q.get("username") || "";
      const product_id = q.get("product_id") || "";

      if (!amiba_endpoint || !amiba_token || !enterprise_id) {
        setState("error"); setMsg("接入参数不完整（缺 amiba_endpoint / amiba_token / enterprise_id）");
        return;
      }
      try {
        await amibaRegister({ amiba_endpoint, amiba_token, enterprise_id, source });

        if (platform_token && username) {
          if (product_id) {
            const d = await amibaLaunch({
              amiba_endpoint, platform_token, username, tool: source,
              enterprise_id, enterprise_name: q.get("enterprise_name") || "",
              product_id, part_no: q.get("part_no") || "", product_name: q.get("product_name") || "",
              connector_token: amiba_token, team: [],
            });
            localStorage.setItem("nesting-amiba-project", JSON.stringify({
              projectId: d.projectId, productName: d.productName, partNo: d.partNo, enterpriseName: d.enterpriseName,
            }));
            window.location.replace("/");
            return;
          }
          await amibaPlatformLogin({ amiba_endpoint, platform_token, username, tool: source, enterprise_id });
          window.location.replace("/");
          return;
        }

        setState("ok"); setMsg("已与阿米巴建立数据回填通道。");
      } catch (e) {
        setState("error"); setMsg((e as Error).message);
      }
    })();
  }, []);

  return (
    <div style={wrap}>
      <div style={box}>
        <h1 style={{ margin: "0 0 8px" }}>接入 Nesting Copilot · 排料套料</h1>
        {state === "working" && <p style={hint}>正在用阿米巴令牌登录并按产品建排料计时项目…</p>}
        {state === "ok" && (<>
          <p style={{ color: "#16a34a" }}>✓ 接入成功</p>
          <p style={hint}>{msg}</p>
          <a href="/" style={btn}>进入排料工作台</a>
        </>)}
        {state === "error" && (<>
          <p style={{ color: "#dc2626" }}>✗ 接入失败</p>
          <p style={hint}>{msg}</p>
          <a href="/" style={btn}>仍然进入工作台</a>
        </>)}
      </div>
    </div>
  );
}

const wrap: React.CSSProperties = { minHeight: "100vh", display: "grid", placeItems: "center", padding: 24, background: "#0b1220", color: "#e2e8f0", fontFamily: 'system-ui,"PingFang SC",sans-serif' };
const box: React.CSSProperties = { width: "100%", maxWidth: 440, padding: 28, border: "1px solid #1e293b", borderRadius: 16, background: "#0f172a" };
const hint: React.CSSProperties = { fontSize: 13, color: "#94a3b8", lineHeight: 1.6 };
const btn: React.CSSProperties = { display: "inline-block", marginTop: 12, padding: "8px 16px", background: "#10b981", color: "#04130c", borderRadius: 8, textDecoration: "none", fontWeight: 600 };
