/**
 * MathRenderer 最小基础测试。
 *
 * 覆盖：
 * - 普通文本能渲染
 * - 合法 LaTeX 进入数学渲染路径
 * - 异常/不完整数学输入不会让组件崩溃
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MathRenderer from '../MathRenderer.vue'

describe('MathRenderer', () => {
  it('should render plain text without crashing', () => {
    const wrapper = mount(MathRenderer, {
      props: { content: 'x + 1 = 2' },
    })
    // KaTeX 输出包含 katex 结构，且不会为空
    expect(wrapper.find('.katex').exists()).toBe(true)
    expect(wrapper.html()).toContain('katex')
  })

  it('should render valid LaTeX into math rendering path', () => {
    const wrapper = mount(MathRenderer, {
      props: { content: '\\frac{1}{2}' },
    })
    // 合法 LaTeX 应进入 KaTeX 渲染路径（产生 .katex 结构）
    expect(wrapper.find('.katex').exists()).toBe(true)
    expect(wrapper.html()).toContain('frac')
  })

  it('should not crash on invalid/incomplete math input', () => {
    // 不完整 LaTeX（未闭合）不应抛出异常
    expect(() => {
      const wrapper = mount(MathRenderer, {
        props: { content: '\\frac{1}{' },
      })
      expect(wrapper.html()).toBeTruthy()
    }).not.toThrow()
  })

  it('should render empty content safely', () => {
    const wrapper = mount(MathRenderer, {
      props: { content: '' },
    })
    // 空内容不产生 KaTeX 结构，也不会崩溃
    expect(wrapper.find('.katex').exists()).toBe(false)
    expect(wrapper.html()).toBe('<span></span>')
  })
})