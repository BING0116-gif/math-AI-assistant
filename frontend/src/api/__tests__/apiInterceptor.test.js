/**
 * API Interceptor 测试。
 *
 * 覆盖：
 * - Authorization header 统一注入（request interceptor）
 * - 401 → refresh 成功 → 重放原请求（response interceptor）
 * - 401 → refresh 失败 → 通过会话失效的唯一出口清理（不在本文件里自己删 key）
 * - 非 401 错误不触发 refresh
 * - refresh 请求本身 401 不循环
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'

// ============================================================
// Mock 设置 — vi.hoisted 确保在 vi.mock 提升前定义变量
// ============================================================
const { mockStore, mockAxiosInstance } = vi.hoisted(() => {
  const mockStore = {
    getAccessToken: vi.fn().mockReturnValue(''),
    refresh: vi.fn(),
    clearSession: vi.fn(),
  }

  const mockAxiosInstance = Object.assign(
    vi.fn().mockResolvedValue({ data: 'retried-ok' }),
    {
      defaults: { headers: { common: {} } },
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
      post: vi.fn(),
      get: vi.fn(),
      request: vi.fn(),
    }
  )

  return { mockStore, mockAxiosInstance }
})

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => mockAxiosInstance),
  },
}))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: vi.fn(() => mockStore),
}))

// ============================================================
// 导入目标模块（mock 生效后）
// ============================================================
import { setAuthTokenGetter } from '@/api'

// ============================================================
// Tests
// ============================================================
describe('API Interceptor', () => {
  let requestHandler
  let responseErrorHandler

  beforeAll(() => {
    // 捕获拦截器处理器
    const reqCalls = mockAxiosInstance.interceptors.request.use.mock.calls
    requestHandler = reqCalls[0][0]

    const respCalls = mockAxiosInstance.interceptors.response.use.mock.calls
    // respCalls[0][0] = 成功处理器 (直接返回 response)
    // respCalls[0][1] = 错误处理器
    responseErrorHandler = respCalls[0][1]
  })

  beforeEach(() => {
    vi.clearAllMocks()
    // 重置 auth token getter（设为 null 触发 localStorage fallback）
    setAuthTokenGetter(null)
    localStorage.clear()
    // 重置 mock store
    mockStore.getAccessToken.mockReturnValue('')
    mockStore.refresh.mockReset()
    mockStore.clearSession.mockReset()
    // 重置 mock 实例
    mockAxiosInstance.mockClear()
    mockAxiosInstance.mockResolvedValue({ data: 'retried-ok' })
    mockAxiosInstance.request.mockReset()
  })

  // ============================================================
  // 3.1 Authorization header injection
  // ============================================================
  describe('Authorization header injection', () => {
    it('should add Bearer token when authStore getter returns a token', () => {
      setAuthTokenGetter(() => 'test-access-token')
      const config = { headers: {} }
      const result = requestHandler(config)
      expect(result.headers.Authorization).toBe('Bearer test-access-token')
    })

    it('should fallback to localStorage when getter is not set', () => {
      localStorage.setItem('auth_token', 'local-fallback-token')
      const config = { headers: {} }
      const result = requestHandler(config)
      expect(result.headers.Authorization).toBe('Bearer local-fallback-token')
    })

    it('should not add Authorization header when no token is available', () => {
      const config = { headers: {} }
      const result = requestHandler(config)
      expect(result.headers.Authorization).toBeUndefined()
    })

    it('should prefer authStore getter over localStorage', () => {
      localStorage.setItem('auth_token', 'local-token')
      setAuthTokenGetter(() => 'store-token')
      const config = { headers: {} }
      const result = requestHandler(config)
      expect(result.headers.Authorization).toBe('Bearer store-token')
    })
  })

  // ============================================================
  // 3.2 401 refresh success
  // ============================================================
  describe('401 refresh success', () => {
    it('should call refresh and retry original request with new token', async () => {
      mockStore.refresh.mockResolvedValue(true)
      mockStore.getAccessToken.mockReturnValue('new-access-token')
      mockAxiosInstance.mockResolvedValue({ data: 'retried-success' })

      const error = {
        config: { headers: {}, url: '/api/test' },
        response: { status: 401 },
      }

      const result = await responseErrorHandler(error)

      // refresh 被调用
      expect(mockStore.refresh).toHaveBeenCalledTimes(1)
      // 原请求被重放（通过 api() 调用）
      expect(mockAxiosInstance).toHaveBeenCalledTimes(1)
      // 重放时使用了新 token
      const retryConfig = mockAxiosInstance.mock.calls[0][0]
      expect(retryConfig.headers.Authorization).toBe('Bearer new-access-token')
      // 返回重放结果
      expect(result).toEqual({ data: 'retried-success' })
    })

    it('should not retry the same request more than once', async () => {
      mockStore.refresh.mockResolvedValue(true)
      mockStore.getAccessToken.mockReturnValue('new-token')
      mockAxiosInstance.mockResolvedValue({ data: 'retried' })

      const error = {
        config: { headers: {}, url: '/api/test' },
        response: { status: 401 },
      }

      // 第一次 401 → 正常重试
      await responseErrorHandler(error)
      expect(mockAxiosInstance).toHaveBeenCalledTimes(1)

      // 第二次 401（_retry 已被标记）→ 不应再重试
      error.config._retry = true
      await expect(responseErrorHandler(error)).rejects.toThrow()

      // api 仍然只被调用一次
      expect(mockAxiosInstance).toHaveBeenCalledTimes(1)
    })
  })

  // ============================================================
  // 3.3 401 refresh failure → clearSession
  // ============================================================
  describe('401 refresh failure → clearSession', () => {
    it('should clear session when refresh fails', async () => {
      localStorage.setItem('auth_token', 'old-token')
      localStorage.setItem('refresh_token', 'old-rt')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))

      // 模拟真实 authStore.refresh() 行为：失败时清除 localStorage
      mockStore.refresh.mockImplementation(() => {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('current_user')
        return Promise.resolve(false)
      })

      const error = {
        config: { headers: {}, url: '/api/test' },
        response: { status: 401 },
      }

      await expect(responseErrorHandler(error)).rejects.toThrow()

      // session 被清理
      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
      expect(localStorage.getItem('current_user')).toBeNull()
      // 没有重放
      expect(mockAxiosInstance).not.toHaveBeenCalled()
    })

    it('refresh 请求自身 401 时走同一个会话出口，而不是自己删 localStorage', async () => {
      localStorage.setItem('auth_token', 'old-token')
      localStorage.setItem('refresh_token', 'old-rt')

      const error = {
        config: { headers: {}, url: '/api/auth/refresh', _isRefreshRequest: true },
        response: { status: 401 },
      }

      await expect(responseErrorHandler(error)).rejects.toThrow()

      // 不触发 refresh
      expect(mockStore.refresh).not.toHaveBeenCalled()
      // 会话失效的语义只有一份：必须重置 store 里的 accessToken/currentUser。
      // 以前这个分支只 removeItem 三个 key，于是会出现「storage 已空、
      // isAuthenticated 仍为 true」的第三种壳态：守卫不拦、页面继续打必 401 的请求。
      expect(mockStore.clearSession).toHaveBeenCalledTimes(1)
      // 还要带上“是服务端判死的”这个理由：登录页的提示有两条来源，守卫兜回 /login
      // 的那条只带 redirect，不标这个就只能靠 URL，而那条路永远不提示。
      expect(mockStore.clearSession).toHaveBeenCalledWith({ reason: 'expired' })
    })

    it('store 不可达时退回直接删 key，不留半认证态', async () => {
      localStorage.setItem('auth_token', 'old-token')
      localStorage.setItem('refresh_token', 'old-rt')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
      mockStore.clearSession.mockImplementation(() => { throw new Error('pinia not ready') })

      const error = {
        config: { headers: {}, url: '/api/auth/refresh', _isRefreshRequest: true },
        response: { status: 401 },
      }

      await expect(responseErrorHandler(error)).rejects.toThrow()

      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
      expect(localStorage.getItem('current_user')).toBeNull()
    })

    it('should detect the refresh endpoint even when the caller marker is missing', async () => {
      const error = {
        config: { headers: {}, url: '/auth/refresh' },
        response: { status: 401 },
      }

      await expect(responseErrorHandler(error)).rejects.toThrow()

      expect(mockStore.refresh).not.toHaveBeenCalled()
      expect(mockAxiosInstance).not.toHaveBeenCalled()
    })
  })

  // ============================================================
  // Non-401 errors are not handled
  // ============================================================
  describe('non-401 errors', () => {
    it('should pass through non-401 errors', async () => {
      const error = {
        config: { headers: {}, url: '/api/test' },
        response: { status: 500 },
      }

      mockStore.refresh.mockResolvedValue(true)
      mockAxiosInstance.mockResolvedValue({ data: 'should-not-happen' })

      await expect(responseErrorHandler(error)).rejects.toThrow()

      // refresh 不应被触发
      expect(mockStore.refresh).not.toHaveBeenCalled()
      // 不应重放
      expect(mockAxiosInstance).not.toHaveBeenCalled()
    })

    it('should pass through network errors without response', async () => {
      const error = { config: { headers: {}, url: '/api/test' }, message: 'Network Error' }

      await expect(responseErrorHandler(error)).rejects.toThrow()
      expect(mockStore.refresh).not.toHaveBeenCalled()
    })
  })

  // ============================================================
  // 登录安全契约：401/423/429 在登录端点上都是业务结果
  // ============================================================
  describe('credential endpoints', () => {
    it('should not refresh or replay when login itself returns 401', async () => {
      localStorage.setItem('auth_token', 'other-account-token')
      localStorage.setItem('refresh_token', 'other-account-rt')
      mockStore.refresh.mockResolvedValue(true)

      const error = {
        config: { headers: {}, url: '/auth/login' },
        response: {
          status: 401,
          data: { code: 'INVALID_CREDENTIALS', message: '用户名或密码错误', retry_after_seconds: null },
        },
      }

      await expect(responseErrorHandler(error)).rejects.toThrow()

      // 不拿旧 refresh token 去换，也不重放同一个错误密码请求
      expect(mockStore.refresh).not.toHaveBeenCalled()
      expect(mockAxiosInstance).not.toHaveBeenCalled()
      // 其它账号已有的会话不应被一次失败登录清掉
      expect(localStorage.getItem('auth_token')).toBe('other-account-token')
    })

    it('should not treat 423 ACCOUNT_LOCKED as a session expiry', async () => {
      const error = {
        config: { headers: {}, url: '/api/auth/login' },
        response: {
          status: 423,
          data: { code: 'ACCOUNT_LOCKED', message: '账户已临时锁定，请稍后再试', retry_after_seconds: 640 },
          headers: { 'retry-after': '640' },
        },
      }

      await expect(responseErrorHandler(error)).rejects.toThrow()

      expect(mockStore.refresh).not.toHaveBeenCalled()
      expect(mockAxiosInstance).not.toHaveBeenCalled()
    })

    it('should pass 429 through without refresh', async () => {
      const error = {
        config: { headers: {}, url: '/auth/login' },
        response: { status: 429, data: { detail: '请求过于频繁，请稍后再试' }, headers: { 'retry-after': '31' } },
      }

      await expect(responseErrorHandler(error)).rejects.toThrow()

      expect(mockStore.refresh).not.toHaveBeenCalled()
    })
  })
})
