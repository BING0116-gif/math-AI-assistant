<template>
  <main class="handwriting-prototype">
    <header>
      <div><p class="eyebrow">阶段 0 · 本地技术验证</p><h1>平板手写实验台</h1></div>
      <p class="save-status" :class="saveState">{{ saveMessage }}</p>
    </header>
    <section class="toolbar" aria-label="手写工具栏">
      <button :class="{ active: tool === 'pen' }" @click="tool = 'pen'">钢笔</button>
      <button :class="{ active: tool === 'eraser' }" @click="tool = 'eraser'">橡皮（整笔划）</button>
      <button :disabled="!history.undo.length" @click="applyHistory(undo(history))">撤销</button>
      <button :disabled="!history.redo.length" @click="applyHistory(redo(history))">重做</button>
      <label>渲染层 <select v-model="engine"><option value="canvas">自研 Canvas 2D</option><option value="konva">Konva 对照</option></select></label>
      <button @click="resetViewport">重置视图</button><button class="danger" @click="eraseDraft">清空本机草稿</button>
    </section>
    <section class="workspace">
      <div ref="surface" class="ink-surface" @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp">
        <canvas ref="canvas" aria-label="手写画布：仅支持触控笔书写，双指可缩放和平移" />
        <div ref="konvaContainer" class="konva-layer" aria-hidden="true" />
        <p v-if="!history.strokes.length" class="hint">使用触控笔书写；双指缩放或移动画布</p>
      </div>
      <aside>
        <h2>基准</h2><p>{{ history.strokes.length.toLocaleString() }} 条笔划 · {{ totalPoints.toLocaleString() }} 个采样点</p>
        <div class="benchmark-buttons"><button v-for="count in [1000, 5000, 10000]" :key="count" @click="loadBenchmark(count)">加载 {{ count.toLocaleString() }}</button></div>
        <button class="measure" @click="measureFrames">测量 1 秒帧间隔</button>
        <dl><dt>样本</dt><dd>{{ metrics.samples }}</dd><dt>P50</dt><dd>{{ metrics.p50.toFixed(1) }} ms</dd><dt>P95</dt><dd>{{ metrics.p95.toFixed(1) }} ms</dd><dt>最大</dt><dd>{{ metrics.max.toFixed(1) }} ms</dd></dl>
        <p class="note">5000 笔迹验收目标：继续书写和缩放可用，P95 ≤ 32 ms。基准数据为确定性合成笔划，真机记录另行填写。</p>
      </aside>
    </section>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { collectInkPoints, createStroke, strokeHitsPoint, toInkPoint } from '@/features/handwriting/ink'
import { commit, createHistory, redo, undo } from '@/features/handwriting/history'
import { defaultViewport, pan, pinch } from '@/features/handwriting/viewport'
import { generateBenchmarkStrokes, summarizeFrames } from '@/features/handwriting/benchmark'
import { clearDraft, loadDraft, saveDraft } from '@/features/handwriting/draftStorage'
import { renderCanvas } from '@/features/handwriting/renderers/canvas2d'
import { renderKonva } from '@/features/handwriting/renderers/konva'

const canvas = ref(null), surface = ref(null), konvaContainer = ref(null)
const tool = ref('pen'), engine = ref('canvas'), viewport = ref(defaultViewport()), history = ref(createHistory())
const saveState = ref('idle'), metrics = ref({ samples: 0, p50: 0, p95: 0, max: 0 })
const activeStroke = ref(null), fingers = new Map(), lastGesture = ref(null)
let stage, saveTimer, resizeObserver
const totalPoints = computed(() => history.value.strokes.reduce((total, stroke) => total + stroke.points.length, 0))
const saveMessage = computed(() => saveState.value === 'saving' ? '正在保存到本机…' : saveState.value === 'saved' ? '已保存到本机' : saveState.value === 'error' ? '本机保存失败' : '本地草稿')

