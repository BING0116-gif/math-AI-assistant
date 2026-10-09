/**
 * 历史回看还原：落库的 agent_trace / tool_calls / visualizations 要能读回来。
 *
 * 思考纪要只在自由对话模式采集并写入 chat_message.metadata.agent_trace；
 * 图形此前只靠 SSE 事件下发，不落库也不映射，刷新页面图就消失。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/chat', () => ({
  getChatSession: vi.fn(),
  listChatSessions: vi.fn(),
  updateChatSession: vi.fn(),
  unwrapChat: (value) => value?.data ?? value,
}))

const { getChatSession } = await import('@/api/chat')
const { useChatStore } = await import('@/stores/chatStore')
const { useAuthStore } = await import('@/stores/authStore')
const { setScopedOwnerGetter } = await import('@/utils/scopedStorage')

const TRACE_ROW = {
  round: 1,
  kind: 'process',
  text: '先取几个点，再调用绘图工具。',
  elapsed_ms: 1600,
  truncated: false,
  tools: [
    {
      tool: 'math_visualize',
      label: '函数图像绘制',
      status: 'success',
      code: '',
      elapsed_ms: 210,
      input_summary: 'type=function_plot, points=3',
      output_summary: 'status=ok',
    },
  ],
}

function assistantMessage(metadata) {
  return {
    id: 42,
    role: 'assistant',
    content: '抛物线开口向上。',
    created_at: '2026-01-01T00:00:00Z',
    metadata,
  }
}

function stubSession(messages) {
  getChatSession.mockResolvedValue({ data: { id: 'chat-1', title: '会话', messages } })
}

describe('历史会话的思考纪要与图形还原', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    setScopedOwnerGetter(() => useAuthStore().userId)
    const auth = useAuthStore()
    auth.currentUser = { user_id: 'u-1', username: 'u-1', role: 'student' }
    auth.accessToken = 'at'
    getChatSession.mockReset()
  })

  it('reads agent_trace back as panel rounds', async () => {
    stubSession([assistantMessage({ agent_trace: [TRACE_ROW] })])

    const chat = await useChatStore().loadServerChat('chat-1')
    const message = chat.messages[0]

    expect(message.trace).toHaveLength(1)
    expect(message.trace[0]).toMatchObject({ round: 1, kind: 'process', elapsedMs: 1600 })
    expect(message.trace[0].tools[0].inputSummary).toBe('type=function_plot, points=3')
  })

  it('restores the visualization that only existed as an SSE event', async () => {
    stubSession([
      assistantMessage({
        visualizations: [{ visualization_status: 'ok', spec: { type: 'function_plot', series: [] }, verification: 'verified' }],
      }),
    ])

    const message = (await useChatStore().loadServerChat('chat-1')).messages[0]

    expect(message.visualization).toEqual({ type: 'function_plot', series: [] })
    expect(message.visualizationStatus).toBe('ok')
    expect(message.visualizationVerification).toBe('verified')
  })

  it('keeps old messages without the new metadata keys working', async () => {
    stubSession([
      assistantMessage({ tool_calls: [{ tool: 'math_verify', label: '数学验证', status: 'success', elapsed_ms: 12 }] }),
      { id: 43, role: 'user', content: '帮我验证', created_at: '2026-01-01T00:00:00Z', metadata: null },
    ])

    const [ai, user] = (await useChatStore().loadServerChat('chat-1')).messages

    expect(ai.trace).toEqual([])
    expect(ai.visualization).toBeNull()
    expect(ai.visualizationStatus).toBeNull()
    expect(ai.agentSteps).toHaveLength(1)
    expect(ai.agentSteps[0].statusText).toBe('调用成功')
    // 旧数据不带模式：置空由调用方按当前选择器兜底
    expect(ai.tutorMode).toBe('')
    expect(user.trace).toEqual([])
  })

  it('remembers which mode produced each answer', async () => {
    stubSession([
      assistantMessage({ agent_trace: [TRACE_ROW], tutor_mode: 'tutor_free' }),
      assistantMessage({ tutor_mode: 'hint_only' }),
    ])

    const [free, guarded] = (await useChatStore().loadServerChat('chat-1')).messages

    // 面板只跟着这条回答自己的模式走，切换选择器不应把上一轮纪要藏起来
    expect(free.tutorMode).toBe('tutor_free')
    expect(guarded.tutorMode).toBe('hint_only')
    expect(guarded.trace).toEqual([])
  })

  it('drops persisted answer rounds that have nothing to show', async () => {
    stubSession([
      assistantMessage({
        agent_trace: [
          TRACE_ROW,
          { round: 2, kind: 'final', text: '', elapsed_ms: 1500, truncated: false, tools: [] },
        ],
      }),
    ])

    const message = (await useChatStore().loadServerChat('chat-1')).messages[0]

    expect(message.trace.map(item => item.round)).toEqual([1])
  })
})
