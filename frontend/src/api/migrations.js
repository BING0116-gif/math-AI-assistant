import api from './index'

const MIGRATION_KEY = 'legacy_client_migration_batch'

export async function migrateLegacyClientState() {
  if (localStorage.getItem(`${MIGRATION_KEY}:completed`)) return null
  let batchId = localStorage.getItem(MIGRATION_KEY)
  if (!batchId) {
    batchId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    localStorage.setItem(MIGRATION_KEY, batchId)
  }
  const chats = JSON.parse(localStorage.getItem('math_ai_chats') || '[]').map((chat) => ({
    external_session_id: String(chat.id), title: chat.title || '本地历史',
    messages: (chat.messages || []).filter((message) => message.content).map((message) => ({
      role: message.sender === 'ai' ? 'assistant' : 'user', content: String(message.content),
    })),
  }))
  const errors = JSON.parse(localStorage.getItem('math_ai_error_book') || '[]').filter((item) => item.question || item.display_question).map((item) => ({
    client_item_id: String(item.id), question: String(item.question || item.display_question),
    question_type: item.question_type || 'text', error_reason: item.error_reason || '',
    categories: item.categories || [], original_answer: item.original_answer || '',
    correct_answer: item.correct_answer || '', notes: item.notes || '', added_at: item.added_at || '',
  }))
  if (!chats.length && !errors.length) {
    localStorage.setItem(`${MIGRATION_KEY}:completed`, 'empty')
    return null
  }
  const { data } = await api.post('/migrations/legacy-client', { batch_id: batchId, chats, errors })
  localStorage.setItem(`${MIGRATION_KEY}:completed`, JSON.stringify(data))
  return data
}
