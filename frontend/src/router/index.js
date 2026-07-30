import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '数学AI助手', transition: 'slide-fade' }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '智能对话 - 数学AI助手', transition: 'slide-fade' }
  },
  {
    path: '/chat/:chatId',
    name: 'ChatDetail',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '智能对话 - 数学AI助手', transition: 'slide-fade' }
  },
  {
    path: '/error-book',
    name: 'ErrorBook',
    component: () => import('@/views/ErrorBookView.vue'),
    meta: { title: '错题本 - 数学AI助手', transition: 'slide-fade' }
  },
  {
    path: '/error-book/:errorId',
    name: 'ErrorDetail',
    component: () => import('@/views/ErrorBookView.vue'),
    meta: { title: '错题详情 - 数学AI助手', transition: 'slide-fade' }
  },
  {
    path: '/knowledge',
    name: 'KnowledgeCatalog',
    component: () => import('@/views/KnowledgeCatalogView.vue'),
    meta: { title: '课程知识目录 - 数学AI助手', transition: 'slide-fade' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  if (to.meta.title) {
    document.title = to.meta.title
  }
})

export default router
