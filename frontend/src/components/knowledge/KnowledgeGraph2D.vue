<template>
  <section class="path-view" aria-labelledby="path-heading">
    <header class="path-toolbar">
      <div>
        <p class="eyebrow">当前学习路径</p>
        <h2 id="path-heading">{{ activeChapter?.name || '选择章节' }}</h2>
        <p>{{ projection.points.length }} 个知识点 · 箭头指向下一步</p>
      </div>
      <div class="path-actions">
        <label class="search-box"><span class="sr-only">搜索知识点名称或编号</span><input v-model="searchQuery" type="search" placeholder="搜索知识点或编号" aria-label="搜索知识点名称或编号" :aria-expanded="Boolean(searchResults.length)" aria-controls="knowledge-search-results" @keydown="onSearchKeydown" /></label>
        <button type="button" class="secondary-button" @click="resetPath">返回学习路径</button>
      </div>
      <ul v-if="searchResults.length" id="knowledge-search-results" class="search-results" role="listbox">
        <li v-for="(point, index) in searchResults" :key="point.id"><button type="button" role="option" :aria-selected="index === searchIndex" :class="{ active: index === searchIndex }" @mouseenter="searchIndex = index" @click="chooseSearchResult(point)"><span>{{ point.name }}</span><small>{{ point.chapterName }} · {{ point.code }}</small></button></li>
      </ul>
    </header>

    <div class="path-stage">
      <div ref="cyContainer" class="cy-canvas" role="application" tabindex="0" aria-label="知识点学习路径。使用方向键切换节点，按回车查看详情。" @keydown="onGraphKeydown"></div>
      <ol class="mobile-path" aria-label="当前章节知识点列表">
        <li v-for="(point, index) in projection.points" :key="point.id"><button type="button" :class="{ selected: point.id === selectedPointId }" :aria-current="point.id === selectedPointId ? 'step' : undefined" @click="selectPoint(point)"><span class="step-number">{{ index + 1 }}</span><span class="step-copy"><strong>{{ point.name }}</strong><small>{{ statusLabel(point.status) }}<template v-if="point.isExternalPrerequisite"> · 跨章前置</template></small></span><span aria-hidden="true">→</span></button></li>
      </ol>
      <div class="path-legend" aria-label="图例"><span><i class="line solid"></i>必要前置</span><span><i class="line dashed"></i>相关知识</span><span><i class="node-sample"></i>未学</span><span><i class="node-sample weak"></i>薄弱</span><span><i class="node-sample locked"></i>未解锁</span><span><i class="node-sample mastered"></i>已掌握</span></div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import { buildGraphElements, buildLocalProjection, flattenKnowledgeTree, getDefaultChapterId, searchKnowledgePoints } from './knowledgeGraphProjection'
import { chartVar } from '@/composables/useChartTheme'
import { useUiStore } from '@/stores/uiStore'

cytoscape.use(dagre)
const props = defineProps({ tree: { type: Object, required: true }, mastery: { type: Object, default: () => ({}) }, activeChapterId: { type: String, default: '' }, selectedPointId: { type: String, default: '' } })
const emit = defineEmits(['select-point', 'chapter-change'])
const ui = useUiStore()
const cyContainer = ref(null)
const searchQuery = ref('')
const searchIndex = ref(0)
const reducedMotion = ref(false)
let instance
let resizeObserver

const catalog = computed(() => flattenKnowledgeTree(props.tree, props.mastery))
const effectiveChapterId = computed(() => props.activeChapterId || getDefaultChapterId(catalog.value.chapters))
const projection = computed(() => buildLocalProjection(catalog.value.points, effectiveChapterId.value, props.selectedPointId))
const activeChapter = computed(() => catalog.value.chapters.find(chapter => chapter.id === projection.value.activeChapterId))
const searchResults = computed(() => searchKnowledgePoints(catalog.value.points, searchQuery.value))
const statusLabel = status => ({ mastered: '已掌握', learning: '学习中', weak: '薄弱', locked: '未解锁', untouched: '未学习' }[status] || '未学习')

