/**
 * 本地缓存的跨账号隔离回归。
 *
 * 这一层测的是真实事故：聊天与错题本都把服务端数据缓存进 localStorage，但 key 曾经
 * 没有用户维度，而 clearSession() 只清 auth_token / refresh_token / current_user，
 * 于是同一浏览器换账号登录后能读到上一个账号的对话标题、题目原文与答案。
 *
 * 覆盖两条互补的保障（缺一不可）：
 * - auth.userId 变化时的换桶（watch）；
 * - store 入口的同步兜底（ensureOwner），避免 watcher 尚未 flush 的窗口读到旧数据。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const chatApi = {
  getChatSession: vi.fn(),
  listChatSessions: vi.fn(),
  updateChatSession: vi.fn(),
  unwrapChat: (value) => value?.data ?? value,
}
vi.mock('@/api/chat', () => chatApi)

const errorBookApi = {
  addErrorBook: vi.fn(),
  getErrorBook: vi.fn(),
  updateErrorBook: vi.fn(),
  deleteErrorBook: vi.fn(),
}
vi.mock('@/api/errorBook', () => errorBookApi)

const { useChatStore } = await import('../chatStore')
const { useErrorBookStore } = await import('../errorBookStore')
const { useAuthStore } = await import('../authStore')
const { setScopedOwnerGetter } = await import('@/utils/scopedStorage')
const { markSkippedSourceId, listSkippedSourceIds } = await import('@/utils/errorBookDismissals')

/** 与 main.js 同一条注入路径：归属只认 authStore.userId，测试不另造一套身份来源。 */
function loginAs(userId) {
  const auth = useAuthStore()
  auth.currentUser = userId
    ? { user_id: userId, username: userId, role: 'student' }
    : null
}

function askQuestion(chat, text) {
  const created = chat.createNewChat()
  chat.addMessage(created.id, {
    content: text,
    sender: 'user',
    timestamp: '2026-10-08 10:00:00',
    type: 'text',
  })
  return created
}

