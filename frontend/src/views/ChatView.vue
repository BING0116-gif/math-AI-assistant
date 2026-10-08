<script setup lang="ts">
import { ref, reactive, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppShell from '@/components/shell/AppShell.vue'
import MessageItem from '@/components/chat/MessageItem.vue'
import AgentComposer from '@/components/conversation/AgentComposer.vue'
import AskStudentCard from '@/components/chat/AskStudentCard.vue'
import ModeGuardNotice from '@/components/chat/ModeGuardNotice.vue'
import FollowUpRecommendation from '@/components/FollowUpRecommendation.vue'
import { useChatStore } from '@/stores/chatStore'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { useAuthStore } from '@/stores/authStore'
import { sendChatMessage, sendMultimodalRequest, answerClarification, parseSSEStream, recoverChatStream, cancelChatStream } from '@/api/chat'
import { formatStreamText } from '@/utils/markdown'
import { generateUUID, chatErrorSourceId } from '@/utils/helpers'
import { markSkippedSourceId, clearSkippedSourceId, listSkippedSourceIds } from '@/utils/errorBookDismissals'
import { DEFAULT_TUTOR_MODE, TUTOR_MODES, normalizeTutorMode } from '@/utils/tutorModes'
import { useAiCapability } from '@/composables/useAiCapability'

const route = useRoute()
const router = useRouter()
const store = useChatStore()
const errorBookStore = useErrorBookStore()
const auth = useAuthStore()
const { isAiAvailable, aiReason } = useAiCapability()

const messagesRef = ref<HTMLElement | null>(null)
const streaming = ref(false)
const streamingMessageId = ref<string | null>(null)
const streamingCharCount = ref(0)
const abortController = ref<AbortController | null>(null)
const activeStreamId = ref<string | null>(null)
const reasonInput = ref<HTMLTextAreaElement | null>(null)
const followUpQuestions = ref<any[]>([])
const askCard = ref<any>(null)
const modeGuardNotice = ref('')
const showErrorModal = ref(false)
const autoScroll = ref(true)
const tutorMode = ref(normalizeTutorMode(route.query.tutor_mode || store.currentChat?.defaultTutorMode || DEFAULT_TUTOR_MODE))
const tutorContext = {
  source_session_id: route.query.source_session_id ? String(route.query.source_session_id) : undefined,
  question_id: route.query.question_id ? String(route.query.question_id) : undefined,
  course_id: route.query.course_id ? String(route.query.course_id) : undefined,
  version_id: route.query.version_id ? String(route.query.version_id) : undefined,
  knowledge_point_codes: route.query.knowledge_point ? [String(route.query.knowledge_point)] : [],
}

const errorForm = reactive({
  id: '',
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
let currentErrorSourceKey = ''
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

// 为一条 AI 回答计算与“加入错题本”一致的稳定来源键（上一句用户问题 + 会话 ID）。
function sourceKeyForAiMessage(msgId: string): string {
  const msgs = store.currentMessages as any[]
  const idx = msgs.findIndex((m: any) => m.id === msgId)
  if (idx <= 0) return ''
  return chatErrorSourceId(store.currentChatId, msgs[idx - 1]?.content || '')
}

// 回填助手消息的错题本徒章：loadServerChat 会把助手消息重置为 pending，
// 这里用稳定来源键比对错题本（added）与本地跳过登记（skipped），added 优先。
function reconcileErrorBookBadges() {
  const chatId = store.currentChatId
  if (!chatId) return
  const addedKeys = new Set<string>(
    (errorBookStore.errors || [])
      .map((e: any) => e.id)
      .filter((id: any) => typeof id === 'string' && (id as string).startsWith('chat:'))
  )
  const skippedKeys = new Set<string>(listSkippedSourceIds(auth.userId))
  if (!addedKeys.size && !skippedKeys.size) return
  const msgs = store.currentMessages as any[]
  for (let i = 1; i < msgs.length; i++) {
    const m = msgs[i]
    if (m.sender === 'ai' && !m.system && m.errorBookStatus !== 'added') {
      const key = chatErrorSourceId(chatId, msgs[i - 1].content || '')
      if (addedKeys.has(key)) store.setErrorBookStatus(chatId, m.id, 'added', key)
      else if (m.errorBookStatus === 'pending' && skippedKeys.has(key)) store.setErrorBookStatus(chatId, m.id, 'skipped')
    }
  }
}

watch(() => store.currentChatId, () => {
  nextTick(reconcileErrorBookBadges)
})

onMounted(async () => {
  await store.syncFromServer().catch(() => {})
  const chatId = route.params.chatId as string
  if (chatId) {
    const exists = store.chats.find(c => c.id === chatId)
    if (exists) {
      store.switchChat(chatId)
    } else {
      await store.loadServerChat(chatId).catch(() => router.replace('/chat'))
    }
  }
  if (!route.query.tutor_mode) {
    tutorMode.value = normalizeTutorMode(store.currentChat?.defaultTutorMode)
  }

  // 加载错题本以回填当前会话消息的“已加入”状态
  await errorBookStore.loadErrors().catch(() => {})
  reconcileErrorBookBadges()

  // 首页带问题进入：自动触发首次回答（文本走 query，图片走 store 暂存）
  const initQuery = typeof route.query.q === 'string' ? route.query.q.trim() : ''
  if (initQuery) {
    router.replace({ path: chatId ? `/chat/${chatId}` : '/chat', query: { ...route.query, q: undefined } })
    await nextTick()
    if (!streaming.value) handleTextSend(initQuery)
  } else if (store.pendingImage) {
    const pending = store.pendingImage
    store.pendingImage = null
    await nextTick()
    if (!streaming.value) handleSendWithImage(pending.text || '', pending.image)
  }
})

onUnmounted(() => {
  if (renderRafId) {
    cancelAnimationFrame(renderRafId)
    renderRafId = null
  }
  // Track A 9.6：组件卸载时取消尚未触发的合并 flush 并丢弃排队事件，
  // 避免卸载后定时器仍回调 store.updateMessage 与滚动
  if (agentStepFlushTimer !== null) {
    clearTimeout(agentStepFlushTimer)
    agentStepFlushTimer = null
  }
  pendingAgentStepBatches.clear()
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

// SSE 事件处理（命名事件：follow_up / ask_student）
// Track A 9.6:agent_step 高频事件按 50ms 窗口合并,统一 flush 进 store,
// 长推导(>100 事件)不再逐条触发响应式更新与滚动
const pendingAgentStepBatches = new Map<string, any[]>()
let agentStepFlushTimer: number | null = null

function queueAgentStep(data: any, messageId: string) {
  const list = pendingAgentStepBatches.get(messageId) || []
  list.push(data)
  pendingAgentStepBatches.set(messageId, list)
  if (agentStepFlushTimer === null) {
    agentStepFlushTimer = window.setTimeout(flushAgentSteps, 50)
  }
}

function applyAgentStep(steps: any[], data: any): any[] {
  const next = [...steps]
  if ((data.event_type === 'tool_end' || data.event_type === 'tool_error') && data.tool) {
    const active = [...next].reverse().find(item => item.tool === data.tool && item.status === 'running')
    if (active) active.status = data.event_type === 'tool_error' ? 'error' : 'done'
  } else {
    next.push({
      type: data.event_type || 'thinking',
      tool: data.tool || '',
      label: data.message || '正在处理',
      status: data.event_type === 'tool_start'
        ? 'running'
        : (data.event_type === 'tool_error' ? 'error' : 'done'),
    })
  }
  return next
}

function flushAgentSteps() {
  // 手动调用（如 handleDone）时同样取消已排的定时器，防止双重 flush 与定时器漂移
  if (agentStepFlushTimer !== null) {
    clearTimeout(agentStepFlushTimer)
    agentStepFlushTimer = null
  }
  if (pendingAgentStepBatches.size === 0) return
  const batches = new Map(pendingAgentStepBatches)
  pendingAgentStepBatches.clear()
  let touched = false
  for (const [messageId, events] of batches) {
    const message = store.currentMessages.find(item => item.id === messageId)
    if (!message) continue
    let steps = [...(message.agentSteps || [])]
    for (const data of events) {
      steps = applyAgentStep(steps, data)
    }
    store.updateMessage(store.currentChatId, messageId, { agentSteps: steps }, { persist: false })
    touched = true
  }
  if (touched) nextTick(() => scrollToBottom())
}

function handleEvent(eventType: string, data: any, messageId?: string) {
  if (eventType === 'agent_step' && messageId) {
    queueAgentStep(data, messageId)
    return
  }
  if (eventType === 'follow_up' && data.type === 'recommendation') {
    const content = data.content || ''
    const questions = parseFollowUpContent(content)
    if (questions.length > 0) {
      followUpQuestions.value = questions
      nextTick(() => scrollToBottom())
    }
  }
  // T03: ask_student 结构化反问事件 → 渲染澄清问题卡片
  if (eventType === 'ask_student' && data.clarification_id) {
    askCard.value = data
    followUpQuestions.value = []
    nextTick(() => scrollToBottom())
  }
  if (eventType === 'mode_guard' && data.type === 'mode_tool_denied') {
    modeGuardNotice.value = data.message || '该模式下此操作不可用'
    ElMessage.warning(modeGuardNotice.value)
    nextTick(() => scrollToBottom())
  }
  if (eventType === 'visualization' && messageId) {
    store.updateMessage(store.currentChatId, messageId, {
      visualization: data.spec || null,
      visualizationStatus: data.visualization_status || 'failed',
      visualizationVerification: data.verification || null,
    })
    nextTick(() => scrollToBottom())
  }
  if (eventType === 'animation_job' && messageId && data.job_id) {
    store.updateMessage(store.currentChatId, messageId, { animation: data })
    nextTick(() => scrollToBottom())
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

// 共享的 SSE 流式处理：负责流式状态、打字机渲染、错误兜底。
// fetchFn 接收 AbortSignal 并返回 Response（/api/chat 与澄清回答端点同构）。
async function streamAgentReply(
  fetchFn: (signal: AbortSignal) => Promise<Response>,
  chatId: string,
  msgId: string,
) {
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
    const response = await fetchFn(abortController.value.signal)
    if (response.status < 200 || response.status >= 300) {
      // 业务校验错误（如 409 CLARIFICATION_MISMATCH）透出后端 message，
      // 不包装成"后端故障"（红线 9）
      let detail = ''
      try {
        const j = await response.json()
        detail = j?.detail?.message || (typeof j?.detail === 'string' ? j.detail : '')
      } catch { /* 非 JSON 响应体时忽略 */ }
      throw new Error(detail || 'API请求失败 (' + response.status + ')')
    }

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

    const handleDone = (state: any = {}) => {
      if (state.disconnected) return
      flushAgentSteps()
      streaming.value = false
      streamingMessageId.value = null
      activeStreamId.value = null
      store.updateMessage(chatId, msgId, {
        content: rawContentBuffer || '抱歉，未获取到有效回复。',
        timestamp: new Date().toISOString(),
      })
      nextTick(() => scrollToBottom())
    }

    let streamId: string | null = null
    let lastEventId = -1
    let currentResponse = response
    let recoveryDeadline: number | null = null
    let userCancelled = false
    while (true) {
      let streamError: any = null
      const result = await parseSSEStream(
        currentResponse,
        handleData,
        handleDone,
        (error: any) => { streamError = error },
        (eventType: string, data: any) => {
          if (eventType === 'stream' && data.stream_id) streamId = data.stream_id
          if (eventType === 'cancelled') userCancelled = true
          if (eventType === 'critic' && data?.verdict) {
            // 5-C 可信度徽标:Critic 后验结果挂到消息上
            store.updateMessage(chatId, msgId, { critic: { verdict: data.verdict, issues: data.issues || [] } })
          }
          if (eventType === 'reset') {
            // 服务端淘汰过旧事件后要求整段重拉：清空本地缓冲，由重放内容重建消息
            typingBuffer = ''
            rawContentBuffer = ''
            // Track A 9.6：同步丢弃该消息尚未 flush 的 agent_step 队列，避免旧事件在重置后回填
            pendingAgentStepBatches.delete(msgId)
            store.updateMessage(chatId, msgId, { content: '', agentSteps: [] })
          }
          handleEvent(eventType, data, msgId)
        },
      )
      streamId = result?.streamId || streamId
      activeStreamId.value = streamId
      lastEventId = Number.isFinite(result?.lastEventId) ? result.lastEventId : lastEventId
      if (result?.completed) {
        if (userCancelled) {
          store.updateMessage(chatId, msgId, {
            content: (rawContentBuffer || '') + '\n\n*(已手动停止)*',
            timestamp: new Date().toISOString(),
          })
        }
        return
      }
      if (!streamId || abortController.value?.signal.aborted) {
        throw streamError || new Error('流式响应中断，续传失败')
      }
      recoveryDeadline ??= performance.now() + 5000
      while (true) {
        if (performance.now() >= recoveryDeadline) throw streamError || new Error('流式响应续传失败')
        await new Promise(resolve => setTimeout(resolve, 500))
        try {
          currentResponse = await recoverChatStream(chatId, streamId, lastEventId, abortController.value.signal)
          if (currentResponse.ok) break
          if (currentResponse.status === 404) throw new Error('流已过期，请重新发送')
        } catch (error: any) {
          if (abortController.value?.signal.aborted || error.message === '流已过期，请重新发送') throw error
          streamError = error
        }
      }
    }
  } catch (err: any) {
    if (err.name !== 'AbortError' && err.code !== 'ERR_CANCELED') {
      streaming.value = false
      streamingMessageId.value = null
      activeStreamId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误: ' + err.message,
        timestamp: new Date().toISOString(),
      })
    }
  }
}

async function handleTextSend(text: string) {
  if (!text || streaming.value) return
  if (!isAiAvailable.value) return
  followUpQuestions.value = []
  modeGuardNotice.value = ''
  // 学生忽略卡片直接发新消息时，收起待答卡片
  askCard.value = null

  const chatId = store.currentChatId
  store.addMessage(chatId, { content: text, sender: 'user', timestamp: new Date().toISOString(), type: 'text' })
  store.persistChats()
  nextTick(() => scrollToBottom())

  const msgId = generateUUID()
  // 占位消息的 timestamp 必须是真正的时间戳：它会被写进 chat.lastMessageTime 参与排序。
  // “正在生成”的提示态由 streaming + streamingMessageId 驱动，不靠时间字段承载。
  const placeholder = { id: msgId, content: '', sender: 'ai', timestamp: new Date().toISOString(), type: 'text', agentSteps: [] }
  store.addMessage(chatId, placeholder)

  await streamAgentReply(
    (signal) => sendChatMessage(text, chatId, signal, { tutorMode: tutorMode.value, context: tutorContext }),
    chatId,
    msgId,
  )
}

// T03: 学生提交澄清回答 → 校验标识并语义续接对话
async function handleClarificationSubmit({ answer }: { answer: string; optionLabel?: string }) {
  const card = askCard.value
  if (!card || streaming.value) return
  if (!answer || !answer.trim()) return
  askCard.value = null
  modeGuardNotice.value = ''

  const chatId = store.currentChatId
  store.addMessage(chatId, { content: answer.trim(), sender: 'user', timestamp: new Date().toISOString(), type: 'text' })
  store.persistChats()
  nextTick(() => scrollToBottom())

  const msgId = generateUUID()
  // 占位消息的 timestamp 必须是真正的时间戳：它会被写进 chat.lastMessageTime 参与排序。
  // “正在生成”的提示态由 streaming + streamingMessageId 驱动，不靠时间字段承载。
  const placeholder = { id: msgId, content: '', sender: 'ai', timestamp: new Date().toISOString(), type: 'text', agentSteps: [] }
  store.addMessage(chatId, placeholder)

  await streamAgentReply(
    (signal) => answerClarification(
      {
        sessionId: chatId,
        clarificationId: card.clarification_id,
        pendingTurnId: card.pending_turn_id,
        answer: answer.trim(),
      },
      signal,
      { tutorMode: tutorMode.value, context: tutorContext },
    ),
    chatId,
    msgId,
  )
}

async function handleSendWithImage(text: string, imageData: string) {
  if (streaming.value) return
  if (!isAiAvailable.value) return
  followUpQuestions.value = []
  modeGuardNotice.value = ''

  const chatId = store.currentChatId
  const userMessageContent = text && text.trim() ? text.trim() : ''
  store.addMessage(chatId, {
    content: imageData,
    sender: 'user',
    timestamp: new Date().toISOString(),
    type: 'image',
    text: userMessageContent,
  })
  store.persistChats()
  nextTick(() => scrollToBottom())

  const msgId = generateUUID()
  store.addMessage(chatId, { id: msgId, content: '', sender: 'ai', timestamp: new Date().toISOString(), type: 'text', agentSteps: [] })

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
    const response = await sendMultimodalRequest(userMessageContent, imageData, chatId, abortController.value.signal, { tutorMode: tutorMode.value, context: tutorContext })
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
        timestamp: new Date().toISOString(),
      })
      nextTick(() => scrollToBottom())
    }

    const handleError = () => {
      streaming.value = false
      streamingMessageId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误，请重试。',
        timestamp: new Date().toISOString(),
      })
    }

    await parseSSEStream(
      response,
      handleData,
      handleDone,
      handleError,
      (eventType: string, data: any) => handleEvent(eventType, data, msgId),
    )
  } catch (err: any) {
    if (err.name !== 'AbortError' && err.code !== 'ERR_CANCELED') {
      streaming.value = false
      streamingMessageId.value = null
      activeStreamId.value = null
      store.updateMessage(chatId, msgId, {
        content: '发生错误: ' + err.message,
        timestamp: new Date().toISOString(),
      })
    }
  }
}

