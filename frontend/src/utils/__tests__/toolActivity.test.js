import { describe, expect, it } from 'vitest'

import {
  applyAgentStep,
  applyTraceEvent,
  isDraftRound,
  isTraceEvent,
  labelOfTraceRound,
  retractFromAnswer,
  stateOfStep,
  stepState,
  stepStatusText,
  stepsFromToolCalls,
  textOfStep,
  textOfTraceRound,
  toolRowStatusText,
  traceFromMetadata,
  traceSeconds,
  visibleTraceRounds,
} from '../toolActivity'

describe('tool activity timeline', () => {
  it('turns a start event into a running step with the readable tool label', () => {
    const steps = applyAgentStep([], {
      event_type: 'tool_start',
      tool: 'math_visualize',
      label: '函数图像绘制',
      status: 'running',
      message: '正在调用：函数图像绘制',
    })

    expect(steps).toHaveLength(1)
    expect(steps[0].label).toBe('函数图像绘制')
    expect(stateOfStep(steps[0])).toBe('running')
    expect(textOfStep(steps[0])).toBe('进行中')
  })

  it('closes the running step with 调用成功 when the tool really succeeded', () => {
    let steps = applyAgentStep([], { event_type: 'tool_start', tool: 'math_verify', label: '数学验证' })
    steps = applyAgentStep(steps, {
      event_type: 'tool_end',
      tool: 'math_verify',
      label: '数学验证',
      status: 'success',
      elapsed_ms: 42.5,
    })

    expect(steps).toHaveLength(1)
    expect(stateOfStep(steps[0])).toBe('done')
    expect(textOfStep(steps[0])).toBe('调用成功')
    expect(steps[0].elapsedMs).toBe(42.5)
  })

  it.each([
    ['error', '调用失败'],
    ['timeout', '调用超时'],
    ['unavailable', '工具暂不可用'],
    ['denied', '该模式下不可用'],
    ['aborted', '调用已中断'],
  ])('keeps the real %s terminal status visible instead of pretending success', (status, expected) => {
    let steps = applyAgentStep([], { event_type: 'tool_start', tool: 'math_visualize', label: '函数图像绘制' })
    steps = applyAgentStep(steps, {
      event_type: 'tool_error',
      tool: 'math_visualize',
      label: '函数图像绘制',
      status,
      code: 'TOOL_TIMEOUT',
    })

    expect(stateOfStep(steps[0])).toBe('failed')
    expect(textOfStep(steps[0])).toBe(expected)
    expect(steps[0].code).toBe('TOOL_TIMEOUT')
  })

  it('never swallows a terminal event whose start message was lost', () => {
    const steps = applyAgentStep([], {
      event_type: 'tool_end',
      tool: 'search_questions',
      label: '题库检索',
      status: 'success',
    })

    expect(steps).toHaveLength(1)
    expect(steps[0].label).toBe('题库检索')
    expect(textOfStep(steps[0])).toBe('调用成功')
  })

  it('does not duplicate the row when the same call starts twice', () => {
    let steps = applyAgentStep([], { event_type: 'tool_start', tool: 'math_animate', label: '动画演示' })
    steps = applyAgentStep(steps, { event_type: 'tool_start', tool: 'math_animate', label: '动画演示' })

    expect(steps).toHaveLength(1)
    expect(stateOfStep(steps[0])).toBe('running')
  })

  it('shows two independent rows for two calls of the same tool', () => {
    let steps = applyAgentStep([], { event_type: 'tool_start', tool: 'math_verify', label: '数学验证' })
    steps = applyAgentStep(steps, { event_type: 'tool_end', tool: 'math_verify', label: '数学验证', status: 'success' })
    steps = applyAgentStep(steps, { event_type: 'tool_start', tool: 'math_verify', label: '数学验证' })
    steps = applyAgentStep(steps, { event_type: 'tool_error', tool: 'math_verify', label: '数学验证', status: 'error' })

    expect(steps).toHaveLength(2)
    expect([textOfStep(steps[0]), textOfStep(steps[1])]).toEqual(['调用成功', '调用失败'])
  })

  it('keeps the 完成 wording on non-tool steps instead of an empty label', () => {
    const steps = applyAgentStep([], { event_type: 'planning', message: '已选择解题能力：solve' })

    expect(stateOfStep(steps[0])).toBe('info')
    expect(textOfStep(steps[0])).toBe('完成')
  })

  it('restores 完成 for legacy steps that stored an empty status text', () => {
    expect(textOfStep({ type: 'thinking', status: 'info', statusText: '' })).toBe('完成')
  })

  it('still closes legacy steps that only stored status', () => {
    const legacy = [{ type: 'tool_start', tool: 'math_visualize', label: '函数图像绘制', status: 'running' }]
    const steps = applyAgentStep(legacy, {
      event_type: 'tool_end',
      tool: 'math_visualize',
      label: '函数图像绘制',
      status: 'success',
    })

    expect(steps).toHaveLength(1)
    expect(stateOfStep(steps[0])).toBe('done')
  })

  it('rebuilds the timeline from persisted tool_calls', () => {
    const steps = stepsFromToolCalls([
      { tool: 'vision_tool', label: '图片题目识别', status: 'success', code: '', elapsed_ms: 900 },
      { tool: 'math_visualize', label: '函数图像绘制', status: 'timeout', code: 'TOOL_TIMEOUT' },
    ])

    expect(steps.map(step => step.type)).toEqual(['tool_end', 'tool_error'])
    expect(steps.map(textOfStep)).toEqual(['调用成功', '调用超时'])
    expect(steps[0].elapsedMs).toBe(900)
  })

  it('maps unknown statuses to a non-empty fallback', () => {
    expect(stepState('weird')).toBe('done')
    expect(stepStatusText('weird')).toBe('已结束')
    expect(toolRowStatusText('weird')).toBe('已结束')
  })

  it('words the panel tool row as 调用完成 so it cannot contradict the output summary', () => {
    // visualization_status=failed 会在同一行里报出来，台账的 success 只能说“调用跑完了”
    expect(toolRowStatusText('success')).toBe('调用完成')
    expect(stepStatusText('success')).toBe('调用成功')
    expect(toolRowStatusText('error')).toBe('调用失败')
    expect(toolRowStatusText('timeout')).toBe('调用超时')
    expect(toolRowStatusText('running')).toBe('进行中')
  })
})

