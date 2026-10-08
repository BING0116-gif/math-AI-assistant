// 对话错题本"跳过"状态的本地登记表。
//
// 仅前端、按真实 user_id 命名空间隔离；内容是 chatErrorSourceId 生成的
// 不透明哈希（会话 ID + 问题文本），不含题目原文，可安全留存于 localStorage。
// 用途：让"跳过"在刷新后仍生效（loadServerChat 会把助手消息重置为 pending，
// 这里据登记表回填 skipped），而不会污染错题本数据。added 状态优先于 skipped。
import { loadFromStorage, saveToStorage } from '@/utils/storage'
import { ANON_OWNER, scopedKey } from '@/utils/scopedStorage'

const PREFIX = 'math_ai_error_book_skipped'

// key 格式由 scopedStorage 统一约定，避免两处各自拼接。这里故意只依赖显式传入的
// userId（缺失才用 anon）而不调用 currentOwner()：调用方漏传时不得静默写进当前登录账号的登记表。
function keyFor(userId) {
  return scopedKey(PREFIX, userId || ANON_OWNER)
}

/** 返回该用户已跳过的来源键列表（副本）。 */
export function listSkippedSourceIds(userId) {
  const list = loadFromStorage(keyFor(userId), [])
  return Array.isArray(list) ? list : []
}

/** 记录某条 AI 回答被跳过（幂等，去重）。 */
export function markSkippedSourceId(userId, sourceId) {
  if (!sourceId) return
  const list = listSkippedSourceIds(userId)
  if (!list.includes(sourceId)) {
    list.push(sourceId)
    saveToStorage(keyFor(userId), list)
  }
}

/** 加入错题本后清除对应跳过记录，保持登记表整洁。 */
export function clearSkippedSourceId(userId, sourceId) {
  if (!sourceId) return
  const list = listSkippedSourceIds(userId)
  const idx = list.indexOf(sourceId)
  if (idx !== -1) {
    list.splice(idx, 1)
    saveToStorage(keyFor(userId), list)
  }
}