/* 节点/边配色全部实时取自设计令牌(§7.3):mastered→green、learning→brand、weak→rose、
   locked→ink-4、selected→accent、predecessor/successor→brand-strong/teal、边→border-strong、related→amber */
function graphStyle() {
  return [
    { selector: 'node', style: { shape: 'round-rectangle', width: 136, height: 56, label: 'data(label)', 'font-size': 14, 'font-weight': 600, 'font-family': 'inherit', color: chartVar('--ink-1'), 'text-wrap': 'wrap', 'text-max-width': 112, 'text-valign': 'center', 'text-halign': 'center', 'background-color': chartVar('--surface'), 'border-color': chartVar('--border-strong'), 'border-width': 2, 'overlay-padding': 8, 'overlay-opacity': 0 } },
    { selector: 'node[status = "mastered"]', style: { 'background-color': chartVar('--green-soft'), 'border-color': chartVar('--green') } },
    { selector: 'node[status = "learning"]', style: { 'background-color': chartVar('--brand-soft-2'), 'border-color': chartVar('--brand') } },
    { selector: 'node[status = "weak"]', style: { 'background-color': chartVar('--rose-soft'), 'border-color': chartVar('--rose'), 'border-style': 'double', 'border-width': 4 } },
    { selector: 'node[status = "locked"]', style: { 'background-color': chartVar('--surface-2'), 'border-color': chartVar('--ink-4'), 'border-style': 'dashed', color: chartVar('--ink-3') } },
    { selector: 'node[external]', style: { 'border-style': 'dashed', 'background-color': chartVar('--surface-2') } },
    { selector: 'node:selected, node.focused', style: { 'font-size': 16, 'font-weight': 700, 'border-color': chartVar('--accent'), 'border-width': 4, 'background-color': chartVar('--surface') } },
    { selector: 'node.predecessor', style: { 'border-color': chartVar('--brand-strong'), 'border-width': 3 } },
    { selector: 'node.successor', style: { 'border-color': chartVar('--teal'), 'border-width': 3 } },
    { selector: 'node.dimmed', style: { opacity: 0.24 } },
    { selector: 'edge', style: { width: 2, 'curve-style': 'taxi', 'taxi-direction': 'rightward', 'taxi-turn': 30, 'line-color': chartVar('--border-strong'), 'target-arrow-color': chartVar('--border-strong'), 'target-arrow-shape': 'triangle', 'arrow-scale': 1.1 } },
    { selector: 'edge[kind = "related"]', style: { 'line-style': 'dashed', 'target-arrow-shape': 'none', 'line-color': chartVar('--amber') } },
    { selector: 'edge.highlighted', style: { width: 4, 'line-color': chartVar('--accent'), 'target-arrow-color': chartVar('--accent'), opacity: 1 } },
    { selector: 'edge.dimmed', style: { opacity: 0.12 } }
  ]
}

function initGraph() {
  if (!cyContainer.value) return
  instance?.destroy()
  instance = cytoscape({ container: cyContainer.value, elements: buildGraphElements(projection.value.points), style: graphStyle(), layout: { name: 'dagre', rankDir: 'LR', nodeSep: 32, rankSep: 72, edgeSep: 16, padding: 40, animate: false }, minZoom: 1, maxZoom: 1.6, boxSelectionEnabled: false })
  instance.on('tap', 'node', event => selectById(event.target.id()))
  if (props.selectedPointId) highlightNeighborhood(props.selectedPointId, false)
  requestAnimationFrame(fitReadable)
}

function fitReadable() {
  if (!instance?.nodes().length) return
  instance.fit(instance.elements(), 44)
  if (instance.zoom() < 1) instance.zoom({ level: 1, renderedPosition: { x: instance.width() / 2, y: instance.height() / 2 } })
}

