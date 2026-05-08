import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { generateUUID } from '@/utils/helpers'
import { loadFromStorage, saveToStorage } from '@/utils/storage'

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
      messages: [createWelcomeMessage()]
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
      chat.title = (message.content || '').substring(0, 20) + ((message.content || '').length > 20 ? '...' : '')
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
    }
  }

  function renameChat(chatId, title) {
    const chat = chats.value.find(c => c.id === chatId)
    if (chat && title.trim()) {
      chat.title = title.trim()
      persistChats()
    }
  }

  function clearChat(chatId) {
    const chat = chats.value.find(c => c.id === chatId)
    if (chat) {
      chat.messages = [createWelcomeMessage()]
      chat.lastMessageTime = new Date().toLocaleString()
      persistChats()
    }
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
    persistChats
  }
})
