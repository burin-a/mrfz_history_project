import { useState } from "react"
import { Send, Loader2 } from "lucide-react"
import useChatStore from "../store/chatStore"

export default function InputArea() {
  const [text, setText] = useState("")
  const isLoading = useChatStore((s) => s.isLoading)
  const sendMessage = useChatStore((s) => s.sendMessage)

  const handleSubmit = () => {
    const msg = text.trim()
    if (!msg || isLoading) return
    sendMessage(msg)
    setText("")
  }

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="px-6 py-4" style={{ background: "rgba(10,10,26,0.85)", borderTop: "1px solid rgba(255,255,255,0.04)", backdropFilter: "blur(8px)" }}>
      <div className="max-w-3xl mx-auto flex items-end gap-3">
        <div
          className="flex-1 transition-all duration-200"
          style={{
            background: "rgba(26,26,46,0.6)",
            border: "1px solid rgba(79,195,247,0.12)",
          }}
        >
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题..."
            rows={1}
            disabled={isLoading}
            className="w-full bg-transparent text-sm text-gray-200 placeholder-gray-600
              px-4 py-3 resize-none outline-none disabled:opacity-50"
            style={{ minHeight: "44px", maxHeight: "120px" }}
            onFocus={(e) => { e.currentTarget.parentElement.style.borderColor = "rgba(79,195,247,0.35)"; e.currentTarget.parentElement.style.boxShadow = "0 0 12px rgba(79,195,247,0.08)" }}
            onBlur={(e) => { e.currentTarget.parentElement.style.borderColor = "rgba(79,195,247,0.12)"; e.currentTarget.parentElement.style.boxShadow = "none" }}
            onInput={(e) => {
              e.target.style.height = "auto"
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px"
            }}
          />
        </div>

        <button
          onClick={handleSubmit}
          disabled={!text.trim() || isLoading}
          className="flex-shrink-0 w-11 h-11 flex items-center justify-center cursor-pointer transition-all duration-200 ark-cut-sm disabled:opacity-30 disabled:cursor-not-allowed"
          style={{
            background: "rgba(79,195,247,0.1)",
            border: "1px solid rgba(79,195,247,0.25)",
            color: "#4fc3f7",
          }}
          onMouseEnter={(e) => { if (text.trim() && !isLoading) { e.currentTarget.style.background = "rgba(79,195,247,0.2)"; e.currentTarget.style.boxShadow = "0 0 12px rgba(79,195,247,0.15)" } }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(79,195,247,0.1)"; e.currentTarget.style.boxShadow = "none" }}
        >
          {isLoading ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <Send size={18} />
          )}
        </button>
      </div>
    </div>
  )
}
