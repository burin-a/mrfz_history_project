import { create } from "zustand/react"
import { sendChatStream, fetchStats, fetchConfig, updateConfig, resetChat, checkUpdate, updateData } from "../api/client"

const loadingMessages = [
  "妮芙正在翻阅历史书",
  "妮芙正在检索知识库",
  "妮芙正在梳理时间线",
  "妮芙正在翻阅档案",
  "妮芙正在查阅资料",
  "正在汇总答案，生成完整答案可能还需要1-2分钟",
]

const useChatStore = create((set, get) => ({
  messages: [],
  sessionId: "",
  isLoading: false,
  streamingText: "",
  stats: null,
  config: null,
  updateStatus: null,
  // 用于取消进行中的 SSE 请求
  abortController: null,
  // 知识库一键更新状态
  dataUpdate: {
    inProgress: false,
    progress: 0,
    message: "",
    step: "",
    error: null,
    done: false,
    versionInfo: null,
  },

  sendMessage: async (message) => {
    const state = get()
    if (state.isLoading) return

    // 创建 AbortController 用于取消此请求
    const controller = new AbortController()
    set((s) => ({
      messages: [...s.messages, { role: "user", content: message }],
      isLoading: true,
      streamingText: "",
      abortController: controller,
    }))

    const sid = state.sessionId

    try {
      await sendChatStream(
        sid,
        message,
        (data) => {
          if (data.clear) {
            set({ streamingText: "" })
            return
          }
          set((s) => ({
            streamingText: s.streamingText + (data.chunk || ""),
          }))
        },
        (data) => {
          set((s) => {
            const fullText = s.streamingText
            const newMessages = [
              ...s.messages,
              { role: "assistant", content: fullText, usage: data.usage },
            ]
            return {
              messages: newMessages,
              sessionId: data.session_id || s.sessionId,
              isLoading: false,
              streamingText: "",
            }
          })
        },
        // onFinally: SSE 中断兜底，确保 isLoading 不卡死
        () => {
          const state = get()
          if (state.isLoading && state.streamingText) {
            // 有部分文本但流中断了，把已有文本保存为回答
            set((s) => ({
              messages: [
                ...s.messages,
                { role: "assistant", content: s.streamingText + "\n\n[回答被中断]" },
              ],
              isLoading: false,
              streamingText: "",
              abortController: null,
            }))
          } else if (state.isLoading) {
            set({ isLoading: false, streamingText: "", abortController: null })
          }
        },
        controller.signal,
      )
    } catch (err) {
      // AbortError 是主动取消，不需要显示错误
      if (err.name === "AbortError") return
      set((s) => ({
        messages: [
          ...s.messages,
          { role: "assistant", content: `[错误] ${err.message}` },
        ],
        isLoading: false,
        streamingText: "",
        abortController: null,
      }))
    }
  },

  resetConversation: async () => {
    const state = get()
    if (state.isLoading) {
      // 加载中重置：取消进行中的 SSE 流
      state.abortController?.abort()
      set({ messages: [], sessionId: "", streamingText: "", isLoading: false, abortController: null })
      return
    }
    const sid = state.sessionId
    if (sid) {
      try { await resetChat(sid) } catch { /* 忽略 */ }
    }
    set({ messages: [], sessionId: "", streamingText: "" })
  },

  loadStats: async () => {
    try {
      const data = await fetchStats()
      set({ stats: data })
    } catch {
      set({ stats: null })
    }
  },

  loadConfig: async () => {
    try {
      const data = await fetchConfig()
      set({ config: data })
    } catch { /* 忽略 */ }
  },

  saveConfig: async (newConfig) => {
    const oldModel = get().config?.model
    try {
      await updateConfig(newConfig)
      const data = await fetchConfig()
      set({ config: data })
      // 仅在模型实际变化时才重置对话（API Key / Base URL 变化不影响上下文兼容性）
      if (newConfig.model && newConfig.model !== oldModel) {
        // 取消进行中的 SSE 流（如果有）
        const state = get()
        state.abortController?.abort()
        set({ messages: [], sessionId: "", streamingText: "", isLoading: false, abortController: null })
      }
      return { success: true }
    } catch (err) {
      return { success: false, error: err.message }
    }
  },

  checkForUpdate: async () => {
    try {
      const data = await checkUpdate()
      set({ updateStatus: data })
    } catch (err) {
      set({ updateStatus: { status: "error", message: err.message } })
    }
  },

  runDataUpdate: async () => {
    const cur = get().dataUpdate
    if (cur.inProgress) return

    set({
      dataUpdate: {
        inProgress: true, progress: 0, message: "正在启动更新...",
        step: "init", error: null, done: false, versionInfo: null,
      },
    })

    try {
      await updateData(
        (data) => {
          set((s) => ({
            dataUpdate: {
              ...s.dataUpdate,
              progress: data.progress ?? s.dataUpdate.progress,
              message: data.message ?? s.dataUpdate.message,
              step: data.step ?? s.dataUpdate.step,
              inProgress: true,
            },
          }))
        },
        (data) => {
          set({
            dataUpdate: {
              inProgress: false,
              progress: 100,
              message: data.message || "知识库更新完成！",
              step: "done",
              error: null,
              done: true,
              versionInfo: data.version_info || null,
            },
          })
          // 重新加载统计与更新检查
          get().loadStats()
          get().checkForUpdate()
        },
        (errMsg) => {
          set((s) => ({
            dataUpdate: {
              ...s.dataUpdate, inProgress: false, error: errMsg, done: true,
            },
          }))
        },
        // onFinally: SSE 异常关闭兜底
        () => {
          const state = get()
          if (state.dataUpdate.inProgress) {
            set((s) => ({
              dataUpdate: {
                ...s.dataUpdate,
                inProgress: false,
                error: "连接中断，请重试",
                done: true,
              },
            }))
          }
        },
      )
    } catch (err) {
      set((s) => ({
        dataUpdate: {
          ...s.dataUpdate, inProgress: false, error: err.message, done: true,
        },
      }))
    }
  },

  clearDataUpdate: () => {
    set({
      dataUpdate: {
        inProgress: false, progress: 0, message: "", step: "",
        error: null, done: false, versionInfo: null,
      },
    })
  },
}))

// 暴露 loadingMessages 给组件使用
export { loadingMessages }
export default useChatStore