describe('thinking trace aggregation', () => {
  it('groups events by model round and keeps the process round text', () => {
    let trace = applyTraceEvent([], { event_type: 'round_process', round: 1, text: '先取几个点再画图。', elapsed_ms: 812.5 })
    trace = applyTraceEvent(trace, {
      event_type: 'tool_io',
      round: 1,
      tool: 'math_visualize',
      label: '函数图像绘制',
      input_summary: 'type=function_plot, points=3',
      output_summary: 'status=ok',
    })
    trace = applyTraceEvent(trace, { event_type: 'round_final', round: 2, elapsed_ms: 1500 })

    expect(trace.map(item => item.round)).toEqual([1, 2])
    expect(textOfTraceRound(trace[0])).toBe('先取几个点再画图。')
    expect(trace[0].tools[0].inputSummary).toBe('type=function_plot, points=3')
    // 答案轮文本就是正文，面板不再复述一遍
    expect(textOfTraceRound(trace[1])).toBe('')
    expect(visibleTraceRounds(trace)).toHaveLength(1)
    expect(labelOfTraceRound(trace[0])).toBe('第 1 轮')
    expect(traceSeconds(trace)).toBe(1)
  })

  it('treats round_process text as authoritative over provisional reasoning', () => {
    let trace = applyTraceEvent([], { event_type: 'reasoning', round: 1, text: '我先看看' })
    expect(trace[0].text).toBe('我先看看')
    trace = applyTraceEvent(trace, { event_type: 'round_process', round: 1, text: '我先看看函数的定义域。' })

    expect(trace).toHaveLength(1)
    expect(trace[0].text).toBe('我先看看函数的定义域。')
    expect(trace[0].moved).toBe(true)
  })

  it('drops reasoning that was classified as the answer round', () => {
    let trace = applyTraceEvent([], { event_type: 'reasoning', round: 1, text: '最终答案是 42。' })
    // 还没定性：数据先拿着，但不外显，免得面板里多出正在流出的答案
    expect(isDraftRound(trace[0])).toBe(true)
    expect(trace[0].text).toBe('最终答案是 42。')
    expect(textOfTraceRound(trace[0])).toBe('')
    expect(labelOfTraceRound(trace[0])).toBe('第 1 轮 · 进行中')
    trace = applyTraceEvent(trace, { event_type: 'round_final', round: 1 })

    expect(textOfTraceRound(trace[0])).toBe('')
    expect(isDraftRound(trace[0])).toBe(false)
    expect(trace[0].moved).toBe(false)
    expect(labelOfTraceRound(trace[0])).toBe('第 1 轮')
  })

  it('shows the round text only after it is classified as a process round', () => {
    let trace = applyTraceEvent([], { event_type: 'reasoning', round: 1, text: '我先看看' })
    expect(textOfTraceRound(trace[0])).toBe('')
    trace = applyTraceEvent(trace, { event_type: 'round_process', round: 1, text: '我先看看函数的定义域。' })

    expect(isDraftRound(trace[0])).toBe(false)
    expect(textOfTraceRound(trace[0])).toBe('我先看看函数的定义域。')
  })

  it('keeps two rows when the same tool is called twice in one round', () => {
    let trace = applyTraceEvent([], { event_type: 'tool_io', round: 1, tool: 'math_verify', label: '数学验证', output_summary: 'status=ok' })
    trace = applyTraceEvent(trace, { event_type: 'tool_io', round: 1, tool: 'math_verify', label: '数学验证', output_summary: 'status=failed' })

    expect(trace[0].tools.map(item => item.outputSummary)).toEqual(['status=ok', 'status=failed'])
  })

  it('attaches direct calls made before the first round to round 0', () => {
    const trace = applyTraceEvent([], { event_type: 'tool_io', round: 0, tool: 'vision_tool', label: '图片题目识别', output_summary: 'status=ok' })

    expect(labelOfTraceRound(trace[0])).toBe('前置处理')
    expect(trace[0].tools).toHaveLength(1)
  })

  it('ignores timeline events instead of inventing a round', () => {
    expect(isTraceEvent('round_process')).toBe(true)
    expect(isTraceEvent('tool_end')).toBe(false)
    expect(applyTraceEvent([], { event_type: 'tool_end', tool: 'math_verify', status: 'success' })).toEqual([])
    expect(applyTraceEvent([], { event_type: 'thinking', message: '正在处理' })).toEqual([])
  })
})

