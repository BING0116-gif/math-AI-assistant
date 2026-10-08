/**
 * 登录页的「登录已过期」提示。
 *
 * 被动过期跳过来时，会话是服务端判死的，不是用户自己退的，也不是他密码输错。
 * 不写清楚的话，凭空变空的表单 + 突然消失的原页面会被读成又一次登录失败。
 * 这条提示是一次性的：只认 ?expired=1，直接访问 /login 不该显示它。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const { route, replace } = vi.hoisted(() => ({
  route: { query: {}, path: '/login', fullPath: '/login', meta: {} },
  replace: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace }),
}))

const LoginView = (await import('@/views/LoginView.vue')).default

function mountLogin(query = {}) {
  route.query = query
  return mount(LoginView, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

describe('LoginView 过期提示', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    replace.mockReset()
  })

  it('带 ?expired=1 时显示 role=status 的过期提示', () => {
    const wrapper = mountLogin({ expired: '1', redirect: '/chat/s-1' })
    const notice = wrapper.find('[role="status"].form-notice')

    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain('登录已过期')
    // 过期不是错误：不能借用告警色的 role=alert，否则用户会以为是自己输错了
    expect(wrapper.find('.form-error').exists()).toBe(false)
  })

  it('直接访问登录页不显示过期提示', () => {
    const wrapper = mountLogin({})
    expect(wrapper.find('.form-notice').exists()).toBe(false)
  })
})
