<template>
  <div class="follow-up-card" v-if="questions.length">

    <div class="header">
      <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
        <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
      </svg>
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
          <span class="label" :class="i === 0 ? 'basic' : 'advanced'">
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
  </div>
</template>

<script setup>
import { renderMarkdown } from '@/utils/markdown'

defineProps({
  questions: { type: Array, default: () => [] }
})

defineEmits(['select'])
</script>

<style scoped>
.follow-up-card {
  margin: 16px 0;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 16px;
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  box-shadow: var(--shadow-sm);
  transition: all 0.3s ease;
}

.follow-up-card:hover {
  box-shadow: var(--shadow-md);
  border-color: rgba(99, 102, 241, 0.2);
}

.header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1.5px solid var(--border-light);
}

.header-icon {
  color: var(--primary);
  flex-shrink: 0;
}

.title {
  font-weight: 700;
  font-size: 15px;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}

.questions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.question-item {
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--bg-secondary);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid transparent;
}

.question-item:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  border-color: rgba(99, 102, 241, 0.15);
  transform: translateY(-1px);
  background: var(--bg-card);
}

.question-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  gap: 8px;
}

.label {
  font-weight: 600;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 20px;
  letter-spacing: 0.02em;
}

.label.basic {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.label.advanced {
  background: rgba(99, 102, 241, 0.1);
  color: var(--primary);
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.difficulty {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.question-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  word-break: break-word;
}

.question-content :deep(.katex) {
  font-size: 1.1em !important;
}

.question-content :deep(.katex-display) {
  margin: 12px 0 !important;
  padding: 12px 16px !important;
  background: var(--bg-card) !important;
  border-radius: 8px !important;
  overflow-x: auto !important;
}

.answer-section {
  margin-top: 10px;
  border-top: 1px solid var(--border-light);
  padding-top: 8px;
}

.answer-section summary {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
  cursor: pointer;
  padding: 4px 0;
  user-select: none;
  transition: color 0.2s;
}

.answer-section summary:hover {
  color: var(--primary-hover);
}

.answer-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-secondary);
  padding: 10px 0 4px;
}

.answer-body :deep(.katex) {
  font-size: 1.1em !important;
}

.answer-body :deep(.katex-display) {
  margin: 10px 0 !important;
  padding: 10px 14px !important;
  background: var(--bg-card) !important;
  border-radius: 8px !important;
}
</style>