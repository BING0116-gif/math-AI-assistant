/**
 * 用户态 localStorage 分桶
 *
 * 背景：math_ai_chats / math_ai_error_book 曾经直接写在没有用户维度的 key 上，而
 * clearSession() 只清理 auth_token / refresh_token / current_user。结果是同一浏览器
 * 换账号登录后，仍能读到上一个账号的对话标题与错题（含题目原文、答案、错因）。
 * 这两个 store 的真值在服务端，本地只是缓存，因此缓存必须绑定到归属账号。
 *
 * key 约定沿用 errorBookDismissals 已有的格式：`${base}:${owner}`，owner 缺失时用 'anon'。
 *
 * 关于旧的无后缀 key：**不迁移**。把一份无主数据归给“碰巧先登录”的账号是错误归属，
 * 而这些数据在服务端本来就有权威副本；store 一律不再读写旧 key。
 * api/migrations.js 仍会读旧 key 做一次性历史上传，但它自己的“已处理”标记也按账号分桶，
 * 并用一个全局标记保证无主数据不会被两个账号各自领走。
 */
import { loadFromStorage, saveToStorage } from './storage'

export const ANON_OWNER = 'anon'

/** 需要按账号隔离的 base key 登记表：store 从这里取值，避免各处硬编码漂移。 */
export const SCOPED_KEYS = {
  chats: 'math_ai_chats',
  errorBook: 'math_ai_error_book',
  legacyMigration: 'legacy_client_migration_batch',
}

let ownerGetter = null

/**
 * 由 main.js 注入 `() => useAuthStore().userId`。
 * 与 api/index.js 的 setAuthTokenGetter 同一手法：util 不 import store，避免循环依赖。
 */
export function setScopedOwnerGetter(getter) {
  ownerGetter = typeof getter === 'function' ? getter : null
}

/** 当前归属账号；未注入 / 未登录 / getter 抛错都落到 anon 桶，绝不默认沿用上一个账号。 */
export function currentOwner() {
  let raw = ''
  try {
    raw = ownerGetter ? ownerGetter() : ''
  } catch {
    raw = ''
  }
  return raw ? String(raw) : ANON_OWNER
}

export function scopedKey(base, owner = currentOwner()) {
  return `${base}:${owner || ANON_OWNER}`
}

export function loadScoped(base, defaultValue = null, owner = currentOwner()) {
  return loadFromStorage(scopedKey(base, owner), defaultValue)
}

export function saveScoped(base, value, owner = currentOwner()) {
  saveToStorage(scopedKey(base, owner), value)
}
