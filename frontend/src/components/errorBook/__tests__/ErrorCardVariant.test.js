import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const push = vi.fn()
const createVariantSession = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/errorBook', () => ({ createVariantSession }))
vi.mock('element-plus', () => ({ ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn() } }))

const { default: ErrorCard } = await import('../ErrorCard.vue')

const baseError = {
  id: 'error-1', question: '已知 $f(x)=x^2$，求 $f(2)$', question_type: 'numeric_fill',
  categories: ['函数'], correct_answer: '4', review_state: 'new',
}

describe('ErrorCard variant action', () => {
  it('disables generation when the server marks the source unsupported', () => {
    const wrapper = mount(ErrorCard, { props: { error: { ...baseError, variant_supported: false } } })
    expect(wrapper.get('button.variant').attributes('disabled')).toBeDefined()
  })

  it('shows loading and navigates to the verified practice session', async () => {
    let resolve
    createVariantSession.mockReturnValueOnce(new Promise(done => { resolve = done }))
    const wrapper = mount(ErrorCard, { props: { error: { ...baseError, variant_supported: true } } })
    await wrapper.get('button.variant').trigger('click')
    expect(wrapper.get('button.variant').text()).toContain('正在生成')
    resolve({ data: { data: { session_id: 'session-1' } } })
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/apply/practice/sessions/session-1')
  })
})
