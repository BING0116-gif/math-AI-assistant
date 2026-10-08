<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chatStore'
import { useErrorBookStore } from '@/stores/errorBookStore'
import AppShell from '@/components/shell/AppShell.vue'
import AgentComposer from '@/components/conversation/AgentComposer.vue'
import { useAiCapability } from '@/composables/useAiCapability'
import { useEntranceAnimation } from '@/composables/useEntranceAnimation'
import { useReminderPolling } from '@/composables/useReminderPolling'
import { Sparkles, ChevronRight, BookOpen, Route } from 'lucide-vue-next'
import { nowIso, parseTimestamp } from '@/utils/dateTime'

const router = useRouter()
const chatStore = useChatStore()
const errorBookStore = useErrorBookStore()
const { isAiAvailable, aiReason } = useAiCapability()
// 首页是提醒中心的两个拉取入口之一（另一个是 /dashboard）：挂载后一次 + 每 5 分钟。
useReminderPolling()

const todayStats = computed(() => {
  const today = new Date()
  const todayStr = today.toDateString()

  let todayMessages = 0
  const dayChats: Set<string> = new Set()

  for (const chat of chatStore.chats) {
    for (const msg of chat.messages) {
      if (msg.sender === 'user') {
        const ts = parseTimestamp(msg.timestamp)
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
    unmasteredErrors: errorBookStore.unmasteredCount,
  }
})

const recentChats = computed(() => {
  return chatStore.sortedChats.slice(0, 3)
})

const continueChat = computed(() => chatStore.sortedChats[0] || null)

const greetingText = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了，注意休息'
  if (hour < 12) return '早上好，欢迎回来'
  if (hour < 14) return '中午好，欢迎回来'
  if (hour < 18) return '下午好，欢迎回来'
  return '晚上好，欢迎回来'
})

const dateLabel = computed(() => {
  const now = new Date()
  const weeks = ['日', '一', '二', '三', '四', '五', '六']
  return `${now.getMonth() + 1}月${now.getDate()}日 周${weeks[now.getDay()]}`
})

const quickPrompts = [
  '出 5 道中值定理练习题',
  '讲讲泰勒展开的直觉',
  '复盘今日错题',
  '帮我制定期末复习计划',
]

function handleSend(text: string) {
  if (!text.trim()) return
  if (!isAiAvailable.value) return
  const chat = chatStore.createNewChat()
  chatStore.persistChats()
  // 把问题作为参数带给聊天页,由 ChatView 接管「发送 + AI 回答」全流程
  router.push({ path: `/chat/${chat.id}`, query: { q: text.trim() } })
}

function handleSendWithImage(text: string, imageData: string) {
  if (!isAiAvailable.value) return
  const chat = chatStore.createNewChat()
  // 图片数据较大,暂存到 store 由聊天页消费后清空
  chatStore.pendingImage = { text: text || '', image: imageData }
  chatStore.persistChats()
  router.push(`/chat/${chat.id}`)
}

function openChat(chatId: string) {
  chatStore.switchChat(chatId)
  router.push(`/chat/${chatId}`)
}

function continueLearning() {
  if (continueChat.value) {
    openChat(continueChat.value.id)
    return
  }
  router.push('/knowledge')
}

function reviewErrors() {
  router.push('/error-book')
}

function formatTimeAgo(timestamp: string): string {
  const date = parseTimestamp(timestamp)
  if (!date) return '时间未知'
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

useEntranceAnimation()
</script>

<template>
  <AppShell>
    <template #topbar-title>
      <span>知微</span>
    </template>

    <div class="home-view">
      <div class="hero-glow" aria-hidden="true"></div>

      <div class="home-wrap">
        <!-- Hero -->
        <section class="home-hero" aria-labelledby="home-title">
          <div class="eyebrow">
            <Sparkles :size="14" :stroke-width="1.75" style="color: var(--brand)" aria-hidden="true" />
            AI 驱动的高等数学学习空间
          </div>
          <h1 id="home-title">
            {{ greetingText }}。<br />
            今天想<span class="grad-text">弄懂</span>哪个知识点？
          </h1>
          <div class="sub">
            {{ dateLabel }} · 今日已提问
            <b class="num">{{ todayStats.todayMessages }}</b> 次 · 待复盘错题
            <b class="num">{{ todayStats.unmasteredErrors }}</b> 道
          </div>
        </section>

        <!-- 提问输入(复用 AgentComposer,P2-2 重皮) -->
        <AgentComposer
          class="home-composer"
          :large="true"
          :disabled="!isAiAvailable"
          :disabled-reason="aiReason"
          @send="handleSend"
          @send-image="handleSendWithImage"
        />

        <!-- 快捷提问 -->
        <div class="home-quick">
          <button
            v-for="prompt in quickPrompts"
            :key="prompt"
            class="chip"
            :disabled="!isAiAvailable"
            @click="handleSend(prompt)"
          >
            {{ prompt }}
          </button>
        </div>

        <!-- 最近对话 -->
        <div class="home-section-label">
          <span class="t-3">最近对话</span>
          <RouterLink v-if="chatStore.sortedChats.length > 3" to="/dashboard" class="more">
            查看全部
            <ChevronRight :size="14" :stroke-width="1.75" aria-hidden="true" />
          </RouterLink>
        </div>
        <div class="home-cards">
          <button
            v-for="chat in recentChats"
            :key="chat.id"
            class="card recent-card"
            @click="openChat(chat.id)"
          >
            <span class="rt">{{ chat.title || '新对话' }}</span>
            <span class="rs">{{ chat.messages.length ? `${chat.messages.length} 条消息 · ${formatTimeAgo(chat.lastMessageTime)}` : '点击继续这段对话' }}</span>
            <span class="rf">
              <span v-if="chat.messages.length" class="tag tag-soft-accent">{{ chat.messages.length }} 条</span>
              <span class="caption">{{ formatTimeAgo(chat.lastMessageTime) }}</span>
            </span>
          </button>
          <p v-if="recentChats.length === 0" class="recent-empty">
            还没有对话记录，在上面提出第一个问题吧
          </p>
        </div>

        <!-- 继续学习 -->
        <div class="home-section-label cont-label">
          <span class="t-3">继续学习</span>
        </div>
        <div class="cont-grid">
          <button class="card cont-card" @click="continueLearning">
            <span class="cont-head">
              <span class="tag tag-soft-accent">
                <BookOpen :size="12" :stroke-width="2" aria-hidden="true" />
                {{ continueChat ? '上次对话' : '知识星球' }}
              </span>
              <span class="caption">{{ continueChat ? formatTimeAgo(continueChat.lastMessageTime) : '按图谱梳理脉络' }}</span>
            </span>
            <span class="tt">{{ continueChat ? continueChat.title || '新对话' : '开始第一次学习' }}</span>
            <span class="meta-row">
              <span class="caption cont-meta">{{ continueChat ? `${continueChat.messages.length} 条消息 · 点击继续` : '浏览知识点目录,选择起点' }}</span>
              <span class="btn btn-primary btn-sm">继续</span>
            </span>
          </button>

          <button class="card cont-card" @click="reviewErrors">
            <span class="cont-head">
              <span class="tag tag-soft-rose">
                <Route :size="12" :stroke-width="2" aria-hidden="true" />
                错题复盘
              </span>
              <span class="caption">艾宾浩斯计划</span>
            </span>
            <span class="tt">
              {{ todayStats.unmasteredErrors > 0 ? `${todayStats.unmasteredErrors} 道错题待复盘` : '错题本已清空' }}
            </span>
            <span class="meta-row">
              <span class="caption cont-meta">优先复习遗忘临界期的题目</span>
              <span class="btn btn-ghost btn-sm">去复盘</span>
            </span>
          </button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.home-view {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg);
}

