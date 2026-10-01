/**
 * Protected Route Guard 测试。
 *
 * 覆盖：
 * - 未认证 + requiresAuth route → redirect to standalone login page
 * - 已认证 + requiresAuth route → 正常进入
 * - 公开路由不受影响
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/authStore'

// 使用同步组件避免懒加载引入的异步问题
const HomeView = { template: '<div>Home</div>' }
const ChatView = { template: '<div>Chat</div>' }
const ErrorBookView = { template: '<div>ErrorBook</div>' }
const DashboardView = { template: '<div>Dashboard</div>' }

describe('Protected Route Guard', () => {
  let router

  beforeEach(() => {
    // 每个测试独立 Pinia 实例
    setActivePinia(createPinia())
    localStorage.clear()

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'Home', component: HomeView },
        { path: '/login', name: 'Login', component: HomeView },
        { path: '/chat', name: 'Chat', component: ChatView },
        {
          path: '/error-book',
          name: 'ErrorBook',
          component: ErrorBookView,
          meta: { title: '错题本', requiresAuth: true },
        },
        {
          path: '/dashboard',
          name: 'Dashboard',
          component: DashboardView,
          meta: { title: '学习看板', requiresAuth: true },
        },
      ],
    })

    // 注入与生产代码一致的 auth guard
    router.beforeEach((to) => {
      if (to.meta.title) {
        document.title = to.meta.title
      }
      if (to.meta.requiresAuth) {
        const authStore = useAuthStore()
        if (!authStore.isAuthenticated) {
          return { path: '/login', query: { redirect: to.fullPath } }
        }
      }
    })
  })

  // ============================================================
  // Unauthenticated
  // ============================================================
  describe('unauthenticated', () => {
    it('should redirect to the standalone login page when accessing a protected route', async () => {
      await router.push('/error-book')

      expect(router.currentRoute.value.path).toBe('/login')
      expect(router.currentRoute.value.query.redirect).toBe('/error-book')
    })

    it('should redirect to home for any requiresAuth route', async () => {
      await router.push('/dashboard')
      expect(router.currentRoute.value.path).toBe('/login')
      expect(router.currentRoute.value.query.redirect).toBe('/dashboard')
    })
  })

  // ============================================================
  // Authenticated
  // ============================================================
  describe('authenticated', () => {
    it('should allow navigation to a protected route', async () => {
      const authStore = useAuthStore()
      localStorage.setItem('auth_token', 'test-token')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
      authStore.restoreSession()

      await router.push('/dashboard')

      expect(router.currentRoute.value.path).toBe('/dashboard')
    })

    it('should allow navigation to a protected route with error-book', async () => {
      const authStore = useAuthStore()
      localStorage.setItem('auth_token', 'test-token')
      localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
      authStore.restoreSession()

      await router.push('/error-book')

      expect(router.currentRoute.value.path).toBe('/error-book')
    })
  })

  // ============================================================
  // Public routes are always accessible
  // ============================================================
  describe('public routes', () => {
    it('should allow access to home without auth', async () => {
      await router.push('/')
      expect(router.currentRoute.value.path).toBe('/')
    })

    it('should allow access to chat without auth', async () => {
      await router.push('/chat')
      expect(router.currentRoute.value.path).toBe('/chat')
    })
  })
})