function render() {
  if (!canvas.value || !surface.value) return
  if (stage) { stage.destroy(); stage = null }
  konvaContainer.value.replaceChildren()
  if (engine.value === 'canvas') { canvas.value.style.display = 'block'; konvaContainer.value.style.display = 'none'; renderCanvas(canvas.value, history.value.strokes, viewport.value) }
  else { canvas.value.style.display = 'none'; konvaContainer.value.style.display = 'block'; stage = renderKonva(konvaContainer.value, history.value.strokes, viewport.value) }
}
function persist() {
  clearTimeout(saveTimer); saveState.value = 'saving'
  saveTimer = setTimeout(async () => {
    try {
      // Vue reactive proxies are not structured-cloneable by IndexedDB.
      const snapshot = JSON.parse(JSON.stringify({ history: history.value, viewport: viewport.value, tool: tool.value, engine: engine.value }))
      await saveDraft(snapshot); saveState.value = 'saved'
    } catch (error) { console.error('Unable to save handwriting draft', error); saveState.value = 'error' }
  }, 120)
}
function applyHistory(next) { history.value = next; persist() }
function localPoint(event) {
  const rect = surface.value.getBoundingClientRect(), raw = toInkPoint(event, rect)
  return { ...raw, x: (raw.x - viewport.value.x) / viewport.value.scale, y: (raw.y - viewport.value.y) / viewport.value.scale }
}
function onPointerDown(event) {
  surface.value.setPointerCapture?.(event.pointerId)
  if (event.pointerType === 'pen') {
    const point = localPoint(event)
    if (tool.value === 'eraser') { applyHistory(commit(history.value, history.value.strokes.filter((stroke) => !strokeHitsPoint(stroke, point, 14 / viewport.value.scale)))) }
    else activeStroke.value = createStroke(event, point)
    return
  }
  if (event.pointerType === 'touch') { fingers.set(event.pointerId, { x: event.clientX, y: event.clientY }); updateGesture() }
}
function onPointerMove(event) {
  if (event.pointerType === 'pen' && activeStroke.value) {
    const rect = surface.value.getBoundingClientRect()
    activeStroke.value.points.push(...collectInkPoints(event, rect).map((point) => ({ ...point, x: (point.x - viewport.value.x) / viewport.value.scale, y: (point.y - viewport.value.y) / viewport.value.scale })))
    history.value = { ...history.value, strokes: [...history.value.strokes.filter((stroke) => stroke.id !== activeStroke.value.id), activeStroke.value] }; render()
  } else if (event.pointerType === 'touch' && fingers.has(event.pointerId)) { fingers.set(event.pointerId, { x: event.clientX, y: event.clientY }); updateGesture() }
}
function onPointerUp(event) {
  if (event.pointerType === 'pen' && activeStroke.value) { history.value = commit(history.value, [...history.value.strokes.filter((stroke) => stroke.id !== activeStroke.value.id), activeStroke.value]); activeStroke.value = null; persist() }
  if (event.pointerType === 'touch') { fingers.delete(event.pointerId); lastGesture.value = null }
}
function updateGesture() {
  if (fingers.size < 2) return
  const [a, b] = [...fingers.values()]; const current = { a, b }
  if (lastGesture.value) viewport.value = pinch(viewport.value, lastGesture.value, current)
  lastGesture.value = current; render()
}
function resetViewport() { viewport.value = defaultViewport(); persist() }
async function eraseDraft() { await clearDraft(); history.value = createHistory(); viewport.value = defaultViewport(); saveState.value = 'idle' }
async function loadBenchmark(count) { history.value = commit(history.value, generateBenchmarkStrokes(count)); await nextTick(); render(); persist(); measureFrames() }
function measureFrames() {
  const samples = []; let previous = performance.now(), started = previous
  const tick = (now) => { samples.push(now - previous); previous = now; if (now - started < 1000) requestAnimationFrame(tick); else metrics.value = summarizeFrames(samples.slice(1)) }
  requestAnimationFrame(tick)
}
watch([engine, viewport], () => { render(); persist() }, { deep: true })
onMounted(async () => {
  const draft = await loadDraft(); if (draft) { history.value = draft.history || createHistory(); viewport.value = draft.viewport || defaultViewport(); tool.value = draft.tool || 'pen'; engine.value = draft.engine || 'canvas'; saveState.value = 'saved' }
  render(); resizeObserver = new ResizeObserver(render); resizeObserver.observe(surface.value)
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') persist() })
})
onBeforeUnmount(() => { clearTimeout(saveTimer); resizeObserver?.disconnect(); stage?.destroy() })
</script>

<style scoped lang="scss">
.handwriting-prototype { min-height: 100vh; padding: 24px; color: #172554; background: #f7f9fc; } header,.toolbar,.workspace { max-width: 1440px; margin: 0 auto; } header { display:flex; justify-content:space-between; align-items:center; } h1 { margin: 0; } .eyebrow { color:#64748b; margin:0 0 4px; } .save-status { color:#166534; } .toolbar { display:flex; flex-wrap:wrap; gap:8px; margin-top:20px; padding:12px; background:white; border-radius:12px; } button,select { min-height:36px; border:1px solid #cbd5e1; border-radius:7px; background:white; padding:0 10px; } button.active { background:#172554; color:white; } button.danger { color:#b91c1c; } .workspace { display:grid; grid-template-columns:minmax(0,1fr) 280px; gap:16px; margin-top:16px; } .ink-surface { position:relative; height:calc(100vh - 190px); min-height:480px; overflow:hidden; background:radial-gradient(#dbeafe 1px,transparent 1px) 0 0/20px 20px,#fff; border:1px solid #cbd5e1; border-radius:12px; touch-action:none; } canvas,.konva-layer { position:absolute; inset:0; width:100%; height:100%; } .konva-layer { pointer-events:none; } .hint { position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); color:#64748b; pointer-events:none; } aside { background:white; padding:16px; border-radius:12px; } aside h2 { margin-top:0; } .benchmark-buttons { display:grid; gap:8px; } .measure { margin-top:8px; width:100%; } dl { display:grid; grid-template-columns:1fr auto; gap:6px; } dt,dd { margin:0; } .note { font-size:12px; color:#475569; line-height:1.5; } @media (max-width: 768px) { .handwriting-prototype { padding:12px; } .workspace { grid-template-columns:1fr; } .ink-surface { height:62vh; min-height:360px; } header { align-items:flex-start; flex-direction:column; } }
</style>
