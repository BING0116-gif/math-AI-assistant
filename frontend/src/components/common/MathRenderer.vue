<template>
  <span ref="mathRef" v-html="renderedHtml"></span>
</template>

<script setup>
import { ref, computed } from 'vue'
import katex from 'katex'

const props = defineProps({
  content: { type: String, default: '' },
  displayMode: { type: Boolean, default: false }
})

const mathRef = ref(null)

const renderedHtml = computed(() => {
  if (!props.content) return ''
  try {
    // 直接使用 katex.renderToString，无需经过 latexPreprocessor
    return katex.renderToString(props.content, {
      displayMode: props.displayMode,
      throwOnError: false,
      strict: false
    })
  } catch (error) {
    console.warn('[MathRenderer] 渲染失败:', error.message)
    return `<span class="math-error">${props.content}</span>`
  }
})

</script>
