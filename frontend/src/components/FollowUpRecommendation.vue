<template>
  <div class="follow-up-card ai-card" v-if="questions.length">
    <div class="header">
      <span class="header-icon" aria-hidden="true"><Lightbulb :size="16" :stroke-width="1.75" /></span>
      <span class="title">推荐练习</span>
    </div>
    <div class="questions">
      <div
        v-for="(q, i) in questions"
        :key="q.id || i"
        class="question-item"
        @click="$emit('select', q)"
      >
        <div class="question-header">
          <span class="label tag" :class="i === 0 ? 'tag-soft-green' : 'tag-soft-accent'">
            {{ i === 0 ? '基础巩固' : '能力提升' }}
          </span>
          <span class="difficulty">难度 {{ q.difficulty }}/5</span>
        </div>
        <div class="question-content" v-html="renderMarkdown(q.content)"></div>
        <details class="answer-section">
          <summary>查看答案</summary>
          <div class="answer-body" v-html="renderMarkdown(q.answer)"></div>
        </details>
      </div>
    </div>
    <div class="practice-cta">
      <button class="practice-btn" type="button" :disabled="busy" @click="goPractice">
        {{ busy ? '智能选材中…' : '练类似题' }}
        <ArrowRight v-if="!busy" :size="14" :stroke-width="1.75" aria-hidden="true" />
      </button>
      <span v-if="hint" class="practice-hint">{{ hint }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Lightbulb, ArrowRight } from 'lucide-vue-next'
import { renderMarkdown } from '@/utils/markdown'
import { recommendApi } from '@/api/recommend'

const props = defineProps({
  questions: { type: Array, default: () => [] }
})

defineEmits(['select'])

const router = useRouter()
const busy = ref(false)
const hint = ref('')

async function goPractice() {
  if (busy.value) return
  busy.value = true
  hint.value = ''
  try {
    const first = props.questions[0]
    const content = first?.content || ''
    const res = await recommendApi.createSession({
      question_content: content.slice(0, 400),
      count: 5,
    })
    const data = res?.data?.data
    const sessionId = data?.session_id
    if (!sessionId) throw new Error('未返回练习会话')
    router.push(`/apply/practice/sessions/${sessionId}`)
  } catch (e) {
    hint.value = e?.response?.data?.detail || e?.message || '推荐失败，请稍后再试'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
/* V4 重皮(对照 chat.html):AI 来源卡片走 ai-card 渐变描边 + surface 卡体;
   练习项 surface-2 内嵌面,基础巩固=green、能力提升=brand(全局 tag 语言) */
.follow-up-card {
  margin: 0;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  background: var(--surface);
  box-shadow: var(--shadow-2);
}

.header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border);
}

.header-icon {
  width: 28px;
  height: 28px;
  border-radius: var(--r-s);
  display: grid;
  place-items: center;
  flex: none;
  background: var(--brand-soft);
  color: var(--brand-text);
}

.title {
  font-weight: 600;
  font-size: 13.5px;
  color: var(--ink-1);
  letter-spacing: 0.02em;
}

.questions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.question-item {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--r-m);
  background: var(--surface-2);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-standard),
    border-color var(--dur-fast) var(--ease-standard),
    transform var(--dur-fast) var(--ease-standard),
    box-shadow var(--dur-fast) var(--ease-standard);
}

.question-item:hover {
  background: var(--surface);
  border-color: var(--brand);
  transform: translateY(-1px);
  box-shadow: var(--shadow-1);
}

.question-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
  gap: var(--space-2);
}

.difficulty {
  font-size: 12px;
  color: var(--ink-3);
  font-weight: 500;
}

.question-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-1);
  word-break: break-word;
}

.question-content :deep(.katex) {
  font-size: 1.05em !important;
}

.question-content :deep(.katex-display) {
  margin: var(--space-3) 0 !important;
  padding: var(--space-3) var(--space-4) !important;
  background: var(--surface) !important;
  border: 1px solid var(--border);
  border-radius: var(--r-m) !important;
  overflow-x: auto !important;
}

.answer-section {
  margin-top: var(--space-2);
  border-top: 1px solid var(--border);
  padding-top: var(--space-2);
}

.answer-section summary {
  font-size: 13px;
  font-weight: 600;
  color: var(--brand-text);
  cursor: pointer;
  padding: 2px 0;
  user-select: none;
  transition: color var(--dur-fast) var(--ease-standard);
}

.answer-section summary:hover {
  color: var(--brand-strong);
}

.answer-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-2);
  padding: var(--space-2) 0 var(--space-1);
}

.answer-body :deep(.katex) {
  font-size: 1.05em !important;
}

.answer-body :deep(.katex-display) {
  margin: var(--space-3) 0 !important;
  padding: var(--space-3) var(--space-4) !important;
  background: var(--surface) !important;
  border: 1px solid var(--border);
  border-radius: var(--r-m) !important;
  overflow-x: auto !important;
}

.practice-cta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border);
}

/* AI 卡内行动位:原型 chat.html「生成 5 道变式练习」强调 chip 语言(brand 描边+soft 底) */
.practice-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--brand);
  border-radius: var(--r-pill);
  background: var(--brand-soft);
  color: var(--brand-text);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-standard),
    box-shadow var(--dur-fast) var(--ease-standard);
}

.practice-btn:hover:not(:disabled) {
  background: var(--brand-soft-2);
  box-shadow: var(--shadow-1);
}

.practice-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.practice-hint {
  font-size: 12px;
  color: var(--rose);
}
</style>