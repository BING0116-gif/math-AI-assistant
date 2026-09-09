<template>
  <svg class="math-plot" :viewBox="`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`" role="img" :aria-label="summary" preserveAspectRatio="xMidYMid meet">
    <defs>
      <marker id="math-vector-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
        <path d="M0,0 L8,4 L0,8 z" class="arrow-head" />
      </marker>
    </defs>
    <g class="grid" aria-hidden="true">
      <line v-for="tick in xTicks" :key="`gx-${tick}`" :x1="project.x(tick)" :x2="project.x(tick)" :y1="PADDING" :y2="SVG_HEIGHT - PADDING" />
      <line v-for="tick in yTicks" :key="`gy-${tick}`" :x1="PADDING" :x2="SVG_WIDTH - PADDING" :y1="project.y(tick)" :y2="project.y(tick)" />
    </g>
    <g class="axes" aria-hidden="true">
      <line :x1="PADDING" :x2="SVG_WIDTH - PADDING" :y1="xAxisY" :y2="xAxisY" />
      <line :x1="yAxisX" :x2="yAxisX" :y1="PADDING" :y2="SVG_HEIGHT - PADDING" />
    </g>
    <g v-for="(item, index) in spec.series" :key="index" :class="['vector-series', `series-${index % 4}`]" aria-hidden="true">
      <line
        v-for="(point, pointIndex) in item.points.slice(1)"
        :key="pointIndex"
        :x1="project.x(item.points[pointIndex][0])"
        :y1="project.y(item.points[pointIndex][1])"
        :x2="project.x(point[0])"
        :y2="project.y(point[1])"
        :marker-end="item.kind === 'vector' ? 'url(#math-vector-arrow)' : undefined"
      />
      <text :x="project.x(item.points.at(-1)[0]) + 8" :y="project.y(item.points.at(-1)[1]) - 8">{{ item.label }}</text>
    </g>
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { SVG_WIDTH, SVG_HEIGHT, PADDING, createProjector, ticks } from './plotGeometry'

const props = defineProps({ spec: { type: Object, required: true }, summary: { type: String, required: true } })
const project = computed(() => createProjector(props.spec.viewport)).value
const xTicks = computed(() => ticks(props.spec.viewport.x_min, props.spec.viewport.x_max))
const yTicks = computed(() => ticks(props.spec.viewport.y_min, props.spec.viewport.y_max))
const xAxisY = computed(() => project.y(Math.min(Math.max(0, props.spec.viewport.y_min), props.spec.viewport.y_max)))
const yAxisX = computed(() => project.x(Math.min(Math.max(0, props.spec.viewport.x_min), props.spec.viewport.x_max)))
</script>

<style scoped>
.math-plot { display: block; width: 100%; height: auto; background: var(--surface); }
.grid line { stroke: var(--border-subtle); stroke-width: 1; }
.axes line { stroke: var(--border-strong); stroke-width: 1.4; }
.vector-series { color: var(--accent); }
.vector-series line { stroke: currentColor; stroke-width: 3; stroke-linecap: round; }
.vector-series text { fill: currentColor; font: 13px var(--font-sans); }
.series-1 { color: var(--warning); } .series-2 { color: var(--knowledge); } .series-3 { color: var(--weak); }
.arrow-head { fill: var(--accent); }
</style>
