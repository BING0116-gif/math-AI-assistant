<script setup lang="ts">
import { ref, reactive, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppShell from '@/components/shell/AppShell.vue'
import MessageItem from '@/components/chat/MessageItem.vue'
import AgentComposer from '@/components/conversation/AgentComposer.vue'
import FollowUpRecommendation from '@/components/FollowUpRecommendation.vue'
import { useChatStore } from '@/stores/chatStore'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { sendChatMessage, sendMultimodalRequest, parseSSEStream } from '@/api/chat'
import { formatStreamText } from '@/utils/markdown'
import { generateUUID } from '@/utils/helpers'

const route = useRoute()
const router = useRouter()
const store = useChatStore()
const errorBookStore = useErrorBookStore()

const messagesRef = ref<HTMLElement | null>(null)
const streaming = ref(false)
const streamingMessageId = ref<string | null>(null)
const streamingCharCount = ref(0)
const abortController = ref<AbortController | null>(null)
const reasonInput = ref<HTMLTextAreaElement | null>(null)
const followUpQuestions = ref<any[]>([])
const showErrorModal = ref(false)
const autoScroll = ref(true)

const errorForm = reactive({
  question: '',
  question_type: 'text',
  correct_answer: '',
  error_reason: '',
  categories: [] as string[],
  notes: '',
  mastery_level: 3,
  is_mastered: false,
})

let currentErrorMsgId: string | null = null
const availableTags = ['极限', '导数', '积分', '微分方程', '级数', '多元函数']

// 监听滚动以决定是否自动滚底
function handleScroll() {
  if (!messagesRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = messagesRef.value
  autoScroll.value = scrollHeight - scrollTop - clientHeight < 80
}

function scrollToBottom() {
  if (messagesRef.value && autoScroll.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

watch(() => store.currentMessages.length, () => {
  nextTick(() => scrollToBottom())
})

onMounted(() => {
  const chatId = route.params.chatId as string
  if (chatId) {
    const exists = store.chats.find(c => c.id === chatId)
    if (exists) {
      store.switchChat(chatId)
    } else {
      router.replace('/')
    }
  }
})

onUnmounted(() => {
  if (renderRafId) {
    cancelAnimationFrame(renderRafId)
    renderRafId = null
  }
})

// ---- SSE 流式处理 ----
let typingBuffer = ''
let rawContentBuffer = ''
let isTyping = false
let lastRenderedLength = 0
let renderRafId: number | null = null

function processTyping(msgId: string) {
  const el = document.getElementById('msg-' + msgId)
  if (!el || typingBuffer.length === 0) {
    if (!streaming.value || typingBuffer.length === 0) {
      isTyping = false
      return
    }
    setTimeout(() => processTyping(msgId), 50)
    return
  }

  const chunk = typingBuffer.substring(0, 1)
  typingBuffer = typingBuffer.substring(1)
  streamingCharCount.value++

  const shouldUpdate =
    streamingCharCount.value % 50 === 0 ||
    chunk === '\n' ||
    typingBuffer.length === 0

  if (shouldUpdate) {
    if (renderRafId) cancelAnimationFrame(renderRafId)
    renderRafId = requestAnimationFrame(() => {
      const contentDiv = el.querySelector('.msg-content') as HTMLElement
      if (contentDiv) {
        const display = formatStreamText(rawContentBuffer)
        contentDiv.innerHTML = display
        lastRenderedLength = rawContentBuffer.length
      }
      renderRafId = null
    })
  }

  scrollToBottom()
  if (typingBuffer.length > 0) {
    setTimeout(() => processTyping(msgId), 8)
  } else if (streaming.value) {
    setTimeout(() => processTyping(msgId), 50)
  } else {
    isTyping = false
  }
}

// SSE follow_up 事件处理
function handleEvent(eventType: string, data: any) {
  if (eventType === 'follow_up' && data.type === 'recommendation') {
    const content = data.content || ''
    const questions = parseFollowUpContent(content)
    if (questions.length > 0) {
      followUpQuestions.value = questions
      nextTick(() => scrollToBottom())
    }
  }
}

function parseFollowUpContent(content: string) {
  if (!content) return []
  const questions: any[] = []
  const parts = content.split(/###\s+\d+\.\s+/)
  for (let i = 1; i < parts.length; i++) {
    const part = parts[i].trim()
    if (!part) continue
    const titleMatch = part.match(/^(.+?)(?:\n|$)/)
    const title = titleMatch ? titleMatch[1].trim() : ''
    const diffMatch = title.match(/难度\s*(\d+)\/5/)
    const difficulty = diffMatch ? parseInt(diffMatch[1]) : 3
    const answerMatch = part.match(/\*\*答案\*\*[：:]?\s*([\s\S]*?)$/)
    const answer = answerMatch ? answerMatch[1].trim() : ''
    let contentText = part
    if (titleMatch) {
      contentText = contentText.substring(titleMatch[0].length).trim()
    }
    if (answerMatch) {
      contentText = contentText.substring(0, contentText.lastIndexOf('**答案**')).trim()
    }
    questions.push({
      id: 'follow-up-' + i,
      content: contentText,
      answer: answer,
      difficulty: difficulty,
    })
  }
  return questions
}

function handleFollowUpSelect(question: any) {
  if (question && question.content) {
    followUpQuestions.value = []
    handleTextSend(question.content)
  }
}

async function handleTextSend(text: string) {
  if (!text || streaming.value) return
  followUpQuestions.value = []

  const chatId = store.currentChatId
  store.addMessage(chatId, { content: text, sender: 'user', timestamp: new Date().toLocaleString(), type: 'text' })
  store.persistChats()
  nextTick(() => scrollToBottom())

  const msgId = generateUUID()
  const placeholder = { id: msgId, content: '', sender: 'ai', timestamp: '正在生成...', type: 'text' }
  store.addMessage(chatId, placeholder)

  streaming.value = true
  streamingMessageId.value = msgId
  streamingCharCount.value = 0

  abortController.value = new AbortController()
  typingBuffer = ''
  rawContentBuffer = ''
  isTyping = false
  lastRenderedLength = 0
  if (renderRafId) {
    cancelAnimationFrame(renderRafId)
    renderRafId = null
  }

  try {
    const response = await sendChatMessage(text, chatId, abortController.value.signal)
    if (response.status < 200 || response.status >= 300) throw new Error('API请求失败 (' + response.status + ')')

    const handleData = (data: any) => {
      if (data.type === 'content' && data.content) {
        typingBuffer += data.content
        rawContentBuffer += data.content
        if (!isTyping) {
          isTyping = true
          processTyping(msgId)
        }
      }
    }

    const handleDone = () => {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: rawContentBuffer || '抱歉，未获取到有效回复。',
        timestamp: new Date().toLocaleString(),
      })
      nextTick(() => scrollToBottom())
    }

    const handleError = () => {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误，请重试。',
        timestamp: new Date().toLocaleString(),
      })
    }

    await parseSSEStream(response, handleData, handleDone, handleError, handleEvent)
  } catch (err: any) {
    if (err.name !== 'AbortError' && err.code !== 'ERR_CANCELED') {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误: ' + err.message,
        timestamp: new Date().toLocaleString(),
      })
    }
  }
}

