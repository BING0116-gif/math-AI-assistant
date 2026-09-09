<template>
  <svg
    class="math-plot"
    :viewBox="`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`"
    role="img"
    :aria-label="summary"
    preserveAspectRatio="xMidYMid meet"
  >
    <g class="grid" aria-hidden="true">
      <line v-for="tick in xTicks" :key="`gx-${tick}`" :x1="project.x(tick)" :x2="project.x(tick)" :y1="PADDING" :y2="SVG_HEIGHT - PADDING" />
      <line v-for="tick in yTicks" :key="`gy-${tick}`" :x1="PADDING" :x2="SVG_WIDTH - PADDING" :y1="project.y(tick)" :y2="project.y(tick)" />
    </g>
    <g class="axes" aria-hidden="true">
      <line :x1="PADDING" :x2="SVG_WIDTH - PADDING" :y1="xAxisY" :y2="xAxisY" />
      <line :x1="yAxisX" :x2="yAxisX" :y1="PADDING" :y2="SVG_HEIGHT - PADDING" />
      <text v-for="tick in xTicks" :key="`tx-${tick}`" :x="project.x(tick)" :y="SVG_HEIGHT - 10" text-anchor="middle">{{ formatTick(tick) }}</text>
      <text v-for="tick in yTicks" :key="`ty-${tick}`" :x="PADDING - 7" :y="project.y(tick) + 4" text-anchor="end">{{ formatTick(tick) }}</text>
    </g>
    <g v-for="(item, index) in spec.series" :key="`${item.kind}-${index}`" :class="['series', `series-${index % 4}`]" aria-hidden="true">
      <polygon v-if="item.kind === 'area'" :points="pointString(item.points, project)" class="area-shape" />
      <polyline v-else :points="pointString(item.points, project)" :class="['series-line', { dashed: item.kind === 'line' }]" />
      <circle v-if="item.kind === 'sequence'" v-for="([x, y], pointIndex) in item.points" :key="pointIndex" :cx="project.x(x)" :cy="project.y(y)" r="4" class="sequence-point" />
    </g>
    <g class="annotations" aria-hidden="true">
      <g v-for="(item, index) in spec.annotations" :key="index">
        <circle v-if="item.kind === 'point'" :cx="project.x(item.x)" :cy="project.y(item.y)" r="5" />
        <line
          v-if="item.kind === 'interval' && item.x_end !== undefined && item.y_end !== undefined"
          :x1="project.x(item.x)"
          :y1="project.y(item.y)"
          :x2="project.x(item.x_end)"
          :y2="project.y(item.y_end)"
        />
        <text :x="project.x(item.x) + 9" :y="project.y(item.y) - 9">{{ item.label }}</text>
      </g>
    </g>
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { SVG_WIDTH, SVG_HEIGHT, PADDING, createProjector, pointString, ticks, formatTick } from './plotGeometry'

const props = defineProps({ spec: { type: Object, required: true }, summary: { type: String, required: true } })
const project = computed(() => createProjector(props.spec.viewport)).value
const xTicks = computed(() => ticks(props.spec.viewport.x_min, props.spec.viewport.x_max))
const yTicks = computed(() => ticks(props.spec.viewport.y_min, props.spec.viewport.y_max))
const xAxisY = computed(() => project.y(Math.min(Math.max(0, props.spec.viewport.y_min), props.spec.viewport.y_max)))
const yAxisX = computed(() => project.x(Math.min(Math.max(0, props.spec.viewport.x_min), props.spec.viewport.x_max)))
</script>

<style scoped>
.math-plot { display: block; width: 100%; height: auto; color: var(--text-secondary); background: var(--surface); }
.grid line { stroke: var(--border-subtle); stroke-width: 1; }
.axes line { stroke: var(--border-strong); stroke-width: 1.4; }
.axes text { fill: var(--text-tertiary); font: 12px var(--font-mono); }
.series-line { fill: none; stroke: var(--accent); stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
.series-1 .series-line, .series-1 .sequence-point { stroke: var(--warning); fill: var(--warning); }
.series-2 .series-line, .series-2 .sequence-point { stroke: var(--knowledge); fill: var(--knowledge); }
.series-3 .series-line, .series-3 .sequence-point { stroke: var(--weak); fill: var(--weak); }
.series-line.dashed { stroke-dasharray: 8 5; }
.area-shape { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.5; }
.sequence-point { fill: var(--accent); stroke: var(--surface); stroke-width: 2; }
.annotations circle { fill: var(--surface); stroke: var(--danger); stroke-width: 2.5; }
.annotations line { stroke: var(--danger); stroke-width: 2; stroke-dasharray: 5 4; }
.annotations text { fill: var(--text-primary); font: 13px var(--font-sans); paint-order: stroke; stroke: var(--surface); stroke-width: 4; }
</style>