describe('moving process narration out of the answer body', () => {
  it('removes the round text from the tail of the answer', () => {
    const { text, removed } = retractFromAnswer('我来画个图。\n\n先取几个点再画图。', '先取几个点再画图。')

    expect(removed).toBe(true)
    expect(text).toBe('我来画个图。')
  })

  it('keeps the answer untouched when the tail no longer matches', () => {
    const answer = '先取几个点再画图。完整解答如下：…'
    const { text, removed } = retractFromAnswer(answer, '这段话已被后续答案覆盖')

    // 宁可重复不可丢字：搬不动就保持正文原样
    expect(removed).toBe(false)
    expect(text).toBe(answer)
  })

  it('does nothing for an empty round', () => {
    expect(retractFromAnswer('答案', '   ')).toEqual({ text: '答案', removed: false })
    expect(retractFromAnswer('', '过程文本')).toEqual({ text: '', removed: false })
  })

  it('digs the narration out of the middle when the next round already streamed', () => {
    // 同一批 flush 里下一轮的正文已经接上，解说不再在尾部，与后端落库剥离开口径一致
    const { text, removed } = retractFromAnswer(
      '我先画个图。\n\n开口向上，顶点在 (1,-1)。',
      '我先画个图。',
    )

    expect(removed).toBe(true)
    expect(text).toBe('开口向上，顶点在 (1,-1)。')
  })

  it('keeps paragraph spacing when the narration sat between two answers', () => {
    const { text, removed } = retractFromAnswer('第一段。\n\n我去验算。\n\n第二段。', '我去验算。')

    expect(removed).toBe(true)
    expect(text).toBe('第一段。\n\n第二段。')
  })
})

