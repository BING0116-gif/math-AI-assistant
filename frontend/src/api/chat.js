import { useAuthStore } from '@/stores/authStore'

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

export function sendChatMessage(message, sessionId, signal) {
  return fetch('/api/chat', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      message,
      session_id: sessionId,
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

export function sendMultimodalRequest(message, imageData, sessionId, signal) {
  return fetch('/api/chat/multimodal', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      message: message || '',
      image: imageData || null,
      session_id: sessionId,
    }),
    signal,
  })
}

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
      if (eventType === 'follow_up' && typeof onEvent === 'function') {
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