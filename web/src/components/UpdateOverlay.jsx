import { Loader2, CheckCircle2, AlertCircle, RefreshCw } from "lucide-react"
import useChatStore from "../store/chatStore"

export default function UpdateOverlay() {
  const dataUpdate = useChatStore((s) => s.dataUpdate)
  const clearDataUpdate = useChatStore((s) => s.clearDataUpdate)

  // 不在更新中、且未完成（或已清除）→ 不显示
  if (!dataUpdate.inProgress && !dataUpdate.done) return null

  const isError = !!dataUpdate.error

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(6px)" }}
    >
      <div
        className="ark-fade-in w-full max-w-sm mx-4 p-6"
        style={{
          background: "rgba(10,10,26,0.98)",
          border: `1px solid ${isError ? "rgba(255,107,107,0.25)" : "rgba(79,195,247,0.18)"}`,
          clipPath: "polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px))",
        }}
      >
        {/* 标题 */}
        <div className="flex items-center gap-2 mb-1">
          {dataUpdate.inProgress ? (
            <Loader2 size={16} className="animate-spin" style={{ color: "#4fc3f7" }} />
          ) : isError ? (
            <AlertCircle size={16} style={{ color: "#ff6b6b" }} />
          ) : (
            <CheckCircle2 size={16} style={{ color: "#00cec9" }} />
          )}
          <h2 className="text-sm font-semibold text-white tracking-wider" style={{ fontFamily: "var(--font-display)" }}>
            {dataUpdate.inProgress ? "正在更新知识库" : isError ? "更新失败" : "更新完成"}
          </h2>
        </div>
        <div className="ark-divider mb-5" />

        {/* 进行中：进度条 */}
        {dataUpdate.inProgress && (
          <>
            <p className="text-[13px] mb-4" style={{ color: "#8892b0" }}>{dataUpdate.message}</p>
            <div className="h-[4px] rounded-full overflow-hidden mb-2" style={{ background: "rgba(79,195,247,0.1)" }}>
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${dataUpdate.progress}%`,
                  background: "linear-gradient(90deg, rgba(79,195,247,0.7), rgba(79,195,247,0.3))",
                }}
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px]" style={{ color: "#5a6178" }}>更新期间暂不可提问，请耐心等待</span>
              <span className="text-[11px] tabular-nums font-medium" style={{ color: "#4fc3f7" }}>{dataUpdate.progress}%</span>
            </div>
          </>
        )}

        {/* 完成：提示刷新 */}
        {!dataUpdate.inProgress && !isError && (
          <>
            <p className="text-[13px] mb-2" style={{ color: "#8892b0" }}>{dataUpdate.message}</p>
            {dataUpdate.versionInfo && dataUpdate.versionInfo.update_available && (
              <div className="mt-3 px-3 py-2 text-[11px]" style={{ background: "rgba(255,214,0,0.06)", border: "1px solid rgba(255,214,0,0.2)", color: "#ffd600" }}>
                检测到新版本应用 v{dataUpdate.versionInfo.latest}（当前 v{dataUpdate.versionInfo.current}）
                {dataUpdate.versionInfo.release_url && (
                  <>, 建议前往 Releases 下载最新版</>
                )}
              </div>
            )}
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => window.location.reload()}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-[12px] cursor-pointer transition-all duration-200 ark-cut-sm"
                style={{ background: "rgba(79,195,247,0.12)", border: "1px solid rgba(79,195,247,0.3)", color: "#4fc3f7" }}
              >
                <RefreshCw size={13} />
                刷新页面
              </button>
            </div>
          </>
        )}

        {/* 失败：显示错误 + 关闭 */}
        {!dataUpdate.inProgress && isError && (
          <>
            <p className="text-[13px] mb-2" style={{ color: "#ff6b6b" }}>{dataUpdate.error}</p>
            <p className="text-[11px] mb-4" style={{ color: "#5a6178" }}>请检查网络连接或手动安装 Git 后重试。</p>
            <div className="flex gap-3 mt-4">
              <button
                onClick={clearDataUpdate}
                className="flex-1 px-4 py-2 text-[12px] cursor-pointer transition-all duration-200 ark-cut-sm"
                style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.08)", color: "#8892b0" }}
              >
                关闭
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
