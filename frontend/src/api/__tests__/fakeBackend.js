/**
 * 进程内假后端（axios adapter 形态）。
 *
 * 为什么用 adapter 而不是 vi.mock('axios')：
 * 学生主链闭环的价值在于"真实客户端代码真的跑一遍"——这里注入的是 adapter，
 * 于是 @/api 的 Authorization 注入拦截器、401 refresh/重放拦截器、各 api 模块的
 * unwrap 语义（envelope `{code:0,data}` / `{status,data}` / 裸对象 / 数组）全部按生产路径执行。
 * mock 掉 axios 只会验证"我调用过 mock"，抓不到字段语义漂移（ChatView openErrorBookDialog 那类事故）。
 *
 * 每个响应体的字段名都对齐后端契约，改动后端字段时这里的断言应当先红：
 * - POST /api/auth/login                app/api/auth.py（401 INVALID_CREDENTIALS / 423 ACCOUNT_LOCKED / 429）
 * - POST /api/auth/refresh              同上，{status:"success", data:{access_token,refresh_token}}
 * - GET /api/knowledge/courses          CourseListResponse
 * - GET /api/knowledge/courses/{id}/tree CourseTreeResponse
 * - GET /api/knowledge/points/{id}      KnowledgePointResponse
 * - GET /api/knowledge/points/{id}/learning KnowledgePointResponse(resources/prerequisite_points)
 * - GET /api/practice/options           StudentOperationEnvelope
 * - POST /api/practice/sessions         同上，_session_payload
 * - POST /api/practice/sessions/{id}/start
 * - POST /api/practice/sessions/{id}/attempts  submit_attempt 判分结果
 * - POST /api/error-book                ErrorItemRequest → ErrorBookCreateResponse
 * - GET /api/learning/reviews/due       ReviewListResponse
 * - POST /api/learning/reviews/{id}/actions    ReviewItem（defer 幂等）
 * - GET /api/learning/reminders         RemindersResponse（派生分档）
 */
import { AxiosError } from 'axios'

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

const STATUS_TEXT = {
  200: 'OK', 401: 'Unauthorized', 403: 'Forbidden', 404: 'Not Found',
  409: 'Conflict', 422: 'Unprocessable Entity', 423: 'Locked', 429: 'Too Many Requests',
}

export const FAKE_ACCOUNT = {
  username: 'journey_student',
  password: 'Journey#2024',
  user_id: 'u-journey-0001',
  role: 'student',
}

const iso = (ms) => new Date(ms).toISOString()

function normalizeHeader(config, name) {
  const headers = config?.headers
  if (!headers) return ''
  const direct = headers[name] ?? headers[name.toLowerCase()]
  if (direct !== undefined && direct !== null && direct !== '') return String(direct)
  if (typeof headers.get === 'function') {
    const value = headers.get(name) ?? headers.get(name.toLowerCase())
    return value === undefined || value === null ? '' : String(value)
  }
  return ''
}

function parseBody(config) {
  if (config.data === undefined || config.data === null || config.data === '') return {}
  if (typeof config.data === 'string') {
    try { return JSON.parse(config.data) } catch { return { __raw: config.data } }
  }
  return config.data
}

/**
 * @param {object} [options] 覆盖限流/锁定阈值，便于用少量请求触发 429/423。
 */
