<script setup>
defineProps({ questions: { type: Array, default: () => [] }, answers: { type: Object, default: () => ({}) }, currentIndex: Number, states: { type: Object, default: () => ({}) }, uncertain: { type: Object, default: () => ({}) } })
const emit = defineEmits(['jump'])
const answered = (value) => Array.isArray(value) ? value.length > 0 : value !== null && value !== undefined && value !== ''
</script>
<template>
  <div class="navigator" aria-label="题号导航">
    <button v-for="(question,index) in questions" :key="question.question_id" type="button" :class="[states[question.question_id],{active:index===currentIndex,answered:answered(answers[question.question_id]),uncertain:uncertain[question.question_id]}]" :aria-current="index===currentIndex?'step':undefined" :aria-label="`第 ${index+1} 题，${answered(answers[question.question_id])?'已答':'未答'}${uncertain[question.question_id]?'，标记不确定':''}`" @click="emit('jump',index)">{{index+1}}</button>
  </div>
</template>
<style scoped>
.navigator{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;flex:1}.navigator button{position:relative;min-width:42px;min-height:42px;padding:0;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface);color:var(--text-primary);cursor:pointer}.navigator button.answered{background:var(--accent-soft)}.navigator button.correct{background:var(--success);border-color:var(--success);color:#fff}.navigator button.wrong{background:var(--danger);border-color:var(--danger);color:#fff}.navigator button.active{outline:2px solid var(--accent);outline-offset:2px}.navigator button.uncertain::after{content:'?';position:absolute;right:-5px;top:-7px;width:17px;height:17px;border-radius:50%;background:#d89000;color:#fff;font-size:11px;line-height:17px}
</style>
