<template>
  <span ref="mathRef" v-html="renderedHtml"></span>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { renderMathInElement } from '@/utils/mathRender'
import latexPreprocessor from '@/utils/latexPreprocessor'

const props = defineProps({
  content: { type: String, default: '' },
  displayMode: { type: Boolean, default: false }
})

const mathRef = ref(null)

const renderedHtml = computed(() => {
  if (!props.content) return ''
  return latexPreprocessor.process(props.content)
})

watch(() => props.content, () => {
  nextTick(() => {
    if (mathRef.value) renderMathInElement(mathRef.value)
  })
}, { flush: 'post' })

onMounted(() => {
  nextTick(() => {
    if (mathRef.value) renderMathInElement(mathRef.value)
  })
})
</script>
