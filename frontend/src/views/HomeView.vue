<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chatStore'
import { useErrorBookStore } from '@/stores/errorBookStore'
import AppShell from '@/components/shell/AppShell.vue'
import AgentComposer from '@/components/conversation/AgentComposer.vue'
import { useAiCapability } from '@/composables/useAiCapability'

const router = useRouter()
const chatStore = useChatStore()
const errorBookStore = useErrorBookStore()
const { isAiAvailable, aiReason } = useAiCapability()

const todayStats = computed(() => {
  const today = new Date()
  const todayStr = today.toDateString()

  let todayMessages = 0
  const dayChats: Set<string> = new Set()

  for (const chat of chatStore.chats) {
    for (const msg of chat.messages) {
      if (msg.sender === 'user') {
        const ts = msg.timestamp ? new Date(msg.timestamp) : null
        if (ts && ts.toDateString() === todayStr) {
          todayMessages++
          dayChats.add(chat.id)
        }
      }
    }
  }

  return {
    todayMessages,
    todayChats: dayChats.size,
    totalChats: chatStore.chats.length,
    totalErrors: errorBookStore.totalErrors,
  }
})

const recentChats = computed(() => {
  return chatStore.sortedChats.slice(0, 4)
})

const greetingText = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了，注意休息'
  if (hour < 12) return '早上好，欢迎回来'
  if (hour < 14) return '中午好，欢迎回来'
  if (hour < 18) return '下午好，欢迎回来'
  return '晚上好，欢迎回来'
})

function handleSend(text: string) {
  if (!text.trim()) return
  if (!isAiAvailable.value) return
  const chat = chatStore.createNewChat()
  chatStore.addMessage(chat.id, {
    content: text.trim(),
    sender: 'user',
    timestamp: new Date().toLocaleString(),
    type: 'text',
  })
  chatStore.persistChats()
  router.push(`/chat/${chat.id}`)
}

function handleSendWithImage(text: string, imageData: string) {
  if (!isAiAvailable.value) return
  const chat = chatStore.createNewChat()
  chatStore.addMessage(chat.id, {
    content: imageData,
    sender: 'user',
    timestamp: new Date().toLocaleString(),
    type: 'image',
    text: text || '',
  })
  chatStore.persistChats()
  router.push(`/chat/${chat.id}`)
}

function openChat(chatId: string) {
  chatStore.switchChat(chatId)
  router.push(`/chat/${chatId}`)
}

function shortcutSolve() {
  if (!isAiAvailable.value) return
  router.push({ path: '/' })
  setTimeout(() => {
    const textarea = document.querySelector('.agent-composer__textarea') as HTMLElement
    if (textarea) textarea.focus()
  }, 100)
}

function shortcutErrorBook() {
  router.push('/error-book')
}

function shortcutKnowledge() {
  router.push('/knowledge')
}

function shortcutPractice() {
  if (!isAiAvailable.value) return
  const chat = chatStore.createNewChat()
  chatStore.addMessage(chat.id, {
    content: '请根据我近期的学习情况和错题记录，为我生成一些针对性的练习题，帮助我巩固薄弱知识点。',
    sender: 'user',
    timestamp: new Date().toLocaleString(),
    type: 'text',
  })
  chatStore.persistChats()
  router.push(`/chat/${chat.id}`)
}

function formatTimeAgo(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) {
    const hours = date.getHours().toString().padStart(2, '0')
    const mins = date.getMinutes().toString().padStart(2, '0')
    return `${hours}:${mins}`
  }
  if (diffDays === 1) return '昨天'
  if (diffDays < 7) return `${diffDays}天前`
  return `${date.getMonth() + 1}月${date.getDate()}日`
}
</script>

