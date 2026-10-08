/**
 * 登录/注册失败响应的前端统一解读。
 *
 * 后端契约：
 * - 401 `{"code":"INVALID_CREDENTIALS","message":"用户名或密码错误","retry_after_seconds":null}`
 * - 423 `{"code":"ACCOUNT_LOCKED","message":"账户已临时锁定，请稍后再试","retry_after_seconds":<n>}` + `Retry-After`
 * - 429 `{"detail":"请求过于频繁，请稍后再试"}` + `Retry-After`（限流中间件既有结构，未变）
 *
 * 页面不应各自猜字段：这里把"新契约"与"仍是 `{detail}` 的旧/其它端点"收敛成同一形状，
 * 未知状态码也能拿到可展示的中文文案，不会退回 `undefined` 或英文。
 */

export const AUTH_ERROR_CODES = {
  INVALID_CREDENTIALS: 'INVALID_CREDENTIALS',
  ACCOUNT_LOCKED: 'ACCOUNT_LOCKED',
  RATE_LIMITED: 'RATE_LIMITED',
  UNKNOWN: 'UNKNOWN',
}

export const GENERIC_AUTH_FAILURE = '操作失败，请检查用户名和密码后重试。'

const MESSAGE_BY_STATUS = {
  401: '用户名或密码错误',
  403: '当前账号无权执行该操作',
  409: '用户名已存在',
  423: '账户已临时锁定，请稍后再试',
  429: '操作过于频繁，请稍后再试',
}

const CODE_BY_STATUS = {
  401: AUTH_ERROR_CODES.INVALID_CREDENTIALS,
  423: AUTH_ERROR_CODES.ACCOUNT_LOCKED,
  429: AUTH_ERROR_CODES.RATE_LIMITED,
}

function toFiniteNumber(value) {
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

function retryAfterSeconds(err, data) {
  const fromBody = toFiniteNumber(data?.retry_after_seconds)
  if (fromBody !== null && fromBody >= 0) return Math.floor(fromBody)
  const headers = err?.response?.headers || {}
  // axios 通常会规范化成小写，但不能依赖它（缓存响应/拦截器改写后可能保留原大小）
  const header = headers['retry-after'] ?? headers['Retry-After']
  const fromHeader = toFiniteNumber(header)
  return fromHeader !== null ? Math.max(0, Math.floor(fromHeader)) : 0
}

function messageOf(data, status) {
  if (typeof data?.message === 'string' && data.message.trim()) return data.message
  const detail = data?.detail
  // 422 的 detail 是数组，不能直接当成文案渲染
  if (typeof detail === 'string' && detail.trim()) return detail
  return MESSAGE_BY_STATUS[status] || GENERIC_AUTH_FAILURE
}

/**
 * @param {unknown} err axios 抛出的错误（也容忍普通 Error / 无响应场景）
 * @returns {{status:number, code:string, message:string, retryAfterSeconds:number, locked:boolean, rateLimited:boolean}}
 */
export function describeAuthError(err) {
  const status = Number(err?.response?.status) || 0
  const data = err?.response?.data
  const safeData = data && typeof data === 'object' ? data : {}
  const code = typeof safeData.code === 'string' && safeData.code
    ? safeData.code
    : (CODE_BY_STATUS[status] || AUTH_ERROR_CODES.UNKNOWN)

  return {
    status,
    code,
    message: messageOf(safeData, status),
    retryAfterSeconds: retryAfterSeconds(err, safeData),
    locked: code === AUTH_ERROR_CODES.ACCOUNT_LOCKED,
    rateLimited: code === AUTH_ERROR_CODES.RATE_LIMITED,
  }
}

/** 把秒数格式化成 mm:ss，供"请 mm:ss 后可重试"文案使用。 */
export function formatRetryDelay(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  const mm = Math.floor(total / 60)
  const ss = total % 60
  return mm > 0 ? `${mm}:${String(ss).padStart(2, '0')}` : `${ss} 秒`
}

/** 该错误是否应当禁用提交按钮并进入倒计时。 */
export function shouldCoolDown(authError) {
  if (!authError) return false
  return (authError.locked || authError.rateLimited) && authError.retryAfterSeconds > 0
}
