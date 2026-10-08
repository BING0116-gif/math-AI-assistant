/**
 * 会话列表排序对脏时间戳免疫。
 *
 * 起因：流式占位消息把提示文案（'正在生成...'）写进了 timestamp，addMessage 又把它抄进
 * chat.lastMessageTime，而排序用 `new Date(a) - new Date(b)` —— 得到 NaN 后比较器返回 NaN，
 * 整个列表顺序变成引擎相关，首页与侧栏的“最近会话”因此乱序，显示成“时间未知”。
 * ChatView 已改为写真正的 ISO 时间戳；这里锁住两件事：新写入必须可解析，旧脏值必须被排到最后
 * 而不是把其它会话一起搅乱。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/chat', () => ({
  getChatSession: vi.fn(),
  listChatSessions: vi.fn(),
  updateChatSession: vi.fn(),
  unwrapChat: (value) => value?.data ?? value,
}))

const { useChatStore } = await import('@/stores/chatStore')
const { useAuthStore } = await import('@/stores/authStore')
const { setScopedOwnerGetter } = await import('@/utils/scopedStorage')
const { parseTimestamp } = await import('@/utils/dateTime')

function seed(chatStore, entries) {
  chatStore.chats = entries.map(([id, lastMessageTime]) => ({
    id,
    title: id,
    lastMessageTime,
    messages: [],
  }))
}

describe('会话列表排序', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    setScopedOwnerGetter(() => useAuthStore().userId)
    const auth = useAuthStore()
    auth.currentUser = { user_id: 'u-1', username: 'u-1', role: 'student' }
    auth.accessToken = 'at'
  })

  it('脏时间戳排到最后，其余仍按新旧倒序，不再搅乱整个列表', () => {
    const chat = useChatStore()
    seed(chat, [
      ['dirty', '正在生成...'],
      ['old', '2026-10-01T08:00:00.000Z'],
      ['new', '2026-10-08T08:00:00.000Z'],
      ['locale', '2026年10月5日 10:30:00'],
    ])

    expect(chat.sortedChats.map((item) => item.id)).toEqual(['new', 'locale', 'old', 'dirty'])
  })

  it('排序不修改原数组，只影响视图顺序', () => {
    const chat = useChatStore()
    seed(chat, [
      ['a', '2026-10-01T08:00:00.000Z'],
      ['b', '2026-10-08T08:00:00.000Z'],
    ])

    const order = chat.sortedChats.map((item) => item.id)

    expect(order).toEqual(['b', 'a'])
    expect(chat.chats.map((item) => item.id)).toEqual(['a', 'b'])
  })

  it('新建会话与首条消息写的是可解析的 ISO 时间', () => {
    const chat = useChatStore()
    const created = chat.createNewChat()
    expect(parseTimestamp(created.lastMessageTime)).toBeInstanceOf(Date)

    chat.addMessage(created.id, {
      content: '求导 x^2',
      sender: 'user',
      timestamp: '2026-10-08T09:00:00.000Z',
      type: 'text',
    })
    expect(chat.chats.find((item) => item.id === created.id).lastMessageTime)
      .toBe('2026-10-08T09:00:00.000Z')

    // 缺省 timestamp 也要落到可解析的值，而不是 locale 字符串
    chat.addMessage(created.id, { content: '2x', sender: 'ai', type: 'text' })
    const refreshed = chat.chats.find((item) => item.id === created.id)
    expect(parseTimestamp(refreshed.lastMessageTime)).toBeInstanceOf(Date)
    expect(refreshed.lastMessageTime).toContain('T')
  })

  it('欢迎消息的时间戳同样可解析（首页统计按天过滤）', () => {
    const chat = useChatStore()
    const created = chat.createNewChat()
    const welcome = chat.chats.find((item) => item.id === created.id).messages[0]

    expect(parseTimestamp(welcome.timestamp)).toBeInstanceOf(Date)
  })

  it('从账号桶读回时，脏值仍排最后且不干扰已有会话', () => {
    localStorage.setItem('math_ai_chats:u-1', JSON.stringify([
      { id: 'dirty', title: '脏值', lastMessageTime: '正在识别...', messages: [] },
      { id: 'recent', title: 'recent', lastMessageTime: '2026-10-08T08:00:00.000Z', messages: [] },
      { id: 'older', title: 'older', lastMessageTime: '2026年10月1日 09:00:00', messages: [] },
    ]))

    // 新 pinia 实例 => 重新从当前账号的桶加载，等价于刷新页面
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.currentUser = { user_id: 'u-1', username: 'u-1', role: 'student' }
    const restored = useChatStore()

    expect(restored.chats.map((item) => item.id)).toEqual(['dirty', 'recent', 'older'])
    expect(restored.sortedChats.map((item) => item.id)).toEqual(['recent', 'older', 'dirty'])
  })
})