describe('本地缓存按账号隔离', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    for (const mock of Object.values(chatApi)) if (mock.mockReset) mock.mockReset()
    for (const mock of Object.values(errorBookApi)) mock.mockReset()
    setScopedOwnerGetter(() => useAuthStore().userId)
    chatApi.updateChatSession.mockResolvedValue({ data: {} })
    errorBookApi.addErrorBook.mockResolvedValue({ data: { id: 'err-a-1' } })
  })

  it('A 的对话在切到 B 后不可见，B 的写入不动 A 的桶，切回 A 又完整回来', async () => {
    loginAs('u-a')
    const chat = useChatStore()
    askQuestion(chat, 'A 的私密提问：求数列极限')

    const bucketA = localStorage.getItem('math_ai_chats:u-a')
    expect(bucketA).toContain('A 的私密提问')

    loginAs('u-b')
    await nextTick()
    expect(chat.chats.some(item => JSON.stringify(item).includes('A 的私密提问'))).toBe(false)

    askQuestion(chat, 'B 的新提问')
    expect(localStorage.getItem('math_ai_chats:u-a')).toBe(bucketA)
    expect(localStorage.getItem('math_ai_chats:u-b')).toContain('B 的新提问')
    expect(localStorage.getItem('math_ai_chats:u-b')).not.toContain('A 的私密提问')

    loginAs('u-a')
    await nextTick()
    expect(chat.chats.some(item => item.title.includes('A 的私密提问'))).toBe(true)
  })

  it('watcher 尚未 flush 的窗口也不串号：store 入口自己会先换桶', () => {
    loginAs('u-a')
    const chat = useChatStore()
    askQuestion(chat, 'A 的不许看')
    const bucketA = localStorage.getItem('math_ai_chats:u-a')

    // 故意不 await nextTick：仅靠入口里的 ensureOwner 也必须完成换桶
    loginAs('u-b')
    askQuestion(chat, 'B 的问题')

    expect(chat.chats.some(item => JSON.stringify(item).includes('A 的不许看'))).toBe(false)
    expect(localStorage.getItem('math_ai_chats:u-a')).toBe(bucketA)
  })

  it('未登录（anon）不读也不写任何本地缓存，legacy 无后缀 key 原样留着', () => {
    const legacy = JSON.stringify([{ id: 'legacy-1', title: '上个版本的历史', messages: [], lastMessageTime: '2020-01-01' }])
    localStorage.setItem('math_ai_chats', legacy)

    loginAs(null)
    const chat = useChatStore()
    chat.createNewChat()
    chat.persistChats()

    expect(chat.chats.some(item => item.id === 'legacy-1')).toBe(false)
    expect(localStorage.getItem('math_ai_chats')).toBe(legacy) // 留给 api/migrations.js 的历史兼容链路
    expect(Object.keys(localStorage).filter(key => key.startsWith('math_ai_chats'))).toEqual(['math_ai_chats'])
  })

  it('登出后的过渡态：既读不到上一个账号，也不在浏览器里留下 anon 桶', async () => {
    loginAs('u-a')
    const chat = useChatStore()
    askQuestion(chat, '登出前写下的私密题干CCC')
    const book = useErrorBookStore()
    await book.addError({ question: '登出前的错题CCC', correct_answer: 'x', is_mastered: false })

    loginAs(null)
    await nextTick()
    expect(chat.chats).toEqual([])
    expect(chat.currentChatId).toBeNull()
    expect(book.errors).toEqual([])
    expect(book.totalErrors).toBe(0)

    // 故意再推一次写入：未登录态必须写入失败（不落盘），而不是落进某个伪桶
    chat.persistChats()
    book.persist()
    expect(localStorage.getItem('math_ai_chats:anon')).toBeNull()
    expect(localStorage.getItem('math_ai_error_book:anon')).toBeNull()
    // A 自己的缓存留在原处：那是 A 的账号数据，重新登录即可恢复，不属于泄露
    expect(localStorage.getItem('math_ai_chats:u-a')).toContain('登出前写下的私密题干CCC')
    expect(localStorage.getItem('math_ai_error_book:u-a')).toContain('登出前的错题CCC')
  })

  it('错题本计数不跨账号：B 看不到 A 的错题，也不把 A 的未掌握数算到自己头上', async () => {
    loginAs('u-a')
    const book = useErrorBookStore()
    await book.addError({ question: 'A 的错题题干', correct_answer: 'A 的答案', is_mastered: false })
    expect(book.totalErrors).toBe(1)
    expect(book.unmasteredCount).toBe(1)

    loginAs('u-b')
    await nextTick()
    expect(book.totalErrors).toBe(0)
    expect(book.unmasteredCount).toBe(0)
    expect(localStorage.getItem('math_ai_error_book:u-b')).toBeNull()

    errorBookApi.addErrorBook.mockResolvedValue({ data: { id: 'err-b-1' } })
    await book.addError({ question: 'B 的错题题干', correct_answer: 'B 的答案', is_mastered: false })
    const bucketA = JSON.parse(localStorage.getItem('math_ai_error_book:u-a'))
    expect(bucketA).toHaveLength(1)
    expect(bucketA[0].question).toBe('A 的错题题干')
    expect(localStorage.getItem('math_ai_error_book:u-b')).toContain('B 的错题题干')
    expect(localStorage.getItem('math_ai_error_book:u-b')).not.toContain('A 的错题题干')
  })

  it('切换账号会清空上一账号遗留的筛选词与选中项', async () => {
    loginAs('u-a')
    const book = useErrorBookStore()
    await book.addError({ question: '函数极限连续', correct_answer: 'x', is_mastered: false })
    book.setFilter({ search: '函数极限连续' })
    book.setCurrentDetail('err-a-1')

    loginAs('u-b')
    await nextTick()
    expect(book.filter.search).toBe('')
    expect(book.currentDetailId).toBeNull()
    expect(book.currentDetail).toBeNull()
  })

  it('跳过登记表的 key 格式保持既有约定，历史 skipped 记录仍能读回', () => {
    markSkippedSourceId('u-a', 'chat:hash-a')
    expect(localStorage.getItem('math_ai_error_book_skipped:u-a')).toContain('chat:hash-a')
    expect(listSkippedSourceIds('u-a')).toEqual(['chat:hash-a'])
    // 漏传 userId 时不得静默写进当前登录账号的登记表
    loginAs('u-a')
    markSkippedSourceId(undefined, 'chat:hash-anon')
    expect(localStorage.getItem('math_ai_error_book_skipped:anon')).toContain('chat:hash-anon')
    expect(listSkippedSourceIds('u-a')).toEqual(['chat:hash-a'])
  })
})
