import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { generateUUID } from '@/utils/helpers'
import { SCOPED_KEYS, ANON_OWNER, currentOwner, loadScoped, saveScoped } from '@/utils/scopedStorage'
import { getChatSession, listChatSessions, unwrapChat, updateChatSession } from '@/api/chat'
import { DEFAULT_TUTOR_MODE, normalizeTutorMode } from '@/utils/tutorModes'
import { useAuthStore } from '@/stores/authStore'

const STORAGE_KEY = SCOPED_KEYS.chats

function createWelcomeMessage() {
  return {
    id: generateUUID(),
    content: '你好！我是你的数学AI助手，有什么我可以帮助你的吗？',
    sender: 'ai',
    timestamp: new Date().toLocaleString(),
    type: 'text',
    system: true, // 系统欢迎语，不应被加入错题本
    errorBookStatus: 'pending',
    errorBookId: null
  }
}

export const useChatStore = defineStore('chat', () => {
  const auth = useAuthStore()
  // owner 是“这份内存数据属于谁”的唯一事实：读写都锁定它，账号一变就整桶换掉
  const owner = ref(currentOwner())
  const chats = ref(loadScoped(STORAGE_KEY, [], owner.value))
  const currentChatId = ref(null)
  const isLoading = ref(false)
  const pendingImage = ref(null)

  const currentChat = computed(() =>
    chats.value.find(c => c.id === currentChatId.value) || null
  )

  const currentMessages = computed(() =>
    currentChat.value?.messages || []
  )

  const sortedChats = computed(() =>
    [...chats.value].sort((a, b) =>
      new Date(b.lastMessageTime) - new Date(a.lastMessageTime)
    )
  )

  function persistChats() {
    // anon 不是账号：登出后的过渡态不得在浏览器里留下任何缓存（包括一个空壳“新对话”）
    if (owner.value === ANON_OWNER) return
    saveScoped(STORAGE_KEY, chats.value, owner.value)
  }

  /**
   * 账号变了就整桶换掉：先锁定新 owner 再加载，保证任何写入都不会落回上一个账号的桶。
   * 退到未登录态时直接清空内存：读取端立刻什么都没有，比“换到一个新桶”更严格。
   */
  function ensureOwner() {
    const next = currentOwner()
    if (next === owner.value) return
    owner.value = next
    if (next === ANON_OWNER) {
      chats.value = []
      currentChatId.value = null
      return
    }
    chats.value = loadScoped(STORAGE_KEY, [], next)
    init()
  }

  // 同页内登录 / 登出 / 切号：读取端立刻换桶，不等到下一次写入
  watch(() => auth.userId, () => ensureOwner())

  function createNewChat() {
    ensureOwner()
    const newChat = {
      id: generateUUID(),
      title: '新对话',
      lastMessageTime: new Date().toLocaleString(),
      messages: [createWelcomeMessage()],
      defaultTutorMode: DEFAULT_TUTOR_MODE
    }
    chats.value.unshift(newChat)
    currentChatId.value = newChat.id
    persistChats()
    return newChat
  }

  function switchChat(chatId) {
    ensureOwner()
    currentChatId.value = chatId
  }

  function addMessage(chatId, message) {
    ensureOwner()
    const chat = chats.value.find(c => c.id === chatId)
    if (!chat) return null

    const newMessage = {
      id: generateUUID(),
      ...message,
      errorBookStatus: message.sender === 'ai' ? 'pending' : undefined,
      errorBookId: message.sender === 'ai' ? null : undefined
    }

    chat.messages.push(newMessage)
    chat.lastMessageTime = newMessage.timestamp || new Date().toLocaleString()

    if (message.sender === 'user' && chat.messages.filter(m => m.sender === 'user').length === 1) {
      const content = (message.type === 'text' && message.content) ? message.content : ''
      chat.title = content.substring(0, 20) + (content.length > 20 ? '...' : '') || '新对话'
    }

    persistChats()
    return newMessage
  }

  function updateMessage(chatId, messageId, updates, options = {}) {
    ensureOwner()
    const chat = chats.value.find(c => c.id === chatId)
    if (!chat) return

    const message = chat.messages.find(m => m.id === messageId)
    if (!message) return

    Object.assign(message, updates)
    if (options.persist !== false) persistChats()
  }

  function deleteChat(chatId) {
    ensureOwner()
    const index = chats.value.findIndex(c => c.id === chatId)
    if (index !== -1) {
      chats.value.splice(index, 1)
      if (chatId === currentChatId.value) {
        currentChatId.value = chats.value.length > 0 ? chats.value[0].id : null
        if (!currentChatId.value) {
          createNewChat()
        }
      }
      persistChats()
      updateChatSession(chatId, { archive: true }).catch(() => {})
    }
  }

  function renameChat(chatId, title) {
    ensureOwner()
    const chat = chats.value.find(c => c.id === chatId)
    if (chat && title.trim()) {
      chat.title = title.trim()
      persistChats()
      updateChatSession(chatId, { title: chat.title }).catch(() => {})
    }
  }

  function clearChat(chatId) {
    ensureOwner()
    const index = chats.value.findIndex(c => c.id === chatId)
    if (index === -1) return
    chats.value.splice(index, 1)
    updateChatSession(chatId, { archive: true }).catch(() => {})
    createNewChat()
  }

  function setErrorBookStatus(chatId, messageId, status, errorBookId = null) {
    updateMessage(chatId, messageId, {
      errorBookStatus: status,
      errorBookId
    })
  }

  function init() {
    if (chats.value.length === 0) {
      createNewChat()
    } else {
      currentChatId.value = chats.value[0].id
    }
  }

  async function loadServerChat(chatId) {
    ensureOwner()
    const data = unwrapChat(await getChatSession(chatId))
    const mapped = (data.messages || []).map(message => ({
      id: `sql-${message.id}`,
      content: message.content,
      sender: message.role === 'assistant' ? 'ai' : message.role,
      timestamp: message.created_at,
      type: 'text',
      errorBookStatus: message.role === 'assistant' ? 'pending' : undefined,
      animation: message.metadata?.animations?.[0] || null,
    }))
    const existing = chats.value.find(item => item.id === chatId)
    const chat = { id: data.id, title: data.title || '新对话', lastMessageTime: data.messages?.at(-1)?.created_at || new Date().toISOString(), messages: mapped.length ? mapped : [createWelcomeMessage()], defaultTutorMode: normalizeTutorMode(data.default_tutor_mode), context: data.context || {} }
    if (existing) Object.assign(existing, chat); else chats.value.push(chat)
    currentChatId.value = chatId; persistChats(); return chat
  }

  async function syncFromServer() {
    ensureOwner()
    const rows = unwrapChat(await listChatSessions()) || []
    for (const row of rows) {
      const existing = chats.value.find(item => item.id === row.id)
      const shell = { id: row.id, title: row.title || '新对话', lastMessageTime: row.updated_at, messages: existing?.messages || [], defaultTutorMode: normalizeTutorMode(row.default_tutor_mode), context: row.context || {} }
      if (existing) Object.assign(existing, shell); else chats.value.push(shell)
    }
    chats.value.sort((a,b)=>new Date(b.lastMessageTime)-new Date(a.lastMessageTime))
    if (currentChatId.value && rows.some(row=>row.id===currentChatId.value)) await loadServerChat(currentChatId.value)
    persistChats(); return rows
  }

  function setTutorMode(chatId, mode) {
    ensureOwner()
    const chat = chats.value.find(item => item.id === chatId)
    if (chat) { chat.defaultTutorMode = normalizeTutorMode(mode); persistChats(); updateChatSession(chatId, { default_tutor_mode: chat.defaultTutorMode }).catch(() => {}) }
  }

  init()

  return {
    chats,
    currentChatId,
    isLoading,
    pendingImage,
    currentChat,
    currentMessages,
    sortedChats,
    createNewChat,
    switchChat,
    addMessage,
    updateMessage,
    deleteChat,
    renameChat,
    clearChat,
    setErrorBookStatus,
    persistChats,
    loadServerChat,
    syncFromServer,
    setTutorMode
  }
})
