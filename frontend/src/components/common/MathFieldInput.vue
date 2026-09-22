<script setup>
/**
 * §5.2 数学作答输入：优先渲染 MathLive <math-field>（虚拟键盘、LaTeX 快捷输入），
 * 动态 import 失败或测试环境自动降级为原生 <input>，判分与旧题不受影响。
 *
 * v-model 值始终是“可判分表达式文本”（经 latexToMathText 转换），
 * 组件内部维护 LaTeX 显示态，提交链路无需感知 MathLive。
 */
import { onMounted, ref } from 'vue'
import { latexToMathText, mathTextToLatex } from '@/utils/latexToMath'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  numeric: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const fieldReady = ref(false)
// 重试/恢复场景：外部已有可判分文本时近似还原为 LaTeX 供编辑
const initialLatex = props.modelValue ? mathTextToLatex(props.modelValue) : ''

onMounted(async () => {
  try {
    await import('mathlive')
    // math-field 是 Web Component，import 副作用完成注册；确认存在再启用
    if (typeof globalThis.customElements !== 'undefined' && globalThis.customElements.get('math-field')) {
      fieldReady.value = true
    }
  } catch {
    fieldReady.value = false
  }
})

function onFieldInput(event) {
  const mathText = latexToMathText(event.target?.value ?? '')
  if (mathText !== props.modelValue) emit('update:modelValue', mathText)
}

function onFallbackInput(event) {
  emit('update:modelValue', event.target.value)
}
</script>
<template>
  <div class="math-input">
    <math-field
      v-if="fieldReady"
      class="math-field"
      :value="initialLatex"
      virtual-keyboard-mode="manual"
      :read-only="disabled"
      :aria-label="numeric ? '数值答案（支持公式键盘）' : '表达式答案（支持公式键盘）'"
      @input="onFieldInput"
    />
    <input
      v-else
      class="fallback-input"
      type="text"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :aria-label="numeric ? '数值答案' : '表达式答案'"
      @input="onFallbackInput"
    >
  </div>
</template>
<style scoped>
.math-input{width:100%}
.math-field{box-sizing:border-box;width:100%;min-height:48px;margin-top:18px;padding:8px 12px;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface);color:var(--text-primary);font-size:18px}
.math-field:focus-within,.math-field:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.fallback-input{box-sizing:border-box;width:100%;min-height:42px;margin-top:18px;padding:8px;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface);color:var(--text-primary);font:inherit}
.fallback-input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
</style>
