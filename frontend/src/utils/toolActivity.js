/**
 * 工具调用时间线（agent_step）状态机 + 思考过程纪要（agent_trace）状态机。
 *
 * 后端台账会为每一次封装好的工具调用发出「开始 + 真实终态」两个事件，
 * 这里只负责把它们折叠成学生可读的步骤：任何调用都必须留下一行，
 * 并且明确标出「调用成功」还是「调用失败/超时/不可用」。
 *
 * 思考纪要走同一条 agent_step 通道，按模型轮次聚合成可折叠面板：
 * 过程轮的文本从正文搬进面板，答案轮的文本留在正文不重复显示。
 */

// 与 tools/tool_ledger.py 的终态字典保持一致，新增状态时两边同步。
const RUNNING = 'running'
const SUCCESS = 'success'
const FAILED_STATUSES = new Set(['error', 'timeout', 'unavailable', 'denied', 'aborted'])

// 面板单轮文本上限：后端已按 4000 字/轮截断，这里只是重放拼接时的兜底。
const MAX_ROUND_TEXT_CHARS = 6000
const INFO_STEP_TEXT = '完成'

const STATUS_TEXT = {
  [RUNNING]: '进行中',
  [SUCCESS]: '调用成功',
  done: '调用成功',
  error: '调用失败',
  timeout: '调用超时',
  unavailable: '工具暂不可用',
  denied: '该模式下不可用',
  aborted: '调用已中断',
}

/** 后端状态 → 展示文案；未知状态用「已结束」兜底，不显示空白。 */
export function stepStatusText(status) {
  return STATUS_TEXT[status] || '已结束'
}

// 纪要面板里的工具行同一行还会列出输出摘要（visualization_status=failed 一类）。
// 台账状态只担保「这次调用按协议跑完了」，不担保工具产出成功，所以成功态写成
// 「调用完成」；沿用时间线的「调用成功」会跟同一行的失败事实相互打架。
const TOOL_ROW_STATUS_TEXT = { ...STATUS_TEXT, [SUCCESS]: '调用完成', done: '调用完成' }

/** 纪要面板工具行的终态文案；失败态仍沿用带指向的措辞。 */
export function toolRowStatusText(status) {
  return TOOL_ROW_STATUS_TEXT[status] || '已结束'
}

/** 后端状态 → 样式态：running（转圈）/ done（成功）/ failed（异常）。 */
export function stepState(status) {
  if (status === RUNNING) return 'running'
  if (FAILED_STATUSES.has(status)) return 'failed'
  return 'done'
}

/**
 * 步骤的样式态；兼容旧版本 localStorage 里只存了 status/type 的记录，
 * 否则历史消息的时间线会因缺字段而变成空白或永远转圈。
 */
export function stateOfStep(step) {
  if (step?.state) return step.state
  if (!isToolEvent(step?.type)) return 'info'
  return stepState(step?.status)
}

/** 步骤右侧状态文案；非工具步骤（思考/规划）不披“调用成功”的标签。 */
export function textOfStep(step) {
  if (step?.statusText) return step.statusText
  if (!isToolEvent(step?.type)) return INFO_STEP_TEXT
  return stepStatusText(step?.status)
}

function isToolEvent(eventType) {
  return eventType === 'tool_start' || eventType === 'tool_end' || eventType === 'tool_error'
}

// 纪要事件与时间线事件共用 agent_step 通道，靠 event_type 分流。
const TRACE_EVENTS = new Set(['reasoning', 'round_process', 'round_final', 'tool_io'])

/** 该 agent_step 事件属于思考面板而非工具时间线。 */
export function isTraceEvent(eventType) {
  return TRACE_EVENTS.has(eventType)
}

function terminalStatusOf(data) {
  if (data.status && data.status !== RUNNING) return data.status
  return data.event_type === 'tool_error' ? 'error' : SUCCESS
}

/**
 * 把一条 agent_step 事件折叠进步骤列表。
 *
 * 关键约束：终态事件找不到配对的「进行中」步骤时也要补一行，
 * 不能因为开始事件丢失（重放截断、跨实例）就把这次调用吞掉。
 */