<template>
  <AppShell>
    <template #topbar-title>
      <span>知微</span>
    </template>

    <div class="home-view">
      <div class="home-content">
        <!-- 欢迎区 -->
        <section class="home-welcome">
          <p class="home-welcome-greeting">{{ greetingText }}</p>
          <h1 class="home-welcome-title">
            我是你的数学学习助手
            <span class="home-welcome-brand">知微</span>
          </h1>
          <p class="home-welcome-subtitle">有问题尽管问我，我会启发思路、讲透原理，陪你一起进步。</p>
        </section>

        <!-- 输入框 -->
        <AgentComposer
          class="home-composer"
          :large="true"
          :disabled="!isAiAvailable"
          :disabled-reason="aiReason"
          @send="handleSend"
          @send-image="handleSendWithImage"
        />

        <!-- 快捷入口 -->
        <section class="home-shortcuts">
          <button class="shortcut-card" @click="shortcutSolve">
            <div class="shortcut-card__icon shortcut-card__icon--teal">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <rect x="3" y="3" width="18" height="18" rx="3"/>
                <path d="M7 7h4M7 11h2M13 7h4v4h-4zM7 15h4v2H7z"/>
              </svg>
            </div>
            <div class="shortcut-card__body">
              <span class="shortcut-card__title">拍题解答</span>
              <span class="shortcut-card__desc">拍照上传题目，即时解析</span>
            </div>
          </button>

          <button class="shortcut-card" @click="shortcutErrorBook">
            <div class="shortcut-card__icon shortcut-card__icon--amber">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M12 9v4M12 17h.01"/>
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              </svg>
            </div>
            <div class="shortcut-card__body">
              <span class="shortcut-card__title">错题复盘</span>
              <span class="shortcut-card__desc">智能分析错因，安排复习</span>
            </div>
          </button>

          <button class="shortcut-card" @click="shortcutKnowledge">
            <div class="shortcut-card__icon shortcut-card__icon--teal">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <circle cx="12" cy="12" r="9"/>
                <path d="M12 3a9 9 0 0 1 0 18M3 12h18"/>
                <path d="M8 7c2 2.5 2 7.5 0 10M16 7c-2 2.5-2 7.5 0 10"/>
              </svg>
            </div>
            <div class="shortcut-card__body">
              <span class="shortcut-card__title">知识点梳理</span>
              <span class="shortcut-card__desc">梳理知识脉络，构建体系</span>
            </div>
          </button>

          <button class="shortcut-card" @click="shortcutPractice">
            <div class="shortcut-card__icon shortcut-card__icon--primary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                <path d="M9 7h7M9 11h5"/>
              </svg>
            </div>
            <div class="shortcut-card__body">
              <span class="shortcut-card__title">生成练习</span>
              <span class="shortcut-card__desc">针对薄弱点生成个性化练习</span>
            </div>
          </button>

          <button class="shortcut-card" @click="router.push('/paper/test')">
            <div class="shortcut-card__icon shortcut-card__icon--teal">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>
                <path d="M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v0a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2z"/>
                <path d="M9 12l2 2 4-4"/>
              </svg>
            </div>
            <div class="shortcut-card__body">
              <span class="shortcut-card__title">组卷测试</span>
              <span class="shortcut-card__desc">按题型组卷，客观题自动判分</span>
            </div>
          </button>

          <button class="shortcut-card" @click="router.push('/admin/review')">
            <div class="shortcut-card__icon shortcut-card__icon--amber">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M9 12l2 2 4-4"/>
                <path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"/>
              </svg>
            </div>
            <div class="shortcut-card__body">
              <span class="shortcut-card__title">题库审核</span>
              <span class="shortcut-card__desc">内容导入 · AI 分析 · 发布治理（管理员）</span>
            </div>
          </button>
        </section>

        <!-- 今日概览 + 最近对话 -->
        <section class="home-grid">
          <!-- 今日学习概览 -->
          <div class="home-overview">
            <h2 class="home-section-title">今日学习概览</h2>
            <div class="home-overview-stats">
              <div class="overview-stat">
                <span class="overview-stat__label">今日练习</span>
                <span class="overview-stat__value">{{ todayStats.todayMessages }}</span>
                <span class="overview-stat__sub">条消息</span>
              </div>
              <div class="overview-stat">
                <span class="overview-stat__label">对话总数</span>
                <span class="overview-stat__value">{{ todayStats.totalChats }}</span>
                <span class="overview-stat__sub">次对话</span>
              </div>
              <div class="overview-stat">
                <span class="overview-stat__label">错题累计</span>
                <span class="overview-stat__value">{{ todayStats.totalErrors }}</span>
                <span class="overview-stat__sub">道错题</span>
              </div>
            </div>
          </div>

          <!-- 最近对话 -->
          <div class="home-recent">
            <div class="home-recent__header">
              <h2 class="home-section-title">最近对话</h2>
              <RouterLink
                v-if="chatStore.sortedChats.length > 4"
                to="/dashboard"
                class="home-recent__more"
              >
                查看全部 →
              </RouterLink>
            </div>
            <div class="home-recent-list">
              <button
                v-for="chat in recentChats"
                :key="chat.id"
                class="home-recent-item"
                @click="openChat(chat.id)"
              >
                <span class="home-recent-item__title">{{ chat.title || '新对话' }}</span>
                <span class="home-recent-item__time">{{ formatTimeAgo(chat.lastMessageTime) }}</span>
              </button>
              <p v-if="recentChats.length === 0" class="home-recent-empty">
                还没有对话记录，开始第一次提问吧
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.home-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--canvas);
}

