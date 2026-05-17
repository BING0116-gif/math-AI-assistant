<template>
  <LayoutDefault>
    <template #header>
      <div class="chat-header-content">
        <h2 class="chat-title">{{ store.currentChat?.title || '新对话' }}</h2>
        <div class="header-actions">
          <button v-if="streaming" class="btn-stop" @click="stopGeneration">
            <span class="stop-dot"></span> 停止生成
          </button>
          <button class="btn-action" @click="handleClear" :disabled="streaming">清空</button>
        </div>
      </div>
    </template>

    <div class="chat-view">
      <div class="messages-area" ref="messagesRef">
        <TransitionGroup name="message">
          <MessageItem
            v-for="msg in store.currentMessages"
            :key="msg.id"
            :message="msg"
            :is-streaming="streaming && msg.id === streamingMessageId"
            @add-to-error-book="openErrorBookDialog"
            @skip-error-book="handleSkip"
          />
        </TransitionGroup>
        <div v-if="streaming && streamingCharCount === 0" class="loading-indicator">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          <span class="loading-text">思考中...</span>
        </div>
      </div>

      <InputArea
        :disabled="streaming"
        @send="handleCombinedSend"
      />
    </div>

    <Teleport to="body">
      <div v-if="showErrorModal" class="modal-backdrop" @click.self="closeErrorModal">
        <div class="error-modal-dialog">
          <h3>📚 添加到错题本</h3>

          <div class="form-group">
            <label>题目预览</label>
            <div class="preview-box">
              <img v-if="errorForm.question_type === 'image'" :src="errorForm.question" class="preview-img" @error="handleImgError" />
              <div v-else class="preview-text">{{ errorForm.question?.substring(0, 200) }}{{ (errorForm.question?.length || 0) > 200 ? '...' : '' }}</div>
            </div>
          </div>

          <div class="form-group">
            <label>错误原因 <span class="required">*</span></label>
            <textarea v-model="errorForm.error_reason" placeholder="请描述错误原因（如：忘记公式、计算错误、概念不清等）..." rows="3" ref="reasonInput"></textarea>
          </div>

          <div class="form-group">
            <label>分类标签</label>
            <div class="tag-grid">
              <button v-for="tag in availableTags" :key="tag" class="tag-btn" :class="{ selected: errorForm.categories.includes(tag) }" @click="toggleTag(tag)">
                {{ tag }}
              </button>
            </div>
          </div>

          <div class="form-group">
            <label>笔记（可选）</label>
            <textarea v-model="errorForm.notes" placeholder="补充说明或解题技巧..." rows="2"></textarea>
          </div>

          <div class="modal-buttons">
            <button class="btn-cancel" @click="closeErrorModal">取消</button>
            <button class="btn-confirm" @click="confirmAddError">✅ 确认添加</button>
          </div>
        </div>
      </div>
    </Teleport>
  </LayoutDefault>
</template>

