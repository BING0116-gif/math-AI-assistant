<template>
  <section class="path-view" aria-labelledby="path-heading">
    <header class="path-toolbar">
      <div>
        <p class="eyebrow">知识关系网络</p>
        <h2 id="path-heading">{{ graphScope === 'global' ? '全部知识点' : (activeChapter?.name || '选择章节') }}</h2>
        <p>{{ graphPoints.length }} 个知识点 · 点击节点聚焦关联</p>
      </div>
      <div class="path-actions">
        <div class="scope-toggle" role="group" aria-label="图谱范围"><button type="button" :class="{active:graphScope==='global'}" :aria-pressed="graphScope==='global'" @click="graphScope='global'">全局图</button><button type="button" :class="{active:graphScope==='local'}" :aria-pressed="graphScope==='local'" @click="graphScope='local'">局部图</button></div>
        <label class="search-box"><span class="sr-only">搜索知识点名称或编号</span><input v-model="searchQuery" type="search" placeholder="搜索知识点或编号" aria-label="搜索知识点名称或编号" :aria-expanded="Boolean(searchResults.length)" aria-controls="knowledge-search-results" @keydown="onSearchKeydown" /></label>
        <button type="button" class="secondary-button" @click="resetPath">返回学习路径</button>
      </div>
      <ul v-if="searchResults.length" id="knowledge-search-results" class="search-results" role="listbox">
        <li v-for="(point, index) in searchResults" :key="point.id"><button type="button" role="option" :aria-selected="index === searchIndex" :class="{ active: index === searchIndex }" @mouseenter="searchIndex = index" @click="chooseSearchResult(point)"><span>{{ point.name }}</span><small>{{ point.chapterName }} · {{ point.code }}</small></button></li>
      </ul>
    </header>

    <div class="path-stage">
      <div ref="cyContainer" class="cy-canvas" role="application" tabindex="0" aria-label="知识关系网络。使用方向键切换节点，按回车查看详情。" @keydown="onGraphKeydown"></div>
      <div class="graph-hint" aria-hidden="true"><span class="hint-orbit"></span><span>拖拽移动 · 滚轮缩放</span></div>
      <ol class="mobile-path" aria-label="当前章节知识点列表">
        <li v-for="(point, index) in graphPoints" :key="point.id"><button type="button" :class="{ selected: point.id === selectedPointId }" :aria-current="point.id === selectedPointId ? 'step' : undefined" @click="selectPoint(point)"><span class="step-number">{{ index + 1 }}</span><span class="step-copy"><strong>{{ point.name }}</strong><small>{{ statusLabel(point.status) }}<template v-if="point.isExternalPrerequisite"> · 跨章前置</template></small></span><span aria-hidden="true">→</span></button></li>
      </ol>
      <div class="path-legend" aria-label="图例"><span><i class="line solid"></i>必要前置</span><span><i class="line dashed"></i>相关知识</span><span><i class="node-sample"></i>未学</span><span><i class="node-sample weak"></i>薄弱</span><span><i class="node-sample locked"></i>未解锁</span><span><i class="node-sample mastered"></i>已掌握</span></div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import cytoscape from 'cytoscape'
import { buildGraphElements, buildLocalProjection, flattenKnowledgeTree, getDefaultChapterId, searchKnowledgePoints } from './knowledgeGraphProjection'

const props = defineProps({ tree: { type: Object, required: true }, mastery: { type: Object, default: () => ({}) }, activeChapterId: { type: String, default: '' }, selectedPointId: { type: String, default: '' }, viewState: { type: Object, default: null } })
const emit = defineEmits(['select-point', 'chapter-change', 'view-state-change'])
const cyContainer = ref(null)
const searchQuery = ref('')
const searchIndex = ref(0)
const reducedMotion = ref(false)
const graphScope = ref('global')
let instance
let resizeObserver

