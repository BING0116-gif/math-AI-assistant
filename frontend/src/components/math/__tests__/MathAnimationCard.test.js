import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/animations', () => ({
  unwrapAnimation: response => response?.data?.data ?? response?.data,
  animationApi: { get: vi.fn(), cancel: vi.fn(), video: vi.fn() },
}))

import { animationApi } from '@/api/animations'
import MathAnimationCard from '../MathAnimationCard.vue'

describe('MathAnimationCard', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders an in-conversation queued teaching animation', () => {
    animationApi.get.mockReturnValue(new Promise(() => {}))
    const wrapper = mount(MathAnimationCard, { props: { initialJob: {
      job_id: 'job-1', status: 'pending', stage: 'queued',
      teaching_note: '观察割线斜率如何趋近切线斜率。',
    } } })
    expect(wrapper.text()).toContain('动态讲解')
    expect(wrapper.text()).toContain('观察割线斜率')
    expect(wrapper.text()).toContain('文字讲解可以先读')
    wrapper.unmount()
  })

  it('renders a non-blocking fallback', () => {
    const wrapper = mount(MathAnimationCard, { props: { initialJob: {
      job_id: 'job-2', status: 'fallback', stage: 'fallback',
    } } })
    expect(wrapper.text()).toContain('静态讲解')
    expect(wrapper.text()).toContain('文字与静态图仍是完整讲解')
  })
})
