/**
 * 统一认证状态 Store
 *
 * 这是前端唯一的认证状态入口。
 * 所有页面/组件必须通过此 store 读取 token、用户信息和认证状态。
 *
 * Token 策略：access token 仅保存在内存，refresh token 由后端写入
 * HttpOnly cookie。旧 token 键只会被清理，不再读取或发送。
 * 非敏感用户信息继续存放在 `current_user`。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

export const useAuthStore = defineStore('auth', () => {
  // ============================================================
  // State
  // ============================================================
  const accessToken = ref('')
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
    const { access_token, user_id, username: uname, role: userRole } = data.data
    removeLegacyTokens()
    saveUser({ user_id, username: uname, role: userRole || 'student' })
    accessToken.value = access_token
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
      await api.post('/auth/logout')
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
    try {
      const { data } = await api.post('/auth/refresh', undefined, {
        // The response interceptor must never recursively refresh this call.
        _isRefreshRequest: true,
      })
      const { access_token } = data.data
      removeLegacyTokens()
      accessToken.value = access_token
      return true
    } catch {
      clearSession()
      return false
    }
  }

  /**
   * 启动时恢复会话。旧版 localStorage token 会被读入内存后立即删除；
   * 新版会话通过 HttpOnly refresh cookie 换取新的 access token。
   */
  async function restoreSession() {
    const user = loadUser()
    removeLegacyTokens()
    if (user) {
      currentUser.value = user
      const restored = await refresh()
      restoring.value = false
      return restored
    }
    accessToken.value = ''
    currentUser.value = null
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

  function removeLegacyTokens() {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('refresh_token')
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
