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
import { sendChatMessage, sendRecognizeRequest, parseSSEStream } from '@/api/chat'
import { renderMathInElement, renderMathSync } from '@/utils/mathRender'
import { formatStreamText, renderMarkdown } from '@/utils/markdown'
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
    await handleImageSend(image)
  }
  if (text && text.trim()) {
    await handleTextSend(text.trim())
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
  let typingBuffer = ''
  let isTyping = false
  let rawContentBuffer = ''

  try {
    const response = await sendChatMessage(text, chatId, abortController.value.signal)

    if (!response.ok) throw new Error('API请求失败')

    const handleData = (data) => {
      if (data.type === 'content' && data.content) {
        typingBuffer += data.content
        rawContentBuffer += data.content
        if (!isTyping) {
          isTyping = true
          processTyping()
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

    function processTyping() {
      const el = document.getElementById(`msg-${msgId}`)
      if (!el || typingBuffer.length === 0) {
        if (!streaming.value || typingBuffer.length === 0) {
          isTyping = false
          return
        }
        setTimeout(processTyping, 50)
        return
      }

      const chunk = typingBuffer.substring(0, 1)
      typingBuffer = typingBuffer.substring(1)
      streamingCharCount.value++

      if (streamingCharCount.value % 30 === 0 || chunk === '\n' || typingBuffer.length === 0) {
        const contentDiv = el.querySelector('.msg-content')
        if (contentDiv) {
          let display = formatStreamText(rawContentBuffer)
          contentDiv.innerHTML = display
          
          renderMathInElement(contentDiv)
        }
      }

      scrollToBottom()
      if (typingBuffer.length > 0) {
        setTimeout(processTyping, 8)
      } else if (streaming.value) {
        setTimeout(processTyping, 50)
      } else {
        isTyping = false
      }
    }

    await parseSSEStream(response, handleData, handleDone, handleError)
  } catch (err) {
    if (err.name !== 'AbortError') {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误: ' + err.message,
        timestamp: new Date().toLocaleString()
      })
    }
  }
}

async function handleImageSend(imageData) {
  if (streaming.value) return

  const chatId = store.currentChatId
  store.addMessage(chatId, { content: imageData, sender: 'user', timestamp: new Date().toLocaleString(), type: 'image' })
  store.persistChats()
  nextTick(() => scrollToBottom())

  const msgId = generateUUID()
  store.addMessage(chatId, { id: msgId, content: '', sender: 'ai', timestamp: '正在识别...', type: 'text' })

  streaming.value = true
  streamingMessageId.value = msgId
  streamingCharCount.value = 0

  let fullText = ''

  try {
    const response = await sendRecognizeRequest(imageData, chatId)

    if (!response.ok) throw new Error('识别请求失败')

    await parseSSEStream(response,
      (data) => {
        if (data.content) {
          fullText += data.content
          store.updateMessage(chatId, msgId, {
            content: fullText,
            timestamp: '识别中...'
          })
          nextTick(() => scrollToBottom())
        }
      },
      () => {
        streaming.value = false
        streamingMessageId.value = null

        let displayText = fullText
        const marker = '【图片识别结果】\n'
        const idx = fullText.indexOf(marker)
        if (idx !== -1) displayText = fullText.substring(idx + marker.length)

        store.updateMessage(chatId, msgId, {
          content: displayText || fullText || '抱歉，图片识别失败。',
          timestamp: new Date().toLocaleString()
        })

        nextTick(() => {
          renderMathInElement(document.getElementById(`msg-${msgId}`))
          scrollToBottom()
        })
      },
      () => {
        streaming.value = false
        streamingMessageId.value = null
        store.updateMessage(chatId, msgId, {
          content: fullText || '识别发生错误',
          timestamp: new Date().toLocaleString()
        })
      }
    )
  } catch (err) {
    streaming.value = false
    streamingMessageId.value = null
    store.updateMessage(chatId, msgId, {
      content: '图片识别错误: ' + err.message,
      timestamp: new Date().toLocaleString()
    })
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
  const userMsg = chat.messages[msgIdx - 1]

  if (!aiMsg || !userMsg) {
    ElMessage.error('未找到对应的问题')
    return
  }

  currentErrorMsgId = msgId
  errorForm.question = userMsg.content || ''
  errorForm.question_type = userMsg.type === 'image' ? 'image' : 'text'
  errorForm.correct_answer = aiMsg.content || ''
  errorForm.error_reason = ''
  errorForm.categories = []
  errorForm.notes = ''

  showErrorModal.value = true
  nextTick(() => reasonInput.value?.focus())
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
  } catch {
    ElMessage.error('添加失败，请重试')
  }
}

function handleSkip(msgId) {
  store.setErrorBookStatus(store.currentChatId, msgId, 'skipped')
}

function handleImgError(e) {
  e.target.style.display = 'none'
  e.target.nextElementSibling && (e.target.nextElementSibling.style.display = 'block')
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
  font-size: 16px;
  font-weight: 600;
  color: $text-primary;
}

.header-actions { display: flex; gap: 10px; }

.btn-action {
  padding: 7px 16px;
  border: 1px solid $border-color;
  border-radius: $radius-full;
  background: white;
  font-size: 13px;
  cursor: pointer;
  color: $text-secondary;
  font-family: inherit;
  transition: all $transition-fast;

  &:hover:not(:disabled) {
    border-color: $primary;
    color: $primary;
  }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.btn-stop {
  padding: 7px 16px;
  border: 1px solid #fca5a5;
  border-radius: $radius-full;
  background: $danger-light;
  color: $danger;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all $transition-fast;

  &:hover {
    background: #fecaca;
  }
}

.stop-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: $danger;
  animation: pulse-dot 1.5s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 20px;
  align-self: flex-start;

  .dot {
    width: 7px; height: 7px;
    background: $primary;
    border-radius: 50%;
    animation: bounce 1.4s infinite both;
    &:nth-child(1) { animation-delay: -0.32s; }
    &:nth-child(2) { animation-delay: -0.16s; }
  }
  .loading-text { font-size: 13px; color: $text-tertiary; margin-left: 6px; }
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.message-enter-active {
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.message-leave-active {
  transition: all 0.2s ease;
  position: absolute;
}
.message-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}
.message-leave-to {
  opacity: 0;
}

// Modal
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.45);
  backdrop-filter: blur(2px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.3s;
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.error-modal-dialog {
  background: white;
  border-radius: $radius-xl;
  padding: 28px 32px;
  max-width: 520px;
  width: 92%;
  max-height: 88vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
  animation: modalIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);

  h3 { font-size: 20px; margin-bottom: 22px; color: $primary; }
}

@keyframes modalIn {
  from { opacity: 0; transform: scale(0.9) translateY(20px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.form-group {
  margin-bottom: 18px;

  label {
    display: block;
    font-size: 13.5px;
    font-weight: 600;
    margin-bottom: 7px;
    color: $text-primary;
  }
  .required { color: $danger; }
}

.form-group textarea {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid $border-color;
  border-radius: $radius-md;
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  outline: none;
  transition: border-color $transition-fast;

  &:focus { border-color: $primary; box-shadow: 0 0 0 3px $primary-bg; }
}

.preview-box { padding: 14px; background: $bg-tertiary; border-radius: $radius-md; min-height: 50px; border: 1px solid $border-light; }
.preview-img { max-width: 100%; max-height: 180px; border-radius: $radius-sm; }
.preview-text { font-size: 14px; color: $text-secondary; }

.tag-grid { display: flex; flex-wrap: wrap; gap: 8px; }

.tag-btn {
  padding: 7px 18px;
  border: 1px solid $border-color;
  border-radius: $radius-full;
  background: white;
  font-size: 13px;
  cursor: pointer;
  color: $text-secondary;
  font-family: inherit;
  transition: all $transition-fast;

  &:hover { border-color: $primary; color: $primary; }
  &.selected {
    background: $primary; border-color: $primary; color: white;
  }
}

.modal-buttons {
  display: flex; gap: 12px; margin-top: 24px; justify-content: flex-end;

  button {
    padding: 10px 24px;
    border-radius: $radius-full;
    font-size: 14px;
    font-family: inherit;
    font-weight: 600;
    cursor: pointer;
    transition: all $transition-fast;
    border: none;
  }
}

.btn-cancel {
  background: $bg-tertiary; color: $text-secondary;
  &:hover { background: $border-color; }
}
.btn-confirm {
  background: $primary; color: white;
  &:hover { background: $primary-dark; transform: translateY(-1px); box-shadow: 0 4px 12px rgba($primary, 0.3); }
}
</style>
