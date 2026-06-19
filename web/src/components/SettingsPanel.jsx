import { useState } from "react"
import { Settings, X, Save, Check } from "lucide-react"
import useChatStore from "../store/chatStore"

export default function SettingsPanel() {
  const [open, setOpen] = useState(false)
  const [apiKey, setApiKey] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [model, setModel] = useState("")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")

  const config = useChatStore((s) => s.config)
  const saveConfig = useChatStore((s) => s.saveConfig)

  const handleOpen = () => {
    if (!open && config) {
      setBaseUrl(config.base_url || "")
      setModel(config.model || "")
      setApiKey("")
    }
    setOpen(true)
  }

  const handleSave = async () => {
    setSaving(true)
    setError("")
    const result = await saveConfig({
      api_key: apiKey || undefined,
      base_url: baseUrl || undefined,
      model: model || undefined,
    })
    setSaving(false)
    if (result.success) {
      setSaved(true)
      setTimeout(() => { setSaved(false); setOpen(false) }, 1500)
    } else {
      setError(result.error || "保存失败，请检查配置")
    }
  }

  const inputStyle = {
    background: "rgba(26,26,46,0.6)",
    border: "1px solid rgba(79,195,247,0.12)",
    color: "#e0e0e0",
    fontSize: "13px",
  }

  const inputFocusStyle = {
    borderColor: "rgba(79,195,247,0.35)",
    boxShadow: "0 0 8px rgba(79,195,247,0.08)",
  }

  return (
    <>
      <button
        onClick={handleOpen}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 text-[12px] cursor-pointer transition-all duration-200 ark-cut-sm"
        style={{
          background: "rgba(79,195,247,0.06)",
          border: "1px solid rgba(79,195,247,0.15)",
          color: "#8892b0",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(79,195,247,0.12)"; e.currentTarget.style.color = "#4fc3f7" }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(79,195,247,0.06)"; e.currentTarget.style.color = "#8892b0" }}
      >
        <Settings size={13} />
        模型设置
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}>
          <div
            className="ark-fade-in w-full max-w-md mx-4 p-6 ark-brackets"
            style={{
              background: "rgba(10,10,26,0.98)",
              border: "1px solid rgba(79,195,247,0.15)",
              clipPath: "polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px))",
            }}
          >
            {/* Title */}
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-sm font-semibold text-white tracking-wider" style={{ fontFamily: "var(--font-display)" }}>MODEL SETTINGS</h2>
              <button onClick={() => setOpen(false)} className="cursor-pointer p-0.5 transition-colors" style={{ color: "#5a6178" }}>
                <X size={18} />
              </button>
            </div>
            <div className="ark-divider mb-5" />

            {/* Form */}
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] uppercase tracking-widest mb-1.5" style={{ color: "#5a6178" }}>API KEY</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={config?.api_key_masked || "sk-..."}
                  className="w-full px-3 py-2 outline-none transition-all"
                  style={inputStyle}
                  onFocus={(e) => Object.assign(e.currentTarget.style, inputFocusStyle)}
                  onBlur={(e) => { e.currentTarget.style.borderColor = "rgba(79,195,247,0.12)"; e.currentTarget.style.boxShadow = "none" }}
                />
                <p className="text-[10px] mt-1" style={{ color: "#3a4050" }}>留空则保持当前 Key 不变</p>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-widest mb-1.5" style={{ color: "#5a6178" }}>BASE URL</label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://api.deepseek.com"
                  className="w-full px-3 py-2 outline-none transition-all"
                  style={inputStyle}
                  onFocus={(e) => Object.assign(e.currentTarget.style, inputFocusStyle)}
                  onBlur={(e) => { e.currentTarget.style.borderColor = "rgba(79,195,247,0.12)"; e.currentTarget.style.boxShadow = "none" }}
                />
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-widest mb-1.5" style={{ color: "#5a6178" }}>MODEL</label>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="deepseek-v4-flash"
                  className="w-full px-3 py-2 outline-none transition-all"
                  style={inputStyle}
                  onFocus={(e) => Object.assign(e.currentTarget.style, inputFocusStyle)}
                  onBlur={(e) => { e.currentTarget.style.borderColor = "rgba(79,195,247,0.12)"; e.currentTarget.style.boxShadow = "none" }}
                />
                <p className="text-[10px] mt-1" style={{ color: "#3a4050" }}>
                  支持 DeepSeek、通义千问、Ollama 等 OpenAI 兼容接口
                </p>
              </div>
            </div>

            {error && (
              <div className="text-[11px] text-red-400 mt-2 text-center">{error}</div>
            )}

            {/* Buttons */}
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setOpen(false)}
                className="flex-1 px-4 py-2 text-[12px] cursor-pointer transition-all duration-200 ark-cut-sm"
                style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.08)", color: "#8892b0" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.04)" }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent" }}
              >
                取消
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-[12px] cursor-pointer transition-all duration-200 ark-cut-sm disabled:opacity-50"
                style={{ background: "rgba(79,195,247,0.1)", border: "1px solid rgba(79,195,247,0.25)", color: "#4fc3f7" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(79,195,247,0.18)" }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(79,195,247,0.1)" }}
              >
                {saved ? <Check size={13} /> : <Save size={13} />}
                {saved ? "已保存" : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
