import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({ getAccessToken: () => 'test-token' }),
}))
vi.mock('../index', () => ({ default: {} }))

const { parseSSEStream, recoverChatStream, sendChatMessage } = await import('../chat')

describe('chat mode gating contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('sends canonical mode names while accepting legacy UI state', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true })
    await sendChatMessage('给提示', 'session-1', undefined, { tutorMode: 'step_by_step' })
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.tutor_mode).toBe('guided')
  })

  it('delivers mode_guard named events to the UI handler', async () => {
    const bytes = new TextEncoder().encode(
      'event: mode_guard\ndata: {"type":"mode_tool_denied","message":"该模式下此操作不可用"}\n\n',
    )
    let delivered = false
    const response = {
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({ done: false, value: bytes })
            .mockResolvedValueOnce({ done: true, value: undefined }),
        }),
      },
    }
    await parseSSEStream(
      response,
      () => {},
      () => {},
      () => {},
      (event, data) => {
        delivered = event === 'mode_guard' && data.message === '该模式下此操作不可用'
      },
    )
    expect(delivered).toBe(true)
  })

  it('exposes the SSE event ID as a sequence number for reconnecting clients', async () => {
    const bytes = new TextEncoder().encode('id: 7\ndata: {"content":"续传"}\n\n')
    const received = []
    const response = { body: { getReader: () => ({ read: vi.fn().mockResolvedValueOnce({ done: false, value: bytes }).mockResolvedValueOnce({ done: true }) }) } }
    const result = await parseSSEStream(response, data => received.push(data), () => {}, () => {})
    expect(received).toEqual([{ content: '续传', seq: 7 }])
    expect(result).toMatchObject({ completed: false, lastEventId: 7 })
  })

  it('sends Last-Event-ID when recovering an interrupted stream', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true })
    await recoverChatStream('session-1', '00000000-0000-0000-0000-000000000001', 7)
    expect(fetchMock).toHaveBeenCalledWith('/api/chat/recover', expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'Last-Event-ID': '7' }),
    }))
  })
})