const catalog = computed(() => flattenKnowledgeTree(props.tree, props.mastery))
const effectiveChapterId = computed(() => props.activeChapterId || getDefaultChapterId(catalog.value.chapters))
const projection = computed(() => buildLocalProjection(catalog.value.points, effectiveChapterId.value, props.selectedPointId))
const graphPoints = computed(() => graphScope.value === 'global' ? catalog.value.points : projection.value.points)
const activeChapter = computed(() => catalog.value.chapters.find(chapter => chapter.id === projection.value.activeChapterId))
const searchResults = computed(() => searchKnowledgePoints(catalog.value.points, searchQuery.value))
const statusLabel = status => ({ mastered: '已掌握', learning: '学习中', weak: '薄弱', locked: '未解锁', untouched: '未学习' }[status] || '未学习')

function graphStyle() {
  return [
    { selector: 'node', style: { shape: 'ellipse', width: 'mapData(degree, 0, 8, 36, 66)', height: 'mapData(degree, 0, 8, 36, 66)', label: 'data(label)', 'font-size': 12, 'font-weight': 600, 'font-family': 'inherit', color: '#d6e0eb', 'text-wrap': 'wrap', 'text-max-width': 104, 'text-valign': 'bottom', 'text-margin-y': 10, 'text-halign': 'center', 'background-color': '#5d83aa', 'background-opacity': .94, 'border-color': '#9bb8d4', 'border-width': 1.5, 'overlay-padding': 10, 'overlay-opacity': 0, 'shadow-blur': 14, 'shadow-color': '#43739c', 'shadow-opacity': .26, 'shadow-offset-y': 2 } },
    { selector: 'node[status = "mastered"]', style: { width: 52, height: 52, 'background-color': '#49b78a', 'border-color': '#9ee2c2', 'shadow-color': '#49b78a', 'shadow-opacity': .45 } },
    { selector: 'node[status = "learning"]', style: { width: 48, height: 48, 'background-color': '#6d9ed0', 'border-color': '#b4d3f0', 'shadow-color': '#5f9bd5', 'shadow-opacity': .42 } },
    { selector: 'node[status = "weak"]', style: { width: 48, height: 48, 'background-color': '#d78963', 'border-color': '#ffc4a4', 'border-width': 3, 'shadow-color': '#d78963', 'shadow-opacity': .44 } },
    { selector: 'node[status = "locked"]', style: { 'background-color': '#4b596a', 'border-color': '#7a8794', 'border-style': 'dashed', color: '#aab5c0', 'shadow-opacity': 0 } },
    { selector: 'node[external]', style: { width: 32, height: 32, 'border-style': 'dashed', 'background-color': '#536273', 'shadow-opacity': 0 } },
    { selector: 'node:selected, node.focused', style: { width: 62, height: 62, 'font-size': 14, 'font-weight': 750, 'border-color': '#f1c878', 'border-width': 4, 'background-color': '#7eabd6', color: '#ffffff', 'shadow-color': '#f0bd63', 'shadow-opacity': .75, 'shadow-blur': 24 } },
    { selector: 'node.predecessor', style: { 'border-color': '#b697e7', 'border-width': 3 } },
    { selector: 'node.successor', style: { 'border-color': '#78d2a4', 'border-width': 3 } },
    { selector: 'node.dimmed', style: { opacity: 0.24 } },
    { selector: 'edge', style: { width: 1.35, 'curve-style': 'bezier', 'line-color': '#7894ae', opacity: .52, 'target-arrow-color': '#7894ae', 'target-arrow-shape': 'triangle', 'arrow-scale': .75 } },
    { selector: 'edge[kind = "related"]', style: { width: 1, 'line-style': 'dashed', 'target-arrow-shape': 'none', 'line-color': '#a78ac6', opacity: .42 } },
    { selector: 'edge.highlighted', style: { width: 3, 'line-color': '#f1c878', 'target-arrow-color': '#f1c878', opacity: 1 } },
    { selector: 'edge.dimmed', style: { opacity: 0.12 } }
  ]
}