<script setup>
import { ref, reactive, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import LayoutDefault from '@/components/layout/LayoutDefault.vue'
import MessageItem from '@/components/chat/MessageItem.vue'
import InputArea from '@/components/chat/InputArea.vue'
import { useChatStore } from '@/stores/chatStore'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { sendChatMessage, sendMultimodalRequest, parseSSEStream } from '@/api/chat'
import { renderMathInElement } from '@/utils/mathRender'
import { formatStreamText } from '@/utils/markdown'
import { generateUUID } from '@/utils/helpers'

const route = useRoute()
const store = useChatStore()
const errorBookStore = useErrorBookStore()

const messagesRef = ref(null)
const streaming = ref(false)
const streamingMessageId = ref(null)
const streamingCharCount = ref(0)
const abortController = ref(null)
const reasonInput = ref(null)

const showErrorModal = ref(false)
const errorForm = reactive({
  question: '',
  question_type: 'text',
  correct_answer: '',
  error_reason: '',
  categories: [],
  notes: '',
  mastery_level: 3,
  is_mastered: false
})

let currentErrorMsgId = null

const availableTags = ['极限', '导数', '积分', '微分方程', '级数', '多元函数']

watch(() => store.currentMessages.length, () => {
  nextTick(() => scrollToBottom())
})

onMounted(() => {
  const chatId = route.params.chatId
  if (chatId) {
    const exists = store.chats.find(c => c.id === chatId)
    if (exists) store.switchChat(chatId)
  }
  nextTick(() => scrollToBottom())
})

function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

async function handleCombinedSend({ text, image }) {
  if (image) {
    await handleMultimodalSend(text, image)
  } else if (text && text.trim()) {
    await handleTextSend(text.trim())
  }
}

let typingBuffer = ''
let rawContentBuffer = ''
let isTyping = false

function processTyping(msgId) {
  const el = document.getElementById(`msg-${msgId}`)
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

  if (streamingCharCount.value % 30 === 0 || chunk === '\n' || typingBuffer.length === 0) {
    const contentDiv = el.querySelector('.msg-content')
    if (contentDiv) {
      const display = formatStreamText(rawContentBuffer)
      contentDiv.innerHTML = display
      renderMathInElement(contentDiv)
    }
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

async function handleMultimodalSend(text, imageData) {
  if (streaming.value) return

  const chatId = store.currentChatId

  const userMessageContent = text && text.trim() ? text.trim() : ''
  store.addMessage(chatId, {
    content: imageData,
    sender: 'user',
    timestamp: new Date().toLocaleString(),
    type: 'image',
    text: userMessageContent
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

  try {
    const response = await sendMultimodalRequest(userMessageContent, imageData, chatId, abortController.value.signal)

    if (!response.ok) throw new Error('多模态请求失败')

    const handleData = (data) => {
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

      let displayText = rawContentBuffer
      store.updateMessage(chatId, msgId, {
        content: displayText || '抱歉，未获取到有效回复。',
        timestamp: new Date().toLocaleString()
      })

      nextTick(() => {
        const el = document.getElementById(`msg-${msgId}`)
        if (el) {
          renderMathInElement(el)
        }
        scrollToBottom()
      })
    }

    const handleError = () => {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误，请重试。',
        timestamp: new Date().toLocaleString()
      })
    }

    await parseSSEStream(response, handleData, handleDone, handleError)
  } catch (err) {
    if (err.name !== 'AbortError' && err.code !== 'ERR_CANCELED') {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误: ' + err.message,
        timestamp: new Date().toLocaleString()
      })
    }
  }
}

async function handleTextSend(text) {
  if (!text || streaming.value) return

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

  try {
    const response = await sendChatMessage(text, chatId, abortController.value.signal)

    if (!response.ok) throw new Error('API请求失败')

    const handleData = (data) => {
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
        timestamp: new Date().toLocaleString()
      })

      nextTick(() => {
        const el = document.getElementById(`msg-${msgId}`)
        if (el) {
          renderMathInElement(el)
        }
        scrollToBottom()
      })
    }

    const handleError = () => {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误，请重试。',
        timestamp: new Date().toLocaleString()
      })
    }

    await parseSSEStream(response, handleData, handleDone, handleError)
  } catch (err) {
    if (err.name !== 'AbortError' && err.code !== 'ERR_CANCELED') {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误: ' + err.message,
        timestamp: new Date().toLocaleString()
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

function openErrorBookDialog(msgId) {
  const chat = store.currentChat
  const msgIdx = chat.messages.findIndex(m => m.id === msgId)
  const aiMsg = chat.messages[msgIdx]
  const userMsg = chat.messages
    .slice(0, msgIdx)
    .reverse()
    .find(m => m.sender === 'user')

  if (!aiMsg || !userMsg) {
    ElMessage.error('未找到对应的问题')
    return
  }

  currentErrorMsgId = msgId
  errorForm.question = userMsg.content || ''
  errorForm.question_type = userMsg.type === 'image' ? 'image' : 'text'
  errorForm.correct_answer = extractBestAnswer(aiMsg.content)
  errorForm.error_reason = ''
  errorForm.categories = []
  errorForm.notes = ''

  showErrorModal.value = true
  nextTick(() => reasonInput.value?.focus())
}

function extractBestAnswer(content) {
  if (!content) return ''
  const lines = content.split('\n')
  const answerLine = lines.find(l => l.startsWith('**答案') || l.startsWith('答案') || l.startsWith('最终答案'))
  if (answerLine) return answerLine
  const lastLine = lines.filter(l => l.trim()).pop()
  if (lastLine && lastLine.length < 500) return lastLine.trim()
  return content.slice(0, 500)
}

function toggleTag(tag) {
  const idx = errorForm.categories.indexOf(tag)
  if (idx === -1) errorForm.categories.push(tag)
  else errorForm.categories.splice(idx, 1)
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
    store.setErrorBookStatus(store.currentChatId, currentErrorMsgId, 'added')
    closeErrorModal()
    ElMessage.success('已成功加入错题本！')
  } catch (err) {
    console.error('添加错题失败:', err)
    ElMessage.error(err?.response?.data?.detail || '添加失败，请重试')
  }
}

function handleSkip(msgId) {
  store.setErrorBookStatus(store.currentChatId, msgId, 'skipped')
}

function handleImgError(e) {
  e.target.style.display = 'none'
  const fallback = e.target.nextElementSibling
  if (fallback && fallback.classList.contains('img-fallback')) {
    fallback.style.display = 'block'
  }
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.chat-header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: 1;
  gap: 16px;
}

.chat-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
}