async function stopGeneration() {
  // 4.5：优先走服务端优雅取消（已产出内容保留，cancelled+done 收尾），
  // 服务端取消不可用时退回本地中断。
  const sid = activeStreamId.value
  if (sid) {
    try {
      await cancelChatStream(sid)
      return
    } catch {
      // 落入本地中断兜底
    }
  }
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
  const messages = store.currentMessages
  const msgIdx = messages.findIndex((m: any) => m.id === msgId)
  const aiMsg = messages[msgIdx]
  const userMsg = messages[msgIdx - 1]

  if (!aiMsg || !userMsg) {
    ElMessage.error('未找到对应的问题')
    return
  }

  currentErrorMsgId = msgId
  // 稳定来源键：会话 ID + 上一句用户问题，后端据此幂等去重、前端据此回填“已加入”
  currentErrorSourceKey = chatErrorSourceId(store.currentChatId, userMsg.content || '')
  errorForm.id = currentErrorSourceKey
  errorForm.question = userMsg.content || ''
  errorForm.question_type = (userMsg as any).type === 'image' ? 'image' : 'text'
  errorForm.correct_answer = errorBookStore.extractBestAnswer(aiMsg.content) || ''
  errorForm.error_reason = ''
  errorForm.categories = []
  errorForm.notes = ''

  showErrorModal.value = true
  nextTick(() => reasonInput.value?.focus())
}