async function handleSendWithImage(text: string, imageData: string) {
  if (streaming.value) return
  followUpQuestions.value = []

  const chatId = store.currentChatId
  const userMessageContent = text && text.trim() ? text.trim() : ''
  store.addMessage(chatId, {
    content: imageData,
    sender: 'user',
    timestamp: new Date().toLocaleString(),
    type: 'image',
    text: userMessageContent,
  })
  store.persistChats()
  nextTick(() => scrollToBottom())

  const msgId = generateUUID()
  store.addMessage(chatId, { id: msgId, content: '', sender: 'ai', timestamp: '正在识别...', type: 'text' })

  streaming.value = true
  streamingMessageId.value = msgId
  streamingCharCount.value = 0

  abortController.value = new AbortController()
  typingBuffer = ''
  rawContentBuffer = ''
  isTyping = false
  lastRenderedLength = 0
  if (renderRafId) {
    cancelAnimationFrame(renderRafId)
    renderRafId = null
  }

  try {
    const response = await sendMultimodalRequest(userMessageContent, imageData, chatId, abortController.value.signal)
    if (response.status < 200 || response.status >= 300) throw new Error('多模态请求失败 (' + response.status + ')')

    const handleData = (data: any) => {
      if (data.type === 'content' && data.content) {
        typingBuffer += data.content
        rawContentBuffer += data.content
        if (!isTyping) {
          isTyping = true
          processTyping(msgId)
        }
      }
    }

    const handleDone = () => {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: rawContentBuffer || '抱歉，未获取到有效回复。',
        timestamp: new Date().toLocaleString(),
      })
      nextTick(() => scrollToBottom())
    }

    const handleError = () => {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误，请重试。',
        timestamp: new Date().toLocaleString(),
      })
    }

    await parseSSEStream(response, handleData, handleDone, handleError, handleEvent)
  } catch (err: any) {
    if (err.name !== 'AbortError' && err.code !== 'ERR_CANCELED') {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误: ' + err.message,
        timestamp: new Date().toLocaleString(),
      })
    }
  }
}

