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

export const useAuthStore = defineStore('auth', () => {
  // ============================================================
  // State
  // ============================================================
  const accessToken = ref(localStorage.getItem('auth_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const currentUser = ref(loadUser())
  const restoring = ref(true) // 启动时恢复会话期间为 true

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
    const { data } = await api.post('/auth/login', credentials)
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
    await api.post('/auth/register', credentials)
    // 注册成功后自动登录
    return login(credentials)
  }

  /**
   * 退出登录：调用后端 logout，清除本地 session。
   */
  async function logout() {
    try {
      await api.post('/auth/logout', {
        refresh_token: refreshToken.value,
      })
    } catch {
      // 后端 logout 失败时，本地 session 仍要清理
    }
    clearSession()
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
      clearSession()
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
   * 清理所有认证状态（本地）。
   */
  function clearSession() {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('current_user')
    accessToken.value = ''
    refreshToken.value = ''
    currentUser.value = null
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
    restoreSession,
    clearSession,
    getAccessToken,
  }
})