function toggleTag(tag: string) {
  const idx = errorForm.categories.indexOf(tag)
  if (idx === -1) errorForm.categories.push(tag)
  else errorForm.categories.splice(idx, 1)
}

function handleImgError(e: Event) {
  const target = e.target as HTMLElement
  target.style.display = 'none'
  const fallback = target.nextElementSibling as HTMLElement | null
  if (fallback && fallback.classList.contains('img-fallback')) {
    fallback.style.display = 'block'
  }
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
    store.setErrorBookStatus(store.currentChatId, currentErrorMsgId!, 'added', currentErrorSourceKey)
    clearSkippedSourceId(auth.userId, currentErrorSourceKey)
    closeErrorModal()
    ElMessage.success('已成功加入错题本！')
  } catch (err: any) {
    console.error('添加错题失败:', err)
    ElMessage.error(err?.response?.data?.detail || '添加失败，请重试')
  }
}

function handleSkip(msgId: string) {
  store.setErrorBookStatus(store.currentChatId, msgId, 'skipped')
  const key = sourceKeyForAiMessage(msgId)
  if (key) markSkippedSourceId(auth.userId, key)
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
          <AskStudentCard
            v-if="askCard"
            :card="askCard"
            :disabled="streaming"
            @submit="handleClarificationSubmit"
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
        <ModeGuardNotice :message="modeGuardNotice" />
        <div class="tutor-modes" aria-label="AI Tutor 辅导方式">
          <span>辅导方式</span>
          <button v-for="item in TUTOR_MODES" :key="item.value" :class="{active:tutorMode===item.value}" :aria-pressed="tutorMode===item.value" :disabled="streaming" @click="tutorMode=item.value;store.setTutorMode(store.currentChatId,item.value)">{{item.label}}</button>
        </div>
        <AgentComposer
          :disabled="!isAiAvailable"
          :disabled-reason="aiReason"
          @send="handleTextSend"
          @send-image="handleSendWithImage"
        />
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showErrorModal" class="modal-backdrop" @click.self="closeErrorModal">
        <div class="error-modal-dialog" role="dialog" aria-modal="true" aria-label="添加到错题本">
          <h3>添加到错题本</h3>

          <div class="form-group">
            <label>题目预览</label>
            <div class="preview-box">
              <img
                v-if="errorForm.question_type === 'image'"
                :src="errorForm.question"
                class="preview-img"
                @error="handleImgError"
              />
              <img v-else class="preview-img img-fallback" style="display:none" alt="" />
              <div class="preview-text">{{ errorForm.question?.substring(0, 200) }}{{ (errorForm.question?.length || 0) > 200 ? '...' : '' }}</div>
            </div>
          </div>

          <div class="form-group">
            <label>错误原因 <span class="required">*</span></label>
            <textarea
              v-model="errorForm.error_reason"
              placeholder="请描述错误原因（如：忘记公式、计算错误、概念不清等）..."
              rows="3"
              ref="reasonInput"
            ></textarea>
          </div>

          <div class="form-group">
            <label>分类标签</label>
            <div class="tag-grid">
              <button
                v-for="tag in availableTags"
                :key="tag"
                class="tag-btn"
                :class="{ selected: errorForm.categories.includes(tag) }"
                @click="toggleTag(tag)"
              >
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
            <button class="btn-confirm" @click="confirmAddError">确认添加</button>
          </div>
        </div>
      </div>
    </Teleport>
  </AppShell>
</template>

<style scoped>
/* 原型 chat.html:正文列 768px 居中,消息区间距 22px,composer 吸底悬浮 */
.chat-view {
  flex: 1;
  /* 作为 .shell-content 的 flex 子项,必须允许收缩(min-height:0),
     否则长对话会撑破容器变回整页滚动,消息区内滚与固定输入框全部失效。 */
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg);
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  position: relative;
}

