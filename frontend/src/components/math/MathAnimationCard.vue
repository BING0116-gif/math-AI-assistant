<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { animationApi, unwrapAnimation } from '@/api/animations'

const props = defineProps({ initialJob: { type: Object, required: true } })
const job = ref({ ...props.initialJob })
const videoUrl = ref('')
const loadingVideo = ref(false)
let timer = null

const terminal = computed(() => ['succeeded', 'fallback', 'failed', 'cancelled'].includes(job.value.status))
const statusText = computed(() => ({
  pending: '动画已排队', running: '正在生成动画', succeeded: '动画已生成',
  fallback: '已切换为静态讲解', failed: '动画生成失败', cancelled: '动画已取消',
}[job.value.status] || '动画处理中'))

async function refresh() {
  try {
    job.value = unwrapAnimation(await animationApi.get(job.value.job_id))
    if (job.value.status === 'succeeded') await loadVideo()
  } catch (_) {
    stopPolling()
  }
  if (terminal.value) stopPolling()
}

async function loadVideo() {
  if (videoUrl.value || loadingVideo.value) return
  loadingVideo.value = true
  try { videoUrl.value = URL.createObjectURL((await animationApi.video(job.value.job_id)).data) } catch (_) {}
  finally { loadingVideo.value = false }
}

async function cancel() {
  try { job.value = unwrapAnimation(await animationApi.cancel(job.value.job_id)) } finally { stopPolling() }
}

function stopPolling() { if (timer) { clearInterval(timer); timer = null } }

onMounted(() => {
  if (job.value.status === 'succeeded') loadVideo()
  else if (!terminal.value) { refresh(); timer = setInterval(refresh, 2500) }
})
onBeforeUnmount(() => { stopPolling(); if (videoUrl.value) URL.revokeObjectURL(videoUrl.value) })
</script>

<template>
  <section class="animation-card" aria-label="数学动画讲解">
    <div class="animation-card__header">
      <div>
        <span class="animation-card__eyebrow">动态讲解</span>
        <strong>{{ statusText }}</strong>
      </div>
      <span v-if="!terminal" class="animation-card__pulse" aria-hidden="true"></span>
    </div>

    <p v-if="job.teaching_note" class="animation-card__note">{{ job.teaching_note }}</p>
    <video v-if="videoUrl" class="animation-card__video" :src="videoUrl" controls playsinline preload="metadata">
      你的浏览器暂不支持视频播放。
    </video>
    <div v-else-if="!terminal" class="animation-card__progress" role="status">
      <span></span><span></span><span></span>
      <small>文字讲解可以先读，动画完成后会自动出现</small>
    </div>
    <p v-else-if="job.status !== 'succeeded'" class="animation-card__fallback" role="status">
      动画暂时不可用，以上文字与静态图仍是完整讲解。
    </p>

    <button v-if="!terminal" type="button" class="animation-card__cancel" @click="cancel">取消生成</button>
  </section>
</template>

<style scoped>
.animation-card { margin-top: var(--space-4); padding: var(--space-4); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: linear-gradient(145deg, var(--surface), var(--surface-muted)); }
.animation-card__header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.animation-card__header > div { display: grid; gap: 2px; }
.animation-card__eyebrow { color: var(--accent); font-size: var(--font-size-xs); letter-spacing: .08em; }
.animation-card__header strong { color: var(--text-primary); font-size: var(--font-size-sm); }
.animation-card__pulse { width: 9px; height: 9px; border-radius: 50%; background: var(--accent); animation: pulse 1.4s ease-in-out infinite; }
.animation-card__note, .animation-card__fallback { margin: var(--space-3) 0 0; color: var(--text-secondary); font-size: var(--font-size-sm); line-height: 1.6; }
.animation-card__video { display: block; width: 100%; max-height: 420px; margin-top: var(--space-3); border-radius: var(--radius-sm); background: #111; }
.animation-card__progress { display: flex; align-items: center; gap: 5px; margin-top: var(--space-3); color: var(--text-tertiary); }
.animation-card__progress span { width: 5px; height: 5px; border-radius: 50%; background: currentColor; animation: pulse 1.2s ease-in-out infinite; }
.animation-card__progress span:nth-child(2) { animation-delay: .15s; }
.animation-card__progress span:nth-child(3) { animation-delay: .3s; }
.animation-card__progress small { margin-left: var(--space-2); }
.animation-card__cancel { margin-top: var(--space-3); padding: 4px 0; border: 0; background: transparent; color: var(--text-tertiary); cursor: pointer; font: inherit; font-size: var(--font-size-xs); }
.animation-card__cancel:hover { color: var(--text-primary); }
@keyframes pulse { 0%, 100% { opacity: .3; transform: scale(.85); } 50% { opacity: 1; transform: scale(1); } }
@media (prefers-reduced-motion: reduce) { .animation-card__pulse, .animation-card__progress span { animation: none; } }
</style>
