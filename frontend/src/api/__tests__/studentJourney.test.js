/**
 * 学生主链闭环回归（Vitest + 进程内假后端）。
 *
 * 这一层的定位不是"组件渲染快照"，而是"客户端真的按后端契约走了一遍"：
 * adapter 注入让 @/api 的 Authorization 拦截器、401 刷新/重放规则、各模块的 unwrap
 * 语义全部按生产路径执行。因此它能抓住"字段语义漂移 / 空函数"这类回归——
 * 例如 ChatView 的 openErrorBookDialog 事故（调用存在但什么都没发生）。
 *
 * 链路：登录 → 课程树 → 知识点学习页 → 创建会话 → 提交作答 → 判分驱动 practiceStore
 *      → 答错项入错题本 → reviews/due → 提醒中心计数/排序 → defer 幂等。
 */
import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import api, { setAuthTokenGetter } from '@/api'
import { useAuthStore } from '@/stores/authStore'
import { usePracticeStore } from '@/stores/practiceStore'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { useReminderStore } from '@/stores/reminderStore'
import { listCourses, getCourseTree, getKnowledgePointLearning } from '@/api/knowledge'
import { deferReview, getDueReviews } from '@/api/learning'
import { createFakeBackend, FAKE_ACCOUNT } from './fakeBackend'

// app/api/error_api.py::ErrorItemRequest 的字段集合，多一个少一个都算契约漂移
const ERROR_ITEM_REQUEST_FIELDS = [
  'id', 'question', 'question_type', 'image_path', 'error_reason', 'categories',
  'original_answer', 'correct_answer', 'notes', 'added_at', 'mastery_level', 'is_mastered',
]

let fake
let realAdapter

beforeAll(() => {
  realAdapter = api.defaults.adapter
})

afterAll(() => {
  api.defaults.adapter = realAdapter
  setAuthTokenGetter(null)
})

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  fake = createFakeBackend()
  api.defaults.adapter = fake.adapter
  // 与 main.js 同口径：token 由拦截器统一注入，api 模块不手动拼 Authorization
  setAuthTokenGetter(() => useAuthStore().getAccessToken())
})

async function loginAsStudent() {
  const auth = useAuthStore()
  await auth.login({ username: FAKE_ACCOUNT.username, password: FAKE_ACCOUNT.password })
  return auth
}