.messages-inner {
  max-width: 768px;
  margin: 0 auto;
  padding: 28px 32px 12px;
  display: flex;
  flex-direction: column;
  gap: 22px;
  width: 100%;
}

/* 输入区 — 底部固定,composer 圆角卡片悬浮在画布上 */
.composer-area {
  flex-shrink: 0;
  padding: 8px 32px 18px;
  max-width: 100%;
  margin: 0 auto;
  width: 100%;
  background: var(--bg);
}
@media (max-width: 768px) {
  .composer-area {
    padding-bottom: calc(18px + env(safe-area-inset-bottom));
  }
}
.tutor-modes{max-width:768px;margin:0 auto 9px;display:flex;align-items:center;gap:4px;flex-wrap:wrap;color:var(--ink-2);font-size:12.5px}.tutor-modes>span{padding:0 6px;font-size:11.5px;color:var(--ink-3)}.tutor-modes button{height:27px;padding:0 12px;border:1px solid transparent;border-radius:8px;background:transparent;color:var(--ink-2);font-size:12.5px;font-weight:500;cursor:pointer;transition:all .15s}.tutor-modes button.active{border-color:transparent;background:var(--brand-soft-2);color:var(--brand-text);font-weight:600}.tutor-modes button:not(.active):hover{color:var(--ink-1)}.tutor-modes button:focus-visible{outline:2px solid var(--brand);outline-offset:2px}

.stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 11px;
  border: 1px solid var(--rose);
  border-radius: 8px;
  color: var(--rose);
  background: var(--rose-soft);
  font-size: 12.5px;
  cursor: pointer;
  font-weight: 600;
  transition: background var(--dur-fast);
}
.stop-btn:hover {
  background: color-mix(in srgb, var(--rose) 18%, transparent);
}
.stop-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--rose);
}

.action-btn {
  height: 30px;
  padding: 0 11px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--ink-2);
  font-size: 12.5px;
  cursor: pointer;
  font-weight: 500;
  box-shadow: var(--shadow-1);
  transition: background var(--dur-fast), color var(--dur-fast), border-color var(--dur-fast);
}
.action-btn:hover:not(:disabled) {
  border-color: var(--border-strong);
  color: var(--ink-1);
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
  font-size: 13px;
  color: var(--ink-3);
}

.scroll-to-bottom {
  position: sticky;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink-2);
  font-size: 12.5px;
  cursor: pointer;
  box-shadow: var(--shadow-2);
  z-index: var(--z-sticky);
}
.scroll-to-bottom:hover {
  background: var(--surface-2);
}

@media (max-width: 768px) {
  .messages-inner {
    padding: var(--space-4) var(--space-4) var(--space-3);
    gap: var(--space-4);
  }
  .composer-area {
    padding: var(--space-2) var(--space-4) var(--space-3);
  }
  .msg-user-wrap {
    max-width: 92%;
  }
}

