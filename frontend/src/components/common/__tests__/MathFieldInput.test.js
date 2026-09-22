import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// jsdom 下不真正加载 MathLive：默认 mock 为空模块（import 成功但元素未注册 → 降级 input）
vi.mock('mathlive', () => ({}))

const { default: MathFieldInput } = await import('../MathFieldInput.vue')

function ensureMathFieldStub() {
  if (!globalThis.customElements?.get('math-field')) {
    globalThis.customElements.define('math-field', class MathFieldStub extends globalThis.HTMLElement {})
  }
}

describe('MathFieldInput §5.2', () => {
  it('falls back to a native input when math-field is not registered', async () => {
    const wrapper = mount(MathFieldInput, { props: { modelValue: '', placeholder: '输入数值答案', numeric: true } })
    await new Promise(resolve => setTimeout(resolve, 0))
    await Promise.resolve()
    const input = wrapper.find('input.fallback-input')
    expect(input.exists()).toBe(true)
    expect(input.attributes('placeholder')).toBe('输入数值答案')
    await input.setValue('3.14')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['3.14'])
  })

  it('renders math-field once the custom element is registered', async () => {
    ensureMathFieldStub()
    const wrapper = mount(MathFieldInput, { props: { modelValue: '' } })
    // 等待动态 import 完成与组件刷新
    await new Promise(resolve => setTimeout(resolve, 10))
    await Promise.resolve()
    const field = wrapper.find('math-field')
    expect(field.exists()).toBe(true)
    expect(field.attributes('virtual-keyboard-mode')).toBe('manual')
  })

  it('emits gradeable math text from a latex input event', async () => {
    ensureMathFieldStub()
    const wrapper = mount(MathFieldInput, { props: { modelValue: '' } })
    await new Promise(resolve => setTimeout(resolve, 10))
    const field = wrapper.find('math-field')
    // 模拟 math-field 的 input 事件：target.value 为 LaTeX
    Object.defineProperty(field.element, 'value', { value: '\\frac{1}{2}', configurable: true })
    await field.trigger('input')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['((1)/(2))'])
  })
})