export function applyAgentStep(steps, data) {
  const next = [...(steps || [])]
  const eventType = data?.event_type || 'thinking'

  if (!isToolEvent(eventType)) {
    next.push({
      type: eventType,
      tool: data.tool || '',
      label: data.message || '正在处理',
      status: 'info',
      state: 'info',
      statusText: INFO_STEP_TEXT,
    })
    return next
  }

  if (eventType === 'tool_start') {
    const running = [...next].reverse().find(item => item.tool === data.tool && stateOfStep(item) === 'running')
    if (running) {
      running.label = data.label || running.label
      return next
    }
    next.push({
      type: eventType,
      tool: data.tool || '',
      label: data.label || data.message || data.tool || '工具',
      status: RUNNING,
      state: 'running',
      statusText: stepStatusText(RUNNING),
    })
    return next
  }

  const status = terminalStatusOf(data)
  const active = [...next].reverse().find(item => item.tool === data.tool && stateOfStep(item) === 'running')
  if (active) {
    active.type = eventType
    active.status = status
    active.state = stepState(status)
    active.statusText = stepStatusText(status)
    active.label = data.label || active.label
    if (data.code) active.code = data.code
    if (Number.isFinite(data.elapsed_ms)) active.elapsedMs = data.elapsed_ms
    return next
  }
  next.push({
    type: eventType,
    tool: data.tool || '',
    label: data.label || data.tool || '工具',
    status,
    state: stepState(status),
    statusText: stepStatusText(status),
    code: data.code || '',
    elapsedMs: Number.isFinite(data.elapsed_ms) ? data.elapsed_ms : undefined,
  })
  return next
}

/**
 * 由落库的 tool_calls 轨迹还原历史消息的时间线。
 * 每个工具调用折叠成一行终态步骤，重开对话时仍能看到「调用成功/失败」。
 */
export function stepsFromToolCalls(toolCalls) {
  return (toolCalls || []).map(call => ({
    type: call.status === SUCCESS ? 'tool_end' : 'tool_error',
    tool: call.tool || '',
    label: call.label || call.tool || '工具',
    status: call.status || SUCCESS,
    state: stepState(call.status),
    statusText: stepStatusText(call.status),
    code: call.code || '',
    elapsedMs: Number.isFinite(call.elapsed_ms) ? call.elapsed_ms : undefined,
  }))
}

/**
 * ---- 思考过程纪要 ----
 *
 * 一轮 = 一次模型调用。条目形状：
 * { round, kind, text, elapsedMs, truncated, moved, tools: [...] }
 * kind: '' 尚未定性 / process 过程轮 / final 答案轮 / direct 开轮前的直连调用 / omitted 中间轮次被预算省略。
 */

function clampText(text) {
  return text.length > MAX_ROUND_TEXT_CHARS ? text.slice(0, MAX_ROUND_TEXT_CHARS) : text
}