/* 错题本弹窗 — 适配 V4 tokens */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: errModalFadeIn 0.25s ease;
}

@keyframes errModalFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.error-modal-dialog {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: var(--space-8);
  max-width: 540px;
  width: 94%;
  max-height: 88vh;
  overflow-y: auto;
  box-shadow: var(--shadow-3);
  animation: errModalIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes errModalIn {
  from { opacity: 0; transform: scale(0.94) translateY(18px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.error-modal-dialog h3 {
  font-size: var(--type-xl);
  margin-bottom: var(--space-5);
  color: var(--ink-1);
  font-weight: 700;
}

.form-group {
  margin-bottom: var(--space-5);
}

.form-group label {
  display: block;
  font-size: var(--type-sm);
  font-weight: 600;
  margin-bottom: var(--space-2);
  color: var(--ink-1);
}

.form-group .required { color: var(--rose); }

.form-group textarea {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border: 1.5px solid var(--border);
  border-radius: var(--r-m);
  font-size: var(--type-md);
  font-family: inherit;
  line-height: var(--line-height-base);
  resize: vertical;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  background: var(--surface-2);
  color: var(--ink-1);
}

.form-group textarea:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 4px var(--brand-soft);
  background: var(--surface);
}

.form-group textarea::placeholder {
  color: var(--ink-3);
}

.preview-box {
  padding: var(--space-4);
  background: var(--surface-2);
  border-radius: var(--r-m);
  min-height: 50px;
  border: 1px solid var(--border);
}

.preview-img {
  max-width: 100%;
  max-height: 180px;
  border-radius: var(--r-s);
  margin-bottom: var(--space-2);
  box-shadow: var(--shadow-1);
}

.preview-text {
  font-size: var(--type-md);
  color: var(--ink-2);
  line-height: var(--line-height-base);
  word-break: break-word;
}

.tag-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.tag-btn {
  padding: 6px 16px;
  border: 1.5px solid var(--border);
  border-radius: var(--r-pill);
  background: var(--surface);
  font-size: var(--type-sm);
  color: var(--ink-2);
  font-weight: 500;
  transition: all 0.2s ease;
}

.tag-btn:hover {
  border-color: var(--brand);
  color: var(--brand-text);
  background: var(--brand-soft);
}

.tag-btn.selected {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
  font-weight: 600;
}

.modal-buttons {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-6);
  justify-content: flex-end;
}

.modal-buttons button {
  padding: 9px 24px;
  border-radius: var(--r-pill);
  font-size: var(--type-md);
  font-weight: 600;
  transition: all 0.2s ease;
}

.btn-cancel {
  background: var(--surface-2);
  color: var(--ink-2);
  border: 1px solid var(--border);
}

.btn-cancel:hover {
  background: var(--surface);
  color: var(--ink-1);
  border-color: var(--border-strong);
}

.btn-confirm {
  background: var(--accent);
  color: #fff;
  box-shadow: var(--glow);
}

.btn-confirm:hover {
  background: var(--accent-strong);
}

.btn-confirm:active {
  transform: translateY(1px);
}

@media (max-width: 768px) {
  .error-modal-dialog {
    padding: var(--space-5);
  }
}
</style>