.header-actions { 
  display: flex; 
  gap: 10px; 
}

.btn-action {
  padding: 8px 18px;
  border: 1.5px solid var(--border-light);
  border-radius: $radius-full;
  background: var(--bg-card);
  backdrop-filter: blur(8px);
  font-size: 13px;
  cursor: pointer;
  color: var(--text-secondary);
  font-family: inherit;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover:not(:disabled) {
    border-color: var(--primary);
    color: var(--primary);
    background: var(--primary-ghost);
    transform: translateY(-1px);
    box-shadow: var(--shadow-md);
  }
  
  &:disabled { 
    opacity: 0.5; 
    cursor: not-allowed; 
  }
}

.btn-stop {
  padding: 8px 18px;
  border: 1.5px solid rgba(239, 68, 68, 0.3);
  border-radius: $radius-full;
  background: rgba(239, 68, 68, 0.08);
  backdrop-filter: blur(8px);
  color: var(--danger);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    background: rgba(239, 68, 68, 0.12);
    transform: translateY(-1px);
    box-shadow: var(--shadow-md);
  }
}

.stop-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--danger);
  animation: pulse-dot 1.5s infinite;
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.3; transform: scale(0.85); }
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 28px 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  scroll-behavior: smooth;

  &::-webkit-scrollbar {
    width: 6px;
    
    &-thumb {
      background: rgba(148, 163, 184, 0.3);
      border-radius: $radius-full;
      
      &:hover {
        background: rgba(148, 163, 184, 0.5);
      }
    }
  }
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 20px;
  align-self: flex-start;
  background: var(--primary-ghost);
  backdrop-filter: blur(10px);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);

  .dot {
    width: 8px; height: 8px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    border-radius: 50%;
    animation: bounce 1.4s infinite both;
    box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3);
    &:nth-child(1) { animation-delay: -0.32s; }
    &:nth-child(2) { animation-delay: -0.16s; }
  }
  .loading-text { 
    font-size: 13px; 
    color: var(--primary); 
    margin-left: 6px;
    font-weight: 500;
  }
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.message-enter-active {
  transition: all 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.message-leave-active {
  transition: all 0.25s ease;
  position: absolute;
}
.message-enter-from {
  opacity: 0;
  transform: translateY(30px) scale(0.95);
}
.message-leave-to {
  opacity: 0;
}

// Modal
.modal-backdrop {
  position: fixed; inset: 0;
  background: var(--bg-overlay);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.35s ease;
}

@keyframes fadeIn { 
  from { 
    opacity: 0; 
    backdrop-filter: blur(0);
  } 
  to { 
    opacity: 1; 
  } 
}

.error-modal-dialog {
  background: var(--bg-card);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border-radius: var(--radius-xl);
  padding: 32px 36px;
  max-width: 540px;
  width: 94%;
  max-height: 88vh;
  overflow-y: auto;
  box-shadow: var(--shadow-lg);
  animation: modalIn 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);

  h3 { 
    font-size: 21px; 
    margin-bottom: 24px; 
    color: var(--primary);
    font-weight: 700;
  }
}

