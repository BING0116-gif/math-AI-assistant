<script setup>
import { onBeforeUnmount, ref } from 'vue'
import AppShell from '@/components/shell/AppShell.vue'
import { animationApi, unwrapAnimation } from '@/api/animations'

const templates = [
  { id: 'secant_to_tangent', title: '割线趋近切线', description: '观察割线斜率如何趋近 y=x² 在 x=1 处的切线斜率 2。' },
  { id: 'riemann_sum', title: 'Riemann 和逼近积分', description: '观察矩形和如何逼近 y=x² 在 [0,2] 上的面积 8/3。' },
]
const selected = ref(templates[0].id)
const job = ref(null)
const busy = ref(false)
const message = ref('')
const videoUrl = ref('')
let timer = null

const tangentSpec = {
  type: 'tangent_line', title: 'y=x² 在 x=1 处的切线',
  viewport: { x_min: -3, x_max: 3, y_min: -7, y_max: 9 },
  series: [
    { kind: 'curve', label: 'y=x²', points: [[-3,9],[-2,4],[0,0],[1,1],[2,4],[3,9]] },
    { kind: 'line', label: 'y=2x-1', points: [[-3,-7],[3,5]] },
  ],
  annotations: [{ kind: 'point', x: 1, y: 1, label: '切点 (1, 1)' }],
  teaching_note: '割线逐步趋近切线。',
  verification_request: { type: 'derivative', expression: 'x**2', derivative: '2*x', variable: 'x' },
  verified_values: { tangent_x: 1, tangent_y: 1, slope: 2 },
}
const riemannSpec = {
  type: 'area_under_curve', title: 'y=x² 在 [0,2] 上的面积',
  viewport: { x_min: 0, x_max: 2, y_min: 0, y_max: 4 },
  series: [
    { kind: 'curve', label: 'y=x²', points: [[0,0],[1,1],[2,4]] },
    { kind: 'area', label: '面积', points: [[0,0],[1,1],[2,4],[2,0],[0,0]] },
  ], annotations: [], teaching_note: 'Riemann 和逼近已验证面积。',
  verification_request: { type: 'integral', expression: 'x**2', variable: 'x', lower: 0, upper: 2, claimed: 8 / 3 },
}

function errorText(error) {
  const code = error?.response?.data?.detail?.code
  if (code === 'ANIMATION_DISABLED') return '动画功能目前处于关闭状态，请等待管理员启用。'
  return error?.response?.data?.detail?.message || '动画任务暂时无法处理，请稍后重试。'
}
function clearTimer() { if (timer) { clearTimeout(timer); timer = null } }
function clearVideo() { if (videoUrl.value) URL.revokeObjectURL(videoUrl.value); videoUrl.value = '' }

async function createJob() {
  busy.value = true; message.value = ''; job.value = null; clearTimer(); clearVideo()
  try {
    const visual_spec = selected.value === 'secant_to_tangent' ? tangentSpec : riemannSpec
    job.value = unwrapAnimation(await animationApi.create({
      idempotency_key: `web-${crypto.randomUUID()}`,
      template_id: selected.value, trigger: 'user_explicit', visual_spec,
    }))
    schedulePoll()
  } catch (error) { message.value = errorText(error) }
  finally { busy.value = false }
}
function schedulePoll() { clearTimer(); timer = setTimeout(refreshJob, 1500) }
async function refreshJob() {
  if (!job.value) return
  try {
    job.value = unwrapAnimation(await animationApi.get(job.value.job_id))
    if (['pending', 'running'].includes(job.value.status)) schedulePoll()
    else if (job.value.status === 'succeeded') await loadVideo()
  } catch (error) { message.value = errorText(error) }
}
async function cancelJob() {
  if (!job.value) return
  busy.value = true
  try {
    job.value = unwrapAnimation(await animationApi.cancel(job.value.job_id))
    clearTimer()
    if (job.value.status === 'running') schedulePoll()
  }
  catch (error) { message.value = errorText(error) }
  finally { busy.value = false }
}
async function loadVideo() {
  clearVideo()
  try { videoUrl.value = URL.createObjectURL((await animationApi.video(job.value.job_id)).data) }
  catch (error) { message.value = errorText(error) }
}
onBeforeUnmount(() => { clearTimer(); clearVideo() })
</script>

