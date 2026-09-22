<template>
  <article class="lesson-card" :class="`lesson-card--${resource.type}`" :aria-labelledby="titleId">
    <header class="lesson-card__header">
      <div><span class="lesson-card__kind">{{ typeLabel }}</span><h3 :id="titleId">{{ resource.title }}</h3></div>
      <button class="lesson-card__ask" type="button" @click="$emit('ask-ai', resource)">让 AI 讲这一步</button>
    </header>
    <ol v-if="isExample" class="example-steps">
      <li v-for="(step, index) in exampleSteps" :key="index">
        <button type="button" :aria-expanded="index <= revealedStep" :aria-controls="`${titleId}-step-${index}`" @click="reveal(index)">
          <span>步骤 {{ index + 1 }}</span><strong>{{ index <= revealedStep ? '收起/查看' : index === revealedStep + 1 ? '展开下一步' : '完成前一步后展开' }}</strong>
        </button>
        <div v-if="index <= revealedStep" :id="`${titleId}-step-${index}`" class="math-content" v-html="renderMarkdown(step)" />
      </li>
    </ol>
    <template v-else-if="isCheckpoint">
      <p class="checkpoint-note">先独立作答，再查看反馈。这里的自检不会写入掌握度。</p>
      <ol class="checkpoint-list">
        <li v-for="(question, index) in checkpointQuestions" :key="index">
          <div class="math-content" v-html="renderMarkdown(question)" />
          <button type="button" :aria-expanded="feedbackOpen[index] || false" @click="toggleFeedback(index)">{{ feedbackOpen[index] ? '收起反馈' : '我已作答，查看反馈' }}</button>
          <div v-if="feedbackOpen[index]" class="checkpoint-feedback" role="status">
            <strong>核对思路与错因</strong>
            <p>先写明使用的定义、条件或法则，再核对每一步变形。若结果不一致，常见原因通常是：</p>
            <div class="math-content" v-html="renderMarkdown(commonError || '遗漏适用条件、跳过关键推导，或没有检查最终结果。')" />
            <p><strong>下一步：</strong>回看上方定义与公式，订正后再进入正式练习。</p>
          </div>
        </li>
      </ol>
    </template>
    <template v-else-if="resource.type === 'visual' && resource.metadata?.visual_spec">
      <MathVisualCard :spec="resource.metadata.visual_spec" :verification="resource.metadata.verification" />
      <div class="math-content resource-fallback" v-html="renderMarkdown(resource.body)" />
    </template>
    <template v-else-if="resource.type === 'animation' && resource.metadata?.animation_job">
      <MathAnimationCard :initial-job="resource.metadata.animation_job" />
      <MathVisualCard v-if="resource.metadata?.fallback_visual_spec" :spec="resource.metadata.fallback_visual_spec" />
      <div class="math-content resource-fallback" v-html="renderMarkdown(resource.body)" />
    </template>
    <div v-else class="math-content" v-html="renderMarkdown(resource.body)" />
    <button v-if="isExercise" class="practice-button" type="button" @click="$emit('practice')">进入正式题库</button>
  </article>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import MathAnimationCard from '@/components/math/MathAnimationCard.vue'
import MathVisualCard from '@/components/math/MathVisualCard.vue'
import { renderMarkdown } from '@/utils/markdown'
const props = defineProps({ resource: { type: Object, required: true }, commonError: { type: String, default: '' } })
defineEmits(['ask-ai', 'practice'])
const titleId = `lesson-resource-${String(props.resource.id).replace(/[^a-zA-Z0-9_-]/g, '')}`
const revealedStep = ref(-1)
const feedbackOpen = reactive({})
const isExample = computed(() => ['example', 'worked_example'].includes(props.resource.type))
const isCheckpoint = computed(() => props.resource.type === 'checkpoint')
const isExercise = computed(() => ['exercise', 'exercise_set'].includes(props.resource.type))
const labels = { intuition:'直觉解释',concept:'核心概念',definition:'定义与条件',formula:'公式与符号',visual:'静态图解',animation:'动态讲解',example:'例题',worked_example:'分步例题',common_error:'易错辨析',exam_focus:'常见考点',checkpoint:'理解检查',exercise:'正式练习',exercise_set:'分层练习',summary:'小结与下一步',source_reference:'来源与署名' }
const typeLabel = computed(() => labels[props.resource.type] || '学习资料')
const exampleSteps = computed(() => {
  const structured = props.resource.metadata?.steps
  if (Array.isArray(structured) && structured.length) return structured.map(item => typeof item === 'string' ? item : item.body).filter(Boolean)
  const sentences = props.resource.body.split(/(?<=[。！？；])/u).map(item => item.trim()).filter(Boolean)
  return sentences.length > 1 ? sentences : [props.resource.body]
})
const checkpointQuestions = computed(() => {
  const structured = props.resource.metadata?.items
  if (Array.isArray(structured) && structured.length) return structured.map(item => typeof item === 'string' ? item : item.prompt).filter(Boolean)
  return props.resource.body.split(/\n+/).map(item => item.replace(/^\s*\d+[.、]\s*/, '').trim()).filter(Boolean)
})
function reveal(index) { if (index <= revealedStep.value + 1) revealedStep.value = index <= revealedStep.value ? index - 1 : index }
function toggleFeedback(index) { feedbackOpen[index] = !feedbackOpen[index] }
</script>

<style scoped>
.lesson-card{scroll-margin-top:20px;padding:24px;border:1px solid var(--border-light);border-radius:18px;background:var(--bg-card);box-shadow:0 8px 24px rgba(15,23,42,.05)}
.lesson-card__header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}.lesson-card__kind{color:var(--primary);font-size:12px;font-weight:700;letter-spacing:.08em}.lesson-card h3{margin:4px 0 0;color:var(--text-primary);font-size:20px}.lesson-card__ask{flex:none;min-height:44px;padding:0 14px;border:1px solid var(--border-light);border-radius:10px;background:transparent;color:var(--primary);cursor:pointer}.math-content{color:var(--text-secondary);line-height:1.8;overflow-wrap:anywhere}.example-steps,.checkpoint-list{display:grid;gap:12px;margin:0;padding:0;list-style:none}.example-steps li,.checkpoint-list li{overflow:hidden;border:1px solid var(--border-light);border-radius:12px;background:var(--bg-secondary)}.example-steps button{display:flex;width:100%;min-height:48px;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;border:0;background:transparent;color:var(--text-primary);cursor:pointer;text-align:left}.example-steps button strong{color:var(--primary);font-size:13px}.example-steps .math-content{padding:4px 16px 16px}.checkpoint-note{margin:0 0 14px;color:var(--text-secondary)}.checkpoint-list li{padding:16px}.checkpoint-list button,.practice-button{min-height:44px;margin-top:10px;padding:0 14px;border:0;border-radius:9px;background:var(--primary);color:#fff;font-weight:700;cursor:pointer}.checkpoint-feedback{margin-top:12px;padding:14px;border-left:4px solid var(--warning);border-radius:8px;background:var(--bg-card);color:var(--text-secondary)}.checkpoint-feedback p{margin:6px 0;line-height:1.7}.resource-fallback{margin-top:14px}button:focus-visible{outline:3px solid var(--primary);outline-offset:3px}@media(max-width:600px){.lesson-card{padding:18px 16px}.lesson-card__header{display:block}.lesson-card__ask{width:100%;margin-top:12px}.lesson-card h3{font-size:18px}.math-content{font-size:16px}.example-steps button{align-items:flex-start;flex-direction:column}}
</style>
