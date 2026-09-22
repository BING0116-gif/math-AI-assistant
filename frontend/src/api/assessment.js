import api from './index'

export const unwrapAssessment = (response) => response?.data?.data ?? response?.data
export const assessmentApi = {
  readiness: (courseId) => api.get('/assessments/readiness', { params: courseId ? { course_id: courseId } : undefined }),
  create: (payload) => api.post('/assessments/sessions', payload),
  get: (id) => api.get(`/assessments/sessions/${id}`),
  start: (id) => api.post(`/assessments/sessions/${id}/start`),
  saveDraft: (id, questionId, payload) => api.put(`/assessments/sessions/${id}/draft-answers/${questionId}`, payload),
  submit: (id, key) => api.post(`/assessments/sessions/${id}/submit`, { idempotency_key: key }),
  result: (id) => api.get(`/assessments/sessions/${id}/result`),
}

/**
 * §5.4 SSE 流式蓝图预览（EventSource 不支持 POST，走 fetch ReadableStream）。
 * handlers.onEvent(event, data) 依次收到 meta / bucket* / done / error。
 * 网络失败 reject（调用方降级快速模式）。
 */
export async function previewBlueprintStream(payload, handlers) {
  const token = localStorage.getItem('auth_token')
  const response = await fetch('/api/assessments/preview-blueprint', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(payload),
    signal: handlers.signal,
  })
  if (!response.ok || !response.body) throw new Error(`预览请求失败（${response.status}）`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let boundary
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      let event = 'message'
      const dataLines = []
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (!dataLines.length) continue
      try { handlers.onEvent(event, JSON.parse(dataLines.join('\n'))) } catch { /* 忽略非 JSON 心跳 */ }
    }
  }
}
