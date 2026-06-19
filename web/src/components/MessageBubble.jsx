import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

export default function MessageBubble({ message }) {
  const isUser = message.role === "user"

  return (
    <div className={`flex gap-3 ark-fade-in ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div className="flex-shrink-0 mt-0.5">
        {isUser ? (
          <img
            src="/avatar-user.jpeg"
            alt="用户"
            className="w-8 h-8 object-cover"
            style={{ border: "1px solid rgba(79,195,247,0.2)", clipPath: "polygon(0 0, calc(100% - 4px) 0, 100% 4px, 100% 100%, 4px 100%, 0 calc(100% - 4px))" }}
          />
        ) : (
          <img
            src="/avatar-agent.png"
            alt="妮芙"
            className="w-8 h-8 object-cover"
            style={{ border: "1px solid rgba(79,195,247,0.2)", clipPath: "polygon(0 0, calc(100% - 4px) 0, 100% 4px, 100% 100%, 4px 100%, 0 calc(100% - 4px))" }}
          />
        )}
      </div>

      {/* Message content */}
      <div
        className={`max-w-[75%] px-4 py-3 text-sm leading-relaxed ark-brackets ${
          isUser ? "ark-cut" : ""
        }`}
        style={
          isUser
            ? { background: "rgba(79,195,247,0.08)", borderLeft: "2px solid #4fc3f7" }
            : { background: "rgba(26,26,46,0.7)", borderLeft: "2px solid rgba(79,195,247,0.4)", border: "1px solid rgba(255,255,255,0.06)" }
        }
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-gray-200">{message.content}</p>
        ) : (
          <div className="prose-invert prose-sm max-w-none
            [&_p]:mb-2 [&_p:last-child]:mb-0
            [&_strong]:text-[#4fc3f7] [&_strong]:font-semibold
            [&_h1]:text-base [&_h1]:font-semibold [&_h1]:mb-2 [&_h1]:text-white
            [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:mb-2 [&_h2]:text-white
            [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mb-1 [&_h3]:text-gray-200
            [&_ul]:mb-2 [&_ul]:pl-4 [&_ul]:list-disc [&_ul]:text-gray-300
            [&_ol]:mb-2 [&_ol]:pl-4 [&_ol]:list-decimal [&_ol]:text-gray-300
            [&_li]:mb-1
            [&_code]:bg-[#0a0a1a]/80 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-xs [&_code]:text-[#4fc3f7]
            [&_pre]:bg-[#0a0a1a]/80 [&_pre]:p-3 [&_pre]:overflow-x-auto [&_pre]:mb-2 [&_pre]:border [&_pre]:border-white/[0.04]
            [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-gray-300
            [&_blockquote]:border-l-2 [&_blockquote]:border-[#4fc3f7]/40 [&_blockquote]:pl-3 [&_blockquote]:text-gray-400 [&_blockquote]:italic
            [&_hr]:border-white/[0.06] [&_hr]:my-3
            [&_a]:text-[#4fc3f7] [&_a]:underline [&_a]:underline-offset-2
            [&_table]:w-full [&_table]:border-collapse [&_table]:my-2 [&_table]:text-xs
            [&_thead]:border-b [&_thead]:border-white/[0.06]
            [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left [&_th]:font-semibold [&_th]:text-gray-200 [&_th]:border-b [&_th]:border-white/[0.04]
            [&_td]:px-2 [&_td]:py-1.5 [&_td]:border-b [&_td]:border-white/[0.04] [&_td]:text-gray-400
            [&_tbody_tr:hover]:bg-[#4fc3f7]/5"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        )}

        {/* Token usage */}
        {message.usage && (
          <div className="mt-2 pt-2 text-[10px] tabular-nums" style={{ borderTop: "1px solid rgba(255,255,255,0.04)", color: "#5a6178" }}>
            TOKEN: {message.usage.total_tokens?.toLocaleString()}
          </div>
        )}
      </div>
    </div>
  )
}
