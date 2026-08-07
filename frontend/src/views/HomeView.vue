<template>
  <AppShell>
    <div class="home-view">
      <div class="home-scroll-area">
        <WelcomeHero />
        <ChatInput
          v-model="inputText"
          placeholder="输入你的数学问题..."
          @send="handleSend"
          @voice-input="handleVoiceInput"
          @tool-click="handleToolClick"
          ref="chatInputRef"
        />
        <FeatureCards />
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/layout/AppShell.vue'
import WelcomeHero from '@/components/home/WelcomeHero.vue'
import FeatureCards from '@/components/home/FeatureCards.vue'
import ChatInput from '@/components/home/ChatInput.vue'
import { useChatStore } from '@/stores/chatStore'

const router = useRouter()
const store = useChatStore()

const inputText = ref('')
const chatInputRef = ref(null)

function handleSend({ text }) {
  if (!text) return

  const chat = store.createNewChat()
  const chatId = chat.id
  store.addMessage(chatId, {
    content: text,
    sender: 'user',
    timestamp: new Date().toLocaleString(),
    type: 'text'
  })
  store.persistChats()

  router.push(`/chat/${chatId}`)
}

function handleVoiceInput() {
  console.log('语音输入功能开发中...')
}

function handleToolClick(tool) {
  if (tool.id === 'quick') {
    router.push('/chat')
  } else if (tool.id === 'image') {
    router.push('/chat')
  } else if (tool.id === 'formula') {
    inputText.value = '请帮我推导以下公式：'
    chatInputRef.value?.focus()
  } else if (tool.id === 'code') {
    inputText.value = '请帮我编写 Python 代码：'
    chatInputRef.value?.focus()
  } else if (tool.id === 'writing') {
    inputText.value = '请帮我：'
    chatInputRef.value?.focus()
  }
}
</script>

<style lang="scss" scoped>
.home-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.home-scroll-area {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.3);
    border-radius: 10px;

    &:hover {
      background: rgba(148, 163, 184, 0.5);
    }
  }
}

@media (max-width: 768px) {
  .home-view {
    padding: 0;
  }
}
</style>