<template>
  <AppShell><template #topbar-title>数学动画</template>
    <div class="studio">
      <header><p class="eyebrow">MathAnimator</p><h1>让变化过程看得见</h1><p>选择经过数学验证的固定教学场景。任务在隔离环境中生成，不执行自定义代码。</p></header>
      <fieldset><legend>选择动画主题</legend><div class="template-grid">
        <label v-for="item in templates" :key="item.id" :class="{ selected: selected === item.id }">
          <input v-model="selected" type="radio" name="template" :value="item.id"><span><strong>{{ item.title }}</strong><small>{{ item.description }}</small></span>
        </label>
      </div></fieldset>
      <button class="primary" :disabled="busy || ['pending','running'].includes(job?.status)" @click="createJob">{{ busy ? '正在提交…' : '生成教学动画' }}</button>
      <p v-if="message" class="notice" role="alert">{{ message }}</p>
      <section v-if="job" class="job-card" aria-live="polite">
        <div><p class="eyebrow">任务状态</p><h2>{{ { pending:'等待处理', running:'正在生成', succeeded:'生成完成', fallback:'已回退静态图', failed:'生成失败', cancelled:'已取消' }[job.status] }}</h2><p>阶段：{{ job.stage }} · 尝试 {{ job.attempt_count }}/2</p></div>
        <button v-if="['pending','running'].includes(job.status)" class="secondary" :disabled="busy" @click="cancelJob">取消生成</button>
        <video v-if="videoUrl" controls preload="metadata" :src="videoUrl" aria-label="无对白数学教学动画"></video>
        <p v-if="job.status === 'fallback'">动画未能安全生成，请继续使用题目中的静态可视化。</p>
      </section>
    </div>
  </AppShell>
</template>

<style scoped>
.studio{width:min(100% - 32px,820px);margin:0 auto;padding:var(--space-12) 0}.studio header{max-width:680px;margin-bottom:var(--space-8)}.eyebrow{color:var(--knowledge);font-size:var(--font-size-xs);font-weight:700;letter-spacing:.1em;text-transform:uppercase}.studio h1{margin:var(--space-2) 0;font-size:var(--font-size-3xl)}.studio p{color:var(--text-secondary);line-height:var(--line-height-base)}fieldset{border:0;margin:0 0 var(--space-6)}legend{margin-bottom:var(--space-3);font-weight:700}.template-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-3)}label{display:flex;gap:var(--space-3);min-height:112px;padding:var(--space-4);border:1px solid var(--border-subtle);border-radius:var(--radius-lg);background:var(--surface);cursor:pointer;transition:border-color var(--transition-base),background var(--transition-base)}label.selected{border-color:var(--accent);background:var(--accent-soft)}label:focus-within{box-shadow:var(--shadow-focus)}label input{margin-top:4px;accent-color:var(--accent)}label span{display:grid;gap:var(--space-2)}label small{color:var(--text-secondary);font-size:var(--font-size-sm);line-height:1.6}.primary,.secondary{min-height:48px;padding:0 var(--space-5);border-radius:var(--radius-sm);font-weight:700;cursor:pointer}.primary{border:0;background:var(--accent);color:#fff}.secondary{border:1px solid var(--border-strong);background:var(--surface);color:var(--danger)}button:disabled{cursor:not-allowed;opacity:.5}.notice,.job-card{margin-top:var(--space-5);padding:var(--space-4);border:1px solid var(--border-subtle);border-radius:var(--radius-lg);background:var(--surface)}.notice{border-color:var(--warning)}.job-card{display:grid;gap:var(--space-4)}.job-card h2{margin:var(--space-1) 0;font-size:var(--font-size-xl)}video{width:100%;aspect-ratio:16/9;border-radius:var(--radius-md);background:#000}@media(max-width:640px){.studio{padding:var(--space-6) 0}.template-grid{grid-template-columns:1fr}.primary,.secondary{width:100%}}@media(prefers-reduced-motion:reduce){label{transition:none}}
</style>
