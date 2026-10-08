/**
 * 退出登录的可交互面（按钮态 + 旧壳遮罩）。
 *
 * 登出要多等一次网络往返（收尾上报 + /auth/logout），这段时间旧壳还在屏幕上：
 * 按钮必须变成「正在退出…」并禁用，遮罩必须出现并在结束后消失。
 * 这两条都是用户能直接感知的契约，写在这里而不是靠浏览器目测。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const { replace, apiMock } = vi.hoisted(() => ({
  replace: vi.fn(),
  apiMock: {
    post: vi.fn(),
    get: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))
vi.mock('@/api', () => ({ default: apiMock, setAuthTokenGetter: vi.fn() }))

const SignOutButton = (await import('@/components/shell/SignOutButton.vue')).default
const SignOutOverlay = (await import('@/components/shell/SignOutOverlay.vue')).default
const { useAuthStore } = await import('@/stores/authStore')
const { useUiStore } = await import('@/stores/uiStore')

const Stage = defineComponent({
  setup: () => () => h('div', [
    h(SignOutButton, { class: 'account-switch' }),
    h(SignOutOverlay),
  ]),
})

/** 遮罩 teleport 到 body（要能盖住同样是 teleport 的移动抽屉），因此从 body 查询。 */
const overlayInBody = () => document.body.querySelector('.sign-out-overlay')

function login() {
  const auth = useAuthStore()
  auth.accessToken = 'at-live'
  auth.refreshToken = 'rt-live'
  auth.currentUser = { user_id: 'u-1', username: 'u-1', role: 'student' }
  return auth
}

function pendingPost() {
  let release
  apiMock.post.mockImplementation(() => new Promise((resolve) => { release = resolve }))
  return () => release({ data: { status: 'success' } })
}

describe('退出登录按钮与遮罩', () => {
  let wrapper

  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    replace.mockReset().mockResolvedValue(undefined)
    apiMock.post.mockReset()
    login()
    wrapper = mount(Stage)
  })

  afterEach(() => {
    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('空闲态：文案是「退出登录」，可点、无遮罩，class 透传到按钮根节点', () => {
    const button = wrapper.find('button')
    expect(button.text()).toBe('退出登录')
    expect(button.attributes('disabled')).toBeUndefined()
    expect(button.attributes('aria-busy')).toBe('false')
    expect(button.classes()).toContain('account-switch')
    expect(overlayInBody()).toBeNull()
  })

  it('登出往返期间：按钮变「正在退出…」并禁用，遮罩以 role=status 出现', async () => {
    const release = pendingPost()
    await wrapper.find('button').trigger('click')
    await flushPromises()

    const button = wrapper.find('button')
    expect(button.text()).toBe('正在退出…')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-busy')).toBe('true')

    const overlay = overlayInBody()
    expect(overlay).not.toBeNull()
    expect(overlay.getAttribute('role')).toBe('status')
    expect(overlay.getAttribute('aria-busy')).toBe('true')
    expect(overlay.textContent).toContain('正在退出登录')

    release()
    await flushPromises()
    expect(overlayInBody()).toBeNull()
    expect(wrapper.find('button').text()).toBe('退出登录')
    expect(useAuthStore().isAuthenticated).toBe(false)
    expect(replace).toHaveBeenCalledWith('/login')
  })

  it('登出期间重复触发也不提前跳转、不把 /auth/logout 跑两遍', async () => {
    // 跳转那一刻的会话状态才是关键不变量：会话还有效时跳 /login 会被 guestOnly 守卫弹回首页
    const authedAtReplace = []
    replace.mockImplementation(() => {
      authedAtReplace.push(useAuthStore().isAuthenticated)
      return Promise.resolve()
    })
    const release = pendingPost()
    const button = wrapper.find('button')
    await button.trigger('click')
    await flushPromises()
    expect(button.attributes('disabled')).toBeDefined()

    // 绕过按钮的禁用态直接再走两次：store 层的任务复用必须接住它
    const auth = useAuthStore()
    const second = auth.logout()
    const third = auth.logout()
    await flushPromises()
    expect(replace).not.toHaveBeenCalled()

    release()
    await Promise.all([second, third])
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(apiMock.post).toHaveBeenCalledWith('/auth/logout', { refresh_token: 'rt-live' })
    expect(authedAtReplace.length).toBeGreaterThan(0)
    expect(authedAtReplace.every((stillAuthenticated) => stillAuthenticated === false)).toBe(true)
  })

  it('后端登出抛错也要回到空闲态：不能把用户永久锁在「正在退出…」', async () => {
    apiMock.post.mockRejectedValue(new Error('logout endpoint unavailable'))
    await wrapper.find('button').trigger('click')
    await flushPromises()

    // 进行中的是「登出流程」，标志位只有一个来源：uiStore.signingOut
    expect(useUiStore().signingOut).toBe(false)
    expect(useAuthStore().isAuthenticated).toBe(false)
    expect(overlayInBody()).toBeNull()
    expect(wrapper.find('button').text()).toBe('退出登录')
    expect(replace).toHaveBeenCalledWith('/login')
  })
})
