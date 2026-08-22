/**
 * API Interceptor 测试。
 *
 * 覆盖：
 * - Authorization header 统一注入（request interceptor）
 * - 401 → refresh 成功 → 重放原请求（response interceptor）
 * - 401 → refresh 失败 → clearSession（response interceptor）
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

    it('should not loop when auth refresh request itself gets 401', async () => {
      localStorage.setItem('auth_token', 'old-token')
      localStorage.setItem('refresh_token', 'old-rt')

      const error = {
        config: { headers: {}, url: '/api/auth/refresh', _isRefreshRequest: true },
        response: { status: 401 },
      }

      await expect(responseErrorHandler(error)).rejects.toThrow()

      // 不触发 refresh
      expect(mockStore.refresh).not.toHaveBeenCalled()
      // session 被清理
      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
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
})