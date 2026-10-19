import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录 - 数学AI助手', transition: 'fade', guestOnly: true },
  },
  { path: '/notes', name: 'NotesLibrary', component: () => import('@/views/NotesLibraryView.vue'), meta: { title: '我的笔记 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/notes/:noteId', name: 'NoteWorkspace', component: () => import('@/views/NoteWorkspaceView.vue'), meta: { title: '手写笔记 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '智能对话 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/chat/:chatId',
    name: 'ChatDetail',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '智能对话 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/error-book',
    name: 'ErrorBook',
    component: () => import('@/views/ErrorBookView.vue'),
    meta: { title: '错题本 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/error-book/:errorId',
    name: 'ErrorDetail',
    component: () => import('@/views/ErrorBookView.vue'),
    meta: { title: '错题详情 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/knowledge',
    name: 'KnowledgeCatalog',
    component: () => import('@/views/KnowledgeCatalogView.vue'),
    meta: { title: '课程知识目录 - 数学AI助手', transition: 'slide-fade' },
  },
  {
    path: '/knowledge/points/:pointId/learn',
    name: 'KnowledgeLearning',
    component: () => import('@/views/KnowledgeLearningView.vue'),
    meta: { title: '知识点学习 - 数学AI助手', transition: 'slide-fade' },
  },
  {
    // 别名入口：/knowledge/{code} 等旧式链接。学习页接口支持 id-or-code 解析，
    // 因此这里直接复用同一视图，route.params.pointId 即可携带 code。
    path: '/knowledge/:pointId',
    name: 'KnowledgeLearningAlias',
    component: () => import('@/views/KnowledgeLearningView.vue'),
    meta: { title: '知识点学习 - 数学AI助手', transition: 'slide-fade' },
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '学习看板 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/views/NotificationCenterView.vue'),
    meta: { title: '通知中心 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { title: '记忆画像 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/learning/path',
    name: 'LearningPath',
    component: () => import('@/views/LearningPathView.vue'),
    meta: { title: '我的学习路径 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/paper/test',
    redirect: '/apply/practice',
  },
  { path: '/apply', name: 'ApplyHub', component: () => import('@/views/ApplyHubView.vue'), meta: { title: '学以致用 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/practice', name: 'PracticeSetup', component: () => import('@/views/PracticeSetupView.vue'), meta: { title: '专项练习 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/practice/sessions/:sessionId', name: 'PracticeSession', component: () => import('@/views/PracticeSessionView.vue'), meta: { title: '专项练习 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/practice/sessions/:sessionId/result', name: 'PracticeResult', component: () => import('@/views/PracticeResultView.vue'), meta: { title: '专项练习结果 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/assessment', name: 'AssessmentSetup', redirect: '/apply/papers/new?source=ai', meta: { title: '智能组卷 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/assessment/sessions/:sessionId', name: 'AssessmentSession', component: () => import('@/views/AssessmentSessionView.vue'), meta: { title: '智能组卷 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/assessment/sessions/:sessionId/result', name: 'AssessmentResult', component: () => import('@/views/AssessmentResultView.vue'), meta: { title: '智能组卷报告 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/chapter-diagnostics/new', name: 'ChapterDiagnosticSetup', component: () => import('@/views/ChapterDiagnosticSetupView.vue'), meta: { title: '开始章节诊断 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/chapter-diagnostics/:sessionId', name: 'ChapterDiagnostic', component: () => import('@/views/ChapterDiagnosticView.vue'), meta: { title: '章节诊断 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/chapter-diagnostics/:sessionId/result', name: 'ChapterDiagnosticResult', component: () => import('@/views/ChapterDiagnosticResultView.vue'), meta: { title: '章节诊断报告 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/papers', name: 'StudentPapers', component: () => import('@/views/StudentPapersView.vue'), meta: { title: '我的试卷 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/papers/new', name: 'StudentPaperCreate', component: () => import('@/views/StudentPaperCreateView.vue'), meta: { title: '智能组卷 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/papers/:paperId/edit', name: 'StudentPaperEditor', component: () => import('@/views/StudentPaperEditorView.vue'), meta: { title: '编辑试卷 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/papers/:paperId', name: 'StudentPaperDetail', component: () => import('@/views/StudentPaperDetailView.vue'), meta: { title: '试卷详情 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/exam', name: 'ExamSetup', component: () => import('@/views/ExamSetupView.vue'), meta: { title: '自主考试 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/exam/sessions/:sessionId', name: 'ExamSession', component: () => import('@/views/ExamSessionView.vue'), meta: { title: '自主考试 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/exam/sessions/:sessionId/report', name: 'ExamReport', component: () => import('@/views/ExamReportView.vue'), meta: { title: '考试报告 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  {
    path: '/admin',
    name: 'AdminHome',
    component: () => import('@/views/AdminHomeView.vue'),
    meta: { title: '管理后台 - 数学AI助手', transition: 'slide-fade', requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/review',
    name: 'AdminReview',
    component: () => import('@/views/AdminReviewView.vue'),
    meta: { title: '题库审核工作台 - 数学AI助手', transition: 'slide-fade', requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/papers',
    name: 'AdminPapers',
    component: () => import('@/views/AdminPapersView.vue'),
    meta: { title: '组卷工作台 - 数学AI助手', transition: 'slide-fade', requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/readiness',
    name: 'AdminReadiness',
    component: () => import('@/views/AdminReadinessView.vue'),
    meta: { title: '能力就绪度 - 数学AI助手', transition: 'slide-fade', requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/agent-metrics',
    name: 'AdminAgentMetrics',
    component: () => import('@/views/AdminAgentMetricsView.vue'),
    meta: { title: 'Agent 指标 - 数学AI助手', transition: 'slide-fade', requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/quality',
    name: 'AdminQuality',
    component: () => import('@/views/AdminQualityView.vue'),
    meta: { title: '回答质量抽检 - 数学AI助手', transition: 'slide-fade', requiresAuth: true, requiresAdmin: true },
  },
  {
    // 兜底 404：未知路径不再渲染空白页（历史 bug：/knowledge/{code} 等死链白屏）
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在 - 数学AI助手' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.title) {
    document.title = to.meta.title
  }

  const authStore = useAuthStore()

  if (to.meta.guestOnly && authStore.isAuthenticated) {
    return authStore.role === 'admin' ? { path: '/admin' } : { path: '/' }
  }

  // 路由守卫：受保护页面需要认证
  if (to.meta.requiresAuth) {
    if (!authStore.isAuthenticated) {
      // 未登录 → 进入独立登录页，并记住原本要去的地址
      return { path: '/login', query: { redirect: to.fullPath } }
    }
    if (to.meta.requiresAdmin && authStore.role !== 'admin') {
      return { path: '/', query: { error: 'admin_required' } }
    }
  }
})

export default router
