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
  // 不设默认 Content-Type：让 axios 根据 data 类型自适应
  // （JSON 对象 → application/json；FormData → multipart/form-data; boundary=...）
  // 显式设成 application/json 会让 FormData 上传被发成 JSON，进而被 FastAPI 422 拒绝
})

// 从 authStore 获取 token 的 getter（由 main.js 在 Pinia 初始化后设置）
let _authTokenGetter = null

/**
 * 设置 auth store 的 token getter。
 * 在 main.js 中 Pinia 初始化后调用。
 */
export function setAuthTokenGetter(getter) {
  _authTokenGetter = getter
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
    if (!token) {
      // fallback: 直接从 localStorage 读取
      token = localStorage.getItem('auth_token')
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
 * 3. 若 refresh 失败，走会话失效的唯一出口 clearSessionOnce()（标记判死 + 重置 store + 本地缓存）
 * 4. 避免 refresh 请求本身进入 refresh 循环
 * 5. 多个并发 401 只发起一次 refresh
 * 6. 登录/注册自身的 401 不刷新、不重放；423/429 不是 401，天然不进入刷新分支
 * 7. 确认会话已死时只清本地态，**不在这里跳转路由**：被动过期的落地交给
 *    composables/useSessionExpiry.js 统一处理，与主动登出同样只依赖 store 态变化
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
      await clearSessionOnce()
      return Promise.reject(error)
    }

    // 登录/提交的凭据错误就是业务结果：既不该拿旧 refresh token 去换，
    // 也不该把同一个错误密码的请求重放一次；更不该清掉其它账号已有的会话。
    if (/(^|\/)auth\/(login|register)(?:$|\?)/.test(requestUrl)) {
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
      const { useAuthStore } = await import('@/stores/authStore')
      const store = useAuthStore()
      const success = await store.refresh()

      if (success) {
        // 刷新成功，重放原始请求
        const newToken = store.getAccessToken()
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

/**
 * 会话失效的唯一出口：`authStore.clearSession({ reason: 'expired' })`。
 *
 * 以前这里自己 removeItem 三个 key，与 store 的实现不等价：它不重置
 * accessToken / refreshToken / currentUser，于是存在第三种壳态——storage 已空、
 * `isAuthenticated` 仍为 true：路由守卫不拦、页面继续打必 401 的请求，本地对话列表
 * 还会因为 owner 变空而被清掉，学生看到的是“应用莫名空了”而不是“登录过期”。
 *
 * 为什么还要带上 reason：被动过期有两条落地路——useSessionExpiry 自己跳（带 ?expired=1）
 * 与路由守卫兜回登录页（只带 redirect）。只看 URL 的话后一条永远不提示，而那条恰恰是
 * 会话在 watcher 建立前就判死时走的那条。标记与清理必须是同一次调用：分成两步就会
 * 留下“标了没清”或“清了没标”这种可命中的中间态。
 *
 * 极端情况下（Pinia 尚未就绪）退回直接删 key：至少不会留下“半认证”状态。这种
 * 降级下记不了标记（refs 不存在），登录页会退化成无提示——比留下壳态轻得多，接受。
 */
async function clearSessionOnce() {
  try {
    const { useAuthStore } = await import('@/stores/authStore')
    const auth = useAuthStore()
    auth.clearSession({ reason: 'expired' })
  } catch {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('current_user')
  }
}

export default api
