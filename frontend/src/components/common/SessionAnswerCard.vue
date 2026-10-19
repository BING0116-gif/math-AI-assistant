<script setup>
import { X } from 'lucide-vue-next'
defineProps({ questions: { type: Array, default: () => [] }, answers: { type: Object, default: () => ({}) }, currentIndex: { type: Number, default: 0 }, open: Boolean, busy: Boolean, finishLabel: { type: String, default: '交卷并查看总览' }, busyLabel: { type: String, default: '正在交卷…' }, footerNote: { type: String, default: '交卷前可检查未作答题目' } })
defineEmits(['jump', 'close', 'finish'])
const answered = value => Array.isArray(value) ? value.length > 0 : value !== null && value !== undefined && value !== ''
</script>
<template>
  <aside :class="['session-card', { open }]" aria-label="答题卡">
    <header><div><strong>答题卡</strong><p>已作答 {{ questions.filter(q => answered(answers[q.question_id])).length }} / {{ questions.length }}</p></div><button class="close" type="button" aria-label="关闭答题卡" @click="$emit('close')"><X :size="18" /></button></header>
    <div class="legend">实色为当前题 · 浅绿为已作答</div>
    <div class="grid"><button v-for="(q, index) in questions" :key="q.question_id" type="button" :class="{ answered: answered(answers[q.question_id]), active: index === currentIndex }" :aria-current="index === currentIndex ? 'step' : undefined" :aria-label="`第 ${index + 1} 题，${answered(answers[q.question_id]) ? '已作答' : '未作答'}`" @click="$emit('jump', index)">{{ index + 1 }}</button></div>
    <footer><button type="button" :disabled="busy" @click="$emit('finish')">{{ busy ? busyLabel : finishLabel }}</button><p>{{ footerNote }}</p></footer>
  </aside>
  <button v-if="open" type="button" class="card-overlay" aria-label="关闭答题卡" @click="$emit('close')" />
</template>
<style scoped>
.session-card{position:sticky;top:20px;padding:22px;border:1px solid var(--border);border-radius:12px;background:var(--surface);box-shadow:var(--shadow-1)}header{display:flex;justify-content:space-between}header strong{font-size:16px}p{margin:7px 0 0;color:var(--ink-3);font-size:12px}.legend{margin:22px 0 14px;font-size:12px;color:var(--ink-3)}.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}button{min-height:42px;padding:0;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);color:var(--ink-2);font:inherit;cursor:pointer}.answered{background:var(--green-soft);border-color:var(--green);color:var(--green)}.active{background:var(--brand);border-color:var(--brand);color:#fff}footer{margin-top:24px;padding-top:18px;border-top:1px solid var(--border);text-align:center}footer button{width:100%;background:var(--surface);font-size:14px}.close,.card-overlay{display:none}button:focus-visible{outline:2px solid var(--brand);outline-offset:2px}button:disabled{opacity:.5;cursor:not-allowed}@media(max-width:1000px){.session-card{position:fixed;z-index:51;left:0;right:0;bottom:0;top:auto;max-height:78dvh;overflow:auto;border-radius:16px 16px 0 0;visibility:hidden;pointer-events:none;transform:translateY(100%)}.session-card.open{visibility:visible;pointer-events:auto;transform:translateY(0)}.close{display:grid;place-items:center;width:42px;border:0;background:transparent}.card-overlay{display:block;position:fixed;z-index:50;inset:0;border:0;border-radius:0;background:rgba(0,0,0,.35)}}
</style>