describe('学生主链闭环', () => {
  it('登录 → 知识目录 → 练习判分 → 错题本 → 提醒中心 → 稍后提醒，全链路字段一致', async () => {
    // ---- 1. 登录：token 落库 + Authorization 由拦截器注入 ----
    const auth = await loginAsStudent()
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.userId).toBe(FAKE_ACCOUNT.user_id)
    expect(auth.role).toBe('student')
    expect(auth.lastAuthError).toBeNull()
    expect(localStorage.getItem('auth_token')).toBe(auth.getAccessToken())

    const loginRequest = fake.requestsFor('/auth/login')[0]
    expect(loginRequest.headers.authorization).toBe('') // 登录自身不带凭据头
    expect(loginRequest.body).toEqual({ username: FAKE_ACCOUNT.username, password: FAKE_ACCOUNT.password })

    // ---- 2. 课程树：进入知识点学习页所需字段齐备 ----
    const { data: courseList } = await listCourses()
    const course = courseList.courses[0]
    const courseRequest = fake.requestsFor('/knowledge/courses')[0]
    expect(courseRequest.headers.authorization).toBe(`Bearer ${auth.getAccessToken()}`)

    const { data: tree } = await getCourseTree(course.id)
    const treePoints = tree.chapters.flatMap((chapter) => chapter.knowledge_points)
    expect(tree.course.id).toBe(course.id)
    expect(tree.version.id).toBeTruthy()
    expect(treePoints.map((point) => point.id)).toContain('kp-limit')
    // 提醒中心深链只带 code，目录侧必须能用 code 找到同一个点（id/code 语义不能漂移）
    expect(treePoints.map((point) => point.code)).toContain('LIMIT')

    const { data: learning } = await getKnowledgePointLearning('kp-limit')
    expect(learning.code).toBe('LIMIT')
    expect(learning.course.id).toBe(course.id)
    expect(learning.version.id).toBe(tree.version.id)
    expect(learning.resources.length).toBeGreaterThan(0)
    expect(learning.resources.every((r) => r.id && r.type && r.title)).toBe(true)
    // KnowledgeLearningView 的"去练习"依赖 exercise/exercise_set 资源存在
    expect(learning.resources.some((r) => ['exercise', 'exercise_set'].includes(r.type))).toBe(true)

    // ---- 3. 创建会话 + 提交作答：判题结果驱动 practiceStore ----
    const practice = usePracticeStore()
    await practice.loadOptions(course.id)
    expect(practice.options.course_id).toBe(course.id)
    expect(practice.options.version_id).toBe(tree.version.id)
    practice.draft.knowledge_point_codes = ['LIMIT', 'DERIV', 'CONT']
    practice.draft.question_types = ['text']
    practice.draft.question_count = 5

    const created = await practice.create()
    expect(created.status).toBe('created')
    expect(created.questions).toHaveLength(5)
    expect(created.questions[0]).toHaveProperty('question_id')
    // 会话载荷不得回传答案：判分真值只属于服务端
    expect(JSON.stringify(created.questions)).not.toContain('"answer"')

    await practice.start()
    expect(practice.session.status).toBe('in_progress')

    const wrongQuestion = practice.session.questions.find((q) => q.question_id === 'q-derivative-tangent')
    practice.currentIndex = practice.session.questions.indexOf(wrongQuestion)
    expect(practice.currentQuestion.question_id).toBe('q-derivative-tangent')
    practice.answers['q-derivative-tangent'] = '1'
    const wrongFeedback = await practice.submitCurrent()
    expect(wrongFeedback.correct).toBe(false)
    expect(wrongFeedback.error_category).toBe('concept')
    expect(practice.feedback['q-derivative-tangent'].correct_answer).toBe('2')
    // immediate 行为下答错可重试一次：这是 PracticeSessionView 的按钮可见性依据
    expect(practice.canRetry('q-derivative-tangent')).toBe(true)
    expect(practice.retryLimit).toBe(1)

    const rightIndex = practice.session.questions.findIndex((q) => q.question_id === 'q-limit-value')
    practice.currentIndex = rightIndex
    practice.answers['q-limit-value'] = '2'
    const rightFeedback = await practice.submitCurrent()
    expect(rightFeedback.correct).toBe(true)
    expect(practice.canRetry('q-limit-value')).toBe(false)

    const attemptRequest = fake.requestsFor('/attempts')[0]
    expect(Object.keys(attemptRequest.body).sort()).toEqual(
      ['answer', 'hint_used', 'idempotency_key', 'question_id'].sort(),
    )

    // ---- 4. 答错项入错题本：payload 与后端 Pydantic 模型逐字段一致 ----
    const errorBook = useErrorBookStore()
    const added = await errorBook.addError({
      id: '',
      question: wrongQuestion.content,
      question_type: wrongQuestion.question_type,
      image_path: null,
      error_reason: '切线斜率用成了割线斜率',
      categories: wrongQuestion.knowledge_point_codes,
      original_answer: '1',
      correct_answer: wrongFeedback.correct_answer,
      notes: '',
      added_at: '',
      mastery_level: 3,
      is_mastered: false,
    })
    const errorRequest = fake.requestsFor('/error-book').find((r) => r.method === 'post')
    expect(Object.keys(errorRequest.body).sort()).toEqual([...ERROR_ITEM_REQUEST_FIELDS].sort())
    expect(errorRequest.body.categories).toEqual(['DERIV'])
    expect(added.id).toBeTruthy()
    expect(errorBook.errors[0].id).toBe(added.id)
    // ErrorBookView 渲染的是服务端回写的 display_question，而不是本地猜测
    expect(errorBook.errors[0].display_question).toBe(wrongQuestion.content)

    // ---- 5. 到期复习 → 提醒中心计数与排序 ----
    const { data: due } = await getDueReviews(false)
    expect(due.items.map((item) => item.id)).toEqual([4101, 4102, 'error-err-001'])
    expect(due.items.every((item) => Date.parse(item.due_at) <= Date.now())).toBe(true)

    const reminders = useReminderStore()
    expect(reminders.badge).toBe(0) // 未拉取前不得凭空出现角标
    expect(await reminders.fetch({ force: true })).toBe(true)
    expect(reminders.counts).toEqual({ overdue: 1, today: 2, upcoming: 1, total: 4 })
    expect(reminders.counts.total).toBe(reminders.items.length)
    expect(reminders.badge).toBe(reminders.counts.overdue + reminders.counts.today)
    expect(reminders.items.map((item) => item.knowledge_point_code)).toEqual(['LIMIT', 'CONT', 'DERIV', 'SERIES'])
    expect(reminders.items.map((item) => item.bucket)).toEqual(['overdue', 'today', 'today', 'upcoming'])
    // 48h 之外的排期不该挤进提醒（TRIPLE 在 30 天后）
    expect(reminders.items.some((item) => item.knowledge_point_code === 'TRIPLE')).toBe(false)
    // 未排期错题（next_review_at 为空）不得被伪造成"今日到期"
    expect(reminders.items.some((item) => item.error_item_id === 'err-unranked')).toBe(false)
    // 提醒里的每个知识点都必须能在课程目录里定位到
    const treeCodes = treePoints.map((point) => point.code)
    expect(reminders.items.every((item) => treeCodes.includes(item.knowledge_point_code))).toBe(true)
    expect(reminders.urgent).toHaveLength(3)
    expect(reminders.primary).toMatchObject({ id: 'review:4101' })

    // 深链形态：知识点级用 ?point=<code>，错题级用 /error-book/<error_item_id>
    const pointReminder = reminders.items.find((item) => item.source === 'knowledge_point')
    expect(pointReminder.action).toEqual({ route: '/knowledge', query: { point: 'LIMIT' } })
    const errorReminder = reminders.items.find((item) => item.source === 'error_item')
    expect(errorReminder.action).toEqual({ route: '/error-book/err-001', query: {} })
    // 错题级没有 deferred_until 字段，因此不提供"稍后提醒"
    expect(errorReminder.can_defer).toBe(false)
    expect(errorReminder.schedule_id).toBeNull()
    expect(errorReminder.defer_disabled_reason).toContain('错题')
    expect(await reminders.defer(errorReminder)).toBe(false)
    expect(fake.requestsFor('/actions')).toHaveLength(0)

    // ---- 6. 稍后提醒：复用服务端 defer，分档随之迁移 ----
    const contReminder = reminders.items.find((item) => item.schedule_id === 4102)
    expect(contReminder.bucket).toBe('today')
    expect(await reminders.defer(contReminder)).toBe(true)
    const deferRequest = fake.requestsFor('/learning/reviews/4102/actions')[0]
    expect(deferRequest.body).toEqual({ action: 'defer', defer_hours: 24, idempotency_key: expect.any(String) })
    expect(reminders.items.find((item) => item.schedule_id === 4102).bucket).toBe('upcoming')
    expect(reminders.counts).toEqual({ overdue: 1, today: 1, upcoming: 2, total: 4 })
    // 提醒拉取失败/主流程不得被拖慢：这里确认全链路只走过一次 refresh 之外的正常请求
    expect(fake.requestsFor('/auth/refresh')).toHaveLength(0)
  })

  it('defer 幂等键重放返回同一结果，同键改时长则 409 冲突', async () => {
    await loginAsStudent()
    const reminders = useReminderStore()
    await reminders.fetch({ force: true })
    const key = 'defer-idempotent-key-0001'

    const first = await deferReview(4102, 24, key)
    const deferredUntil = fake.state.schedules[4102].deferred_until
    const second = await deferReview(4102, 24, key)
    expect(second.data).toEqual(first.data)
    // 重放不得把到期时间再往后推一格
    expect(fake.state.schedules[4102].deferred_until).toBe(deferredUntil)

    await expect(deferReview(4102, 48, key)).rejects.toMatchObject({
      response: { status: 409, data: { detail: { code: 'IDEMPOTENCY_CONFLICT' } } },
    })
  })

  it('会话越界配置按后端校验语义失败，practiceStore 记录可读文案', async () => {
    const auth = await loginAsStudent()
    const practice = usePracticeStore()
    await practice.loadOptions('course-advanced-math')
    practice.draft.knowledge_point_codes = ['LIMIT']
    practice.draft.question_count = 2 // CreatePracticeSessionRequest: ge=5
    await expect(practice.create()).rejects.toBeTruthy()
    expect(practice.errorKind).toBe('create')
    expect(practice.error).toBe('题目数量需在 5 到 20 之间')
    expect(practice.session).toBeNull()
    expect(auth.isAuthenticated).toBe(true) // 业务 422 不得把用户踢下线
  })

  it('未登录访问提醒端点得到结构化 401，且提醒失败保持静默', async () => {
    const reminders = useReminderStore()
    // 未认证 → auth.userId 为空 → 直接不发请求（避免匿名请求撞上登录限流预算）
    expect(await reminders.fetch({ force: true })).toBe(false)
    expect(fake.requestsFor('/learning/reminders')).toHaveLength(0)

    localStorage.setItem('auth_token', 'stale-token-from-another-device')
    const auth = useAuthStore()
    // 有旧身份 + 失效 token（换设备/长时间未打开）：拉取必须失败得特别安静
    auth.currentUser = { user_id: 'u-stale', username: 'stale', role: 'student' }
    const refreshed = await reminders.fetch({ force: true })
    expect(refreshed).toBe(false)
    expect(reminders.lastError).toContain('401')
    expect(reminders.badge).toBe(0) // 失败必须安静：不留任何可被误当成"你的提醒"的数据
    expect(reminders.items).toEqual([])
  })

  it('密码错误只回 401 INVALID_CREDENTIALS，不刷新、不重放、不清会话', async () => {
    const auth = await loginAsStudent()
    const goodToken = auth.getAccessToken()
    auth.lastAuthError = null

    await expect(auth.login({ username: FAKE_ACCOUNT.username, password: 'wrong-password' })).rejects.toBeTruthy()
    expect(auth.lastAuthError).toMatchObject({
      status: 401,
      code: 'INVALID_CREDENTIALS',
      message: '用户名或密码错误',
      locked: false,
      rateLimited: false,
    })
    expect(fake.requestsFor('/auth/login')).toHaveLength(2) // 失败的那次没有被重放
    expect(fake.requestsFor('/auth/refresh')).toHaveLength(0)
    // 其它账号的既有会话不能被一次失败登录清掉
    expect(localStorage.getItem('auth_token')).toBe(goodToken)
  })

  it('连续失败触发账户锁定：423 + Retry-After，锁定期间正确密码也被拒', async () => {
    const auth = useAuthStore()
    const maxFailed = fake.state.maxFailedLogins
    let lastError = null
    for (let attempt = 0; attempt < maxFailed; attempt += 1) {
      try {
        await auth.login({ username: FAKE_ACCOUNT.username, password: 'bad-password' })
      } catch (err) {
        lastError = auth.lastAuthError
      }
    }
    expect(lastError).toMatchObject({ status: 423, code: 'ACCOUNT_LOCKED', locked: true })
    expect(lastError.retryAfterSeconds).toBeGreaterThan(0)
    expect(fake.state.users[FAKE_ACCOUNT.username].locked_until).toBeGreaterThan(Date.now())

    // 锁定生效：即便这次密码是对的，也必须拿到 423，而不是悄悄放行
    await expect(auth.login({ username: FAKE_ACCOUNT.username, password: FAKE_ACCOUNT.password })).rejects.toBeTruthy()
    expect(auth.lastAuthError).toMatchObject({ status: 423, code: 'ACCOUNT_LOCKED' })
    expect(auth.isAuthenticated).toBe(false)
    expect(fake.requestsFor('/auth/login')).toHaveLength(maxFailed + 1)
    expect(fake.requestsFor('/auth/refresh')).toHaveLength(0)
  })

  it('登录预算耗尽回 429（既有结构不变），归一化为可倒计时文案', async () => {
    const auth = useAuthStore()
    fake.setLoginBudget(0)
    await expect(auth.login({ username: FAKE_ACCOUNT.username, password: FAKE_ACCOUNT.password })).rejects.toBeTruthy()
    expect(auth.lastAuthError).toMatchObject({
      status: 429,
      code: 'RATE_LIMITED',
      message: '请求过于频繁，请稍后再试',
      rateLimited: true,
    })
    // Retry-After 头兜底（响应体没有 retry_after_seconds 时仍要能倒计时）
    expect(auth.lastAuthError.retryAfterSeconds).toBe(60)
    expect(fake.requestsFor('/auth/login')).toHaveLength(1)
  })

  it('未知用户名只回 401，绝不因为 423 泄露账号是否存在', async () => {
    const auth = useAuthStore()
    for (let attempt = 0; attempt < 8; attempt += 1) {
      await auth.login({ username: 'no_such_student', password: 'whatever' }).catch(() => {})
    }
    const loginCalls = fake.requestsFor('/auth/login').length
    expect(loginCalls).toBe(8)
    expect(auth.lastAuthError).toMatchObject({ status: 401, code: 'INVALID_CREDENTIALS', locked: false })
    expect(fake.state.users[FAKE_ACCOUNT.username].locked_until).toBeNull()
  })
})
