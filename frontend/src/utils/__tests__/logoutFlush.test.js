/**
 * 登出收尾钩子。
 *
 * 真实事故：学习时长的结束上报（POST /learning/activities/{id}/end）在 clearSession() 之后
 * 才被路由跳转触发，请求带着空 Authorization 拿到 401 并被静默 catch，最后一段学习时长丢失。
 * 这里锁定两件事：钩子确实在 token 仍有效时跑完；单个钩子不能拖住或破坏登出。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMock = {
  post: vi.fn(),
  get: vi.fn(),
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
}
vi.mock('@/api', () => ({ default: apiMock, setAuthTokenGetter: vi.fn() }))

const { useAuthStore } = await import('@/stores/authStore')
const { LOGOUT_FLUSH_TIMEOUT_MS, registerLogoutFlush, runLogoutFlushes } = await import('@/utils/logoutFlush')

describe('登出收尾钩子', () => {
  const disposers = []

  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    apiMock.post.mockReset()
  })

  afterEach(() => {
    // flushers 是模块级集合：用例之间必须摘干净，否则后一个用例会收到前一个的钩子
    while (disposers.length) disposers.pop()()
  })

  it('并发执行所有钩子，单个抛错不影响其它钩子', async () => {
    const a = vi.fn()
    const b = vi.fn(() => { throw new Error('boom') })
    const c = vi.fn(async () => { await Promise.resolve(); c.calls++ })
    disposers.push(registerLogoutFlush(a), registerLogoutFlush(b), registerLogoutFlush(c))

    await runLogoutFlushes()

    expect(a).toHaveBeenCalledTimes(1)
    expect(b).toHaveBeenCalledTimes(1)
    expect(c).toHaveBeenCalledTimes(1)
  })

  it('返回的注销函数会把钩子摘掉（组件卸载必须调用，避免闭包跨账号存活）', async () => {
    const fn = vi.fn()
    const off = registerLogoutFlush(fn)
    disposers.push(off)
    off()

    await runLogoutFlushes()

    expect(fn).not.toHaveBeenCalled()
  })

  it('非函数注册被忽略，注销函数依然可用', async () => {
    const off = registerLogoutFlush(null)
    disposers.push(off)

    await expect(runLogoutFlushes()).resolves.toBeUndefined()
    expect(() => off()).not.toThrow()
  })

  it('挂死的钩子不会永久阻塞登出：整体超时后放行', async () => {
    vi.useFakeTimers()
    try {
      disposers.push(registerLogoutFlush(() => new Promise(() => {})))
      const pending = runLogoutFlushes()
      await vi.advanceTimersByTimeAsync(LOGOUT_FLUSH_TIMEOUT_MS)
      await expect(pending).resolves.toBeUndefined()
    } finally {
      vi.useRealTimers()
    }
  })

  it('authStore.logout() 在 clearSession() 之前跑完收尾，上报时 access token 仍有效', async () => {
    const auth = useAuthStore()
    apiMock.post.mockResolvedValueOnce({
      data: { data: { access_token: 'test-at', refresh_token: 'test-rt', user_id: 'u-1', username: 'u-1', role: 'student' } },
    })
    await auth.login({ username: 'u-1', password: 'p' })
    expect(auth.getAccessToken()).toBe('test-at')

    const tokenDuringFlush = []
    disposers.push(registerLogoutFlush(async () => { tokenDuringFlush.push(auth.getAccessToken()) }))

    apiMock.post.mockResolvedValue({ data: { status: 'success' } })
    await auth.logout()

    expect(tokenDuringFlush).toEqual(['test-at'])
    expect(auth.isAuthenticated).toBe(false)
    // 收尾跑完后才轮到后端登出与本地清理
    expect(apiMock.post).toHaveBeenCalledWith('/auth/logout', { refresh_token: 'test-rt' })
  })

  it('收尾抛错也不会阻断本地会话清理', async () => {
    const auth = useAuthStore()
    auth.accessToken = 'at'
    auth.refreshToken = 'rt'
    disposers.push(registerLogoutFlush(() => { throw new Error('network down') }))
    apiMock.post.mockRejectedValue(new Error('logout endpoint unavailable'))

    await auth.logout()

    expect(auth.isAuthenticated).toBe(false)
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('登出进行中的重复调用复用同一任务：/auth/logout 只发一次，后一个 await 也在会话清完后才返回', async () => {
    const auth = useAuthStore()
    auth.accessToken = 'at'
    auth.refreshToken = 'rt'
    let release
    apiMock.post.mockImplementation(() => new Promise((resolve) => { release = resolve }))

    const first = auth.logout()
    const second = auth.logout()
    await Promise.resolve()
    // 进行中的那一次还没清完会话：早退会让调用方拿着有效会话去跳 /login，被 guestOnly 弹回
    expect(auth.isAuthenticated).toBe(true)

    release({ data: { status: 'success' } })
    await Promise.all([first, second])

    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(apiMock.post).toHaveBeenCalledWith('/auth/logout', { refresh_token: 'rt' })
    expect(auth.isAuthenticated).toBe(false)
  })
})