function highlightNeighborhood(id, center = true) {
  if (!instance) return
  const root = instance.getElementById(id)
  if (!root.length) return
  const incoming = root.incomers('edge[kind = "prereq"]')
  const outgoing = root.outgoers('edge[kind = "prereq"]')
  const related = root.connectedEdges('edge[kind = "related"]')
  const activeEdges = incoming.union(outgoing).union(related)
  const activeNodes = activeEdges.connectedNodes().union(root)
  instance.elements().removeClass('focused predecessor successor highlighted dimmed')
  instance.elements().difference(activeNodes.union(activeEdges)).addClass('dimmed')
  root.addClass('focused'); incoming.sources().addClass('predecessor'); outgoing.targets().addClass('successor'); activeEdges.addClass('highlighted'); root.select()
  if (center) instance.animate({ center: { eles: root }, duration: reducedMotion.value ? 0 : 180 })
}

function selectById(id) {
  const point = catalog.value.points.find(item => item.id === id)
  if (!point) return
  if (point.chapterId !== effectiveChapterId.value) emit('chapter-change', point.chapterId)
  highlightNeighborhood(id); emit('select-point', id)
}
function selectPoint(point) { if (point.chapterId !== effectiveChapterId.value) emit('chapter-change', point.chapterId); emit('select-point', point.id) }
function chooseSearchResult(point) { searchQuery.value = ''; searchIndex.value = 0; if (point.chapterId !== effectiveChapterId.value) emit('chapter-change', point.chapterId); nextTick(() => selectById(point.id)) }
function onSearchKeydown(event) {
  if (!searchResults.value.length) return
  if (event.key === 'ArrowDown') { event.preventDefault(); searchIndex.value = (searchIndex.value + 1) % searchResults.value.length }
  else if (event.key === 'ArrowUp') { event.preventDefault(); searchIndex.value = (searchIndex.value - 1 + searchResults.value.length) % searchResults.value.length }
  else if (event.key === 'Enter') { event.preventDefault(); chooseSearchResult(searchResults.value[searchIndex.value]) }
  else if (event.key === 'Escape') searchQuery.value = ''
}
function onGraphKeydown(event) {
  const nodes = instance?.nodes().toArray() || []
  if (!nodes.length) return
  const current = instance.$('node:selected')[0]
  let index = Math.max(0, nodes.findIndex(node => node.id() === current?.id()))
  if (['ArrowRight', 'ArrowDown'].includes(event.key)) index = (index + 1) % nodes.length
  else if (['ArrowLeft', 'ArrowUp'].includes(event.key)) index = (index - 1 + nodes.length) % nodes.length
  else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectById(nodes[index].id()); return }
  else return
  event.preventDefault(); instance.nodes().unselect(); nodes[index].select(); instance.center(nodes[index])
}
function resetPath() { instance?.elements().removeClass('focused predecessor successor highlighted dimmed'); instance?.nodes().unselect(); fitReadable(); cyContainer.value?.focus() }

watch(searchQuery, () => { searchIndex.value = 0 })
watch(projection, () => nextTick(initGraph), { deep: true })
watch(() => props.selectedPointId, id => { if (id) nextTick(() => highlightNeighborhood(id)) })
// 主题切换:rAF 等 data-theme 落地后重取令牌重建样式(类/选中态由 cytoscape 保留)
watch(() => ui.theme, () => { requestAnimationFrame(() => { if (instance && !instance.destroyed()) instance.style(graphStyle()) }) })
onMounted(() => { reducedMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches; initGraph(); resizeObserver = new ResizeObserver(() => { instance?.resize(); fitReadable() }); resizeObserver.observe(cyContainer.value) })
onBeforeUnmount(() => { resizeObserver?.disconnect(); instance?.destroy() })
</script>

