import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '知微', transition: 'fade' },
  },
  {
    path: '/chat/:chatId',
    name: 'ChatDetail',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '对话', transition: 'fade' },
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '学习看板', transition: 'fade' },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { title: '记忆画像', transition: 'fade' },
  },
  {
    path: '/knowledge',
    name: 'KnowledgeCatalog',
    component: () => import('@/views/KnowledgeCatalogView.vue'),
    meta: { title: '知识地图', transition: 'fade' },
  },
  {
    path: '/knowledge/points/:pointId/learn',
    name: 'KnowledgeLearning',
    component: () => import('@/views/KnowledgeLearningView.vue'),
    meta: { title: '知识点学习', transition: 'fade' },
  },
  {
    path: '/error-book',
    name: 'ErrorBook',
    component: () => import('@/views/ErrorBookView.vue'),
    meta: { title: '错题复盘', transition: 'fade' },
  },
  {
    path: '/error-book/:errorId',
    name: 'ErrorDetail',
    component: () => import('@/views/ErrorBookView.vue'),
    meta: { title: '错题详情', transition: 'fade' },
  },
  // 旧路由重定向
  {
    path: '/chat',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.title) {
    document.title = `${to.meta.title} | 知微 Math AI`
  }
})

export default router