@keyframes modalIn {
  from { 
    opacity: 0; 
    transform: scale(0.92) translateY(30px); 
  }
  to { 
    opacity: 1; 
    transform: scale(1) translateY(0); 
  }
}

.form-group {
  margin-bottom: 20px;

  label {
    display: block;
    font-size: 13.5px;
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--text-primary);
  }
  .required { color: var(--danger); }
}

.form-group textarea {
  width: 100%;
  padding: 12px 16px;
  border: 1.5px solid var(--border-light);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  outline: none;
  transition: all 0.3s ease;
  background: var(--bg-card);
  color: var(--text-primary);

  &:focus { 
    border-color: var(--primary); 
    box-shadow: 0 0 0 4px var(--primary-ghost); 
    background: var(--bg-card);
  }

  &::placeholder {
    color: var(--text-tertiary);
  }
}

.preview-box { 
  padding: 16px; 
  background: var(--bg-card); 
  border-radius: var(--radius-md); 
  min-height: 50px; 
  border: 1.5px solid var(--border-light);
}
.preview-img { 
  max-width: 100%; 
  max-height: 180px; 
  border-radius: $radius-sm; 
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.preview-text { 
  font-size: 14px; 
  color: var(--text-secondary); 
  line-height: 1.6;
}

.tag-grid { 
  display: flex; 
  flex-wrap: wrap; 
  gap: 8px; 
}

.tag-btn {
  padding: 8px 20px;
  border: 1.5px solid var(--border-light);
  border-radius: $radius-full;
  background: var(--bg-card);
  backdrop-filter: blur(8px);
  font-size: 13px;
  cursor: pointer;
  color: var(--text-secondary);
  font-family: inherit;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover { 
    border-color: var(--primary); 
    color: var(--primary);
    background: var(--primary-ghost);
    transform: translateY(-1px);
  }
  
  &.selected {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%); 
    border-color: transparent; 
    color: white;
    box-shadow: var(--shadow-md);
  }
}

.modal-buttons {
  display: flex; 
  gap: 12px; 
  margin-top: 28px; 
  justify-content: flex-end;

  button {
    padding: 11px 26px;
    border-radius: $radius-full;
    font-size: 14px;
    font-family: inherit;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border: none;
  }
}

.btn-cancel {
  background: var(--primary-ghost); 
  color: var(--text-secondary);
  
  &:hover { 
    background: var(--border-light);
    transform: translateY(-1px);
  }
}

.btn-confirm {
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%); 
  color: white;
  box-shadow: var(--shadow-glow);
  
  &:hover { 
    filter: brightness(1.1);
    transform: translateY(-2px); 
    box-shadow: var(--shadow-glow);
  }
  
  &:active {
    transform: translateY(0);
  }
}

@media (max-width: 768px) {
  .chat-title {
    font-size: 15px;
  }
  
  .messages-area {
    padding: 20px 16px;
    gap: 20px;
  }
  
  .error-modal-dialog {
    padding: 24px;
    margin: 16px;
  }
}
</style>