<style scoped>
.path-view { height: 100%; min-height: 560px; display: flex; flex-direction: column; background: var(--surface-2); color: var(--ink-1); }
.path-toolbar { position: relative; z-index: 3; display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 18px 20px; border-bottom: 1px solid var(--border); background: var(--surface); }
.path-toolbar h2 { margin: 1px 0 2px; font-size: 20px; line-height: 1.3; }.path-toolbar p { margin: 0; color: var(--ink-2); font-size: 14px; }.path-toolbar .eyebrow { color: var(--brand); font-size: 12px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
.path-actions { display: flex; align-items: center; gap: 8px; }.search-box input { width: 220px; min-height: 44px; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: 0 13px; background: var(--surface); color: var(--ink-1); font: inherit; font-size: 14px; }
.search-box input:focus, button:focus-visible, .cy-canvas:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; box-shadow: 0 0 0 3px var(--brand-soft); }.secondary-button { min-height: 44px; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: 0 14px; background: var(--surface); color: var(--ink-1); font: inherit; font-weight: 650; cursor: pointer; }
.search-results { position: absolute; right: 20px; top: 68px; z-index: 9; width: 340px; margin: 0; padding: 6px; list-style: none; border: 1px solid var(--border); border-radius: var(--r-m); background: var(--surface); box-shadow: var(--shadow-3); }.search-results button { width: 100%; min-height: 52px; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 2px; border: 0; border-radius: var(--r-s); padding: 6px 10px; background: transparent; color: var(--ink-1); font: inherit; text-align: left; cursor: pointer; }.search-results button.active, .search-results button:hover { background: var(--brand-soft); }.search-results small { color: var(--ink-3); font-size: 12px; }
.path-stage { position: relative; flex: 1; min-height: 0; overflow: hidden; }.cy-canvas { width: 100%; height: 100%; min-height: 470px; background-image: radial-gradient(var(--border-strong) 1px, transparent 1px); background-size: 20px 20px; }.mobile-path { display: none; }
.path-legend { position: absolute; left: 16px; bottom: 14px; display: flex; flex-wrap: wrap; gap: 10px 16px; padding: 9px 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: color-mix(in srgb, var(--surface) 94%, transparent); color: var(--ink-2); font-size: 12px; backdrop-filter: blur(8px); }.path-legend span { display: inline-flex; align-items: center; gap: 6px; }.line { width: 26px; border-top: 2px solid var(--ink-3); }.line.dashed { border-top-style: dashed; }.node-sample { width: 18px; height: 12px; border: 2px solid var(--border-strong); border-radius: 4px; background: var(--surface); }.node-sample.weak { border: 3px double var(--rose); background: var(--rose-soft); }.node-sample.locked { border-style: dashed; border-color: var(--ink-4); background: var(--surface-2); }.node-sample.mastered { border-color: var(--green); background: var(--green-soft); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media (max-width: 1100px) { .path-toolbar { flex-wrap: wrap; }.path-actions { width: 100%; }.search-box { flex: 1; }.search-box input { width: 100%; } }
@media (max-width: 768px) { .path-view { min-height: 0; }.path-toolbar { align-items: stretch; flex-direction: column; gap: 12px; padding: 16px; }.path-actions { width: 100%; }.search-box { flex: 1; }.search-box input { width: 100%; font-size: 16px; }.search-results { top: 132px; left: 16px; right: 16px; width: auto; }.cy-canvas, .path-legend { display: none; }.path-stage { overflow: visible; }.mobile-path { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 14px 16px 18px; list-style: none; }.mobile-path button { width: 100%; min-height: 64px; display: flex; align-items: center; gap: 12px; border: 1px solid var(--border); border-radius: var(--r-m); padding: 8px 12px; background: var(--surface); color: var(--ink-1); font: inherit; text-align: left; cursor: pointer; }.mobile-path button.selected { border: 3px solid var(--accent); background: var(--accent-soft); }.step-number { width: 34px; height: 34px; display: grid; flex: 0 0 auto; place-items: center; border-radius: 50%; background: var(--surface-2); color: var(--ink-2); font-weight: 750; }.step-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }.step-copy strong { font-size: 16px; }.step-copy small { color: var(--ink-3); font-size: 13px; } }
@media (prefers-contrast: more) { .path-view, .path-toolbar, .mobile-path button { border-color: currentColor; }.path-toolbar p, .step-copy small { color: var(--ink-1); } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; } }
</style>
