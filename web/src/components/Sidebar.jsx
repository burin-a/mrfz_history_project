import { useEffect, useState } from "react"
import { BookOpen, Database, FileText, User, Layers, Shirt, Swords, RotateCcw, RefreshCw, Check, AlertTriangle, Download, Loader2 } from "lucide-react"
import useChatStore from "../store/chatStore"
import SettingsPanel from "./SettingsPanel"

const typeLabels = {
  story: { label: "剧情", icon: FileText },
  module: { label: "模组", icon: Layers },
  character: { label: "干员语音、密录和其他数据", icon: User },
  skin: { label: "皮肤", icon: Shirt },
  roguelike: { label: "集成战略", icon: Swords },
}

export default function Sidebar() {
  const stats = useChatStore((s) => s.stats)
  const config = useChatStore((s) => s.config)
  const updateStatus = useChatStore((s) => s.updateStatus)
  const dataUpdate = useChatStore((s) => s.dataUpdate)
  const runDataUpdate = useChatStore((s) => s.runDataUpdate)
  const resetConversation = useChatStore((s) => s.resetConversation)
  const isLoading = useChatStore((s) => s.isLoading)
  const loadStats = useChatStore((s) => s.loadStats)
  const loadConfig = useChatStore((s) => s.loadConfig)
  const checkForUpdate = useChatStore((s) => s.checkForUpdate)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    loadStats()
    loadConfig()
    checkForUpdate()
  }, [loadStats, loadConfig, checkForUpdate])

  const handleCheckUpdate = async () => {
    setChecking(true)
    await checkForUpdate()
    setChecking(false)
  }

  const arkCard = "ark-brackets"
  const arkBorder = "border border-white/[0.06]"
  const arkBg = "bg-[#1a1a2e]/60"

  return (
    <aside className="w-72 min-h-screen flex flex-col" style={{ background: "rgba(10,10,26,0.95)", borderRight: "1px solid rgba(255,255,255,0.06)", backdropFilter: "blur(12px)" }}>
      {/* Title */}
      <div className="p-5">
        <div className="ark-divider mb-4" />
        <div className="flex items-center gap-3 mb-1">
          <div
            className="w-9 h-9 flex items-center justify-center ark-cut-sm"
            style={{ background: "rgba(79,195,247,0.1)", border: "1px solid rgba(79,195,247,0.2)" }}
          >
            <BookOpen size={18} style={{ color: "#4fc3f7" }} />
          </div>
          <div>
            <h1 className="text-base font-semibold text-white tracking-wider" style={{ fontFamily: "var(--font-display)" }}>TERRA HISTORIAN</h1>
            {config && (
              <p className="text-[10px] tracking-wide" style={{ color: "#5a6178" }}>{config.model}</p>
            )}
          </div>
        </div>
      </div>

      {/* Knowledge base stats */}
      <div className="flex-1 px-5 overflow-y-auto">
        <h2 className="text-[10px] font-medium uppercase tracking-[0.2em] mb-4" style={{ color: "#5a6178" }}>
          KNOWLEDGE BASE
        </h2>

        {stats ? (
          <div className="space-y-3">
            {/* Total chunks */}
            <div className={`${arkCard} ${arkBg} ${arkBorder} p-3`}>
              <div className="flex items-center gap-2 mb-2">
                <Database size={13} style={{ color: "#4fc3f7" }} />
                <span className="text-[11px]" style={{ color: "#8892b0" }}>总文本块</span>
              </div>
              <span className="text-2xl font-bold tabular-nums" style={{ color: "#4fc3f7", fontFamily: "var(--font-display)" }}>
                {stats.total_chunks?.toLocaleString()}
              </span>
              {stats.timeline_latest_year && (
                <p className="text-[10px] mt-1" style={{ color: "#5a6178" }}>
                  含年表数据，截至泰拉历 {stats.timeline_latest_year} 年
                </p>
              )}
            </div>

            {/* Operators */}
            <div className={`${arkCard} ${arkBg} ${arkBorder} p-3`}>
              <div className="flex items-center gap-2 mb-2">
                <User size={13} style={{ color: "#4fc3f7" }} />
                <span className="text-[11px]" style={{ color: "#8892b0" }}>收录干员</span>
              </div>
              <span className="text-2xl font-bold text-white tabular-nums" style={{ fontFamily: "var(--font-display)" }}>
                {stats.unique_operators}
              </span>
            </div>

            {/* Distribution */}
            <h3 className="text-[10px] font-medium uppercase tracking-[0.2em] mt-5 mb-3" style={{ color: "#5a6178" }}>
              DATA DISTRIBUTION
            </h3>
            <div className="space-y-2">
              {Object.entries(typeLabels).map(([key, { label, icon: Icon }]) => {
                const count = stats.by_type?.[key] || 0
                const maxCount = Math.max(...Object.values(stats.by_type || {}), 1)
                const pct = (count / maxCount) * 100
                return (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <Icon size={11} style={{ color: "#5a6178" }} />
                        <span className="text-[11px]" style={{ color: "#8892b0" }}>{label}</span>
                      </div>
                      <span className="text-[11px] tabular-nums" style={{ color: "#5a6178" }}>
                        {count.toLocaleString()}
                      </span>
                    </div>
                    <div className="h-[3px] rounded-sm overflow-hidden" style={{ background: "rgba(79,195,247,0.08)" }}>
                      <div
                        className="h-full rounded-sm transition-all duration-700"
                        style={{ width: `${pct}%`, background: "linear-gradient(90deg, rgba(79,195,247,0.5), rgba(79,195,247,0.15))" }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
          <div className="text-[11px]" style={{ color: "#5a6178" }}>加载中...</div>
        )}

        {/* Update check */}
        <div className="mt-6">
          <h3 className="text-[10px] font-medium uppercase tracking-[0.2em] mb-3" style={{ color: "#5a6178" }}>
            DATA SOURCE
          </h3>
          {updateStatus && (
            <div className={`px-3 py-2 text-[11px] mb-3 ${arkBorder}`}
              style={{
                background: updateStatus.status === "up_to_date"
                  ? "rgba(0,206,201,0.05)"
                  : updateStatus.status === "update_available"
                    ? "rgba(255,214,0,0.05)"
                    : "rgba(255,107,107,0.05)",
                borderColor: updateStatus.status === "up_to_date"
                  ? "rgba(0,206,201,0.2)"
                  : updateStatus.status === "update_available"
                    ? "rgba(255,214,0,0.2)"
                    : "rgba(255,107,107,0.2)",
                color: updateStatus.status === "up_to_date"
                  ? "#00cec9"
                  : updateStatus.status === "update_available"
                    ? "#ffd600"
                    : "#ff6b6b",
              }}
            >
              {updateStatus.status === "up_to_date" && (
                <span className="flex items-center gap-1.5">
                  <Check size={11} /> {updateStatus.message}
                </span>
              )}
              {updateStatus.status === "update_available" && (
                <span className="flex items-center gap-1.5">
                  <AlertTriangle size={11} /> {updateStatus.message}
                </span>
              )}
              {updateStatus.status !== "up_to_date" && updateStatus.status !== "update_available" && (
                <span>{updateStatus.message}</span>
              )}
            </div>
          )}
          <button
            onClick={handleCheckUpdate}
            disabled={checking || dataUpdate.inProgress}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 text-[12px] cursor-pointer transition-all duration-200 ark-cut-sm disabled:opacity-50"
            style={{
              background: "rgba(79,195,247,0.06)",
              border: "1px solid rgba(79,195,247,0.15)",
              color: "#8892b0",
            }}
            onMouseEnter={(e) => { if (!dataUpdate.inProgress) { e.currentTarget.style.background = "rgba(79,195,247,0.12)"; e.currentTarget.style.color = "#4fc3f7" } }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(79,195,247,0.06)"; e.currentTarget.style.color = "#8892b0" }}
          >
            <RefreshCw size={13} className={checking ? "animate-spin" : ""} />
            检查更新
          </button>

          {/* 一键更新按钮 */}
          <button
            onClick={runDataUpdate}
            disabled={dataUpdate.inProgress}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 text-[12px] mt-2 cursor-pointer transition-all duration-200 ark-cut-sm disabled:opacity-60"
            style={{
              background: dataUpdate.inProgress ? "rgba(79,195,247,0.15)" : "rgba(79,195,247,0.06)",
              border: "1px solid rgba(79,195,247,0.2)",
              color: "#4fc3f7",
            }}
          >
            {dataUpdate.inProgress
              ? <Loader2 size={13} className="animate-spin" />
              : <Download size={13} />}
            {dataUpdate.inProgress ? "正在更新..." : "一键更新知识库"}
          </button>

          {/* 更新进度条 */}
          {dataUpdate.inProgress && (
            <div className="mt-2 px-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] truncate" style={{ color: "#8892b0" }}>{dataUpdate.message}</span>
                <span className="text-[10px] tabular-nums" style={{ color: "#5a6178" }}>{dataUpdate.progress}%</span>
              </div>
              <div className="h-[3px] rounded-full overflow-hidden" style={{ background: "rgba(79,195,247,0.08)" }}>
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${dataUpdate.progress}%`, background: "linear-gradient(90deg, rgba(79,195,247,0.6), rgba(79,195,247,0.2))" }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom buttons */}
      <div className="p-5 space-y-2" style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
        <SettingsPanel />
        <button
          onClick={resetConversation}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 text-[12px] cursor-pointer transition-all duration-200 ark-cut-sm"
          style={{
            background: "rgba(79,195,247,0.06)",
            border: "1px solid rgba(79,195,247,0.15)",
            color: "#8892b0",
          }}
          onMouseEnter={(e) => { if (!isLoading) { e.currentTarget.style.background = "rgba(79,195,247,0.12)"; e.currentTarget.style.color = "#4fc3f7" } }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(79,195,247,0.06)"; e.currentTarget.style.color = "#8892b0" }}
        >
          <RotateCcw size={13} />
          重置对话
        </button>
        {/* Disclaimer */}
        <p className="text-[9px] leading-relaxed text-center px-1" style={{ color: "#3a4050" }}>
          非官方交流学习工具 · 数据来自 GitHub 开放仓库及 PRTS Wiki<br />
          游戏内容版权归属鹰角网络 · 严禁用于盈利服务<br />
          AI 回答仅供参考，以官方信息为准
        </p>
      </div>
    </aside>
  )
}
