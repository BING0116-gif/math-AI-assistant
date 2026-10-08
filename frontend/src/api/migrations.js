/**
 * 旧版（未分桶时代）浏览器本地历史的一次性上传。
 *
 * 载荷读的仍是无后缀的 `math_ai_chats` / `math_ai_error_book`：那是本仓库引入按账号分桶
 * 之前的唯一一份本地历史，没有用户维度。因此“是否已经处理过”必须区分两层语义：
 *
 * 1. 本账号是否已决定过 —— 按账号记录（`${base}:${userId}:completed`）。以前它是全局单键，
 *    结果是同一浏览器上先登录的账号写完成标记后，后登录的账号会被全局标记永久跳过。
 * 2. 这份无主数据是否已被某个账号领走 —— 全局 `:consumed` 标记。若没有它，按账号分桶后
 *    第二个账号会把同一个账号的题目原文与答案再上传一次，等于制造跨账号泄漏。
 *
 * 服务端本身也是双重幂等的：`legacy_client_imports` 按 (user_id, batch_id) 去重，
 * 会话按 (user_id, external_session_id)、错题按 (user_id, item_id) 跳过，所以换 batch_id
 * 重跑只会增加 skipped_items，不会产生重复数据。
 */
import api from './index'
import { SCOPED_KEYS, ANON_OWNER, currentOwner, scopedKey } from '@/utils/scopedStorage'

const MIGRATION_KEY = SCOPED_KEYS.legacyMigration
const CONSUMED_KEY = `${MIGRATION_KEY}:consumed`

function completedKeyFor(owner) {
  return `${scopedKey(MIGRATION_KEY, owner)}:completed`
}

export async function migrateLegacyClientState() {
  const owner = currentOwner()
  // 未登录时上传等于把无主数据交给“下一个读到标记的人”，直接跳过
  if (owner === ANON_OWNER) return null

  const ownMarker = localStorage.getItem(completedKeyFor(owner))
  if (ownMarker) return null

  // 旧版全局标记：代表这台浏览器已经处理过无主历史，采纳为已领走，避免分桶后二次上传
  const legacyGlobalMarker = localStorage.getItem(`${MIGRATION_KEY}:completed`)
  if (legacyGlobalMarker) {
    localStorage.setItem(CONSUMED_KEY, 'adopted-legacy-marker')
    localStorage.setItem(completedKeyFor(owner), legacyGlobalMarker)
    return null
  }

  if (localStorage.getItem(CONSUMED_KEY)) {
    localStorage.setItem(completedKeyFor(owner), 'skipped-already-consumed')
    return null
  }

  const batchKey = scopedKey(MIGRATION_KEY, owner)
  let batchId = localStorage.getItem(batchKey)
  if (!batchId) {
    batchId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    localStorage.setItem(batchKey, batchId)
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
  // 本地确实没有历史：只记本账号已决定过，不占用全局“已领走”，其它账号仍可各自认领
  if (!chats.length && !errors.length) {
    localStorage.setItem(completedKeyFor(owner), 'empty')
    return null
  }
  const { data } = await api.post('/migrations/legacy-client', { batch_id: batchId, chats, errors })
  localStorage.setItem(completedKeyFor(owner), JSON.stringify(data))
  localStorage.setItem(CONSUMED_KEY, batchId)
  return data
}
