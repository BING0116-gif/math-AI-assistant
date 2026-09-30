<script setup>
import { computed } from 'vue'
import MathFieldInput from '@/components/common/MathFieldInput.vue'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps({ question: { type: Object, required: true }, modelValue: { default: null }, disabled: Boolean })
const emit = defineEmits(['update:modelValue', 'commit'])
const value = computed({ get: () => props.modelValue, set: (next) => emit('update:modelValue', next) })
const selected = (id) => Array.isArray(props.modelValue) && props.modelValue.includes(id)
function toggle(id) {
  const current = Array.isArray(props.modelValue) ? props.modelValue : []
  emit('update:modelValue', current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  emit('commit', true)
}
</script>

<template>
  <div class="question-answer">
    <div v-if="question.question_type === 'choice'" class="options">
      <label v-for="option in question.options || []" :key="option.id">
        <input v-model="value" type="radio" :value="option.id" :disabled="disabled" @change="emit('commit', true)">
        <strong>{{ option.id }}.</strong><span v-html="renderMarkdown(option.text)" />
      </label>
    </div>
    <div v-else-if="question.question_type === 'multi_choice'" class="options">
      <span class="hint">多选题：选择所有正确选项</span>
      <label v-for="option in question.options || []" :key="option.id">
        <input type="checkbox" :checked="selected(option.id)" :disabled="disabled" @change="toggle(option.id)">
        <strong>{{ option.id }}.</strong><span v-html="renderMarkdown(option.text)" />
      </label>
    </div>
    <div v-else-if="question.question_type === 'judge'" class="options">
      <label><input v-model="value" type="radio" value="true" :disabled="disabled" @change="emit('commit', true)">正确</label>
      <label><input v-model="value" type="radio" value="false" :disabled="disabled" @change="emit('commit', true)">错误</label>
    </div>
    <MathFieldInput
      v-else
      v-model="value"
      :numeric="question.question_type === 'numeric_fill'"
      :disabled="disabled"
      :placeholder="question.question_type === 'numeric_fill' ? '输入数值答案（支持公式键盘）' : '输入数学表达式（支持公式键盘）'"
      @update:model-value="emit('commit', false)"
      @blur="emit('commit', true)"
    />
  </div>
</template>

<style scoped>
.options{display:flex;flex-direction:column;gap:10px;margin-top:20px}.options label{display:flex;align-items:flex-start;gap:10px;min-height:46px;padding:12px 14px;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);cursor:pointer}.options label:has(input:checked){border-color:var(--accent);background:var(--accent-soft)}.options input{margin-top:4px}.hint{color:var(--text-tertiary);font-size:13px}
</style>
