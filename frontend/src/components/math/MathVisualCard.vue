<template>
  <section class="visual-card" :aria-labelledby="titleId">
    <header class="visual-header">
      <div>
        <p class="visual-eyebrow">数学可视化</p>
        <h3 :id="titleId">{{ spec.title }}</h3>
      </div>
      <span v-if="verification?.status === 'verified'" class="verified-badge">已验证</span>
    </header>

    <div class="visual-canvas">
      <component :is="renderer" :spec="spec" :summary="summary" />
    </div>

    <ul v-if="spec.series.length" class="visual-legend" aria-label="图例">
      <li v-for="(item, index) in spec.series" :key="`${item.kind}-${index}`">
        <span :class="['legend-swatch', `legend-${index % 4}`]" aria-hidden="true"></span>
        {{ item.label || kindLabels[item.kind] || item.kind }}
      </li>
    </ul>
    <p v-if="spec.teaching_note" class="teaching-note">{{ spec.teaching_note }}</p>
    <p class="sr-only">{{ summary }}</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import FunctionPlotRenderer from './renderers/FunctionPlotRenderer.vue'
import GeometryRenderer from './renderers/GeometryRenderer.vue'
import VectorRenderer from './renderers/VectorRenderer.vue'

const props = defineProps({
  spec: { type: Object, required: true },
  verification: { type: Object, default: null },
})

const rendererByType = {
  function_plot: FunctionPlotRenderer,
  tangent_line: FunctionPlotRenderer,
  area_under_curve: FunctionPlotRenderer,
  sequence_plot: FunctionPlotRenderer,
  vector_plot: VectorRenderer,
  geometry_plot: GeometryRenderer,
}
const kindLabels = { curve: '曲线', line: '直线', area: '面积', vector: '向量', sequence: '数列', polygon: '几何图形' }
const renderer = computed(() => rendererByType[props.spec.type] || FunctionPlotRenderer)
const titleId = `math-visual-${Math.random().toString(36).slice(2)}`
const summary = computed(() => {
  const labels = props.spec.series.map((item) => item.label || kindLabels[item.kind] || item.kind).join('、')
  return `${props.spec.title}。横轴范围 ${props.spec.viewport.x_min} 到 ${props.spec.viewport.x_max}，纵轴范围 ${props.spec.viewport.y_min} 到 ${props.spec.viewport.y_max}。包含 ${labels}。${props.spec.teaching_note || ''}`
})
</script>

<style scoped>
.visual-card { margin-top: var(--space-4); overflow: hidden; border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); background: var(--surface); box-shadow: var(--shadow-sm); }
.visual-header { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-3); padding: var(--space-4) var(--space-4) var(--space-2); }
.visual-eyebrow { margin: 0 0 var(--space-1); color: var(--knowledge); font-size: var(--font-size-xs); font-weight: 600; letter-spacing: .08em; }
.visual-header h3 { margin: 0; color: var(--text-primary); font-size: var(--font-size-base); line-height: var(--line-height-tight); }
.verified-badge { flex: none; padding: var(--space-1) var(--space-2); border-radius: var(--radius-pill); background: var(--accent-soft); color: var(--accent); font-size: var(--font-size-xs); font-weight: 600; }
.visual-canvas { aspect-ratio: 16 / 9; width: 100%; min-height: 220px; border-block: 1px solid var(--border-subtle); background: var(--surface); }
.visual-legend { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); margin: 0; padding: var(--space-3) var(--space-4); list-style: none; color: var(--text-secondary); font-size: var(--font-size-sm); }
.visual-legend li { display: inline-flex; align-items: center; gap: var(--space-2); }
.legend-swatch { width: 18px; height: 3px; border-radius: var(--radius-pill); background: var(--accent); }
.legend-1 { background: var(--warning); } .legend-2 { background: var(--knowledge); } .legend-3 { background: var(--weak); }
.teaching-note { margin: 0; padding: 0 var(--space-4) var(--space-4); color: var(--text-secondary); font-size: var(--font-size-sm); line-height: var(--line-height-base); }
@media (max-width: 480px) { .visual-header { padding: var(--space-3); } .visual-canvas { min-height: 190px; } .visual-legend { padding-inline: var(--space-3); } .teaching-note { padding-inline: var(--space-3); } }
</style>
