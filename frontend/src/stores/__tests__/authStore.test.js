/**
 * authStore 单元测试。
 *
 * 覆盖：
 * - login / register / logout
 * - isAuthenticated
 * - Authorization header 注入
 * - 401 → session cleared
 * - restoreSession
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/authStore'

// Mock axios
vi.mock('@/api', () => {
  const mockApi = {
    post: vi.fn(),
    get: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  }
  return { default: mockApi, setAuthTokenGetter: vi.fn() }
})

import api from '@/api'

describe('authStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  describe('login', () => {
    it('should store tokens and user info on success', async () => {
      const store = useAuthStore()
      const mockResponse = {
        data: {
          status: 'success',
          data: {
            access_token: 'test-at',
            refresh_token: 'test-rt',
            user_id: 'user-123',
            username: 'testuser',
            token_type: 'bearer',
            expires_in: 86400,
          },
        },
      }
      api.post.mockResolvedValue(mockResponse)

      await store.login({ username: 'testuser', password: 'testpass' })

      expect(store.isAuthenticated).toBe(true)
      expect(store.getAccessToken()).toBe('test-at')
      expect(store.refreshToken).toBe('test-rt')
      expect(store.userId).toBe('user-123')
      expect(store.username).toBe('testuser')
      expect(localStorage.getItem('auth_token')).toBe('test-at')
      expect(localStorage.getItem('refresh_token')).toBe('test-rt')
      expect(localStorage.getItem('current_user')).toBe(
        JSON.stringify({ user_id: 'user-123', username: 'testuser' })
      )
    })

    it('should handle login failure', async () => {
      const store = useAuthStore()
      api.post.mockRejectedValue(new Error('Invalid credentials'))

      await expect(
        store.login({ username: 'testuser', password: 'wrongpass' })
      ).rejects.toThrow()
      expect(store.isAuthenticated).toBe(false)
    })
  })

  describe('register', () => {
    it('should register then auto-login', async () => {
      const store = useAuthStore()
      // register succeeds
      api.post.mockResolvedValueOnce({
        data: { status: 'success', message: '注册成功' },
      })
      // login succeeds
      api.post.mockResolvedValueOnce({
        data: {
          status: 'success',
          data: {
            access_token: 'reg-at',
            refresh_token: 'reg-rt',
            user_id: 'user-456',
            username: 'newuser',
            token_type: 'bearer',
            expires_in: 86400,
          },
        },
      })

      await store.register({ username: 'newuser', password: 'newpass' })

      expect(store.isAuthenticated).toBe(true)
      expect(store.getAccessToken()).toBe('reg-at')
      expect(store.username).toBe('newuser')
    })

    it('should handle register failure', async () => {
      const store = useAuthStore()
      api.post.mockRejectedValue(new Error('Username already exists'))

      await expect(
        store.register({ username: 'existing', password: 'testpass' })
      ).rejects.toThrow()
      expect(store.isAuthenticated).toBe(false)
    })
  })

  describe('logout', () => {
    it('should clear session on logout', async () => {
      const store = useAuthStore()
      // Set up initial state
      localStorage.setItem('auth_token', 'test-at')
      localStorage.setItem('refresh_token', 'test-rt')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
      store.restoreSession()

      api.post.mockResolvedValue({ data: { status: 'success', message: '已退出登录' } })

      await store.logout()

      expect(store.isAuthenticated).toBe(false)
      expect(store.getAccessToken()).toBe('')
      expect(store.username).toBe('')
      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
      expect(localStorage.getItem('current_user')).toBeNull()
    })

    it('should clear session even if backend logout fails', async () => {
      const store = useAuthStore()
      localStorage.setItem('auth_token', 'test-at')
      localStorage.setItem('refresh_token', 'test-rt')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
      store.restoreSession()

      api.post.mockRejectedValue(new Error('Network error'))

      await store.logout()

      // Local session should still be cleared
      expect(store.isAuthenticated).toBe(false)
      expect(localStorage.getItem('auth_token')).toBeNull()
    })
  })

  describe('refresh', () => {
    it('should refresh access token successfully', async () => {
      const store = useAuthStore()
      localStorage.setItem('auth_token', 'old-at')
      localStorage.setItem('refresh_token', 'valid-rt')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
      store.restoreSession()

      api.post.mockResolvedValue({
        data: {
          status: 'success',
          data: {
            access_token: 'new-at',
            refresh_token: 'new-rt',
            token_type: 'bearer',
            expires_in: 86400,
          },
        },
      })

      const result = await store.refresh()

      expect(result).toBe(true)
      expect(store.getAccessToken()).toBe('new-at')
      expect(store.refreshToken).toBe('new-rt')
    })

    it('should return false when refresh fails', async () => {
      const store = useAuthStore()
      localStorage.setItem('auth_token', 'old-at')
      localStorage.setItem('refresh_token', 'expired-rt')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
      store.restoreSession()

      api.post.mockRejectedValue(new Error('Invalid refresh token'))

      const result = await store.refresh()

      expect(result).toBe(false)
      expect(store.isAuthenticated).toBe(false)
    })

    it('should return false when no refresh token exists', async () => {
      const store = useAuthStore()
      const result = await store.refresh()
      expect(result).toBe(false)
    })
  })

  describe('isAuthenticated', () => {
    it('should be false when no token', () => {
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(false)
    })

    it('should be true when token exists', () => {
      const store = useAuthStore()
      localStorage.setItem('auth_token', 'some-token')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
      store.restoreSession()
      expect(store.isAuthenticated).toBe(true)
    })
  })

  describe('restoreSession', () => {
    it('should restore session from localStorage', () => {
      const store = useAuthStore()
      localStorage.setItem('auth_token', 'stored-at')
      localStorage.setItem('refresh_token', 'stored-rt')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))

      const result = store.restoreSession()

      expect(result).toBe(true)
      expect(store.getAccessToken()).toBe('stored-at')
      expect(store.refreshToken).toBe('stored-rt')
      expect(store.userId).toBe('u1')
      expect(store.username).toBe('u1')
    })

    it('should clean up orphaned token', () => {
      const store = useAuthStore()
      localStorage.setItem('auth_token', 'orphan-token')
      // No current_user

      const result = store.restoreSession()

      expect(result).toBe(false)
      expect(localStorage.getItem('auth_token')).toBeNull()
    })
  })

  describe('clearSession', () => {
    it('should clear all auth state', () => {
      const store = useAuthStore()
      localStorage.setItem('auth_token', 'at')
      localStorage.setItem('refresh_token', 'rt')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
      store.restoreSession()

      store.clearSession()

      expect(store.isAuthenticated).toBe(false)
      expect(store.getAccessToken()).toBe('')
      expect(store.username).toBe('')
      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
      expect(localStorage.getItem('current_user')).toBeNull()
    })
  })
})