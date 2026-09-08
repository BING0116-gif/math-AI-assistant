<script setup>
/**
 * AskStudentCard — ask_student 结构化反问卡片（T03）。
 *
 * 渲染后端 SSE `ask_student` 事件下发的澄清问题：
 * - 选项按钮（kind 三种：missing_condition / ambiguous_term / confirm_approach）
 * - 自由输入回答
 * 提交后由父组件（ChatView）调用 /api/chat/clarification/answer 续接对话。
 */
import { ref, computed } from 'vue'

const props = defineProps({
  card: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['submit'])

const freeText = ref('')

const kindLabel = computed(() => {
  const labels = {
    missing_condition: '缺条件',
    ambiguous_term: '概念歧义',
    confirm_approach: '确认思路',
  }
  return labels[props.card?.kind] || '澄清提问'
})

function submitOption(opt) {
  if (props.disabled) return
  if (!opt || !opt.text) return
  emit('submit', { answer: opt.text, optionLabel: opt.label })
}

function submitFree() {
  if (props.disabled) return
  const text = freeText.value.trim()
  if (!text) return
  emit('submit', { answer: text })
}
</script>

<template>
  <div class="ask-card" role="group" :aria-label="`老师提问：${card.question}`">
    <div class="ask-card__head">
      <span class="ask-card__kind">{{ kindLabel }}</span>
      <span class="ask-card__hint">老师需要你补充一些信息</span>
    </div>
    <p class="ask-card__question">{{ card.question }}</p>
    <div v-if="card.options && card.options.length" class="ask-card__options">
      <button
        v-for="opt in card.options"
        :key="opt.label"
        type="button"
        class="ask-card__option"
        :disabled="disabled"
        @click="submitOption(opt)"
      >
        {{ opt.label }}. {{ opt.text }}
      </button>
    </div>
    <div class="ask-card__free">
      <textarea
        v-model="freeText"
        class="ask-card__input"
        rows="2"
        :disabled="disabled"
        placeholder="也可以直接输入你的回答…"
        @keydown.enter.exact.prevent="submitFree"
      ></textarea>
      <button
        type="button"
        class="ask-card__submit"
        :disabled="disabled || !freeText.trim()"
        @click="submitFree"
      >
        提交回答
      </button>
    </div>
  </div>
</template>

<style scoped>
.ask-card {
  align-self: flex-start;
  width: min(100%, 560px);
  padding: var(--space-4);
  border: 1.5px solid var(--accent);
  border-radius: var(--radius-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ask-card__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.ask-card__kind {
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.ask-card__hint {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.ask-card__question {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  white-space: pre-wrap;
  word-break: break-word;
}

.ask-card__options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ask-card__option {
  padding: 8px 14px;
  border: 1.5px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background var(--transition-base), border-color var(--transition-base);
}
.ask-card__option:hover:not(:disabled) {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.ask-card__option:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ask-card__option:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.ask-card__free {
  display: flex;
  gap: var(--space-2);
  align-items: flex-end;
}

.ask-card__input {
  flex: 1;
  resize: vertical;
  min-height: 44px;
  padding: 8px 12px;
  border: 1.5px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-family: inherit;
}
.ask-card__input:focus {
  outline: none;
  border-color: var(--accent);
}
.ask-card__input:disabled {
  opacity: 0.5;
}

.ask-card__submit {
  padding: 10px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff;
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-base);
}
.ask-card__submit:hover:not(:disabled) {
  background: var(--accent-hover);
}
.ask-card__submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