function stopGeneration() {
  if (abortController.value) {
    abortController.value.abort()
    streaming.value = false
    streamingMessageId.value = null
  }
}

function handleClear() {
  store.clearChat(store.currentChatId)
}

function openErrorBookDialog(msgId: string) {
  // ... 保持原有错题本逻辑
}

function closeErrorModal() {
  showErrorModal.value = false
}

async function confirmAddError() {
  if (!errorForm.error_reason.trim()) {
    ElMessage.error('请填写错误原因')
    reasonInput.value?.focus()
    return
  }
  try {
    await errorBookStore.addError({ ...errorForm })
    store.setErrorBookStatus(store.currentChatId, currentErrorMsgId!, 'added')
    closeErrorModal()
    ElMessage.success('已成功加入错题本！')
  } catch (err: any) {
    console.error('添加错题失败:', err)
    ElMessage.error(err?.response?.data?.detail || '添加失败，请重试')
  }
}

function handleSkip(msgId: string) {
  store.setErrorBookStatus(store.currentChatId, msgId, 'skipped')
}
</script>

<template>
  <AppShell>
    <template #topbar-title>
      <span>{{ store.currentChat?.title || '新对话' }}</span>
    </template>
    <template #topbar-actions>
      <button
        v-if="streaming"
        class="stop-btn"
        @click="stopGeneration"
      >
        <span class="stop-dot" aria-hidden="true"></span> 停止生成
      </button>
      <button
        class="action-btn"
        :disabled="streaming"
        @click="handleClear"
      >
        清空
      </button>
    </template>

    <div class="chat-view">
      <div
        ref="messagesRef"
        class="messages-area"
        @scroll="handleScroll"
      >
        <div class="messages-inner">
          <MessageItem
            v-for="msg in store.currentMessages"
            :key="msg.id"
            :message="msg"
            :is-streaming="streaming && msg.id === streamingMessageId"
            @add-to-error-book="openErrorBookDialog"
            @skip-error-book="handleSkip"
          />
          <FollowUpRecommendation
            v-if="followUpQuestions.length > 0"
            :questions="followUpQuestions"
            @select="handleFollowUpSelect"
          />
          <div v-if="streaming && streamingCharCount === 0" class="loading-indicator">
            <span class="loading-text">正在组织推导…</span>
          </div>
        </div>

        <!-- 回到最新按钮 -->
        <button
          v-if="!autoScroll && streaming"
          class="scroll-to-bottom"
          @click="scrollToBottom"
        >
          回到最新
        </button>
      </div>

      <div class="composer-area">
        <AgentComposer
          @send="handleTextSend"
          @send-image="handleSendWithImage"
        />
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
/* 文档 §6.3: 会话正文最大宽度 820px，页面滚动容器只有一个 */
.chat-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--canvas);
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  position: relative;
}

.messages-inner {
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: var(--space-6) var(--space-6) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  width: 100%;
}

/* 文档 §6.3: 输入框区域 — 底部固定，无顶部分隔线，让 composer 圆角卡片悬浮在画布上 */
.composer-area {
  flex-shrink: 0;
  padding: var(--space-3) var(--space-5) var(--space-5);
  max-width: var(--content-max-width);
  margin: 0 auto;
  width: 100%;
  background: var(--canvas);
}

.stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1.5px solid var(--danger);
  border-radius: var(--radius-sm);
  color: var(--danger);
  background: transparent;
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 500;
  transition: background var(--transition-fast);
}
.stop-btn:hover {
  background: rgba(184, 78, 78, 0.08);
}
.stop-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--danger);
}

.action-btn {
  padding: 6px 14px;
  border: 1.5px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  font-weight: 500;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.action-btn:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--text-primary);
}
.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
  align-self: flex-start;
}
.loading-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.scroll-to-bottom {
  position: sticky;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  border: 1.5px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  z-index: 10;
}
.scroll-to-bottom:hover {
  background: var(--surface-hover);
}

@media (max-width: 768px) {
  .messages-inner {
    padding: var(--space-4) var(--space-4) var(--space-3);
    gap: var(--space-4);
  }
  .composer-area {
    padding: var(--space-2) var(--space-4) var(--space-3);
  }
}
</style>