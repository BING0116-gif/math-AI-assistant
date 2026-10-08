/**
 * 生产路由守卫回归。
 *
 * 历史版本在这里用 createRouter + 内联 routes/guard 复制了一份"和看起来一样的"逻辑，
 * 于是 router/index.js 里的守卫改错了也不会有任何测试变红 —— 属于伪覆盖。
 * 现在直接 import 生产 router：路由表、meta 标记、guestOnly 与 requiresAdmin 分支都由真实模块提供。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import router from '@/router'
import { useAuthStore } from '@/stores/authStore'

// 中立起点：/knowledge 在生产路由表里是公开页，既不会触发登录重定向，也不会与任何断言目标同路径
// （vue-router 对"导航到当前路由"会直接短路，守卫不执行，那样断言就会假通过）。
const NEUTRAL_PATH = '/knowledge'

function authenticateAs(user) {
  localStorage.setItem('auth_token', 'test-token')
  localStorage.setItem('current_user', JSON.stringify(user))
  useAuthStore().restoreSession()
}

describe('生产路由守卫', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    localStorage.clear()
    if (router.currentRoute.value.path !== NEUTRAL_PATH) {
      await router.replace(NEUTRAL_PATH)
    }
  })

  describe('未认证', () => {
    it('受保护页面跳到独立登录页并记住原地址', async () => {
      await router.push('/error-book')
      expect(router.currentRoute.value.path).toBe('/login')
      expect(router.currentRoute.value.query.redirect).toBe('/error-book')
    })

    it('看板同样受保护', async () => {
      await router.push('/dashboard')
      expect(router.currentRoute.value.path).toBe('/login')
      expect(router.currentRoute.value.query.redirect).toBe('/dashboard')
    })

    it('首页入口本身也是受保护路由', async () => {
      await router.push('/')
      expect(router.currentRoute.value.path).toBe('/login')
      expect(router.currentRoute.value.query.redirect).toBe('/')
    })

    it('知识目录是公开页，未登录也能进', async () => {
      await router.push('/knowledge')
      expect(router.currentRoute.value.path).toBe(NEUTRAL_PATH)
    })

    it('登录后再访问受保护页面可正常进入', async () => {
      authenticateAs({ user_id: 'u1', username: 'u1', role: 'student' })
      await router.push('/dashboard')
      expect(router.currentRoute.value.path).toBe('/dashboard')
    })
  })

  describe('角色边界', () => {
    it('学生访问后台被挡回首页并带上错误标记', async () => {
      authenticateAs({ user_id: 'u1', username: 'u1', role: 'student' })
      await router.push('/admin')
      expect(router.currentRoute.value.path).toBe('/')
      expect(router.currentRoute.value.query.error).toBe('admin_required')
    })

    it('管理员可以进后台', async () => {
      authenticateAs({ user_id: 'a1', username: 'admin', role: 'admin' })
      await router.push('/admin')
      expect(router.currentRoute.value.path).toBe('/admin')
    })
  })

  describe('guestOnly', () => {
    it('已登录学生停在登录页会被送回首页', async () => {
      authenticateAs({ user_id: 'u1', username: 'u1', role: 'student' })
      await router.push('/login')
      expect(router.currentRoute.value.path).toBe('/')
    })

    it('已登录管理员会被送进后台', async () => {
      authenticateAs({ user_id: 'a1', username: 'admin', role: 'admin' })
      await router.push('/login')
      expect(router.currentRoute.value.path).toBe('/admin')
    })
  })

  it('页面标题由生产路由 meta 写入 document.title', async () => {
    await router.push('/error-book')
    expect(document.title).toBe('登录 - 数学AI助手')
  })
})
