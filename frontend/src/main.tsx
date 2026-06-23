import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import AmibaRegister from "./AmibaRegister";
import "./styles.css";

// 阿米巴接入/平台登录入口走独立页，其余走主排料应用。
function pickRoot() {
  if (window.location.pathname === "/register") return <AmibaRegister />;
  return <App />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {pickRoot()}
  </React.StrictMode>
);
