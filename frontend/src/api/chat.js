import { useAuthStore } from '@/stores/authStore'
import api from './index'

function getAuthHeaders() {
  const store = useAuthStore()
  const token = store.getAccessToken()
  const headers = {
    'Content-Type': 'application/json',
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

export function sendChatMessage(message, sessionId, signal, options = {}) {
  return fetch('/api/chat', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      message,
      session_id: sessionId,
      tutor_mode: options.tutorMode || 'step_by_step',
      context: options.context || {},
    }),
    signal,
  })
}

export function sendRecognizeRequest(imageData, sessionId, signal) {
  return fetch('/api/recognize', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      image: imageData,
      session_id: sessionId,
    }),
    signal,
  })
}

export function sendMultimodalRequest(message, imageData, sessionId, signal, options = {}) {
  return fetch('/api/chat/multimodal', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      message: message || '',
      image: imageData || null,
      session_id: sessionId,
      tutor_mode: options.tutorMode || 'step_by_step',
      context: options.context || {},
    }),
    signal,
  })
}

// T03: 学生回答 ask_student 澄清问题（返回 SSE 流，与 /api/chat 同构）
export function answerClarification({ sessionId, clarificationId, pendingTurnId, answer }, signal, options = {}) {
  return fetch('/api/chat/clarification/answer', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      session_id: sessionId,
      clarification_id: clarificationId,
      pending_turn_id: pendingTurnId,
      answer,
      tutor_mode: options.tutorMode || 'step_by_step',
      context: options.context || {},
    }),
    signal,
  })
}

export const unwrapChat = (response) => response?.data?.data ?? response?.data
export const listChatSessions = () => api.get('/chat/sessions')
export const getChatSession = (id) => api.get(`/chat/sessions/${id}`)
export const updateChatSession = (id, payload) => api.patch(`/chat/sessions/${id}`, payload)

export function parseSSEStream(response, onData, onDone, onError, onEvent) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = ''

  async function read() {
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (buffer.trim()) {
            processLine(buffer.trim())
          }
          onDone()
          return
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')

        for (let i = 0; i < lines.length - 1; i++) {
          processLine(lines[i])
        }
        buffer = lines[lines.length - 1]
      }
    } catch (err) {
      if (err.name !== 'AbortError' && err.code !== 'ERR_CANCELED') {
        onError(err)
      }
    }
  }

  function processLine(block) {
    const trimmed = block.trim()
    if (!trimmed) return

    // Reset event type for each block
    let eventType = currentEvent || ''
    currentEvent = ''

    // Process each line in the block
    const lines = trimmed.split('\n')
    let dataLine = ''

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.substring(7).trim()
      } else if (line.startsWith('data: ')) {
        dataLine = line.substring(6)
      }
    }

    if (!dataLine) return

    if (dataLine === '[DONE]') {
      onDone()
      return
    }

    try {
      const parsed = JSON.parse(dataLine)
      if (parsed.type === 'done') {
        onDone()
        return
      }
      if (parsed.type === 'error') {
        onError(new Error(parsed.content || '服务器错误'))
        return
      }
      if (eventType && typeof onEvent === 'function') {
        // 命名事件（follow_up / ask_student 等）统一交给 onEvent 处理
        onEvent(eventType, parsed)
        return
      }
      if (parsed.content !== undefined) {
        onData(parsed)
      }
    } catch (e) {
      console.warn('SSE parse warning:', e.message, 'data:', dataLine.substring(0, 100))
    }
  }

  return read()
}