.home-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-8) var(--content-padding) var(--space-12);
  max-width: 960px;
  margin: 0 auto;
  width: 100%;
}

/* ============ 欢迎区 ============ */
.home-welcome {
  margin-bottom: var(--space-8);
}
.home-welcome-greeting {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  margin-bottom: var(--space-2);
  letter-spacing: 0.01em;
}
.home-welcome-title {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
  margin-bottom: var(--space-3);
}
.home-welcome-brand {
  color: var(--accent);
  margin-left: var(--space-2);
}
.home-welcome-subtitle {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.6;
}

/* ============ 输入框 ============ */
.home-composer {
  width: 100%;
  margin-bottom: var(--space-8);
}

/* ============ 快捷入口 ============ */
.home-shortcuts {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
  margin-bottom: var(--space-8);
}
.shortcut-card {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface);
  text-align: left;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast);
}
.shortcut-card:hover {
  background: var(--surface-hover);
  border-color: var(--border-strong);
}
.shortcut-card__icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-md);
  flex-shrink: 0;
  color: var(--text-primary);
}
.shortcut-card__icon svg {
  width: 22px;
  height: 22px;
}
.shortcut-card__icon--teal {
  background: var(--knowledge-soft);
  color: var(--knowledge);
}
.shortcut-card__icon--amber {
  background: rgba(200, 145, 61, 0.12);
  color: var(--warning);
}
.shortcut-card__icon--primary {
  background: var(--accent-soft);
  color: var(--accent);
}
.shortcut-card__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.shortcut-card__title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.shortcut-card__desc {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* ============ 概览 + 最近对话 ============ */
.home-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: var(--space-4);
}

.home-overview {
  padding: var(--space-5);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.home-section-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-4);
}
.home-overview-stats {
  display: flex;
  gap: var(--space-6);
}
.overview-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}
.overview-stat__label {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}
.overview-stat__value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}
.overview-stat__sub {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.home-recent {
  padding: var(--space-5);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface);
  display: flex;
  flex-direction: column;
}
.home-recent__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.home-recent__more {
  font-size: var(--font-size-xs);
  color: var(--accent);
  text-decoration: none;
}
.home-recent__more:hover {
  color: var(--accent-hover);
}
.home-recent-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.home-recent-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-2);
  border-radius: var(--radius-xs);
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  transition: background var(--transition-fast);
  width: 100%;
  gap: var(--space-3);
}
.home-recent-item:hover {
  background: var(--surface-hover);
}
.home-recent-item__title {
  flex: 1;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.home-recent-item__time {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.home-recent-empty {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  padding: var(--space-4) var(--space-2);
  text-align: center;
}

/* ============ 响应式 ============ */
@media (max-width: 1024px) {
  .home-shortcuts {
    grid-template-columns: repeat(2, 1fr);
  }
  .home-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .home-content {
    padding: var(--space-4) var(--space-4) var(--space-8);
  }
  .home-welcome-title {
    font-size: var(--font-size-2xl);
  }
  .home-shortcuts {
    grid-template-columns: 1fr;
  }
  .home-overview-stats {
    gap: var(--space-4);
  }
  .home-grid {
    gap: var(--space-3);
  }
}
</style>