function initGraph() {
  if (!cyContainer.value) return
  instance?.destroy()
  instance = cytoscape({ container: cyContainer.value, elements: buildGraphElements(graphPoints.value), style: graphStyle(), layout: { name: 'cose', animate: !reducedMotion.value, animationDuration: 260, fit: true, padding: 76, nodeRepulsion: 8800, idealEdgeLength: 120, gravity: .28, numIter: 900, tile: true }, minZoom: .35, maxZoom: 2.4, boxSelectionEnabled: false })
  instance.on('tap', 'node', event => selectById(event.target.id()))
  instance.on('zoom pan', reportViewState)
  if (props.selectedPointId) highlightNeighborhood(props.selectedPointId, false)
  requestAnimationFrame(() => { fitReadable(); restoreViewState() })
}

function reportViewState() {
  if (!instance) return
  emit('view-state-change', { zoom: instance.zoom(), pan: instance.pan() })
}

function restoreViewState() {
  const state = props.viewState
  if (!instance || !state || !Number.isFinite(state.zoom) || !state.pan) return
  instance.zoom(state.zoom)
  instance.pan({ x: Number(state.pan.x) || 0, y: Number(state.pan.y) || 0 })
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
watch([projection, graphScope], () => nextTick(initGraph), { deep: true })
watch(() => props.selectedPointId, id => { if (id) nextTick(() => highlightNeighborhood(id)) })
onMounted(() => { reducedMotion.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches; initGraph(); resizeObserver = new ResizeObserver(() => { instance?.resize(); fitReadable() }); resizeObserver.observe(cyContainer.value) })
onBeforeUnmount(() => { resizeObserver?.disconnect(); instance?.destroy() })
</script>

<style scoped>
.path-view { height: 100%; min-height: 560px; display: flex; flex-direction: column; overflow: hidden; border-radius: 14px; background: #121820; color: #e7eef5; }
.path-toolbar { position: relative; z-index: 3; display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 18px 20px; border-bottom: 1px solid rgba(177,197,218,.16); background: linear-gradient(180deg,#1d2732,#18212b); }
.path-toolbar h2 { margin: 1px 0 2px; font-size: 20px; line-height: 1.3; color:#f4f7fb; }.path-toolbar p { margin: 0; color: #a9b8c7; font-size: 14px; }.path-toolbar .eyebrow { color: #e4bb69; font-size: 11px; font-weight: 750; letter-spacing: .11em; text-transform: uppercase; }
.path-actions { display: flex; align-items: center; gap: 8px; }.scope-toggle{display:flex;padding:3px;border:1px solid rgba(167,190,213,.26);border-radius:8px;background:#10161e}.scope-toggle button{min-height:36px;border:0;border-radius:5px;padding:0 10px;background:transparent;color:#a9b8c7;font:inherit;font-size:12px;font-weight:650;cursor:pointer}.scope-toggle button.active{background:#344b60;color:#fff;box-shadow:0 1px 4px rgba(0,0,0,.25)}.search-box input { width: 240px; min-height: 44px; border: 1px solid rgba(167,190,213,.32); border-radius: 8px; padding: 0 13px; background: #10161e; color: #e7eef5; font: inherit; font-size: 14px; }
.search-box input::placeholder{color:#8091a2}.search-box input:focus, button:focus-visible, .cy-canvas:focus-visible { outline: 3px solid #e4bb69; outline-offset: 2px; }.secondary-button { min-height: 44px; border: 1px solid rgba(167,190,213,.32); border-radius: 8px; padding: 0 14px; background: #263443; color: #e7eef5; font: inherit; font-weight: 650; cursor: pointer; }.secondary-button:hover{background:#334558}
.search-results { position: absolute; right: 20px; top: 68px; z-index: 9; width: 340px; margin: 0; padding: 6px; list-style: none; border: 1px solid rgba(176,201,224,.25); border-radius: 10px; background: #202c38; box-shadow: 0 18px 40px rgba(0,0,0,.42); }.search-results button { width: 100%; min-height: 52px; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 2px; border: 0; border-radius: 6px; padding: 6px 10px; background: transparent; color: #e7eef5; font: inherit; text-align: left; cursor: pointer; }.search-results button.active, .search-results button:hover { background: #31465a; }.search-results small { color: #a9b8c7; font-size: 12px; }
.path-stage { position: relative; flex: 1; min-height: 0; overflow: hidden; background:radial-gradient(ellipse at 50% 45%,rgba(70,105,137,.22),transparent 52%),#10161d; }.cy-canvas { width: 100%; height: 100%; min-height: 470px; background-image: linear-gradient(rgba(137,167,196,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(137,167,196,.055) 1px,transparent 1px),radial-gradient(rgba(190,211,231,.2) 1px,transparent 1px); background-size: 36px 36px,36px 36px, 12px 12px; }.mobile-path { display: none; }
.graph-hint{position:absolute;right:16px;top:14px;display:flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid rgba(177,197,218,.2);border-radius:999px;background:rgba(18,24,32,.74);color:#a9b8c7;font-size:12px;pointer-events:none;backdrop-filter:blur(8px)}.hint-orbit{width:12px;height:12px;border:1px solid #e4bb69;border-radius:50%;box-shadow:inset 0 0 0 3px rgba(228,187,105,.18)}
.path-legend { position: absolute; left: 16px; bottom: 14px; display: flex; flex-wrap: wrap; gap: 9px 14px; max-width:calc(100% - 32px); padding: 9px 12px; border: 1px solid rgba(177,197,218,.2); border-radius: 8px; background: rgba(18,24,32,.82); color: #c5d0da; font-size: 12px; backdrop-filter:blur(8px); }.path-legend span { display: inline-flex; align-items: center; gap: 6px; }.line { width: 26px; border-top: 2px solid #7894ae; }.line.dashed { border-top-style: dashed;border-color:#a78ac6 }.node-sample { width: 14px; height: 14px; border: 2px solid #9bb8d4; border-radius: 50%; background: #5d83aa; }.node-sample.weak { border: 3px solid #ffc4a4; background: #d78963; }.node-sample.locked { border-style: dashed; border-color: #7a8794; background: #4b596a; }.node-sample.mastered { border-color: #9ee2c2; background: #49b78a; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media (max-width: 1100px) { .path-toolbar { flex-wrap: wrap; }.path-actions { width: 100%; }.search-box { flex: 1; }.search-box input { width: 100%; } }
@media (max-width: 768px) { .path-view { min-height: 0; }.path-toolbar { align-items: stretch; flex-direction: column; gap: 12px; padding: 16px; }.path-actions { width: 100%; }.search-box { flex: 1; }.search-box input { width: 100%; font-size: 16px; }.search-results { top: 132px; left: 16px; right: 16px; width: auto; }.cy-canvas, .path-legend { display: none; }.path-stage { overflow: visible; }.mobile-path { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 14px 16px 18px; list-style: none; }.mobile-path button { width: 100%; min-height: 64px; display: flex; align-items: center; gap: 12px; border: 1px solid #bdcad7; border-radius: 12px; padding: 8px 12px; background: #fff; color: #122235; font: inherit; text-align: left; cursor: pointer; }.mobile-path button.selected { border: 3px solid #0b63ce; background: #eef6ff; }.step-number { width: 34px; height: 34px; display: grid; flex: 0 0 auto; place-items: center; border-radius: 50%; background: #e6edf5; color: #28435d; font-weight: 750; }.step-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }.step-copy strong { font-size: 16px; }.step-copy small { color: #52677c; font-size: 13px; } }
@media (prefers-contrast: more) { .path-view, .path-toolbar, .mobile-path button { border-color: currentColor; }.path-toolbar p, .step-copy small { color: #26384a; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; } }
</style>
