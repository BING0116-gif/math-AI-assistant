/**
 * 统一认证状态 Store
 *
 * 这是前端唯一的认证状态入口。
 * 所有页面/组件必须通过此 store 读取 token、用户信息和认证状态。
 *
 * Token Key 策略：
 * - 正式 access token key: `auth_token`
 * - 正式 refresh token key: `refresh_token`
 * - 用户信息 key: `current_user`
 * - 无旧 key 需要兼容迁移
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'
import { describeAuthError } from '@/api/authErrors'
import { runLogoutFlushes } from '@/utils/logoutFlush'

export const useAuthStore = defineStore('auth', () => {
  // ============================================================
  // State
  // ============================================================
  const accessToken = ref(localStorage.getItem('auth_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const currentUser = ref(loadUser())
  const restoring = ref(true) // 启动时恢复会话期间为 true
  // 会话是被服务端判死的（401 → refresh 也失效），不是用户自己退的。这个标记存内存而不
  // 是存 URL：被动过期有两条落地路，一条是 useSessionExpiry 主动跳（带 ?expired=1），另一条是
  // 路由守卫兜到 /login（只带 redirect）；只看 URL 的话后一条永远不提示。登录成功即消费。
  const sessionExpired = ref(false)
  // 最近一次登录/注册失败的归一化描述（{code, message, retryAfterSeconds}）。
  // 仅供页面展示与倒计时使用；原始错误仍原样抛出，保持调用方既有 catch 语义。
  const lastAuthError = ref(null)

  // ============================================================
  // Getters
  // ============================================================
  const isAuthenticated = computed(() => !!accessToken.value)
  const username = computed(() => currentUser.value?.username || '')
  const userId = computed(() => currentUser.value?.user_id || '')
  const role = computed(() => currentUser.value?.role || 'student')

  // ============================================================
  // Actions
  // ============================================================

  /**
   * 登录：调用 /api/auth/login，存储 tokens 和用户信息。
   */
  async function login(credentials) {
    let data
    try {
      ;({ data } = await api.post('/auth/login', credentials))
    } catch (err) {
      // 401 INVALID_CREDENTIALS / 423 ACCOUNT_LOCKED / 429 限流都归一化后再抛出
      lastAuthError.value = describeAuthError(err)
      throw err
    }
    lastAuthError.value = null
    sessionExpired.value = false
    const { access_token, refresh_token, user_id, username: uname, role: userRole } = data.data
    saveTokens(access_token, refresh_token)
    saveUser({ user_id, username: uname, role: userRole || 'student' })
    accessToken.value = access_token
    refreshToken.value = refresh_token
    currentUser.value = { user_id, username: uname, role: userRole || 'student' }
    import('@/api/migrations').then(({ migrateLegacyClientState }) => migrateLegacyClientState()).catch(() => {})
    return data
  }

  /**
   * 注册：调用 /api/auth/register，然后自动登录。
   */
  async function register(credentials) {
    try {
      await api.post('/auth/register', credentials)
    } catch (err) {
      lastAuthError.value = describeAuthError(err)
      throw err
    }
    // 注册成功后自动登录
    return login(credentials)
  }

  /**
   * 退出登录：先跑完依赖会话的收尾上报，再调后端 logout，最后清除本地 session。
   *
   * 顺序不能换：收尾钩子需要当前 access token 仍有效。以前是先 clearSession()，
   * 等路由跳走才触发学习时长的结束上报，那时已无 Authorization，401 被静默吃掉。
   *
   * 重复调用复用同一个进行中的任务（而不是直接返回）：调用方通常是
   * `await logout()` 再 `router.replace('/login')`，早退会让第二次点击在会话还没清完时
   * 就去跳登录页，被 /login 的 guestOnly 守卫弹回首页。
   *
   * 这里不管“正在退出”的 UI 态：那个周期包含路由跳转，属于登出流程，住在 uiStore.signingOut。
   */
  let logoutTask = null
  async function logout() {
    if (logoutTask) return logoutTask
    logoutTask = (async () => {
      try {
        await runLogoutFlushes()
        try {
          await api.post('/auth/logout', {
            refresh_token: refreshToken.value,
          })
        } catch {
          // 后端 logout 失败时，本地 session 仍要清理
        }
        clearSession()
      } finally {
        logoutTask = null
      }
    })()
    return logoutTask
  }

  /**
   * 刷新 access token。
   * 返回 true 表示成功，false 表示失败。
   */
  async function refresh() {
    if (!refreshToken.value) return false
    try {
      const { data } = await api.post('/auth/refresh', {
        refresh_token: refreshToken.value,
      }, {
        // The response interceptor must never recursively refresh this call.
        _isRefreshRequest: true,
      })
      const { access_token, refresh_token: newRefresh } = data.data
      saveTokens(access_token, newRefresh)
      accessToken.value = access_token
      refreshToken.value = newRefresh
      return true
    } catch {
      // 只有真被服务端拒绝才算判死：无 refresh token 的早退分支不走到这里，
      // 否则游客在公开页上碰一个普通 401 也会被当成“登录已过期”。
      clearSession({ reason: 'expired' })
      return false
    }
  }

  /** Synchronize identity and role with the authenticated server session. */
  async function syncCurrentUser() {
    if (!accessToken.value) return false
    try {
      const { data } = await api.get('/auth/me')
      const user = data.data
      const normalized = {
        user_id: user.user_id,
        username: user.username,
        role: user.role || 'student',
      }
      saveUser(normalized)
      currentUser.value = normalized
      return true
    } catch {
      return false
    }
  }

  /**
   * 启动时恢复会话：从 localStorage 读取已有 tokens。
   * 返回 true 表示已有有效会话。
   */
  function restoreSession() {
    const at = localStorage.getItem('auth_token')
    const rt = localStorage.getItem('refresh_token')
    const user = loadUser()
    if (at && user) {
      accessToken.value = at
      refreshToken.value = rt || ''
      currentUser.value = user
      restoring.value = false
      return true
    }
    // 只有 token 没有用户信息 → 清理
    if (at && !user) {
      clearSession()
    }
    restoring.value = false
    return false
  }

  /**
   * 记下“会话是被判死的”。不对外暴露：只能由 clearSession({ reason: 'expired' })
   * 顺便设上，否则“标了没清”与“清了没标”都会变成一个可命中的中间态。
   */
  function markSessionExpired() {
    sessionExpired.value = true
  }

  /**
   * 清理所有认证状态（本地）。
   *
   * `reason` 只影响一个事实：这次清理能不能被当成“登录已过期”。
   * 默认 `local`：主动退出登录、启动时本地态残缺那种清理都走这一条，不能标过期。
   * `expired`：服务端已经拒掉本会话（refresh 也失效），登录页据此提示。
   */
  function clearSession({ reason = 'local' } = {}) {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('current_user')
    accessToken.value = ''
    refreshToken.value = ''
    currentUser.value = null
    lastAuthError.value = null
    if (reason === 'expired') markSessionExpired()
  }

  /**
   * 获取当前 access token（供 axios 拦截器使用）。
   */
  function getAccessToken() {
    return accessToken.value
  }

  // ============================================================
  // 内部辅助
  // ============================================================

  function saveTokens(at, rt) {
    try {
      localStorage.setItem('auth_token', at)
      localStorage.setItem('refresh_token', rt)
    } catch {
      // localStorage 不可用时静默失败
    }
  }

  function saveUser(user) {
    try {
      localStorage.setItem('current_user', JSON.stringify(user))
    } catch {
      // 静默失败
    }
  }

  function loadUser() {
    try {
      const raw = localStorage.getItem('current_user')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }

  return {
    // state
    accessToken,
    refreshToken,
    currentUser,
    restoring,
    lastAuthError,
    sessionExpired,
    // getters
    isAuthenticated,
    username,
    userId,
    role,
    // actions
    login,
    register,
    logout,
    refresh,
    syncCurrentUser,
    restoreSession,
    clearSession,
    getAccessToken,
  }
})
