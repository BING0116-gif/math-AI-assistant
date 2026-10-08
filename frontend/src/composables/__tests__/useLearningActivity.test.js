/**
 * 学习时长上报与登出时序的回归。
 *
 * 修掉的缺陷：结束上报（POST /learning/activities/{id}/end）原本在 clearSession() 之后才被
 * 路由跳转触发，请求带着空 Authorization 拿到 401 并被 `.catch(() => {})` 吞掉，最后一段
 * 学习时长静默丢失。现在 authStore.logout() 会先跑登出收尾钩子，再清本地会话。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick, reactive } from 'vue'

const mocks = vi.hoisted(() => ({
  route: null,
  startLearningActivity: vi.fn(),
  heartbeatLearningActivity: vi.fn(),
  endLearningActivity: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => mocks.route }))
vi.mock('@/api/learning', () => ({
  startLearningActivity: (...args) => mocks.startLearningActivity(...args),
  heartbeatLearningActivity: (...args) => mocks.heartbeatLearningActivity(...args),
  endLearningActivity: (...args) => mocks.endLearningActivity(...args),
}))

const apiMock = {
  post: vi.fn(),
  get: vi.fn(),
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
}
vi.mock('@/api', () => ({ default: apiMock, setAuthTokenGetter: vi.fn() }))

const { useLearningActivity } = await import('@/composables/useLearningActivity')
const { useAuthStore } = await import('@/stores/authStore')

const Host = defineComponent({
  setup() {
    useLearningActivity()
    return () => h('div')
  },
})

/** 记录每次结束上报那一刻的 access token：用来证明上报发生在会话清理之前。 */
let tokenAtEnd

// 登出钩子是模块级集合：用例里挂载过的组件必须卸载，否则上一个用例的闭包会在
// 下一个用例的 logout() 里再发一次 end，把计数打脏（本身就是钩子泄漏的同款形状）。
const mounted = []

async function mountAt(path, params = {}) {
  mocks.route = reactive({ path, fullPath: path, params })
  const wrapper = mount(Host)
  await flushPromises()
  mounted.push(wrapper)
  return wrapper
}

function unmount(wrapper) {
  const index = mounted.indexOf(wrapper)
  if (index >= 0) mounted.splice(index, 1)
  wrapper.unmount()
}

function login(userId = 'u-1') {
  const auth = useAuthStore()
  auth.accessToken = 'at-live'
  auth.refreshToken = 'rt-1'
  auth.currentUser = { user_id: userId, username: userId, role: 'student' }
  return auth
}

async function navigate(path) {
  mocks.route.path = path
  mocks.route.fullPath = path
  await nextTick()
  await flushPromises()
}

describe('学习时长上报与登出时序', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
    tokenAtEnd = []
    // /learning/activities* 的 response_model 是 ActivityItem 本体（不带 {status,data} 外壳），
    // 生产代码直接读 body.id，mock 必须保持同一形状，否则 activity 根本开不起来。
    mocks.startLearningActivity.mockResolvedValue({ data: { id: 'activity-1', status: 'active' } })
    mocks.endLearningActivity.mockImplementation(async () => {
      tokenAtEnd.push(useAuthStore().accessToken)
      return { data: { id: 'activity-1', status: 'ended' } }
    })
    mocks.heartbeatLearningActivity.mockResolvedValue({ data: {} })
    apiMock.post.mockResolvedValue({ data: { status: 'success' } })
  })

  afterEach(() => {
    while (mounted.length) mounted.pop().unmount()
  })

  it('挂载时按当前路由开一条 activity', async () => {
    login()
    await mountAt('/chat/s-1', { chatId: 's-1' })

    expect(mocks.startLearningActivity).toHaveBeenCalledTimes(1)
    expect(mocks.startLearningActivity.mock.calls[0][0]).toMatchObject({
      context_type: 'chat',
      context_id: 's-1',
    })
  })

  it('登出时先结束 activity（此刻 access token 仍有效），且只结束一次', async () => {
    const auth = login()
    await mountAt('/chat/s-1')

    await auth.logout()
    expect(tokenAtEnd).toEqual(['at-live'])
    expect(auth.isAuthenticated).toBe(false)

    // 登出后路由会跳到 /login，触发 fullPath watch 里的第二次 stop：不得重复上报
    await navigate('/login')
    await flushPromises()

    expect(mocks.endLearningActivity).toHaveBeenCalledTimes(1)
  })

  it('会话已被清理（被动过期路径）时不再发无鉴权的结束请求', async () => {
    const auth = login()
    await mountAt('/chat/s-1')

    // 被动过期：拦截器现在也走 store 的 clearSession（会话失效只有一个出口），组件还没卸载
    auth.clearSession()
    await navigate('/knowledge/graph')

    // 契约（不是巧合）：此刻 access token 已死，end 必 401，发一条被吃掉的 401 只会把
    // “时长丢了”伪装成“网络抽风”。心跳已按间隔落库，丢失上限就是一个心跳间隔；
    // 本轮明确选择**不跨登录补报**（要补得改服务端语义）。
    expect(mocks.endLearningActivity).not.toHaveBeenCalled()
    // 未登录状态也不该再开新的 activity
    expect(mocks.startLearningActivity).toHaveBeenCalledTimes(1)
  })

  it('同页换账号时上一个账号的钩子不会残留（卸载即注销）', async () => {
    const auth = login('u-a')
    const wrapper = await mountAt('/chat/s-1')
    unmount(wrapper)
    expect(mocks.endLearningActivity).toHaveBeenCalledTimes(1)

    // 新账号登录再登出：旧闭包已被注销，不该再收到 end 调用
    login('u-b')
    tokenAtEnd = []
    await auth.logout()

    expect(mocks.endLearningActivity).toHaveBeenCalledTimes(1)
    expect(tokenAtEnd).toEqual([])
  })

  it('切到非学习路由会结束上一条 activity 并不再开新的', async () => {
    login()
    await mountAt('/chat/s-1')

    await navigate('/profile')

    expect(mocks.endLearningActivity).toHaveBeenCalledTimes(1)
    expect(mocks.startLearningActivity).toHaveBeenCalledTimes(1)
  })
})