export function createFakeBackend(options = {}) {
  const clock = options.now ? () => options.now() : () => new Date()
  const state = {
    loginBudgetTotal: options.loginBudget ?? 10,
    loginBudgetLeft: options.loginBudget ?? 10,
    maxFailedLogins: options.maxFailedLogins ?? 5,
    lockMinutes: options.lockMinutes ?? 15,
    users: {
      [FAKE_ACCOUNT.username]: {
        user_id: FAKE_ACCOUNT.user_id,
        username: FAKE_ACCOUNT.username,
        role: FAKE_ACCOUNT.role,
        password: FAKE_ACCOUNT.password,
        failed_login_count: 0,
        locked_until: null,
      },
    },
    accessTokens: {},
    refreshTokens: {},
    sessions: {},
    sessionKeys: {},
    attemptKeys: {},
    errorItems: {},
    // 知识点级复习排期：覆盖 overdue / today / upcoming / 被 defer 后 effective_due 晚于 due_at 四种形态
    schedules: {
      4101: { id: 4101, knowledge_point_code: 'LIMIT', knowledge_point_name: '极限的四则运算', due_at: clock().getTime() - 3 * DAY, interval_days: 8, review_count: 3, stage: 4, algorithm_version: 'sm-ef-v1', deferred_until: null, actions: {} },
      4102: { id: 4102, knowledge_point_code: 'CONT', knowledge_point_name: '连续函数的性质', due_at: clock().getTime() - 2 * HOUR, interval_days: 4, review_count: 2, stage: 3, algorithm_version: 'sm-ef-v1', deferred_until: null, actions: {} },
      4103: { id: 4103, knowledge_point_code: 'SERIES', knowledge_point_name: '数项级数敛散性', due_at: clock().getTime() + 6 * HOUR, interval_days: 2, review_count: 1, stage: 2, algorithm_version: 'sm-ef-v1', deferred_until: null, actions: {} },
      4104: { id: 4104, knowledge_point_code: 'TRIPLE', knowledge_point_name: '三重积分', due_at: clock().getTime() + 30 * DAY, interval_days: 1, review_count: 0, stage: 1, algorithm_version: 'sm-ef-v1', deferred_until: null, actions: {} },
    },
    // 错题级到期项：真实实现来自 ErrorItem.next_review_at，没有 deferred_until，因此不可 defer
    errorReviews: {
      'err-001': { id: 'error-err-001', source: 'error_item', error_item_id: 'err-001', question_id: 'q-derivative-tangent', knowledge_point_code: 'DERIV', knowledge_point_name: '导数的几何意义', due_at: clock().getTime() - 30 * MINUTE, interval_days: 3, review_count: 1, stage: 2, algorithm_version: 'error-sm-v1' },
      'err-unranked': { id: 'error-err-unranked', source: 'error_item', error_item_id: 'err-unranked', question_id: 'q-unranked', knowledge_point_code: 'DERIV', knowledge_point_name: '未排期错题', due_at: null, interval_days: 0, review_count: 0, stage: 0, algorithm_version: 'error-sm-v1' },
    },
    requests: [],
  }

  // ------------------------------------------------------------
  // 领域数据
  // ------------------------------------------------------------
  const COURSE_ID = 'course-advanced-math'
  const VERSION_ID = 'v-2024-1'

  const knowledgePoints = {
    LIMIT: {
      id: 'kp-limit', code: 'LIMIT', name: '极限的四则运算', description: '极限的加减乘除与分式化简',
      difficulty: 2, importance: 5, sort_order: 1, prerequisites: ['SEQ'], related: ['CONT'],
      course: { id: COURSE_ID, code: 'AM', name: '高等数学', description: '', subject: '数学' },
      version: { id: VERSION_ID, name: '2024 版', status: 'published' },
      aliases: ['极限运算'],
      resources: [
        { id: 'res-limit-intuition', type: 'intuition', title: '直觉：无限逼近', body: '把 n 变大时数列项落在极限附近。' },
        { id: 'res-limit-formula', type: 'formula', title: '运算法则', body: 'lim(a±b)=lim a±lim b。' },
        { id: 'res-limit-exercise', type: 'exercise', title: '课后自测', body: '求 lim (2n²+1)/(n²+3)。' },
      ],
      prerequisite_points: [{ code: 'SEQ', name: '数列的概念' }],
    },
    DERIV: {
      id: 'kp-deriv', code: 'DERIV', name: '导数的几何意义', description: '切线斜率与差商极限',
      difficulty: 3, importance: 5, sort_order: 2, prerequisites: ['LIMIT'], related: [],
      course: { id: COURSE_ID, code: 'AM', name: '高等数学', description: '', subject: '数学' },
      version: { id: VERSION_ID, name: '2024 版', status: 'published' },
      aliases: [],
      resources: [{ id: 'res-deriv-example', type: 'worked_example', title: '例题', body: '求 y=x² 在 x=1 处切线。' }],
      prerequisite_points: [{ code: 'LIMIT', name: '极限的四则运算' }],
    },
    CONT: {
      id: 'kp-cont', code: 'CONT', name: '连续函数的性质', description: '介值定理与最值定理',
      difficulty: 3, importance: 4, sort_order: 3, prerequisites: ['LIMIT'], related: [],
      course: { id: COURSE_ID, code: 'AM', name: '高等数学', description: '', subject: '数学' },
      version: { id: VERSION_ID, name: '2024 版', status: 'published' },
      aliases: [], resources: [], prerequisite_points: [],
    },
    SERIES: {
      id: 'kp-series', code: 'SERIES', name: '数项级数敛散性', description: '正项级数的审敛法',
      difficulty: 4, importance: 4, sort_order: 4, prerequisites: ['LIMIT'], related: [],
      course: { id: COURSE_ID, code: 'AM', name: '高等数学', description: '', subject: '数学' },
      version: { id: VERSION_ID, name: '2024 版', status: 'published' },
      aliases: [], resources: [], prerequisite_points: [],
    },
    TRIPLE: {
      id: 'kp-triple', code: 'TRIPLE', name: '三重积分', description: '直角与柱坐标下的三重积分',
      difficulty: 5, importance: 3, sort_order: 5, prerequisites: [], related: [],
      course: { id: COURSE_ID, code: 'AM', name: '高等数学', description: '', subject: '数学' },
      version: { id: VERSION_ID, name: '2024 版', status: 'published' },
      aliases: [], resources: [], prerequisite_points: [],
    },
  }

  const questionBank = {
    'q-derivative-tangent': {
      question_id: 'q-derivative-tangent', content: '求 y=x² 在 x=1 处切线斜率。', question_type: 'text',
      options: null, difficulty: 3, estimated_time: 120, knowledge_point_codes: ['DERIV'],
      common_mistakes: ['忘记取极限'], answer: '2', analysis: '差商极限为 2。',
    },
    'q-limit-value': {
      question_id: 'q-limit-value', content: '求 lim (2n²+1)/(n²+3)。', question_type: 'text',
      options: null, difficulty: 2, estimated_time: 90, knowledge_point_codes: ['LIMIT'],
      common_mistakes: ['分子分母同除 n 而非 n²'], answer: '2', analysis: '最高次项系数比为 2。',
    },
    'q-limit-inf': {
      question_id: 'q-limit-inf', content: '求 lim n/(n+1)。', question_type: 'text',
      options: null, difficulty: 2, estimated_time: 60, knowledge_point_codes: ['LIMIT'],
      common_mistakes: [], answer: '1', analysis: '同除 n 后得 1/(1+1/n)。',
    },
    'q-deriv-chain': {
      question_id: 'q-deriv-chain', content: '求 d/dx sin(2x)。', question_type: 'text',
      options: null, difficulty: 3, estimated_time: 90, knowledge_point_codes: ['DERIV'],
      common_mistakes: ['漏乘内层导数'], answer: '2cos(2x)', analysis: '链式法则。',
    },
    'q-cont-ivt': {
      question_id: 'q-cont-ivt', content: '闭区间上连续函数必有最值，此定理名称是？', question_type: 'text',
      options: null, difficulty: 2, estimated_time: 45, knowledge_point_codes: ['CONT'],
      common_mistakes: ['与介值定理混淆'], answer: '最值定理', analysis: 'Weierstrass 定理。',
    },
  }

  // ------------------------------------------------------------
  // 认证
  // ------------------------------------------------------------
  function issueTokens(user) {
    const access = `access-${user.user_id}-${Object.keys(state.accessTokens).length + 1}`
    const refresh = `refresh-${user.user_id}-${Object.keys(state.refreshTokens).length + 1}`
    state.accessTokens[access] = user.user_id
    state.refreshTokens[refresh] = user.user_id
    return { access_token: access, refresh_token: refresh }
  }

  function authenticate(config) {
    const raw = normalizeHeader(config, 'Authorization')
    const token = raw.startsWith('Bearer ') ? raw.slice(7) : ''
    return state.accessTokens[token] || null
  }

  function lockoutSeconds(user, nowMs) {
    if (!user.locked_until) return 0
    return Math.max(1, Math.ceil((user.locked_until - nowMs) / 1000))
  }

  function handleLogin(config) {
    const body = parseBody(config)
    if (state.loginBudgetLeft <= 0) {
      // 限流中间件既有结构：detail 是纯字符串，且带 Retry-After
      return { status: 429, data: { detail: '请求过于频繁，请稍后再试' }, headers: { 'retry-after': '60' } }
    }
    state.loginBudgetLeft -= 1
    const nowMs = clock().getTime()
    const user = state.users[body.username]
    if (!user) {
      // 与后端一致：未知用户名不累计失败、不锁定，避免用 423 泄露账号存在性
      return { status: 401, data: { code: 'INVALID_CREDENTIALS', message: '用户名或密码错误', retry_after_seconds: null } }
    }
    if (user.locked_until && user.locked_until > nowMs) {
      const retry = lockoutSeconds(user, nowMs)
      return {
        status: 423,
        data: { code: 'ACCOUNT_LOCKED', message: '账户已临时锁定，请稍后再试', retry_after_seconds: retry },
        headers: { 'retry-after': String(retry) },
      }
    }
    if (user.password !== body.password) return handleFailedPassword(user)
    user.failed_login_count = 0
    user.locked_until = null
    const tokens = issueTokens(user)
    return {
      status: 200,
      data: { status: 'success', data: { user_id: user.user_id, username: user.username, role: user.role, ...tokens } },
    }
  }

  function handleFailedPassword(user) {
    const nowMs = clock().getTime()
    user.failed_login_count += 1
    if (user.failed_login_count >= state.maxFailedLogins) {
      user.locked_until = nowMs + state.lockMinutes * 60_000
      const retry = lockoutSeconds(user, nowMs)
      return {
        status: 423,
        data: { code: 'ACCOUNT_LOCKED', message: '账户已临时锁定，请稍后再试', retry_after_seconds: retry },
        headers: { 'retry-after': String(retry) },
      }
    }
    return { status: 401, data: { code: 'INVALID_CREDENTIALS', message: '用户名或密码错误', retry_after_seconds: null } }
  }

  function handleRefresh(config) {
    const body = parseBody(config)
    const ownerId = state.refreshTokens[body.refresh_token]
    if (!ownerId) return { status: 401, data: { detail: { code: 'INVALID_REFRESH_TOKEN', message: '登录状态已失效' } } }
    const user = Object.values(state.users).find((item) => item.user_id === ownerId)
    return { status: 200, data: { status: 'success', data: issueTokens(user) } }
  }

  // ------------------------------------------------------------
  // 知识目录
  // ------------------------------------------------------------
  function coursePayload() {
    return { id: COURSE_ID, code: 'AM', name: '高等数学', description: '一元微积分', subject: '数学' }
  }

  function pointSummary(point) {
    const { id, code, name, description, difficulty, importance, sort_order, prerequisites, related } = point
    return { id, code, name, description, difficulty, importance, sort_order, prerequisites, related }
  }

  function handleCourseTree() {
    const chapter = {
      id: 'ch-1', code: 'CH1', name: '第 1 章 函数与极限', description: '', sort_order: 1, level: 1, children: [],
      knowledge_points: [pointSummary(knowledgePoints.LIMIT), pointSummary(knowledgePoints.CONT)],
    }
    const chapter2 = {
      id: 'ch-2', code: 'CH2', name: '第 2 章 导数', description: '', sort_order: 2, level: 1, children: [],
      knowledge_points: [pointSummary(knowledgePoints.DERIV)],
    }
    const chapter3 = {
      id: 'ch-3', code: 'CH3', name: '第 3 章 级数与多元积分', description: '', sort_order: 3, level: 1, children: [],
      knowledge_points: [pointSummary(knowledgePoints.SERIES), pointSummary(knowledgePoints.TRIPLE)],
    }
    return {
      status: 200,
      data: {
        course: coursePayload(),
        version: { id: VERSION_ID, name: '2024 版', status: 'published', chapter_count: 3, knowledge_point_count: 5 },
        chapters: [chapter, chapter2, chapter3],
      },
    }
  }

  function findPoint(ref) {
    return Object.values(knowledgePoints).find((p) => p.id === ref || p.code === ref) || null
  }

  // ------------------------------------------------------------
  // 练习：会话 + 判分
  // ------------------------------------------------------------
  function sessionPayload(session) {
    return {
      session_id: session.session_id, mode: 'practice', status: session.status,
      course_id: session.course_id, version_id: session.version_id, config: session.config,
      started_at: session.started_at, completed_at: session.completed_at,
      recovery_snapshot: session.recovery_snapshot || {}, recovery_snapshot_at: null,
      questions: session.questions.map((row) => ({
        question_id: row.question_id, content: row.content, question_type: row.question_type,
        options: row.options, difficulty: row.difficulty, estimated_time: row.estimated_time,
        knowledge_point_codes: row.knowledge_point_codes, common_mistakes: row.common_mistakes,
        position: row.position, score: row.score, attempted: row.attempted,
      })),
      feedback: session.feedback,
    }
  }

  // 幂等键比较时服务端会丢弃的键，这里保持同口径，否则"重放"判定会比真实实现更严
  function comparableConfig(config) {
    const normalized = { ...config }
    delete normalized.random_seed
    delete normalized.resolved_knowledge_point_codes
    if (!normalized.behavior || normalized.behavior === 'immediate') delete normalized.behavior
    if (!normalized.order_mode || normalized.order_mode === 'random') delete normalized.order_mode
    return normalized
  }

  function createPracticeSession(userId, body) {
    const key = `${userId}|${body.idempotency_key}`
    const prior = state.sessionKeys[key]
    if (prior) {
      const priorSession = state.sessions[prior.sessionId]
      if (JSON.stringify(comparableConfig(prior.config)) !== JSON.stringify(comparableConfig(body))) {
        return { status: 409, data: { detail: { code: 'IDEMPOTENCY_CONFLICT', message: '该幂等键已用于不同的练习配置' } } }
      }
      return { status: 200, data: { code: 0, data: sessionPayload(priorSession) } }
    }
    if (!body.course_id || !body.version_id) {
      return { status: 422, data: { detail: { code: 'VALIDATION_FAILED', message: '缺少课程或知识版本' } } }
    }
    // CreatePracticeSessionRequest 的 question_count 是 Field(ge=5, le=20)，越界在真实后端是 422
    if (!(body.question_count >= 5) || body.question_count > 20) {
      return { status: 422, data: { detail: { code: 'VALIDATION_FAILED', message: '题目数量需在 5 到 20 之间' } } }
    }
    const codes = body.knowledge_point_codes || []
    if (!(body.chapter_ids || []).length && !codes.length) {
      return { status: 422, data: { detail: { code: 'VALIDATION_FAILED', message: '至少选择一个章节或知识点' } } }
    }
    const wanted = Object.values(questionBank).filter((q) => !codes.length || q.knowledge_point_codes.some((code) => codes.includes(code)))
    if (wanted.length < (body.question_count || 0)) {
      return {
        status: 422,
        data: { detail: { code: 'INSUFFICIENT_QUESTION_POOL', message: '当前筛选条件下正式题目不足', requested: body.question_count, available: wanted.length } },
      }
    }
    const picked = wanted.slice(0, body.question_count)
    if (!picked.length) {
      return { status: 422, data: { detail: { code: 'INSUFFICIENT_QUESTION_POOL', message: '当前筛选条件下正式题目不足' } } }
    }
    const sessionId = `ps-${Object.keys(state.sessions).length + 1}`
    const session = {
      session_id: sessionId, user_id: userId, status: 'created', course_id: body.course_id,
      version_id: body.version_id, config: { behavior: 'immediate', ...body },
      started_at: null, completed_at: null, recovery_snapshot: {}, feedback: {},
      questions: picked.map((q, index) => ({ ...q, position: index + 1, score: 10, attempted: false, attempts: [] })),
    }
    state.sessions[sessionId] = session
    state.sessionKeys[key] = { sessionId, config: body }
    return { status: 200, data: { code: 0, data: sessionPayload(session) } }
  }

  function startSession(userId, sessionId) {
    const session = state.sessions[sessionId]
    if (!session || session.user_id !== userId) return { status: 404, data: { detail: { code: 'SESSION_NOT_FOUND', message: '练习会话不存在' } } }
    if (session.status === 'completed') return { status: 409, data: { detail: { code: 'SESSION_STATE_CONFLICT', message: '会话已结束' } } }
    if (session.status === 'created') {
      session.status = 'in_progress'
      session.started_at = iso(clock().getTime())
    }
    return { status: 200, data: { code: 0, data: sessionPayload(session) } }
  }

  function grade(session, row, answer) {
    const expected = row.answer
    const given = typeof answer === 'string' ? answer.trim() : answer
    return { correct: String(given) === String(expected), correct_answer: expected }
  }

  function submitAttempt(userId, sessionId, body) {
    const session = state.sessions[sessionId]
    if (!session || session.user_id !== userId) return { status: 404, data: { detail: { code: 'SESSION_NOT_FOUND', message: '练习会话不存在' } } }
    if (session.status !== 'in_progress') return { status: 409, data: { detail: { code: 'SESSION_STATE_CONFLICT', message: '会话尚未开始或已结束' } } }
    const row = session.questions.find((item) => item.question_id === body.question_id)
    if (!row) return { status: 422, data: { detail: { code: 'VALIDATION_FAILED', message: '题目不属于该练习会话' } } }
    const key = `${userId}|${body.idempotency_key}`
    if (state.attemptKeys[key]) return { status: 200, data: { code: 0, data: state.attemptKeys[key] } }
    const { correct, correct_answer: correctAnswer } = grade(session, row, body.answer)
    const result = {
      question_id: row.question_id, question_content: row.content, correct, needs_review: false,
      correct_answer: correctAnswer, analysis: row.analysis, difficulty: row.difficulty,
      estimated_time: row.estimated_time, knowledge_point_codes: row.knowledge_point_codes,
      error_category: correct ? null : 'concept', error_classification: correct ? null : { category: 'concept', confidence: 0.8, evidence: '答案与参考解答不一致' },
      learning_signals: { hint_used: Boolean(body.hint_used), behavior: 'immediate', retry_count: 0 },
      submissions: [{ answer: body.answer, correct, submitted_at: iso(clock().getTime()) }],
      retry_count: 0, attempt_id: `at-${row.attempts.length + 1}-${row.question_id}`,
    }
    row.attempts.push(result)
    row.attempted = true
    session.feedback[row.question_id] = result
    state.attemptKeys[key] = result
    return { status: 200, data: { code: 0, data: result } }
  }

  function saveRecoverySnapshot(userId, sessionId, body) {
    const session = state.sessions[sessionId]
    if (!session || session.user_id !== userId) return { status: 404, data: { detail: { code: 'SESSION_NOT_FOUND', message: '练习会话不存在' } } }
    if (session.status !== 'in_progress') return { status: 409, data: { detail: { code: 'SESSION_STATE_CONFLICT', message: '会话尚未开始' } } }
    session.recovery_snapshot = { current_question_id: body?.current_question_id ?? null }
    return { status: 200, data: { code: 0, data: { completed: false, saved: true } } }
  }

  // ------------------------------------------------------------
  // 错题本
  // ------------------------------------------------------------
  function handleErrorField(body) {
    // 与 ErrorItemRequest 同口径：未提供的可选字段回填默认值，而不是原样透传客户端负载
    const nowMs = clock().getTime()
    const id = body.id && body.id !== '' ? String(body.id) : `err-${Object.keys(state.errorItems).length + 1}`
    const item = {
      id, question: body.question, question_type: body.question_type ?? 'text',
      image_path: body.image_path ?? null, error_reason: body.error_reason ?? '',
      categories: body.categories ?? [], original_answer: body.original_answer ?? '',
      correct_answer: body.correct_answer ?? '', notes: body.notes ?? '',
      added_at: body.added_at || iso(nowMs), mastery_level: body.mastery_level ?? 3,
      is_mastered: body.is_mastered ?? false,
      display_question: body.question, answer_preview: (body.correct_answer ?? '').slice(0, 30),
      has_image: Boolean(body.image_path), recognized_text: '',
    }
    state.errorItems[id] = item
    return item
  }

  // ------------------------------------------------------------
  // 复习排期 + 提醒（派生聚合，语义对齐 app/services/reminders.py）
  // ------------------------------------------------------------
  function scheduleItems(includeUpcoming, nowMs) {
    const rows = Object.values(state.schedules)
      .filter((row) => (includeUpcoming ? true : row.due_at <= nowMs && (!row.deferred_until || row.deferred_until <= nowMs)))
      .map((row) => ({
        id: row.id, knowledge_point_code: row.knowledge_point_code, knowledge_point_name: row.knowledge_point_name,
        due_at: iso(row.due_at), interval_days: row.interval_days, review_count: row.review_count,
        stage: row.stage, algorithm_version: row.algorithm_version, source: 'knowledge_point',
        error_item_id: null, question_id: null,
      }))
    const errors = Object.values(state.errorReviews)
      .filter((row) => row.due_at !== null && (includeUpcoming ? true : row.due_at <= nowMs))
      .map((row) => ({
        id: row.id, knowledge_point_code: row.knowledge_point_code, knowledge_point_name: row.knowledge_point_name,
        due_at: iso(row.due_at), interval_days: row.interval_days, review_count: row.review_count,
        stage: row.stage, algorithm_version: row.algorithm_version, source: 'error_item',
        error_item_id: row.error_item_id, question_id: row.question_id,
      }))
    return [...rows, ...errors].sort((a, b) => String(a.due_at).localeCompare(String(b.due_at)))
  }

  function effectiveDue(item) {
    const schedule = state.schedules[item.id]
    const dueMs = Date.parse(item.due_at)
    if (schedule?.deferred_until && schedule.deferred_until > dueMs) return schedule.deferred_until
    return dueMs
  }

  function classify(item, nowMs) {
    const dueMs = effectiveDue(item)
    if (!Number.isFinite(dueMs)) return 'today'
    if (dueMs < nowMs - DAY) return 'overdue'
    if (dueMs <= nowMs) return 'today'
    return dueMs <= nowMs + 2 * DAY ? 'upcoming' : ''
  }

  function buildRemindersResponse(nowMs) {
    const merged = new Map()
    scheduleItems(true, nowMs).forEach((item) => merged.set(`${item.source}:${item.id}`, item))
    scheduleItems(false, nowMs).forEach((item) => merged.set(`${item.source}:${item.id}`, item))
    const items = []
    merged.forEach((item) => {
      const bucket = classify(item, nowMs)
      if (!bucket) return
      const dueMs = effectiveDue(item)
      items.push({
        key: `${item.source}:${item.id}`,
        kind: item.source === 'error_item' ? 'error_review' : 'review_schedule',
        bucket,
        source: item.source,
        schedule_id: item.source === 'error_item' ? null : item.id,
        error_item_id: item.error_item_id,
        question_id: item.question_id,
        knowledge_point_code: item.knowledge_point_code,
        knowledge_point_name: item.knowledge_point_name,
        due_at: item.due_at,
        overdue_minutes: dueMs <= nowMs ? Math.floor((nowMs - dueMs) / MINUTE) : 0,
        title: item.source === 'error_item' ? `重练错题 · ${item.knowledge_point_name}` : `复习 ${item.knowledge_point_name}`,
        hint: bucket === 'overdue' ? '已逾期' : bucket === 'today' ? '今日到期' : '即将到期',
        interval_days: item.interval_days,
        review_count: item.review_count,
        algorithm_version: item.algorithm_version,
        action: item.source === 'error_item'
          ? { route: `/error-book/${item.error_item_id}`, query: {} }
          : { route: '/knowledge', query: { point: item.knowledge_point_code } },
        can_defer: item.source !== 'error_item',
        defer_disabled_reason: item.source === 'error_item'
          ? '错题复习节奏由错题本自动排期，暂不支持单独稍后提醒'
          : null,
      })
    })
    items.sort((a, b) => String(a.due_at).localeCompare(String(b.due_at)))
    const counts = {
      overdue: items.filter((i) => i.bucket === 'overdue').length,
      today: items.filter((i) => i.bucket === 'today').length,
      upcoming: items.filter((i) => i.bucket === 'upcoming').length,
      total: items.length,
    }
    return {
      status: 200,
      data: {
        generated_at: iso(nowMs),
        version: 'reminders-derived-v1',
        counts,
        items,
        primary: {
          id: 'review:4101', type: 'review', title: '复习「极限的四则运算」',
          target_knowledge_point: { code: 'LIMIT', name: '极限的四则运算' },
          reason: '该知识点的复习计划已到期', evidence: [], estimated_minutes: 8, priority: 1,
          available_question_count: 2, start: { path: '/apply/practice', query: { knowledge_point: 'LIMIT' } },
          degradation: null,
        },
      },
    }
  }

  function deferSchedule(userId, scheduleId, body) {
    const schedule = state.schedules[scheduleId]
    if (!schedule) return { status: 404, data: { detail: { code: 'REVIEW_NOT_FOUND', message: '复习计划不存在' } } }
    const prior = schedule.actions[body.idempotency_key]
    if (prior) {
      if (prior.action !== 'defer' || prior.hours !== (body.defer_hours || 24)) {
        return { status: 409, data: { detail: { code: 'IDEMPOTENCY_CONFLICT', message: '幂等键已用于不同操作' } } }
      }
      return { status: 200, data: prior.result }
    }
    const hours = body.defer_hours || 24
    const nowMs = clock().getTime()
    schedule.deferred_until = nowMs + hours * HOUR
    const result = {
      id: schedule.id, knowledge_point_code: schedule.knowledge_point_code, knowledge_point_name: schedule.knowledge_point_name,
      due_at: iso(schedule.due_at), interval_days: schedule.interval_days, review_count: schedule.review_count,
      stage: schedule.stage, algorithm_version: schedule.algorithm_version, source: 'knowledge_point',
      error_item_id: null, question_id: null,
    }
    schedule.actions[body.idempotency_key] = { action: 'defer', hours, result }
    return { status: 200, data: result }
  }

  // ------------------------------------------------------------
  // 路由表
  // ------------------------------------------------------------
  const routes = [
    { method: 'post', pattern: /^\/auth\/login$/, auth: false, handler: (config) => handleLogin(config) },
    { method: 'post', pattern: /^\/auth\/register$/, auth: false, handler: () => ({ status: 409, data: { detail: '用户名已存在' } }) },
    { method: 'post', pattern: /^\/auth\/refresh$/, auth: false, handler: (config) => handleRefresh(config) },
    { method: 'get', pattern: /^\/knowledge\/courses$/, handler: () => ({ status: 200, data: { courses: [coursePayload()] } }) },
    { method: 'get', pattern: /^\/knowledge\/courses\/([^/]+)\/tree$/, handler: () => handleCourseTree() },
    { method: 'get', pattern: /^\/knowledge\/points\/([^/]+)$/, handler: (config, m) => {
      const point = findPoint(decodeURIComponent(m[1]))
      if (!point) return { status: 404, data: { detail: '未找到已发布知识点' } }
      return { status: 200, data: { ...point, ...pointSummary(point), common_errors: [], key_formulas: [] } }
    } },
    { method: 'get', pattern: /^\/knowledge\/points\/([^/]+)\/learning$/, handler: (config, m) => {
      const point = findPoint(decodeURIComponent(m[1]))
      if (!point) return { status: 404, data: { detail: '未找到已发布知识点' } }
      return { status: 200, data: { ...pointSummary(point), course: point.course, version: point.version, resources: point.resources, prerequisite_points: point.prerequisite_points } }
    } },
    { method: 'get', pattern: /^\/practice\/options$/, handler: () => ({
      status: 200,
      data: {
        code: 0,
        data: {
          courses: [{ id: COURSE_ID, name: '高等数学', default_version_id: VERSION_ID }],
          course_id: COURSE_ID, version_id: VERSION_ID,
          chapters: [{ id: 'ch-1', name: '第 1 章 函数与极限', parent_id: null, level: 1 }],
          knowledge_points: [{ code: 'LIMIT', name: '极限的四则运算', chapter_id: 'ch-1' }, { code: 'DERIV', name: '导数的几何意义', chapter_id: 'ch-2' }],
          question_types: [{ value: 'text', available: 5 }],
        },
      },
    }) },
    { method: 'post', pattern: /^\/practice\/sessions$/, handler: (config, m, ctx) => createPracticeSession(ctx.userId, parseBody(config)) },
    { method: 'post', pattern: /^\/practice\/sessions\/([^/]+)\/start$/, handler: (config, m, ctx) => startSession(ctx.userId, decodeURIComponent(m[1])) },
    { method: 'post', pattern: /^\/practice\/sessions\/([^/]+)\/attempts$/, handler: (config, m, ctx) => submitAttempt(ctx.userId, decodeURIComponent(m[1]), parseBody(config)) },
    { method: 'put', pattern: /^\/practice\/sessions\/([^/]+)\/recovery-snapshot$/, handler: (config, m, ctx) => saveRecoverySnapshot(ctx.userId, decodeURIComponent(m[1]), parseBody(config)) },
    { method: 'get', pattern: /^\/error-book$/, handler: (config, m, ctx) => ({ status: 200, data: Object.values(state.errorItems).filter((item) => item.user_id === ctx.userId || !item.user_id) }) },
    { method: 'post', pattern: /^\/error-book$/, handler: (config, m, ctx) => {
      const item = handleErrorField(parseBody(config))
      item.user_id = ctx.userId
      return { status: 200, data: { id: item.id, status: 'success', message: '错题添加成功', data: item } }
    } },
    { method: 'get', pattern: /^\/learning\/reviews\/due$/, handler: (config, m, ctx) => {
      const nowMs = clock().getTime()
      const includeUpcoming = Boolean(config.params?.include_upcoming)
      return { status: 200, data: { generated_at: iso(nowMs), items: scheduleItems(includeUpcoming, nowMs) } }
    } },
    { method: 'post', pattern: /^\/learning\/reviews\/(\d+)\/actions$/, handler: (config, m, ctx) => deferSchedule(ctx.userId, Number(m[1]), parseBody(config)) },
    { method: 'get', pattern: /^\/learning\/reminders$/, handler: (config, m, ctx) => buildRemindersResponse(clock().getTime()) },
  ]

  function dispatch(config) {
    const method = String(config.method || 'get').toLowerCase()
    const full = `${config.baseURL || ''}${config.url || ''}`
    const path = full.replace(/^\/api/, '')
    const clean = path.split('?')[0]
    const matched = routes.find((route) => route.method === method && route.pattern.test(clean))
    const userId = authenticate(config)
    const record = { method, path: clean, url: full, body: parseBody(config), params: config.params || {}, headers: { authorization: normalizeHeader(config, 'Authorization') }, userId }
    state.requests.push(record)
    if (!matched) {
      return { status: 404, data: { detail: `fake backend 未实现 ${method.toUpperCase()} ${clean}` } }
    }
    // 与真实中间件一致的顺序：先认证再业务，未认证拿到结构化 401
    if (matched.auth !== false && !userId) {
      return { status: 401, data: { detail: { code: 'UNAUTHENTICATED', message: '请先登录' } } }
    }
    const m = matched.pattern.exec(clean)
    record.userId = userId
    return matched.handler(config, m, { userId })
  }

  function adapter(config) {
    return new Promise((resolve, reject) => {
      const outcome = dispatch(config)
      const response = {
        data: outcome.data,
        status: outcome.status,
        statusText: STATUS_TEXT[outcome.status] || '',
        headers: { 'content-type': 'application/json', ...(outcome.headers || {}) },
        config,
        request: {},
      }
      const validate = config.validateStatus
      if (!outcome.status || !validate || validate(outcome.status)) {
        resolve(response)
        return
      }
      reject(new AxiosError(
        `Request failed with status code ${outcome.status}`,
        outcome.status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
        config,
        response.request,
        response,
      ))
    })
  }

  return {
    adapter,
    state,
    requests: state.requests,
    lastRequest: () => state.requests[state.requests.length - 1] || null,
    requestsFor: (needle) => state.requests.filter((item) => item.path.includes(needle)),
    // 直接暴露领域写回，让测试可以制造"服务端状态已变化"的场景而不必靠多次点击模拟
    patchSchedule: (id, changes) => Object.assign(state.schedules[id] || {}, changes),
    setLoginBudget: (left) => { state.loginBudgetLeft = left },
  }
}
