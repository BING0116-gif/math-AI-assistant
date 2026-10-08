/**
 * 被动会话过期的落地契约。
 *
 * 保护的是四件容易被改坏的事：
 * 1. 会话被判死后必须真的离开旧壳（守卫只在导航时跑，不跳就一直停在 401 页面上）；
 * 2. 跳转要带 redirect（回得到原页面）与一次性的 expired 标记（说清是过期不是失败）；
 * 3. 主动登出不能被抓过期这条路二次跳转 —— 遮罩与导航归 useSignOut 所有；
 * 4. 公开页（无 requiresAuth）不因过期被踢走。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const { replace, route } = vi.hoisted(() => ({
  replace: vi.fn(),
  // 可变的路由替身：这些用例关心的就是「当前这条路由是什么」
  route: { path: '/chat/s-1', fullPath: '/chat/s-1', meta: { requiresAuth: true }, query: {} },
}))
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace }),
}))

const { useSessionExpiry } = await import('@/composables/useSessionExpiry')
const { useAuthStore } = await import('@/stores/authStore')
const { useUiStore } = await import('@/stores/uiStore')

const Subject = defineComponent({
  setup: () => {
    useSessionExpiry()
    return () => h('div')
  },
})

function login(userId = 'u-1') {
  const auth = useAuthStore()
  auth.accessToken = 'at-live'
  auth.refreshToken = 'rt-live'
  auth.currentUser = { user_id: userId, username: userId, role: 'student' }
  return auth
}

function setRoute(path, meta) {
  route.path = path
  route.fullPath = path
  route.meta = meta
}

describe('useSessionExpiry', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    replace.mockReset().mockResolvedValue(undefined)
    setRoute('/chat/s-1', { requiresAuth: true })
  })

  it('受保护页上会话被判死：跳登录页并带 redirect 与一次性 expired 标记', async () => {
    const auth = login()
    mount(Subject)

    // 被动路径：401 → refresh 失败 → store 的 clearSession()（没有走过 useSignOut）
    auth.clearSession()
    await nextTick()
    await flushPromises()

    expect(replace).toHaveBeenCalledTimes(1)
    expect(replace).toHaveBeenCalledWith({
      path: '/login',
      query: { redirect: '/chat/s-1', expired: '1' },
    })
  })

  it('一开始就没登录：清一次会话不算过期，不该把人扔向登录页', async () => {
    mount(Subject)
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)

    auth.clearSession()
    await nextTick()
    await flushPromises()

    expect(replace).not.toHaveBeenCalled()
  })

  it('主动登出（signingOut 为真）时不插手：跳转与遮罩归 useSignOut', async () => {
    const auth = login()
    const ui = useUiStore()
    mount(Subject)

    ui.signingOut = true
    auth.clearSession()
    await nextTick()
    await flushPromises()

    expect(replace).not.toHaveBeenCalled()
  })

  it('公开页（无 requiresAuth）不因过期被踢走：知识目录不看会话也能读', async () => {
    setRoute('/knowledge', {})
    const auth = login()
    mount(Subject)

    auth.clearSession()
    await nextTick()
    await flushPromises()

    expect(replace).not.toHaveBeenCalled()
  })

  it('重新登录后再次过期仍然会跳（不是一次性闩）', async () => {
    const auth = login()
    mount(Subject)

    auth.clearSession()
    await nextTick()
    await flushPromises()
    expect(replace).toHaveBeenCalledTimes(1)

    login('u-2')
    await nextTick()
    setRoute('/dashboard', { requiresAuth: true })
    auth.clearSession()
    await nextTick()
    await flushPromises()

    expect(replace).toHaveBeenCalledTimes(2)
    expect(replace.mock.calls[1][0]).toMatchObject({
      path: '/login',
      query: { redirect: '/dashboard', expired: '1' },
    })
  })

  it('导航被守卫取消或判定为重复时只吞掉，不冒成 unhandled rejection', async () => {
    replace.mockRejectedValue(new Error('Navigation aborted'))
    const auth = login()
    mount(Subject)

    auth.clearSession()
    await nextTick()
    await flushPromises()

    expect(replace).toHaveBeenCalledTimes(1)
    // 走到这里没有未捕获的 rejection：mock 的拒绝已在 composable 内被 catch
  })
})
