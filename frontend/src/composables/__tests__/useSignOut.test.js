/**
 * 退出登录入口的共享行为。
 *
 * 侧栏 / 移动抽屉 / Admin 底栏以前各写一遍「logout() 再 replace('/login')」，文案与失败
 * 语义都容易漂移。这里锁两件事：顺序（会话还有效时跳 /login 会被 guestOnly 守卫弹回首页）、
 * 以及登出抛错也必须离开旧壳（不能把人卡在原地反复点）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'

const { replace, logout, authState } = vi.hoisted(() => ({
  replace: vi.fn(),
  logout: vi.fn(),
  // 真实 store 才有的进行中状态：这里只需要让按钮知道现在是否 busy
  authState: { loggingOut: false },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: () => authState }))

const { useSignOut } = await import('@/composables/useSignOut')

const Harness = defineComponent({
  setup() {
    const { signOut } = useSignOut()
    return () => h('button', { onClick: () => signOut() }, '退出登录')
  },
})

function mountHarness() {
  return mount(Harness)
}

describe('useSignOut', () => {
  beforeEach(() => {
    replace.mockReset()
    // 真 router 的 replace 始终返回 Promise；mock 成 undefined 会把“假设”当成被测行为
    replace.mockResolvedValue(undefined)
    logout.mockReset()
    authState.loggingOut = false
    authState.logout = logout
  })

  it('先跑完登出再跳登录页：收尾上报要用得上仍然有效的会话', async () => {
    const order = []
    logout.mockImplementation(async () => {
      order.push('logout')
    })
    replace.mockImplementation(async () => {
      order.push('replace')
    })

    await mountHarness().find('button').trigger('click')
    // click handler 是 async：等它把两条 await 都跑完
    await vi.waitFor(() => expect(order).toEqual(['logout', 'replace']))
  })

  it('登出抛错也照样离开旧壳，并把错误吞在入口层（不制造 unhandled rejection）', async () => {
    logout.mockRejectedValue(new Error('store 内部未预期的错误'))

    await mountHarness().find('button').trigger('click')

    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith('/login'))
  })

  it('跳转被取消或短路时不冒成登出失败', async () => {
    logout.mockResolvedValue(undefined)
    replace.mockRejectedValue(new Error('navigation aborted'))

    await mountHarness().find('button').trigger('click')

    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith('/login'))
  })
})
