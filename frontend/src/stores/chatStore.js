import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { generateUUID } from '@/utils/helpers'
import { loadFromStorage, saveToStorage } from '@/utils/storage'
import { getChatSession, listChatSessions, unwrapChat, updateChatSession } from '@/api/chat'

const STORAGE_KEY = 'math_ai_chats'

function createWelcomeMessage() {
  return {
    id: generateUUID(),
    content: '你好！我是你的数学AI助手，有什么我可以帮助你的吗？',
    sender: 'ai',
    timestamp: new Date().toLocaleString(),
    type: 'text',
    errorBookStatus: 'pending',
    errorBookId: null
  }
}

export const useChatStore = defineStore('chat', () => {
  const chats = ref(loadFromStorage(STORAGE_KEY, []))
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
    saveToStorage(STORAGE_KEY, chats.value)
  }

  function createNewChat() {
    const newChat = {
      id: generateUUID(),
      title: '新对话',
      lastMessageTime: new Date().toLocaleString(),
      messages: [createWelcomeMessage()],
      defaultTutorMode: 'step_by_step'
    }
    chats.value.unshift(newChat)
    currentChatId.value = newChat.id
    persistChats()
    return newChat
  }

  function switchChat(chatId) {
    currentChatId.value = chatId
  }

  function addMessage(chatId, message) {
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

  function updateMessage(chatId, messageId, updates) {
    const chat = chats.value.find(c => c.id === chatId)
    if (!chat) return

    const message = chat.messages.find(m => m.id === messageId)
    if (!message) return

    Object.assign(message, updates)
    persistChats()
  }

  function deleteChat(chatId) {
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
    const chat = chats.value.find(c => c.id === chatId)
    if (chat && title.trim()) {
      chat.title = title.trim()
      persistChats()
      updateChatSession(chatId, { title: chat.title }).catch(() => {})
    }
  }

  function clearChat(chatId) {
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
    const data = unwrapChat(await getChatSession(chatId))
    const mapped = (data.messages || []).map(message => ({ id: `sql-${message.id}`, content: message.content, sender: message.role === 'assistant' ? 'ai' : message.role, timestamp: message.created_at, type: 'text', errorBookStatus: message.role === 'assistant' ? 'pending' : undefined }))
    const existing = chats.value.find(item => item.id === chatId)
    const chat = { id: data.id, title: data.title || '新对话', lastMessageTime: data.messages?.at(-1)?.created_at || new Date().toISOString(), messages: mapped.length ? mapped : [createWelcomeMessage()], defaultTutorMode: data.default_tutor_mode || 'step_by_step', context: data.context || {} }
    if (existing) Object.assign(existing, chat); else chats.value.push(chat)
    currentChatId.value = chatId; persistChats(); return chat
  }

  async function syncFromServer() {
    const rows = unwrapChat(await listChatSessions()) || []
    for (const row of rows) {
      const existing = chats.value.find(item => item.id === row.id)
      const shell = { id: row.id, title: row.title || '新对话', lastMessageTime: row.updated_at, messages: existing?.messages || [], defaultTutorMode: row.default_tutor_mode || 'step_by_step', context: row.context || {} }
      if (existing) Object.assign(existing, shell); else chats.value.push(shell)
    }
    chats.value.sort((a,b)=>new Date(b.lastMessageTime)-new Date(a.lastMessageTime))
    if (currentChatId.value && rows.some(row=>row.id===currentChatId.value)) await loadServerChat(currentChatId.value)
    persistChats(); return rows
  }

  function setTutorMode(chatId, mode) {
    const chat = chats.value.find(item => item.id === chatId)
    if (chat) { chat.defaultTutorMode = mode; persistChats(); updateChatSession(chatId, { default_tutor_mode: mode }).catch(() => {}) }
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