/* 首页背景微光 */
.hero-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}
.hero-glow::before {
  content: '';
  position: absolute;
  top: -180px;
  left: 50%;
  transform: translateX(-50%);
  width: 720px;
  height: 420px;
  border-radius: 50%;
  opacity: 0.5;
  filter: blur(60px);
  background: radial-gradient(closest-side, rgba(11, 122, 94, 0.11), rgba(27, 191, 160, 0.06) 60%, transparent);
}
[data-theme='dark'] .hero-glow::before {
  background: radial-gradient(closest-side, rgba(69, 200, 160, 0.09), rgba(27, 191, 160, 0.04) 60%, transparent);
}

.home-wrap {
  position: relative;
  flex: 1;
  width: 100%;
  max-width: 860px;
  margin: 0 auto;
  padding: 5vh 24px 56px;
  overflow-y: auto;
}

/* ---------- Hero ---------- */
.home-hero {
  text-align: center;
  margin-bottom: 34px;
}
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 26px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 12px;
  color: var(--ink-2);
  font-weight: 500;
  box-shadow: var(--shadow-1);
  margin-bottom: 18px;
}
.home-hero h1 {
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.25;
  color: var(--ink-1);
}
.home-hero .sub {
  font-size: 14.5px;
  color: var(--ink-3);
  margin-top: 8px;
}
.home-hero .sub .num {
  color: var(--ink-2);
  font-weight: 600;
}

/* ---------- Composer 占位(AgentComposer 自身皮在 P2-2) ---------- */
.home-composer {
  margin-bottom: 18px;
}

/* ---------- 快捷提问 ---------- */
.home-quick {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  justify-content: center;
  margin: 18px 0 40px;
}
.home-quick .chip {
  cursor: pointer;
}
.home-quick .chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ---------- 区块标签 ---------- */
.home-section-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 2px 12px;
}
.home-section-label .t-3 {
  font-size: 14px;
}
.cont-label {
  margin-top: 6px;
}
.more {
  font-size: 12.5px;
  color: var(--ink-3);
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-weight: 500;
}
.more:hover {
  color: var(--brand-text);
}

/* ---------- 最近对话 3 卡 ---------- */
.home-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}
.recent-card {
  padding: 16px;
  transition: all 0.16s;
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;
}
.recent-card:hover {
  border-color: var(--accent);
  transform: translateY(-1px);
  box-shadow: var(--shadow-3);
}
.recent-card .rt {
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.recent-card .rs {
  font-size: 12px;
  color: var(--ink-3);
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 37px;
}
.recent-card .rf {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
}
.recent-empty {
  grid-column: 1 / -1;
  text-align: center;
  font-size: 13px;
  color: var(--ink-3);
  padding: 24px 0;
}

/* ---------- 继续学习 2 卡 ---------- */
.cont-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 14px;
}
.cont-card {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition: all 0.16s;
}
.cont-card:hover {
  border-color: var(--brand);
  transform: translateY(-1px);
  box-shadow: var(--shadow-3);
}
.cont-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cont-head .tag {
  gap: 4px;
}
.cont-card .tt {
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cont-meta {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta-row .btn {
  flex: none;
}

/* ---------- 响应式 ---------- */
@media (max-width: 768px) {
  .home-wrap {
    padding: 24px 16px 40px;
  }
  .home-hero h1 {
    font-size: 26px;
  }
  .home-cards {
    grid-template-columns: 1fr;
  }
  .cont-grid {
    grid-template-columns: 1fr;
  }
  .home-hero .sub {
    font-size: 13px;
  }
}
</style>
