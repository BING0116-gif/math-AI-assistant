export function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/**
 * 为“从对话加入错题本”生成稳定、可重现的来源键。
 *
 * 以会话 ID + 该 AI 回复对应的上一句用户问题文本为输入，产生不依赖
 * 后端自增消息 ID 的确定性键（新消息与刷新后重射都能算出同一值）。
 * 用作错题本 ``item_id``：后端据此幂等去重，前端据此回填“已加入”状态。
 * 纯同步、无副作用；非加密哈希，仅用于同一用户会话内去重。
 */
export function chatErrorSourceId(sessionId, questionText) {
  const raw = `${sessionId || ''}\u0000${questionText || ''}`
  let h1 = 0x811c9dc5
  let h2 = 0x1000193
  for (let i = 0; i < raw.length; i++) {
    const c = raw.charCodeAt(i)
    h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0
    h2 = Math.imul((h2 + c) ^ (h2 >>> 5), 0x85ebca6b) >>> 0
  }
  return `chat:${h1.toString(36)}${h2.toString(36)}`
}

export function escapeHtml(text) {
  if (!text) return ''
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

export function debounce(fn, delay = 300) {
  let timer = null
  return function (...args) {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn.apply(this, args), delay)
  }
}

export function getRelativeTime(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  const now = new Date()
  const diff = now - date
  if (diff < 0) return date.toLocaleString()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  return date.toLocaleString()
}
