import { useEffect, useState } from "react";
import { getLLMConfig, setLLMConfig, type LLMConfig } from "./api";

const LABELS: Record<string, string> = {
  claude: "Claude", qwen: "Qwen3", minimax: "MiniMax 2.7", glm: "GLM 5.2",
};

export function LLMConfigModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [cfg, setCfg] = useState<LLMConfig | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [models, setModels] = useState<Record<string, string>>({});
  const [bases, setBases] = useState<Record<string, string>>({});
  const [provider, setProvider] = useState("claude");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getLLMConfig().then((c) => {
      setCfg(c);
      setProvider(c.provider);
      setModels(Object.fromEntries(Object.entries(c.providers).map(([k, p]) => [k, p.model])));
      setBases(Object.fromEntries(Object.entries(c.providers).map(([k, p]) => [k, p.base_url])));
    });
  }, []);

  async function save() {
    setSaving(true);
    const configs: Record<string, { api_key?: string; model?: string; base_url?: string }> = {};
    for (const name of Object.keys(cfg!.providers)) {
      configs[name] = { model: models[name], base_url: bases[name] };
      if (keys[name]) configs[name].api_key = keys[name];
    }
    await setLLMConfig(provider, configs);
    setSaving(false);
    onSaved();
    onClose();
  }

  if (!cfg) return null;

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>模型配置</h2>
        <p className="hint">配置各大模型的 API Key 与参数;选择默认模型。Key 仅存于后端,不回显明文。</p>

        <label className="defsel">默认模型
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            {Object.keys(cfg.providers).map((k) => <option key={k} value={k}>{LABELS[k] ?? k}</option>)}
          </select>
        </label>

        {Object.entries(cfg.providers).map(([name, p]) => (
          <div key={name} className="provblock">
            <div className="provh">
              {LABELS[name] ?? name}
              <span className={p.key_set ? "ks ok" : "ks no"}>{p.key_set ? "已配置 Key" : "未配置 Key"}</span>
            </div>
            <input placeholder={p.key_set ? "（已保存,留空不改）" : "API Key"}
              value={keys[name] ?? ""} onChange={(e) => setKeys({ ...keys, [name]: e.target.value })} />
            <div className="provrow">
              <input placeholder="model" value={models[name] ?? ""}
                onChange={(e) => setModels({ ...models, [name]: e.target.value })} />
              {name !== "claude" && (
                <input placeholder="base_url" value={bases[name] ?? ""}
                  onChange={(e) => setBases({ ...bases, [name]: e.target.value })} />
              )}
            </div>
          </div>
        ))}

        <div className="modal-actions">
          <button className="ghost" onClick={onClose}>取消</button>
          <button onClick={save} disabled={saving}>{saving ? "保存中…" : "保存"}</button>
        </div>
      </div>
    </div>
  );
}
