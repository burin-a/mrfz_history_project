const API_BASE = ""

export async function fetchStats() {
  const res = await fetch(`${API_BASE}/api/stats`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function sendChatStream(sessionId, message, onChunk, onDone, onFinally, signal) {
  const res = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body.detail) detail = body.detail
      else if (body.error) detail = body.error
    } catch { /* ignore parse error */ }
    throw new Error(detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() || ""
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      const jsonStr = line.slice(6)
      if (!jsonStr.trim()) continue
      try {
        const data = JSON.parse(jsonStr)
        if (data.error) {
          throw new Error(data.error)
        }
        if (data.done) {
          onDone(data)
          return
        }
        if (data.clear) {
          onChunk(data)
          continue
        }
        onChunk(data)
      } catch (e) {
        // 只吞掉 JSON 解析错误（SyntaxError），其余错误（如服务端 error）正常抛出
        if (!(e instanceof SyntaxError)) throw e
      }
    }
  }
  // 连接关闭兜底：如果没收到 done 事件，也要通知调用方结束
  if (onFinally) onFinally()
}

export async function resetChat(sessionId) {
  const res = await fetch(`${API_BASE}/api/chat/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchConfig() {
  const res = await fetch(`${API_BASE}/api/config`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function updateConfig(config) {
  const res = await fetch(`${API_BASE}/api/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function checkUpdate() {
  const res = await fetch(`${API_BASE}/api/check-update`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function updateData(onProgress, onDone, onError, onFinally) {
  const res = await fetch(`${API_BASE}/api/update-data`, {
    method: "POST",
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body.detail) detail = body.detail
    } catch { /* ignore parse error */ }
    throw new Error(detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() || ""
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      const jsonStr = line.slice(6)
      if (!jsonStr.trim()) continue
      try {
        const data = JSON.parse(jsonStr)
        if (data.error) {
          if (onError) {
            onError(data.error)
            return  // 收到 error 后终止
          }
          throw new Error(data.error)
        } else if (data.done) {
          onDone(data)
          return  // 收到 done 后终止
        } else {
          onProgress(data)
        }
      } catch (e) {
        if (!(e instanceof SyntaxError)) throw e
      }
    }
  }
  // 连接关闭兜底
  if (onFinally) onFinally()
}
