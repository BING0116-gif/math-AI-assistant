<script setup>
/**
 * §5.4 交卷前答题卡总览弹层：网格大字号、已答/未答/当前三态，
 * 未答题红色脉冲提醒；替代原生 confirm 的无障碍友好确认层。
 */
import { computed } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  questions: { type: Array, default: () => [] },
  answers: { type: Object, default: () => ({}) },
  currentIndex: { type: Number, default: 0 },
  submitting: { type: Boolean, default: false },
  title: { type: String, default: '交卷前总览' },
})
const emit = defineEmits(['confirm', 'cancel'])

function isAnswered(item) {
  const value = props.answers[item.question_id]
  return Array.isArray(value) ? value.length > 0 : value !== null && value !== undefined && value !== ''
}
const unansweredCount = computed(() => props.questions.filter((item) => !isAnswered(item)).length)
</script>
<template>
  <div v-if="visible" class="overlay" role="dialog" aria-modal="true" :aria-label="title" @click.self="emit('cancel')">
    <section class="sheet">
      <header>
        <h2>{{ title }}</h2>
        <p :class="unansweredCount ? 'warn' : 'ok'" aria-live="polite">
          {{ unansweredCount ? `还有 ${unansweredCount} 题未作答，未作答按错误计分` : '全部题目已作答' }}
        </p>
      </header>
      <div class="grid">
        <button
          v-for="(item, index) in questions"
          :key="item.question_id"
          type="button"
          :class="{ answered: isAnswered(item), current: index === currentIndex }"
          :aria-label="`第 ${index + 1} 题${isAnswered(item) ? '，已作答' : '，未作答'}`"
          @click="emit('jump', index)"
        >{{ index + 1 }}</button>
      </div>
      <footer>
        <button type="button" class="cancel" @click="emit('cancel')">继续作答</button>
        <button type="button" class="confirm" :disabled="submitting" @click="emit('confirm')">
          {{ submitting ? '正在交卷…' : unansweredCount ? `仍要交卷（${unansweredCount} 题未答）` : '确认交卷' }}
        </button>
      </footer>
    </section>
  </div>
</template>
<style scoped>
.overlay{position:fixed;inset:0;z-index:60;display:flex;align-items:center;justify-content:center;padding:20px;background:color-mix(in srgb, #1c221c 55%, transparent)}
.sheet{width:min(560px,100%);max-height:82vh;display:flex;flex-direction:column;padding:24px;border-radius:var(--radius-lg);background:var(--surface);box-shadow:0 18px 48px rgba(0,0,0,.28)}
header h2{margin:0 0 6px;font-size:18px}
header p{margin:0 0 16px;font-size:14px}
.warn{color:var(--danger)}
.ok{color:var(--success)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(56px,1fr));gap:10px;overflow:auto;padding:2px}
.grid button{min-height:56px;min-width:56px;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-muted);color:var(--danger);font-size:20px;font-variant-numeric:tabular-nums;cursor:pointer;transition:background .2s ease,border-color .2s ease;animation:pulse-unanswered 1.6s ease-in-out infinite}
.grid button.answered{background:var(--accent-soft);border-color:var(--accent);color:var(--text-primary);animation:none}
.grid button.current{outline:2px solid var(--accent);outline-offset:2px}
.grid button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@keyframes pulse-unanswered{0%,100%{border-color:var(--border-subtle)}50%{border-color:var(--danger)}}
footer{display:flex;justify-content:flex-end;gap:12px;margin-top:18px}
.cancel,.confirm{min-height:44px;padding:0 18px;border-radius:var(--radius-sm);font:inherit;cursor:pointer}
.cancel{border:1px solid var(--border-subtle);background:var(--surface);color:var(--text-primary)}
.confirm{border:0;background:var(--danger);color:#fff}
.confirm:disabled{opacity:.6;cursor:not-allowed}
@media(max-width:600px){.sheet{padding:18px}.grid{grid-template-columns:repeat(auto-fill,minmax(48px,1fr))}.grid button{min-height:48px;font-size:18px}footer{flex-direction:column-reverse}.cancel,.confirm{width:100%}}
</style>
