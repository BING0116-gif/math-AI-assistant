/**
 * 统一 API 客户端。
 *
 * 所有前端 API 请求统一通过此 axios 实例。
 * Authorization 头由拦截器从 authStore 统一注入，禁止各模块手动拼接 token。
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true,
  // 不设默认 Content-Type：让 axios 根据 data 类型自适应
  // （JSON 对象 → application/json；FormData → multipart/form-data; boundary=...）
  // 显式设成 application/json 会让 FormData 上传被发成 JSON，进而被 FastAPI 422 拒绝
})

// 从 authStore 获取 token 的 getter（由 main.js 在 Pinia 初始化后设置）
let _authTokenGetter = null
let _authRefreshHandler = null
let _authClearHandler = null

/**
 * 设置 auth store 的 token getter。
 * 在 main.js 中 Pinia 初始化后调用。
 */
export function setAuthTokenGetter(getter) {
  _authTokenGetter = getter
}

/**
 * Inject auth actions after Pinia is initialized. Keeping the API layer store-
 * agnostic avoids a circular import and a dynamic import that cannot split.
 */
export function setAuthSessionHandlers({ getToken, refresh, clearSession } = {}) {
  _authTokenGetter = typeof getToken === 'function' ? getToken : null
  _authRefreshHandler = typeof refresh === 'function' ? refresh : null
  _authClearHandler = typeof clearSession === 'function' ? clearSession : null
}

// 是否正在刷新 token 的标记
let isRefreshing = false
// 等待刷新完成后的请求队列
let refreshQueue = []

/**
 * 请求拦截器：统一注入 Authorization 头。
 */
api.interceptors.request.use(
  (config) => {
    let token = null
    if (_authTokenGetter) {
      token = _authTokenGetter()
    }
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

/**
 * 响应拦截器：统一处理 401。
 *
 * 行为：
 * 1. 401 时尝试刷新 token
 * 2. 若 refresh 成功，重放原始请求
 * 3. 若 refresh 失败，清理 session
 * 4. 避免 refresh 请求本身进入 refresh 循环
 * 5. 多个并发 401 只发起一次 refresh
 */
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // 不是 401 或没有 config（网络错误等），直接拒绝
    if (!error.response || error.response.status !== 401 || !originalRequest) {
      return Promise.reject(error)
    }

    // 已经是 refresh 请求本身失败 → 不再重试，清理 session
    const requestUrl = String(originalRequest.url || '')
    if (originalRequest._isRefreshRequest || /(^|\/)auth\/refresh(?:$|\?)/.test(requestUrl)) {
      clearAuthSession()
      return Promise.reject(error)
    }

    // 已经重试过 → 不再重试
    if (originalRequest._retry) {
      return Promise.reject(error)
    }

    // 处理 refresh 并发
    if (isRefreshing) {
      // 正在刷新中，将请求加入队列等待
      return new Promise((resolve, reject) => {
        refreshQueue.push((newToken) => {
          if (newToken) {
            originalRequest.headers.Authorization = `Bearer ${newToken}`
            resolve(api(originalRequest))
          } else {
            reject(error)
          }
        })
      })
    }

    originalRequest._retry = true
    isRefreshing = true

    try {
      if (!_authRefreshHandler) {
        clearAuthSession()
        return Promise.reject(error)
      }
      const success = await _authRefreshHandler()

      if (success) {
        // 刷新成功，重放原始请求
        const newToken = _authTokenGetter?.()
        if (!newToken) {
          clearAuthSession()
          refreshQueue.forEach((cb) => cb(null))
          refreshQueue = []
          return Promise.reject(error)
        }
        originalRequest.headers.Authorization = `Bearer ${newToken}`

        // 处理队列中的请求
        refreshQueue.forEach((cb) => cb(newToken))
        refreshQueue = []

        return api(originalRequest)
      } else {
        // 刷新失败，通知队列
        refreshQueue.forEach((cb) => cb(null))
        refreshQueue = []
        return Promise.reject(error)
      }
    } catch {
      refreshQueue.forEach((cb) => cb(null))
      refreshQueue = []
      return Promise.reject(error)
    } finally {
      isRefreshing = false
    }
  }
)

function clearLocalSession() {
  // Token keys are removed for one-release compatibility with legacy sessions.
  localStorage.removeItem('auth_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('current_user')
}

function clearAuthSession() {
  if (_authClearHandler) {
    _authClearHandler()
    return
  }
  clearLocalSession()
}

export default api
