/**
 * 启动竞态：会话过期那一刻，初始导航还没落地。
 *
 * 这条是用真 vue-router（memory history）复现浏览器实测抓到的失败：
 * main.js 在 mount 之前就发了 GET /auth/me，它的 401 → refresh 401 → clearSession
 * 这条链落地时，DashboardView 的懒加载 chunk 还在飞行中，`useRoute()` 仍是
 * START_LOCATION（meta 为空）。当时那句 `if (!route.meta.requiresAuth) return`
 * 于是把过期吞掉：URL 停在 /dashboard，登录页提示永远不出现；而之后每个 401 的
 * refresh() 都因为 refreshToken 已空而即时返回 false，再没有 true→false 的边沿，
 * watcher 不会第二次触发 —— 一次没跳成就永远不会跳。
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

const { useSessionExpiry } = await import('@/composables/useSessionExpiry')
const { useAuthStore } = await import('@/stores/authStore')

const Subject = defineComponent({
  setup: () => {
    useSessionExpiry()
    return () => h('div')
  },
})
const Dashboard = defineComponent({ render: () => h('p', '看板') })
const Login = defineComponent({ render: () => h('p', '登录') })

/** 可控的懒加载：resolve 之前初始导航一直悬着 */
function deferredLoader(component) {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { loader: () => promise, resolve: () => resolve(component) }
}

describe('被动过期 × 启动竞态', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('初始导航悬在半路时过期：导航落地后仍要补跳登录页并带 expired', async () => {
    const gate = deferredLoader(Dashboard)
    // createMemoryHistory 收的是 base 字符串（不是 initialEntries）：先把历史推到
    // /dashboard，install 时的初始导航才会去解析它
    const history = createMemoryHistory()
    history.push('/dashboard')
    const router = createRouter({
      history,
      routes: [
        { path: '/dashboard', name: 'Dashboard', component: gate.loader, meta: { requiresAuth: true } },
        { path: '/login', name: 'Login', component: Login, meta: { guestOnly: true } },
      ],
    })

    const auth = useAuthStore()
    auth.accessToken = 'garbage.access.token'
    auth.refreshToken = 'garbage.refresh.token'
    auth.currentUser = { user_id: 'u-1', username: 'u-1', role: 'student' }

    mount(Subject, { global: { plugins: [router] } })

    // 此刻初始导航尚未确认：route 还是启动位置，matched 空、meta 也是空的
    expect(router.currentRoute.value.matched).toHaveLength(0)

    const ready = router.isReady().catch(() => null)
    auth.clearSession()
    await nextTick()
    await flushPromises()

    // 过期发在导航落地之前：当时那一版实现就是在这里把过期吞掉，URL 停在原地
    expect(router.currentRoute.value.path).not.toBe('/login')

    // 懒加载 chunk 落地，初始导航完成
    gate.resolve()
    await ready
    await nextTick()
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query).toMatchObject({
      redirect: expect.stringContaining('/dashboard'),
      expired: '1',
    })
    // 一次性标记不能留在地址栏里等下一次刷新
    expect(router.currentRoute.value.query.redirect).not.toContain('expired')
  })

  /**
   * 同一个竞态的另一个形状：会话在 watcher 建立之前就被判死。
   * 这里没有 true→false 的边沿可抓，只能靠 store 上那份“曾被判死”的标记让
   * composable 在建立时就补上闩。（真实应用里路由守卫会先赢下这次导航，此时人仍然
   * 会落到 /login，只是靠 LoginView 读同一个标记来补提示。）
   */
  it('边沿错过了（watcher 建立前已判死）：建立时补闩，导航落地后照样带 expired 跳', async () => {
    const gate = deferredLoader(Dashboard)
    const history = createMemoryHistory()
    history.push('/dashboard')
    const router = createRouter({
      history,
      routes: [
        { path: '/dashboard', name: 'Dashboard', component: gate.loader, meta: { requiresAuth: true } },
        { path: '/login', name: 'Login', component: Login, meta: { guestOnly: true } },
      ],
    })

    const auth = useAuthStore()
    auth.accessToken = 'garbage.access.token'
    auth.refreshToken = 'garbage.refresh.token'
    auth.currentUser = { user_id: 'u-1', username: 'u-1', role: 'student' }

    // mount 之前就走完 401 → refresh 401 → 判死：watcher 建立时已经是 false
    auth.clearSession({ reason: 'expired' })
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.sessionExpired).toBe(true)

    mount(Subject, { global: { plugins: [router] } })

    gate.resolve()
    await router.isReady().catch(() => null)
    await nextTick()
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query).toMatchObject({ expired: '1' })
  })
})
