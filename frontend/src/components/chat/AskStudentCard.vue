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
import { GraduationCap } from 'lucide-vue-next'

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
  <div class="ask-card ai-card" role="group" :aria-label="`老师提问：${card.question}`">
    <div class="ask-card__head">
      <span class="ask-card__icon" aria-hidden="true"><GraduationCap :size="15" :stroke-width="1.75" /></span>
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
/* V4 重皮(对照 chat.html):AI 来源反问卡走 ai-card 渐变描边 + brand 系徽章/聚焦环;
   提交键为卡内主行动 → 行动橙(白字 ≥14px/600,hover 加深,glow 光效) */
.ask-card {
  align-self: flex-start;
  width: min(100%, 560px);
  padding: var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  background: var(--surface);
  box-shadow: var(--shadow-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ask-card__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.ask-card__icon {
  width: 24px;
  height: 24px;
  border-radius: var(--r-s);
  display: grid;
  place-items: center;
  flex: none;
  background: var(--brand-soft-2);
  color: var(--brand-text);
}

.ask-card__kind {
  padding: 3px 8px;
  border-radius: 7px;
  background: var(--brand-soft);
  color: var(--brand-text);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.ask-card__hint {
  color: var(--ink-3);
  font-size: 12.5px;
}

.ask-card__question {
  margin: 0;
  color: var(--ink-1);
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.ask-card__options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ask-card__option {
  padding: 7px 12px;
  border: 1px solid var(--border-strong);
  border-radius: var(--r-s);
  background: var(--surface);
  color: var(--ink-1);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-standard),
    border-color var(--dur-fast) var(--ease-standard),
    color var(--dur-fast) var(--ease-standard);
}
.ask-card__option:hover:not(:disabled) {
  border-color: var(--brand);
  background: var(--brand-soft);
  color: var(--brand-text);
}
.ask-card__option:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ask-card__option:focus-visible {
  outline: 2px solid var(--brand);
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
  padding: 9px 12px;
  border: 1px solid var(--border-strong);
  border-radius: var(--r-m);
  background: var(--surface-2);
  color: var(--ink-1);
  font-size: 13.5px;
  font-family: inherit;
  transition: border-color var(--dur-fast) var(--ease-standard),
    box-shadow var(--dur-fast) var(--ease-standard);
}
.ask-card__input:focus {
  outline: none;
  border-color: var(--brand);
  box-shadow: 0 0 0 3px var(--brand-soft);
}
.ask-card__input:disabled {
  opacity: 0.5;
}

.ask-card__submit {
  padding: 9px 16px;
  border-radius: var(--r-s);
  background: var(--accent);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--glow);
  transition: background var(--dur-fast) var(--ease-standard),
    box-shadow var(--dur-fast) var(--ease-standard);
}
.ask-card__submit:hover:not(:disabled) {
  background: var(--accent-strong);
}
.ask-card__submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
}
</style>
