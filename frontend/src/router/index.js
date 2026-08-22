import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useLoginDialog } from '@/composables/useLoginDialog'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '数学AI助手', transition: 'slide-fade' },
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '智能对话 - 数学AI助手', transition: 'slide-fade' },
  },
  {
    path: '/chat/:chatId',
    name: 'ChatDetail',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '智能对话 - 数学AI助手', transition: 'slide-fade' },
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
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '学习看板 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { title: '记忆画像 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
  },
  {
    path: '/paper/test',
    redirect: '/apply/practice',
  },
  { path: '/apply', name: 'ApplyHub', component: () => import('@/views/ApplyHubView.vue'), meta: { title: '学以致用 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/practice', name: 'PracticeSetup', component: () => import('@/views/PracticeSetupView.vue'), meta: { title: '专项练习 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/practice/sessions/:sessionId', name: 'PracticeSession', component: () => import('@/views/PracticeSessionView.vue'), meta: { title: '专项练习 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/practice/sessions/:sessionId/result', name: 'PracticeResult', component: () => import('@/views/PracticeResultView.vue'), meta: { title: '专项练习结果 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/assessment', name: 'AssessmentSetup', component: () => import('@/views/AssessmentSetupView.vue'), meta: { title: '智能检测 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/assessment/sessions/:sessionId', name: 'AssessmentSession', component: () => import('@/views/AssessmentSessionView.vue'), meta: { title: '智能检测 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  { path: '/apply/assessment/sessions/:sessionId/result', name: 'AssessmentResult', component: () => import('@/views/AssessmentResultView.vue'), meta: { title: '智能检测报告 - 数学AI助手', transition: 'slide-fade', requiresAuth: true } },
  {
    path: '/admin/review',
    name: 'AdminReview',
    component: () => import('@/views/AdminReviewView.vue'),
    meta: { title: '题库审核工作台 - 数学AI助手', transition: 'slide-fade', requiresAuth: true },
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

  // 路由守卫：受保护页面需要认证
  if (to.meta.requiresAuth) {
    const authStore = useAuthStore()
    if (!authStore.isAuthenticated) {
      // 未登录 → 重定向到首页并打开登录对话框
      const { openLogin } = useLoginDialog()
      openLogin('login')
      return { path: '/', query: { login: 'required' } }
    }
  }
})

export default router
