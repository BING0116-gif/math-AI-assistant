<template>
  <svg class="math-plot" :viewBox="`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`" role="img" :aria-label="summary" preserveAspectRatio="xMidYMid meet">
    <g v-for="(item, index) in spec.series" :key="index" :class="['geometry-series', `series-${index % 4}`]" aria-hidden="true">
      <polygon v-if="item.kind === 'polygon'" :points="pointString(item.points, project)" />
      <polyline v-else :points="pointString(item.points, project)" />
      <text v-if="item.label" :x="project.x(item.points[0][0]) + 8" :y="project.y(item.points[0][1]) - 8">{{ item.label }}</text>
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
import { SVG_WIDTH, SVG_HEIGHT, createProjector, pointString } from './plotGeometry'

const props = defineProps({ spec: { type: Object, required: true }, summary: { type: String, required: true } })
const project = computed(() => createProjector(props.spec.viewport)).value
</script>

<style scoped>
.math-plot { display: block; width: 100%; height: auto; background: var(--surface); }
.geometry-series { color: var(--accent); }
.geometry-series polyline, .geometry-series polygon { fill: var(--accent-soft); stroke: currentColor; stroke-width: 2.5; stroke-linejoin: round; }
.geometry-series polyline { fill: none; }
.geometry-series text, .annotations text { fill: var(--text-primary); font: 13px var(--font-sans); paint-order: stroke; stroke: var(--surface); stroke-width: 4; }
.series-1 { color: var(--warning); } .series-2 { color: var(--knowledge); } .series-3 { color: var(--weak); }
.annotations circle { fill: var(--surface); stroke: var(--danger); stroke-width: 2.5; }
.annotations line { stroke: var(--danger); stroke-width: 2; stroke-dasharray: 5 4; }
</style>