// 面板按纯文本渲染（v-text，不 v-html），所以把模型偶尔写的 markdown 记号清掉，
// 不要把星号原样摆给学生。单星号与下划线一律不动：那是乘号与下标的高频写法。
const MD_FENCE_RE = /^[ \t]{0,3}```[^\n]*$/gm
const MD_HEADING_RE = /^[ \t]{0,3}#{1,6}[ \t]+/gm
const MD_BOLD_RE = /\*\*(\S(?:[^*]*\S)?)\*\*/g
const MD_CODE_RE = /`([^`\n]+)`/g

function plainText(text) {
  return String(text || '')
    .replace(MD_FENCE_RE, '')
    .replace(MD_HEADING_RE, '')
    .replace(MD_BOLD_RE, '$1')
    .replace(MD_CODE_RE, '$1')
}

function toolRowOf(data) {
  return {
    tool: data.tool || '',
    label: data.label || data.tool || '工具',
    status: data.status || '',
    code: data.code || '',
    elapsedMs: Number.isFinite(data.elapsed_ms) ? data.elapsed_ms : undefined,
    inputSummary: data.input_summary || '',
    outputSummary: data.output_summary || '',
  }
}

function ensureRound(trace, round) {
  let entry = trace.find(item => item.round === round)
  if (!entry) {
    entry = { round, kind: '', text: '', elapsedMs: undefined, truncated: false, moved: false, tools: [] }
    trace.push(entry)
    // 重放与跨实例补发可能乱序到达，面板始终按轮号递增排列
    trace.sort((a, b) => a.round - b.round)
  }
  return entry
}

function attachToolIo(entry, data) {
  const row = toolRowOf(data)
  // 同一轮里同名工具可能调多次：先填补尚无摘要的那一行，配不上就补一行
  const target = entry.tools.find(item => item.tool === row.tool && !item.inputSummary && !item.outputSummary)
  if (target) Object.assign(target, row)
  else entry.tools.push(row)
}

/**
 * 把一条纪要事件折叠进轮次列表。
 *
 * 关键约束：面板只能“多一份”，不能“少一份”。
 * reasoning 是尚未定性时的临时增量，round_process 携带该轮全文并以它为准，
 * 因此不会出现临时文本被截断后永久丢字。
 */
export function applyTraceEvent(trace, data) {
  const next = [...(trace || [])]
  const eventType = data?.event_type
  if (!TRACE_EVENTS.has(eventType)) return next

  const entry = ensureRound(next, Number.isFinite(data.round) ? data.round : 0)

  if (eventType === 'reasoning') {
    entry.text = clampText(entry.text + (data.text || ''))
    if (data.truncated) entry.truncated = true
    return next
  }
  if (eventType === 'round_process') {
    entry.kind = 'process'
    entry.text = clampText(data.text || '')
    entry.moved = true
    entry.truncated = Boolean(data.truncated)
    if (Number.isFinite(data.elapsed_ms)) entry.elapsedMs = data.elapsed_ms
    return next
  }
  if (eventType === 'round_final') {
    entry.kind = 'final'
    // 答案轮文本就是正文本身，面板撤掉临时内容，不重复显示
    entry.text = ''
    entry.moved = false
    entry.truncated = Boolean(data.truncated)
    if (Number.isFinite(data.elapsed_ms)) entry.elapsedMs = data.elapsed_ms
    return next
  }
  attachToolIo(entry, data)
  return next
}

/**
 * 把过程轮文本从答案正文里移除。
 *
 * 先试尾部（常见情形：该轮刚说完就定性为过程轮），尾部对不上再按原文挖中间那一段
 * ——一批事件里同时到了下一轮的文本时，解说就不再在尾部了；后一种定位与后端落库时的
 * 剥离同口径，否则会出现「流式时看到解说、刷新后解说又消失」的口径差。
 * 两处都定位不到时不清空正文，宁可面板与正文重复一份也不丢字。
 */
export function retractFromAnswer(answerText, retractedText) {
  const answer = answerText || ''
  const body = (retractedText || '').trimEnd()
  if (!body) return { text: answer, removed: false }
  const trimmed = answer.trimEnd()
  if (trimmed.endsWith(body)) {
    return { text: trimmed.slice(0, trimmed.length - body.length).trimEnd(), removed: true }
  }
  const index = trimmed.indexOf(body)
  if (index < 0) return { text: answer, removed: false }
  const joined = `${trimmed.slice(0, index)}${trimmed.slice(index + body.length)}`.replace(/\n{3,}/g, '\n\n')
  return { text: joined.trim(), removed: true }
}

/**
 * 由落库的 metadata.agent_trace 还原历史消息的思考面板。
 * 面板只在自由辅导模式渲染，受限模式的正文与旧数据不受影响。
 */
export function traceFromMetadata(trace) {
  return (trace || [])
    .map(row => ({
      round: Number.isFinite(row.round) ? row.round : 0,
      kind: row.kind || (row.text ? 'process' : 'final'),
      text: row.text || '',
      elapsedMs: Number.isFinite(row.elapsed_ms) ? row.elapsed_ms : undefined,
      truncated: Boolean(row.truncated),
      moved: Boolean(row.text),
      tools: (row.tools || []).map(toolRowOf),
    }))
    .filter(entry => entry.kind === 'omitted' || entry.text || entry.tools.length)
}

/** 面板标题轮数：只数真正有内容可看的轮。 */
export function visibleTraceRounds(trace) {
  return (trace || []).filter(entry => entry.text || entry.tools.length || entry.kind === 'omitted')
}

/** 面板标题耗时（向上取整到秒）：答案轮耗时不算进思考时间。 */
export function traceSeconds(trace) {
  const ms = visibleTraceRounds(trace).reduce(
    (total, entry) => total + (Number.isFinite(entry.elapsedMs) ? entry.elapsedMs : 0),
    0,
  )
  return ms > 0 ? Math.max(1, Math.round(ms / 1000)) : 0
}

/** 轮次标题；round 0 是开轮前的直连调用（如多模态识图）。 */
export function labelOfTraceRound(entry) {
  if (entry?.kind === 'omitted') return '中间轮次已省略'
  if (entry?.round === 0) return '前置处理'
  // 还没定性的轮只拿着临时增量：标「进行中」，免得学生把草稿当成最终结论。
  if (!entry?.kind) return `第 ${entry.round} 轮 · 进行中`
  return `第 ${entry.round} 轮`
}

/**
 * 轮次正文；答案轮不重复展示正文。
 *
 * 尚未定性的轮也不展示：那段增量可能就是正在流出的答案本身，
 * 摆在面板里会与正文重复一份、定性后又消失。面板先给出「进行中」轮壳与工具条，
 * 文本要等 round_process 把该轮定为过程轮后才归档显示。
 */
export function textOfTraceRound(entry) {
  if (!entry || !entry.kind || entry.kind === 'final') return ''
  return plainText(entry.text || '')
}

/** 该轮还没定性（文本已到达但尚未归档），面板只给轮壳与提示。 */
export function isDraftRound(entry) {
  return Boolean(entry) && !entry.kind
}

