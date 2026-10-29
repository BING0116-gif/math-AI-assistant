import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentComposer from '../AgentComposer.vue'

describe('AgentComposer offline mode', () => {
  it('should disable all inputs when disabled prop is true', () => {
    const wrapper = mount(AgentComposer, {
      props: {
        disabled: true,
        disabledReason: 'AI 功能当前不可用',
      },
    })

    // Check that textarea is disabled
    const textarea = wrapper.find('textarea')
    expect(textarea.exists()).toBe(true)
    expect(textarea.attributes('disabled')).toBeDefined()

    // Check that image upload button is disabled
    const imageBtn = wrapper.find('.agent-composer__tool-btn[aria-label="添加图片"]')
    expect(imageBtn.attributes('disabled')).toBeDefined()

    // Check that send button is disabled
    const sendBtn = wrapper.find('.agent-composer__send-btn')
    expect(sendBtn.attributes('disabled')).toBeDefined()

    // Check that offline banner is displayed
    const banner = wrapper.find('.agent-composer__offline-banner')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('AI 功能当前不可用')
  })

  it('should not allow send when disabled', async () => {
    const emitSpy = vi.fn()
    const wrapper = mount(AgentComposer, {
      props: {
        disabled: true,
      },
    })

    // Set some text and try to send
    wrapper.vm.text = 'test message'
    wrapper.vm.handleSend()

    // Should not emit when disabled
    expect(wrapper.emitted('send')).toBeUndefined()
  })

  it('should allow all interactions when disabled is false', () => {
    const wrapper = mount(AgentComposer, {
      props: {
        disabled: false,
      },
    })

    // Check that textarea is not disabled
    const textarea = wrapper.find('textarea')
    expect(textarea.attributes('disabled')).toBeUndefined()

    // Check that offline banner is not displayed
    const banner = wrapper.find('.agent-composer__offline-banner')
    expect(banner.exists()).toBe(false)
  })

  it('should show custom disabled reason when provided', () => {
    const wrapper = mount(AgentComposer, {
      props: {
        disabled: true,
        disabledReason: 'AI 服务未配置 API 密钥',
      },
    })

    const banner = wrapper.find('.agent-composer__offline-banner')
    expect(banner.text()).toContain('AI 服务未配置 API 密钥')
  })

  it('shows estimated context budget details when the ring is opened', async () => {
    const wrapper = mount(AgentComposer, {
      props: { contextUsage: { used_tokens_estimated: 1000, budget_tokens: 4000, remaining_tokens_estimated: 3000 } },
    })
    const button = wrapper.find('.agent-composer__usage-btn')
    expect(button.attributes('aria-label')).toContain('25%')
    await button.trigger('click')
    expect(wrapper.find('.agent-composer__usage-popover').text()).toContain('约 1.0k token 已用 / 4.0k token 预算')
    expect(wrapper.find('.agent-composer__usage-popover').text()).toContain('估算')
  })

  it('shows compression progress beside the ring and in its details', async () => {
    const wrapper = mount(AgentComposer, {
      props: { contextUsage: { used_tokens_estimated: 3000, budget_tokens: 4000, remaining_tokens_estimated: 1000, compression_status: 'compressing' } },
    })
    expect(wrapper.find('.agent-composer__compression-label').text()).toContain('正在压缩上下文')
    expect(wrapper.find('.agent-composer__usage-ring--active').exists()).toBe(true)
    await wrapper.find('.agent-composer__usage-btn').trigger('click')
    expect(wrapper.find('.agent-composer__usage-popover').text()).toContain('正在压缩上下文')
  })
})