describe('rebuilding the trace from persisted metadata', () => {
  it('restores rounds, tool summaries and the omitted marker', () => {
    const trace = traceFromMetadata([
      { round: 0, kind: 'omitted', text: '', elapsed_ms: null, truncated: true, tools: [] },
      {
        round: 1,
        kind: 'process',
        text: '先取几个点。',
        elapsed_ms: 900.5,
        truncated: false,
        tools: [{ tool: 'math_visualize', label: '函数图像绘制', status: 'timeout', code: 'TOOL_TIMEOUT', elapsed_ms: 3000, input_summary: 'type=function_plot', output_summary: 'code=TOOL_TIMEOUT' }],
      },
      { round: 2, kind: 'final', text: '', elapsed_ms: 1200, truncated: false, tools: [] },
    ])

    // 答案轮无内容可看，不占面板一行
    expect(trace.map(item => item.round)).toEqual([0, 1])
    expect(trace[1].tools[0].status).toBe('timeout')
    expect(trace[1].elapsedMs).toBe(900.5)
    expect(labelOfTraceRound(trace[0])).toBe('中间轮次已省略')
  })

  it('infers the kind when an old row stored no kind', () => {
    const trace = traceFromMetadata([{ round: 1, text: '带文本的旧轮次', tools: [] }])

    expect(trace[0].kind).toBe('process')
    expect(trace[0].moved).toBe(true)
  })

  it('tolerates a missing metadata field', () => {
    expect(traceFromMetadata(undefined)).toEqual([])
    expect(traceSeconds(undefined)).toBe(0)
  })
})

describe('plain-text narration in the thinking panel', () => {
  it('strips markdown markers the panel would otherwise show literally', () => {
    const trace = applyTraceEvent([], {
      event_type: 'round_process',
      round: 1,
      text: '## 先定计划\n\n**图像绘制**：取样本点。',
    })

    expect(textOfTraceRound(trace[0])).toBe('先定计划\n\n图像绘制：取样本点。')
  })

  it('keeps inline code text without the backticks', () => {
    const trace = applyTraceEvent([], { event_type: 'round_process', round: 1, text: '用 `f(x)=x^2` 取点。' })

    expect(textOfTraceRound(trace[0])).toBe('用 f(x)=x^2 取点。')
  })

  it('drops code fences but keeps the fenced content', () => {
    const trace = applyTraceEvent([], { event_type: 'round_process', round: 1, text: '```python\nf(x)=x^2\n```' })
    const rendered = textOfTraceRound(trace[0])

    expect(rendered).toContain('f(x)=x^2')
    expect(rendered).not.toContain('```')
    expect(rendered).not.toContain('python')
  })

  it('leaves multiplication asterisks alone', () => {
    const trace = applyTraceEvent([], { event_type: 'round_process', round: 1, text: '先算 2 ** 3 与 3 ** 2 的大小。' })

    expect(textOfTraceRound(trace[0])).toBe('先算 2 ** 3 与 3 ** 2 的大小。')
  })

  it('only affects display, the stored round text stays verbatim for retraction', () => {
    const raw = '**图像绘制**：取样本点。'
    const trace = applyTraceEvent([], { event_type: 'round_process', round: 1, text: raw })

    expect(trace[0].text).toBe(raw)
    expect(retractFromAnswer('好，**图像绘制**：取样本点。', raw).removed).toBe(true)
  })
})
