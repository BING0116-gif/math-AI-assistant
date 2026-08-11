<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chatStore'
import AppShell from '@/components/shell/AppShell.vue'
import AgentComposer from '@/components/conversation/AgentComposer.vue'

const router = useRouter()
const chatStore = useChatStore()

const hasHistory = computed(() => chatStore.sortedChats.length > 0)

const greeting = computed(() => {
  return hasHistory.value
    ? '继续学习，或提出一个新问题。'
    : '今天想解决什么数学问题？'
})

// 真实数据存在时显示的继续入口
const recentItems = computed(() => {
  const items: { label: string; action: () => void }[] = []
  if (hasHistory.value) {
    const lastChat = chatStore.sortedChats[0]
    if (lastChat) {
      items.push({
        label: `继续：${lastChat.title || '上次对话'}`,
        action: () => router.push(`/chat/${lastChat.id}`),
      })
    }
  }
  return items.slice(0, 3)
})

function handleSend(text: string) {
  if (!text.trim()) return
  const chat = chatStore.createNewChat()
  chatStore.addMessage(chat.id, {
    content: text.trim(),
    sender: 'user',
    type: 'text',
  })
  chatStore.persistChats()
  router.push(`/chat/${chat.id}`)
}

function handleSendWithImage(text: string, imageData: string) {
  const chat = chatStore.createNewChat()
  chatStore.addMessage(chat.id, {
    content: imageData,
    sender: 'user',
    type: 'image',
    text: text || '',
  })
  chatStore.persistChats()
  router.push(`/chat/${chat.id}`)
}
</script>

<template>
  <AppShell>
    <template #topbar-title>
      <span>知微</span>
    </template>

    <div class="home-view">
      <div class="home-content">
        <!-- 标题 — 文档 §6.2: 标题最多两行 -->
        <h1 class="home-greeting">{{ greeting }}</h1>

        <!-- 输入区 — 文档 §6.2: 垂直位置约在视口 42%–48% -->
        <AgentComposer
          class="home-composer"
          :large="true"
          @send="handleSend"
          @send-image="handleSendWithImage"
        />

        <!-- 继续入口 — 文档 §6.2: 最多三条与真实状态相关的继续入口 -->
        <div v-if="recentItems.length > 0" class="home-continue">
          <button
            v-for="(item, i) in recentItems"
            :key="i"
            class="home-continue-btn"
            @click="item.action"
          >
            {{ item.label }}
          </button>
        </div>

        <!-- 无历史时显示示例问题 — 文档 §6.2: 可显示两条纯文本示例问题 -->
        <div v-else class="home-suggestions">
          <button
            class="home-suggestion"
            @click="handleSend('求函数 f(x) = x^2 的导数')"
          >
            求函数 f(x) = x² 的导数
          </button>
          <button
            class="home-suggestion"
            @click="handleSend('如何证明勾股定理？')"
          >
            如何证明勾股定理？
          </button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
/* 文档 §6.2: 内容区最大宽度 820px，输入区垂直位置约在视口 42%–48% */
.home-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--canvas);
}

.home-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  /* 文档 §6.2: 输入区垂直位置约在视口 42%–48%
     使用 padding-top 将内容中心推到约 45% 处 */
  padding: 0 var(--space-6) var(--space-6);
  overflow-y: auto;
  width: 100%;
  max-width: var(--content-max-width);
  margin: 0 auto;
}

.home-greeting {
  font-size: var(--font-size-2xl);
  font-weight: 600;
  text-align: center;
  color: var(--text-primary);
  line-height: var(--line-height-tight);
  max-width: 600px;
  margin-bottom: var(--space-6);
}

.home-composer {
  width: 100%;
  max-width: 760px;
}

.home-continue {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 100%;
  max-width: 760px;
  margin-top: var(--space-4);
}

.home-continue-btn {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  text-align: left;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast);
  width: 100%;
}
.home-continue-btn:hover {
  background: var(--surface-hover);
  border-color: var(--border-strong);
  color: var(--text-primary);
}

.home-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: center;
  margin-top: var(--space-4);
}
.home-suggestion {
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}
.home-suggestion:hover {
  background: var(--surface-hover);
  border-color: var(--border-strong);
  color: var(--text-primary);
}

@media (max-width: 768px) {
  .home-content {
    padding: var(--space-12) var(--space-4) var(--space-4);
  }
  .home-greeting {
    font-size: var(--font-size-xl);
  }
}
</style>
