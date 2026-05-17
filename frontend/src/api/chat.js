import api from './index'

export function sendChatMessage(message, sessionId, signal) {
  return api.post('/chat', {
    message,
    session_id: sessionId
  }, {
    signal,
    responseType: 'stream',
    timeout: 0
  })
}

export function sendRecognizeRequest(imageData, sessionId) {
  return api.post('/recognize', {
    image: imageData,
    session_id: sessionId
  })
}

export function sendMultimodalRequest(message, imageData, sessionId, signal) {
  return api.post('/chat/multimodal', {
    message: message || '',
    image: imageData || null,
    session_id: sessionId
  }, {
    signal,
    responseType: 'stream',
    timeout: 0
  })
}

export function parseSSEStream(response, onData, onDone, onError) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

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

  function processLine(line) {
    const trimmed = line.trim()
    if (!trimmed || !trimmed.startsWith('data: ')) return

    const data = trimmed.substring(6)
    if (data === '[DONE]') {
      onDone()
      return
    }
    try {
      const parsed = JSON.parse(data)
      if (parsed.type === 'done') {
        onDone()
        return
      }
      if (parsed.type === 'error') {
        onError(new Error(parsed.content || '服务器错误'))
        return
      }
      if (parsed.content !== undefined) {
        onData(parsed)
      }
    } catch (e) {
      console.warn('SSE parse warning:', e.message, 'data:', data.substring(0, 100))
    }
  }

  return read()
}