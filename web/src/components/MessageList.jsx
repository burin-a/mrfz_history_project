import { useEffect, useState, useRef } from "react"
import MessageBubble from "./MessageBubble"
import useChatStore, { loadingMessages } from "../store/chatStore"

const welcomeHints = [
  { text: "四皇会战发生在哪一年？", tag: "事实检索" },
  { text: "乌萨斯学生自治团和整合运动的关系是什么？", tag: "关系分析" },
  { text: "分析莫斯提马的人格特点", tag: "人物画像" },
  { text: "凯尔希的几次复活与死亡", tag: "事件梳理" },
  { text: "以年和夕为主角写个小故事", tag: "创意生成" },
  { text: "黑蛇是塔露拉吗？", tag: "反幻觉测试" },
]

function LoadingIndicator() {
  const [msgIndex, setMsgIndex] = useState(0)
  const [dotCount, setDotCount] = useState(0)

  useEffect(() => {
    const msgInterval = setInterval(() => {
      setMsgIndex((i) => (i + 1) % loadingMessages.length)
    }, 3000)
    const dotInterval = setInterval(() => {
      setDotCount((d) => (d + 1) % 4)
    }, 800)
    return () => {
      clearInterval(msgInterval)
      clearInterval(dotInterval)
    }
  }, [])

  const dots = ".".repeat(dotCount)

  return (
    <div className="flex gap-3 ark-fade-in">
      <div className="flex-shrink-0 mt-0.5">
        <img
          src="/avatar-agent.png"
          alt="妮芙"
          className="w-8 h-8 object-cover"
          style={{ border: "1px solid rgba(79,195,247,0.2)", clipPath: "polygon(0 0, calc(100% - 4px) 0, 100% 4px, 100% 100%, 4px 100%, 0 calc(100% - 4px))" }}
        />
      </div>
      <div className="flex flex-col gap-1 py-1">
        <span className="text-sm" style={{ color: "#8892b0" }}>
          {loadingMessages[msgIndex]}{dots}
        </span>
        {/* Scan line effect */}
        <div className="ark-scan-line h-[2px] mt-1" style={{ background: "rgba(79,195,247,0.08)" }}>
        </div>
      </div>
    </div>
  )
}

export default function MessageList() {
  const messages = useChatStore((s) => s.messages)
  const isLoading = useChatStore((s) => s.isLoading)
  const streamingText = useChatStore((s) => s.streamingText)
  const sendMessage = useChatStore((s) => s.sendMessage)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, streamingText])

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8">
      {messages.length === 0 ? (
        <div className="h-full flex flex-col items-center justify-center">
          {/* Welcome page */}
          <div className="text-center mb-10 ark-fade-in">
            <div
              className="w-16 h-16 mx-auto mb-4 overflow-hidden ark-cut"
              style={{ border: "1px solid rgba(79,195,247,0.2)", animation: "subtleFloat 4s ease-in-out infinite" }}
            >
              <img src="/logo.png" alt="Logo" className="w-full h-full object-cover" />
            </div>
            <h2 className="text-xl font-semibold text-white mb-2 tracking-wider" style={{ fontFamily: "var(--font-display)" }}>TERRA HISTORIAN</h2>
            <p className="text-sm max-w-md" style={{ color: "#5a6178" }}>
              基于 30,574 个文本块的明日方舟知识库，为你解答剧情、角色、世界观相关问题。
            </p>
            <div className="ark-divider mt-6 mx-auto" style={{ maxWidth: "200px" }} />
          </div>

          {/* Hint cards */}
          <div className="grid grid-cols-2 gap-3 max-w-lg w-full">
            {welcomeHints.map((hint) => (
              <button
                key={hint.text}
                onClick={() => sendMessage(hint.text)}
                className="ark-brackets text-left px-4 py-3 cursor-pointer transition-all duration-200"
                style={{
                  background: "rgba(26,26,46,0.5)",
                  border: "1px solid rgba(79,195,247,0.1)",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(79,195,247,0.08)"; e.currentTarget.style.borderColor = "rgba(79,195,247,0.25)" }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(26,26,46,0.5)"; e.currentTarget.style.borderColor = "rgba(79,195,247,0.1)" }}
              >
                <span className="text-[10px] uppercase tracking-widest block mb-1" style={{ color: "rgba(79,195,247,0.5)" }}>{hint.tag}</span>
                <span className="text-[13px] leading-snug" style={{ color: "#8892b0" }}>{hint.text}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}

          {/* Streaming text */}
          {isLoading && streamingText && (
            <div className="flex gap-3 ark-fade-in">
              <div className="flex-shrink-0 mt-0.5">
                <img
                  src="/avatar-agent.png"
                  alt="妮芙"
                  className="w-8 h-8 object-cover"
                  style={{ border: "1px solid rgba(79,195,247,0.2)", clipPath: "polygon(0 0, calc(100% - 4px) 0, 100% 4px, 100% 100%, 4px 100%, 0 calc(100% - 4px))" }}
                />
              </div>
              <div
                className="max-w-[75%] px-4 py-3 text-sm leading-relaxed"
                style={{ background: "rgba(26,26,46,0.7)", border: "1px solid rgba(255,255,255,0.06)", borderLeft: "2px solid rgba(79,195,247,0.4)" }}
              >
                <p className="whitespace-pre-wrap text-gray-300">{streamingText}</p>
              </div>
            </div>
          )}

          {isLoading && !streamingText && <LoadingIndicator />}

          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}
