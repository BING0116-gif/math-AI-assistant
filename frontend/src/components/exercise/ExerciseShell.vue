<script setup>
import { renderMarkdown } from '@/utils/markdown'
defineProps({ question: { type: Object, required: true }, total: { type: Number, required: true }, statusText: String, timerText: String })
</script>
<template>
  <main class="exercise-shell">
    <header><span>{{statusText}}</span><strong v-if="timerText" class="timer">{{timerText}}</strong><slot name="save-state" /></header>
    <slot name="alert" />
    <section class="question-card">
      <div class="meta">第 {{question.position}} / {{total}} 题 · {{question.question_type}}</div>
      <div class="content" v-html="renderMarkdown(question.content)" />
      <slot />
    </section>
    <slot name="feedback" />
    <slot name="actions" />
  </main>
</template>
<style scoped>
.exercise-shell{max-width:980px;margin:0 auto;padding:26px 24px 84px}.exercise-shell>header{display:flex;justify-content:space-between;align-items:center;gap:16px;color:var(--text-secondary);font-size:14px}.timer{font-variant-numeric:tabular-nums;color:var(--text-primary)}.question-card{margin-top:18px;padding:28px;border:1px solid var(--border-subtle);border-radius:var(--radius-lg);background:var(--surface)}.meta{color:var(--text-tertiary);font-size:14px;margin-bottom:18px}.content{line-height:1.8;font-size:17px}@media(max-width:600px){.exercise-shell{padding:18px 14px 72px}.question-card{padding:18px}.exercise-shell>header{flex-wrap:wrap}}
</style>
