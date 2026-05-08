import api from './index'

export function sendChatMessage(message, sessionId, signal) {
  return fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal
  })
}

export function sendRecognizeRequest(imageData, sessionId) {
  return fetch('/api/recognize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: imageData, session_id: sessionId })
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
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')

        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i]
          if (line.startsWith('data: ')) {
            const data = line.substring(6)
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
              if (parsed.content !== undefined) {
                onData(parsed)
              }
            } catch {
              // skip parse errors
            }
          }
        }
        buffer = lines[lines.length - 1]
      }
      onDone()
    } catch (err) {
      if (err.name !== 'AbortError') {
        onError(err)
      }
    }
  }

  return read()
}
