import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MessageItem from '../MessageItem.vue'

const PROCESS_ROUND = {
  round: 1,
  kind: 'process',
  text: '先取几个点，再调用绘图工具。',
  elapsedMs: 1600,
  truncated: false,
  moved: true,
  tools: [
    {
      tool: 'math_visualize',
      label: '函数图像绘制',
      status: 'success',
      code: '',
      elapsedMs: 210,
      inputSummary: 'type=function_plot, points=3',
      outputSummary: 'status=ok',
    },
  ],
}

const ANSWER_ROUND = {
  round: 2,
  kind: 'final',
  text: '',
  elapsedMs: 1500,
  truncated: false,
  moved: false,
  tools: [],
}

const STEPS = [
  { type: 'tool_end', tool: 'math_visualize', label: '函数图像绘制', status: 'success', state: 'done', statusText: '调用成功' },
]

function aiMessage(extra = {}) {
  return {
    id: 'm-1',
    sender: 'ai',
    content: '抛物线开口向上，顶点在原点。',
    timestamp: '2026-01-01T00:00:00Z',
    type: 'text',
    agentSteps: STEPS,
    trace: [PROCESS_ROUND, ANSWER_ROUND],
    ...extra,
  }
}

function mountItem(props = {}) {
  return mount(MessageItem, {
    props: { message: aiMessage(), isStreaming: false, tutorMode: 'tutor_free', ...props },
    global: { stubs: { MathVisualCard: true, MathAnimationCard: true } },
  })
}

describe('MessageItem thinking panel', () => {
  it('shows the collapsible trace with rounds, tool summaries and elapsed time', () => {
    const wrapper = mountItem()
    const panel = wrapper.find('details.agent-thinking')

    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('思考过程 · 2s')
    expect(panel.text()).toContain('1 轮')
    expect(panel.text()).toContain('以下为 Agent 实际执行与决策纪要')
    expect(wrapper.find('.thinking-round__label').text()).toBe('第 1 轮')
    expect(wrapper.find('.thinking-round__text').text()).toBe('先取几个点，再调用绘图工具。')
    const strips = wrapper.findAll('.thinking-tool__io')
    expect(strips.map(item => item.text())).toEqual(['type=function_plot, points=3', 'status=ok'])
    expect(wrapper.find('.thinking-tool__status').text()).toBe('调用完成')
    // 时间线仍按工具调用生命周期报“调用成功”，两个面板不共用措辞
    expect(wrapper.find('.agent-step__status').text()).toBe('调用成功')
  })

  it('does not call a failed graph run a success inside the panel', () => {
    // 调用本身跑完了，但图形规格被服务端拒了：行内文案不能与输出摘要打架
    const row = {
      ...PROCESS_ROUND.tools[0],
      outputSummary: 'status=ok, visualization_status=failed',
    }
    const wrapper = mountItem({ message: aiMessage({ trace: [{ ...PROCESS_ROUND, tools: [row] }] }) })

    expect(wrapper.find('.thinking-tool__status').text()).toBe('调用完成')
    expect(wrapper.findAll('.thinking-tool__io')[1].text()).toContain('visualization_status=failed')
  })

  it('names the terminal status of a failed tool inside the panel', () => {
    // 被 LangChain 提前拦下的调用没有摘要，面板也得说清它失败了
    const failed = {
      ...PROCESS_ROUND,
      tools: [{ tool: 'math_visualize', label: '函数图像绘制', status: 'error', code: 'TOOL_INVOCATION_ERROR', inputSummary: '', outputSummary: '' }],
    }
    const wrapper = mountItem({ message: aiMessage({ trace: [failed] }) })

    expect(wrapper.find('.thinking-tool').classes()).toContain('thinking-tool--failed')
    expect(wrapper.find('.thinking-tool__status').text()).toBe('调用失败')
    expect(wrapper.findAll('.thinking-tool__io')).toHaveLength(0)
  })

  it('marks an unclassified round as a working draft', () => {
    // 流式中的临时轮：文本不外显（那可能就是正在流出的答案），只给轮壳与提示
    const draft = { ...PROCESS_ROUND, kind: '', elapsedMs: undefined, moved: false }
    const wrapper = mountItem({ message: aiMessage({ trace: [draft] }) })

    expect(wrapper.find('.thinking-round').classes()).toContain('thinking-round--draft')
    expect(wrapper.find('.thinking-round__label').text()).toBe('第 1 轮 · 进行中')
    expect(wrapper.find('.thinking-round__text').exists()).toBe(false)
    expect(wrapper.find('.thinking-round__draft').text()).toContain('定性后归档')
    expect(mountItem({ message: aiMessage({ trace: [PROCESS_ROUND] }) }).find('.thinking-round').classes())
      .not.toContain('thinking-round--draft')
  })

  it('does not repeat the answer round inside the panel', () => {
    const wrapper = mountItem()

    expect(wrapper.findAll('.thinking-round')).toHaveLength(1)
    expect(wrapper.find('.thinking-round__text').text()).not.toContain('抛物线')
  })

  it.each(['hint_only', 'guided', 'review'])('renders no thinking panel in %s mode', mode => {
    const wrapper = mountItem({ tutorMode: mode })

    expect(wrapper.find('details.agent-thinking').exists()).toBe(false)
    // 工具时间线四种模式保持现状
    expect(wrapper.find('details.agent-timeline').exists()).toBe(true)
  })

  it('hides the panel when the message carries no visible round', () => {
    expect(mountItem({ message: aiMessage({ trace: [ANSWER_ROUND] }) }).find('details.agent-thinking').exists()).toBe(false)
    expect(mountItem({ message: aiMessage({ trace: undefined }) }).find('details.agent-thinking').exists()).toBe(false)
  })

  it('stays open while streaming and collapses afterwards', () => {
    expect(mountItem({ isStreaming: true }).find('details.agent-thinking').attributes('open')).toBeDefined()
    expect(mountItem({ isStreaming: false }).find('details.agent-thinking').attributes('open')).toBeUndefined()
  })

  it('renders round narration as plain text instead of interpreting it as HTML', () => {
    const hostile = { ...PROCESS_ROUND, text: '<img class="xss-probe" src=x onerror="alert(1)">' }
    const wrapper = mountItem({ message: aiMessage({ trace: [hostile] }) })

    expect(wrapper.find('.xss-probe').exists()).toBe(false)
    expect(wrapper.find('.thinking-round__text').text()).toContain('onerror="alert(1)"')
  })

  it('marks over-budget rounds as truncated', () => {
    const wrapper = mountItem({ message: aiMessage({ trace: [{ ...PROCESS_ROUND, truncated: true }] }) })

    expect(wrapper.find('.thinking-round__cut').text()).toContain('已截断')
  })

  it('shows narration without literal markdown markers', () => {
    const noisy = { ...PROCESS_ROUND, text: '## 计划\n\n**图像绘制**：取样本点。' }
    const wrapper = mountItem({ message: aiMessage({ trace: [noisy] }) })

    // 面板不跑 markdown，所以要把记号清成可读文本，不能摆星号给学生
    expect(wrapper.find('.thinking-round__text').element.textContent).toBe('计划\n\n图像绘制：取样本点。')
  })
})

describe('MessageItem tool timeline', () => {
  it('keeps the 完成 wording for non-tool steps', () => {
    const wrapper = mountItem({
      message: aiMessage({
        trace: [],
        agentSteps: [{ type: 'planning', tool: '', label: '已选择解题能力：solve', status: 'info', state: 'info', statusText: '完成' }],
      }),
    })

    expect(wrapper.find('.agent-timeline').text()).toContain('完成')
  })
})
