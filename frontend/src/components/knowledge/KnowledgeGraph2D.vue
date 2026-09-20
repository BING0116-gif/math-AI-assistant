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
      <div class="path-legend" aria-label="图例"><span><i class="line solid"></i>必要前置</span><span><i class="line dashed"></i>相关知识</span><span><i class="node-sample"></i>未学</span><span><i class="node-sample mastered"></i>已掌握</span></div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import { buildGraphElements, buildLocalProjection, flattenKnowledgeTree, getDefaultChapterId, searchKnowledgePoints } from './knowledgeGraphProjection'

cytoscape.use(dagre)
const props = defineProps({ tree: { type: Object, required: true }, mastery: { type: Object, default: () => ({}) }, activeChapterId: { type: String, default: '' }, selectedPointId: { type: String, default: '' } })
const emit = defineEmits(['select-point', 'chapter-change'])
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
const statusLabel = status => ({ mastered: '已掌握', learning: '学习中', weak: '薄弱', untouched: '未学习' }[status] || '未学习')

function graphStyle() {
  return [
    { selector: 'node', style: { shape: 'round-rectangle', width: 136, height: 56, label: 'data(label)', 'font-size': 14, 'font-weight': 600, 'font-family': 'inherit', color: '#122235', 'text-wrap': 'wrap', 'text-max-width': 112, 'text-valign': 'center', 'text-halign': 'center', 'background-color': '#F8FBFF', 'border-color': '#7592AE', 'border-width': 2, 'overlay-padding': 8, 'overlay-opacity': 0 } },
    { selector: 'node[status = "mastered"]', style: { 'background-color': '#E4F5EB', 'border-color': '#267A4B' } },
    { selector: 'node[status = "learning"]', style: { 'background-color': '#E8F1FF', 'border-color': '#2563A6' } },
    { selector: 'node[status = "weak"]', style: { 'background-color': '#FFF0E5', 'border-color': '#A54A1B', 'border-style': 'double', 'border-width': 4 } },
    { selector: 'node[external]', style: { 'border-style': 'dashed', 'background-color': '#F3F5F8' } },
    { selector: 'node:selected, node.focused', style: { 'font-size': 16, 'font-weight': 700, 'border-color': '#0B63CE', 'border-width': 4, 'background-color': '#FFFFFF' } },
    { selector: 'node.predecessor', style: { 'border-color': '#5B4AB5', 'border-width': 3 } },
    { selector: 'node.successor', style: { 'border-color': '#16755B', 'border-width': 3 } },
    { selector: 'node.dimmed', style: { opacity: 0.24 } },
    { selector: 'edge', style: { width: 2, 'curve-style': 'taxi', 'taxi-direction': 'rightward', 'taxi-turn': 30, 'line-color': '#718096', 'target-arrow-color': '#718096', 'target-arrow-shape': 'triangle', 'arrow-scale': 1.1 } },
    { selector: 'edge[kind = "related"]', style: { 'line-style': 'dashed', 'target-arrow-shape': 'none', 'line-color': '#697386' } },
    { selector: 'edge.highlighted', style: { width: 4, 'line-color': '#0B63CE', 'target-arrow-color': '#0B63CE', opacity: 1 } },
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
onMounted(() => { reducedMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches; initGraph(); resizeObserver = new ResizeObserver(() => { instance?.resize(); fitReadable() }); resizeObserver.observe(cyContainer.value) })
onBeforeUnmount(() => { resizeObserver?.disconnect(); instance?.destroy() })
</script>

<style scoped>
.path-view { height: 100%; min-height: 560px; display: flex; flex-direction: column; background: #f4f7fb; color: #122235; }
.path-toolbar { position: relative; z-index: 3; display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 18px 20px; border-bottom: 1px solid #d6e0ea; background: #fff; }
.path-toolbar h2 { margin: 1px 0 2px; font-size: 20px; line-height: 1.3; }.path-toolbar p { margin: 0; color: #53677d; font-size: 14px; }.path-toolbar .eyebrow { color: #0b63ce; font-size: 12px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
.path-actions { display: flex; align-items: center; gap: 8px; }.search-box input { width: 220px; min-height: 44px; border: 1px solid #91a4b8; border-radius: 10px; padding: 0 13px; background: #fff; color: #122235; font: inherit; font-size: 14px; }
.search-box input:focus, button:focus-visible, .cy-canvas:focus-visible { outline: 3px solid #7db4f4; outline-offset: 2px; }.secondary-button { min-height: 44px; border: 1px solid #91a4b8; border-radius: 10px; padding: 0 14px; background: #fff; color: #17324d; font: inherit; font-weight: 650; cursor: pointer; }
.search-results { position: absolute; right: 20px; top: 68px; z-index: 9; width: 340px; margin: 0; padding: 6px; list-style: none; border: 1px solid #b7c6d6; border-radius: 12px; background: #fff; box-shadow: 0 16px 36px rgba(30,55,80,.18); }.search-results button { width: 100%; min-height: 52px; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 2px; border: 0; border-radius: 8px; padding: 6px 10px; background: transparent; color: #122235; font: inherit; text-align: left; cursor: pointer; }.search-results button.active, .search-results button:hover { background: #e8f2ff; }.search-results small { color: #586d83; font-size: 12px; }
.path-stage { position: relative; flex: 1; min-height: 0; overflow: hidden; }.cy-canvas { width: 100%; height: 100%; min-height: 470px; background-image: radial-gradient(#c9d5e1 1px, transparent 1px); background-size: 20px 20px; }.mobile-path { display: none; }
.path-legend { position: absolute; left: 16px; bottom: 14px; display: flex; flex-wrap: wrap; gap: 10px 16px; padding: 9px 12px; border: 1px solid #c4d0dc; border-radius: 10px; background: rgba(255,255,255,.94); color: #344b62; font-size: 12px; }.path-legend span { display: inline-flex; align-items: center; gap: 6px; }.line { width: 26px; border-top: 2px solid #53677d; }.line.dashed { border-top-style: dashed; }.node-sample { width: 18px; height: 12px; border: 2px solid #7592ae; border-radius: 4px; background: #f8fbff; }.node-sample.mastered { border-color: #267a4b; background: #e4f5eb; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media (max-width: 768px) { .path-view { min-height: 0; }.path-toolbar { align-items: stretch; flex-direction: column; gap: 12px; padding: 16px; }.path-actions { width: 100%; }.search-box { flex: 1; }.search-box input { width: 100%; font-size: 16px; }.search-results { top: 132px; left: 16px; right: 16px; width: auto; }.cy-canvas, .path-legend { display: none; }.path-stage { overflow: visible; }.mobile-path { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 14px 16px 18px; list-style: none; }.mobile-path button { width: 100%; min-height: 64px; display: flex; align-items: center; gap: 12px; border: 1px solid #bdcad7; border-radius: 12px; padding: 8px 12px; background: #fff; color: #122235; font: inherit; text-align: left; cursor: pointer; }.mobile-path button.selected { border: 3px solid #0b63ce; background: #eef6ff; }.step-number { width: 34px; height: 34px; display: grid; flex: 0 0 auto; place-items: center; border-radius: 50%; background: #e6edf5; color: #28435d; font-weight: 750; }.step-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }.step-copy strong { font-size: 16px; }.step-copy small { color: #52677c; font-size: 13px; } }
@media (prefers-contrast: more) { .path-view, .path-toolbar, .mobile-path button { border-color: currentColor; }.path-toolbar p, .step-copy small { color: #26384a; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; } }
</style>
