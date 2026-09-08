<template>
  <section ref="container" class="graph2d" aria-label="二维知识依赖图谱">
    <div ref="cy" class="cy"></div>

    <!-- 顶部工具：搜索 + 章节筛选 -->
    <div class="hud">
      <input
        v-model="searchQuery"
        class="search-input"
        type="search"
        placeholder="搜索知识点…"
        aria-label="搜索知识点"
      />
      <select v-model="chapterFilter" class="chapter-select" aria-label="按章节筛选">
        <option value="">全部章节</option>
        <option v-for="c in chapterLegend" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
    </div>

    <!-- 底部图例 -->
    <div class="legend">
      <span class="legend-title">掌握状态</span>
      <span class="legend-item" v-for="s in masteryLegend" :key="s.key">
        <i class="lg" :style="{ background: s.color, border: `2px solid ${s.border}` }"></i>{{ s.label }}
      </span>
      <span class="legend-sep"></span>
      <span class="legend-item"><i class="lg prereq"></i>前置依赖</span>
      <span class="legend-item"><i class="lg related"></i>相关/易混淆</span>
      <span class="legend-sep"></span>
      <span class="legend-title">章节分组</span>
      <span class="legend-item" v-for="c in chapterLegend" :key="'c-' + c.id">
        <i class="lg" :style="{ background: 'transparent', border: `2px dashed ${c.color}` }"></i>{{ c.name }}
      </span>
    </div>

    <!-- 右下操作 -->
    <div class="view-tools">
      <button type="button" :disabled="!hasNext" @click="showNext">推荐下一步</button>
      <button type="button" @click="fitView">适配视图</button>
    </div>

    <!-- 推荐卡 -->
    <div v-if="nextShown" class="next-card">
      <div class="next-card-head">
        <span>推荐学习</span>
        <button type="button" class="next-close" @click="clearNext">×</button>
      </div>
      <button v-for="n in nextList" :key="n.id" type="button" class="next-item" @click="selectNode(n.id)">
        <span class="next-name">{{ n.name }}</span>
        <span class="next-badge" :class="n.mstatus">{{ masteryLabel(n.mstatus) }}</span>
      </button>
      <p v-if="!nextList.length" class="next-empty">没有可推荐的下一步</p>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'

// 注册 dagre 布局器
cytoscape.use(dagre)

const props = defineProps({
  tree: { type: Object, required: true },
  mastery: { type: Object, default: () => ({}) }
})
const emit = defineEmits(['select-point'])

const container = ref(null)
const cy = ref(null)
const searchQuery = ref('')
const chapterFilter = ref('')
const nextShown = ref(false)
let instance = null
let resizeObserver = null
let pointsCache = []
let chapterMetaCache = []

// 章节配色
const CHAPTER_COLORS = [
  '#C8913D', '#5F947C', '#417E7A', '#5A8A8A', '#7F77DD',
  '#D4537E', '#BA7517', '#378ADD', '#639922', '#D85A30'
]

const MASTERY_STYLES = {
  mastered: { fill: '#2F8F5B', label: '已掌握' },
  learning: { fill: '#B08A2E', label: '学习中' },
  weak: { fill: '#C0554F', label: '薄弱' },
  untouched: { fill: '#3B4857', label: '未学' }
}

const masteryLegend = Object.entries(MASTERY_STYLES).map(([key, v]) => ({ key, ...v }))
const chapterLegend = ref([])

const hasNext = computed(() => computeNext().length > 0)
const nextList = ref([])

function masteryLabel(status) {
  return MASTERY_STYLES[status]?.label || '未学'
}

function flatten(tree) {
  const points = []
  const chapterMeta = []
  const chapters = tree?.chapters || []
  chapters.forEach((chapter, ci) => {
    const color = CHAPTER_COLORS[ci % CHAPTER_COLORS.length]
    chapterMeta.push({ id: chapter.id, name: chapter.name, color })
    const sections = chapter.children || []
    const buckets = [chapter, ...sections]
    buckets.forEach(b => {
      ;(b.knowledge_points || []).forEach(p => {
        points.push({
          id: p.id,
          code: p.code,
          name: p.name,
          difficulty: p.difficulty || 3,
          prerequisites: p.prerequisites || [],
          related: p.related || [],
          chapterId: chapter.id,
          chapterName: chapter.name,
          chapterColor: color
        })
      })
    })
  })
  return { points, chapterMeta }
}

function masteryOf(point) {
  const entry = props.mastery?.[point.code]
  return entry?.status || 'untouched'
}

function buildElements(points, chapterMeta) {
  const byCode = new Map()
  points.forEach(p => { if (p.code) byCode.set(p.code, p.id) })

  // 章节 compound node（用真实存在的小节作为父容器，让所有子知识点归属同一 compound）
  const nodes = []
  const chapterPointCount = {}
  points.forEach(p => {
    chapterPointCount[p.chapterId] = (chapterPointCount[p.chapterId] || 0) + 1
  })
  chapterMeta.forEach(c => {
    nodes.push({
      data: {
        id: `chap-${c.id}`,
        name: c.name,
        rawName: c.name,
        color: c.color,
        collapsed: false,
        pointCount: chapterPointCount[c.id] || 0
      }
    })
  })

  // 知识点节点
  points.forEach(p => {
    const mstatus = masteryOf(p)
    const ms = MASTERY_STYLES[mstatus] || MASTERY_STYLES.untouched
    nodes.push({
      data: {
        id: p.id,
        code: p.code,
        label: p.name,
        chapterId: p.chapterId,
        chapterColor: p.chapterColor,
        difficulty: p.difficulty,
        mstatus,
        mfill: ms.fill,
        parent: `chap-${p.chapterId}`
      }
    })
  })

  const edges = []
  const seen = new Set()
  points.forEach(p => {
    ;(p.prerequisites || []).forEach(code => {
      const src = byCode.get(code)
      if (!src || src === p.id) return
      const key = `pre:${src}->${p.id}`
      if (seen.has(key)) return
      seen.add(key)
      edges.push({ data: { id: key, source: src, target: p.id, kind: 'prereq' } })
    })
    ;(p.related || []).forEach(code => {
      const src = byCode.get(code)
      if (!src || src === p.id) return
      const key = `rel:${[src, p.id].sort().join('-')}`
      if (seen.has(key)) return
      seen.add(key)
      edges.push({ data: { id: key, source: src, target: p.id, kind: 'related' } })
    })
  })

  return { nodes, edges }
}

function applyLayout() {
  if (!instance) return
  // dagre 失败回退到 breadthfirst
  let layout
  try {
    layout = instance.layout({
      name: 'dagre',
      rankDir: 'LR',
      nodeSep: 60,
      edgeSep: 24,
      rankSep: 110,
      padding: 50,
      animate: true
    })
    layout.run()
  } catch (err) {
    console.warn('[KnowledgeGraph2D] dagre 失败，回退 breadthfirst', err)
    instance.layout({
      name: 'breadthfirst',
      directed: true,
      orientation: 'horizontal',
      spacingFactor: 1.6,
      padding: 40,
      animate: false
    }).run()
  }
}

function init() {
  if (!container.value || !cy.value) return
  if (instance) { instance.destroy(); instance = null }

  const { points, chapterMeta } = flatten(props.tree)
  pointsCache = points
  chapterMetaCache = chapterMeta
  chapterLegend.value = chapterMeta
  const { nodes, edges } = buildElements(points, chapterMeta)
  if (!points.length) return

  instance = cytoscape({
    container: cy.value,
    elements: { nodes, edges },
    style: [
      // 知识点节点：圆角矩形、加大尺寸
      {
        selector: 'node[^compound]',
        style: {
          'shape': 'round-rectangle',
          'background-color': 'data(mfill)',
          'label': 'data(label)',
          'color': '#E6F1FB',
          'font-size': 12,
          'font-weight': 500,
          'text-valign': 'center',
          'text-halign': 'center',
          'text-wrap': 'wrap',
          'text-max-width': '96px',
          'width': 110,
          'height': 38,
          'border-width': 2,
          'border-color': 'data(chapterColor)',
          'padding': '4px'
        }
      },
      {
        selector: 'node[^compound][mstatus = "weak"]',
        style: { 'border-width': 4, 'border-color': '#E08A7A' }
      },
      {
        selector: 'node[^compound][mstatus = "mastered"]',
        style: { 'border-width': 3 }
      },
      {
        selector: 'node[^compound]:selected',
        style: { 'border-color': '#EF9F27', 'border-width': 3 }
      },
      // 章节 compound：半透明容器、章节名+三角标记
      {
        selector: 'node[?compound]',
        style: {
          'shape': 'round-rectangle',
          'background-color': 'rgba(11,25,36,0.55)',
          'background-opacity': 0.35,
          'border-color': 'data(color)',
          'border-width': 1.5,
          'border-style': 'dashed',
          'label': 'data(label)',
          'color': 'data(color)',
          'font-size': 13,
          'font-weight': 700,
          'text-valign': 'top',
          'text-halign': 'left',
          'text-margin-x': 8,
          'text-margin-y': -8,
          'padding': 18,
          'compound-sizing-w-b': 'min-width: 200px; height: 80px;',
          'events': 'yes'
        }
      },
      // 边
      {
        selector: 'edge[kind = "prereq"]',
        style: {
          'width': 1.6,
          'line-color': '#5A7A7A',
          'target-arrow-color': '#5A7A7A',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier'
        }
      },
      {
        selector: 'edge[kind = "related"]',
        style: {
          'width': 1.2,
          'line-color': '#3a4d63',
          'line-style': 'dashed',
          'curve-style': 'bezier',
          'opacity': 0.7
        }
      },
      // 选中高亮
      {
        selector: '.focused',
        style: { 'border-color': '#EF9F27', 'border-width': 4 }
      },
      {
        selector: '.linked',
        style: { 'opacity': 1, 'border-color': '#7FB8E6', 'border-width': 2 }
      },
      {
        selector: '.linked-edge',
        style: { 'opacity': 1, 'line-color': '#7FB8E6', 'width': 2.4 }
      },
      {
        selector: '.dimmed',
        style: { 'opacity': 0.16 }
      },
      // 搜索命中
      {
        selector: '.search-hit',
        style: { 'border-color': '#46C7C7', 'border-width': 4, 'opacity': 1 }
      },
      {
        selector: '.search-dim',
        style: { 'opacity': 0.12 }
      },
      // 推荐下一步
      {
        selector: '.next',
        style: { 'border-color': '#46C77F', 'border-width': 4, 'opacity': 1 }
      }
    ],
    layout: { name: 'preset' }, // 用我们手动布局
    minZoom: 0.15,
    maxZoom: 1.5
  })

  // 化合物点击：折叠/展开
  instance.on('tap', 'node[?compound]', evt => {
    toggleChapter(evt.target)
  })
  // 知识点点击：详情
  instance.on('tap', 'node[^compound]', evt => {
    clearNext()
    highlightNeighborhood(evt.target.id())
    emit('select-point', evt.target.id())
  })
  instance.on('tap', evt => {
    if (evt.target === instance) {
      clearHighlights()
      clearNext()
    }
  })

  applyLayout()
  resizeObserver = new ResizeObserver(() => instance && instance.resize())
  resizeObserver.observe(container.value)
  setTimeout(() => instance && instance.fit(undefined, 40), 300)
}

function fitView() {
  if (instance) instance.fit(undefined, 40)
}

/* ---------------- 章节折叠 ---------------- */
function toggleChapter(compoundNode) {
  if (!instance) return
  const collapsed = !compoundNode.data('collapsed')
  compoundNode.data('collapsed', collapsed)
  compoundNode.data('label', (collapsed ? '▶ ' : '▼ ') + compoundNode.data('rawName'))
  applyVisibility()
  setTimeout(() => instance && instance.fit(undefined, 50), 80)
}

/* ---------------- 可见性（章节筛选 + 折叠合并） ---------------- */
function applyVisibility() {
  if (!instance) return
  const filter = chapterFilter.value
  const collapsedChapIds = new Set()
  instance.nodes().forEach(n => {
    if (n.isParent() && n.data('collapsed')) collapsedChapIds.add(n.id())
  })

  instance.nodes().forEach(n => {
    if (n.isParent()) {
      // compound 始终可见（即便折叠）
      n.style('display', 'element')
      return
    }
    const chapterId = n.data('chapterId')
    const visible = (!filter || chapterId === filter) && !collapsedChapIds.has(`chap-${chapterId}`)
    n.style('display', visible ? 'element' : 'none')
  })
  instance.edges().forEach(edge => {
    const s = edge.source(), t = edge.target()
    const sv = s.style('display') !== 'none' && !s.isParent()
    const tv = t.style('display') !== 'none' && !t.isParent()
    edge.style('display', sv && tv ? 'element' : 'none')
  })
}

watch(chapterFilter, () => {
  applyVisibility()
  clearNext()
  setTimeout(() => instance && instance.fit(undefined, 50), 80)
})

/* ---------------- 选中节点：高亮上游前置 + 下游后继 + 相关 ---------------- */
function collectNeighborhood(rootId) {
  const up = new Set()
  const down = new Set()
  const side = new Set()
  if (!instance) return { up, down, side }
  const edgeList = instance.edges().map(e => ({ src: e.source().id(), tgt: e.target().id(), kind: e.data('kind') }))

  let frontier = new Set([rootId])
  while (frontier.size) {
    const next = new Set()
    edgeList.forEach(ed => {
      if (ed.kind === 'prereq' && frontier.has(ed.tgt) && !up.has(ed.src) && ed.src !== rootId) {
        up.add(ed.src); next.add(ed.src)
      }
    })
    frontier = next
  }
  frontier = new Set([rootId])
  while (frontier.size) {
    const next = new Set()
    edgeList.forEach(ed => {
      if (ed.kind === 'prereq' && frontier.has(ed.src) && !down.has(ed.tgt) && ed.tgt !== rootId) {
        down.add(ed.tgt); next.add(ed.tgt)
      }
    })
    frontier = next
  }
  edgeList.forEach(ed => {
    if (ed.kind !== 'related') return
    if (ed.src === rootId) side.add(ed.tgt)
    if (ed.tgt === rootId) side.add(ed.src)
  })
  return { up, down, side }
}

function highlightNeighborhood(rootId) {
  if (!instance) return
  const { up, down, side } = collectNeighborhood(rootId)
  const linkedIds = new Set([rootId, ...up, ...down, ...side])

  instance.elements().removeClass('focused linked linked-edge dimmed')
  const root = instance.$(`#${rootId}`)
  if (root.length) root.addClass('focused')
  linkedIds.forEach(id => {
    if (id !== rootId) {
      const n = instance.$(`#${id}`)
      if (n.length && !n.isParent()) n.addClass('linked')
    }
  })
  instance.edges().forEach(edge => {
    const s = edge.source().id()
    const t = edge.target().id()
    const linked = (s === rootId && (down.has(t) || side.has(t))) ||
      (t === rootId && (up.has(s) || side.has(s)))
    if (linked) edge.addClass('linked-edge')
    else if (!linkedIds.has(s) || !linkedIds.has(t)) edge.addClass('dimmed')
  })
  instance.nodes().forEach(node => {
    if (node.isParent()) return
    if (!linkedIds.has(node.id())) node.addClass('dimmed')
  })
}

function clearHighlights() {
  if (!instance) return
  instance.elements().removeClass('focused linked linked-edge dimmed search-hit search-dim next')
}

/* ---------------- 关键词搜索 ---------------- */
watch(searchQuery, val => {
  if (!instance) return
  const q = (val || '').trim().toLowerCase()
  clearHighlights()
  if (!q) return
  let firstHit = null
  instance.nodes().forEach(node => {
    if (node.isParent()) return
    const label = (node.data('label') || '').toLowerCase()
    const code = (node.data('code') || '').toLowerCase()
    const hit = label.includes(q) || code.includes(q)
    if (hit) {
      node.addClass('search-hit')
      if (!firstHit) firstHit = node
    } else node.addClass('search-dim')
  })
  if (firstHit) instance.animate({ fit: { eles: firstHit, padding: 80 }, duration: 300 })
})

/* ---------------- 推荐下一步 ---------------- */
function computeNext() {
  const results = []
  const statusOf = {}
  pointsCache.forEach(p => { statusOf[p.code] = masteryOf(p) })

  pointsCache.forEach(p => {
    const unlocked = (p.prerequisites || []).every(code => statusOf[code] === 'mastered')
    if (!unlocked) return
    const status = statusOf[p.code]
    if (status === 'untouched' || status === 'weak') {
      results.push(p)
    }
  })
  results.sort((a, b) => a.difficulty - b.difficulty || a.code.localeCompare(b.code))
  return results.slice(0, 3)
}

function showNext() {
  const list = computeNext()
  nextList.value = list
  nextShown.value = true
  if (!instance || !list.length) return
  const ids = list.map(n => `#${n.id}`).join(', ')
  const eles = instance.$(ids)
  instance.elements().removeClass('next dimmed')
  eles.addClass('next')
  instance.edges().forEach(edge => {
    if (edge.data('kind') === 'prereq' && eles.some(n => n.id() === edge.target().id())) {
      const src = edge.source().id()
      const srcStatus = instance.$(`#${src}`).data('mstatus')
      if (srcStatus === 'mastered') edge.removeClass('dimmed')
    }
  })
  instance.animate({ fit: { eles, padding: 90 }, duration: 400 })
}

function selectNode(id) {
  const node = instance && instance.$(`#${id}`)
  if (node && node.length) {
    highlightNeighborhood(id)
    emit('select-point', id)
  }
}

function clearNext() {
  nextShown.value = false
  nextList.value = []
  if (instance) instance.elements().removeClass('next')
}

/* ---------------- 数据变化重建 ---------------- */
watch(() => props.tree, () => { init() }, { deep: true })
watch(() => props.mastery, () => {
  if (props.tree) init()
}, { deep: true })

onMounted(init)
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  instance?.destroy()
  instance = null
})
</script>

<style scoped>
.graph2d { position: relative; width: 100%; height: 100%; min-height: 560px; border-radius: 16px; overflow: hidden; background: #0B1924; }
.cy { width: 100%; height: 100%; }

.hud { position: absolute; left: 14px; top: 14px; display: flex; gap: 8px; flex-wrap: wrap; z-index: 5; }
.search-input, .chapter-select {
  border: 1px solid rgba(90,122,122,.35);
  border-radius: 999px;
  background: rgba(11,25,36,.78);
  color: rgba(214,224,218,.9);
  padding: 5px 12px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
  backdrop-filter: blur(8px);
  max-width: 160px;
}
.search-input::placeholder { color: rgba(180,196,188,.55); }
.search-input:focus, .chapter-select:focus { border-color: rgba(95,148,124,.6); }
.chapter-select { cursor: pointer; }
.chapter-select option { background: #0B1924; color: #E6F1FB; }

.legend {
  position: absolute; left: 14px; bottom: 14px;
  display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
  background: rgba(11,25,36,.78); border: 1px solid rgba(90,122,122,.35);
  border-radius: 12px; padding: 8px 12px; backdrop-filter: blur(8px);
  z-index: 4; max-width: calc(100% - 28px);
}
.legend-title { font-size: 11px; font-weight: 700; color: rgba(214,224,218,.9); letter-spacing: .04em; }
.legend-item { display: flex; align-items: center; gap: 6px; color: rgba(214,224,218,.85); font-size: 11px; }
.legend-sep { width: 1px; height: 14px; background: rgba(90,122,122,.35); }
.lg { width: 12px; height: 12px; border-radius: 50%; display: inline-block; box-sizing: border-box; }
.lg.prereq { background: transparent; border: 1px solid #5A7A7A; border-radius: 0; }
.lg.related { background: transparent; border: 1px dashed #3a4d63; border-radius: 0; }

.view-tools { position: absolute; right: 14px; bottom: 14px; display: flex; gap: 6px; z-index: 5; }
.view-tools button {
  border: 1px solid rgba(90,122,122,.35); border-radius: 999px;
  background: rgba(11,25,36,.78); color: rgba(180,196,188,.82);
  padding: 5px 10px; font-size: 11px; cursor: pointer; font: inherit;
  backdrop-filter: blur(8px);
}
.view-tools button:hover:not(:disabled) { border-color: rgba(95,148,124,.5); background: rgba(11,25,36,.9); }
.view-tools button:disabled { opacity: .4; cursor: not-allowed; }

.next-card {
  position: absolute; right: 14px; top: 14px; z-index: 6;
  min-width: 190px; max-width: 230px;
  background: rgba(11,25,36,.92); border: 1px solid rgba(95,148,124,.45);
  border-radius: 12px; padding: 10px 12px; backdrop-filter: blur(10px);
  box-shadow: 0 8px 24px rgba(0,0,0,.35);
}
.next-card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.next-card-head span { font-size: 12px; font-weight: 700; color: #E6F1FB; letter-spacing: .04em; }
.next-close { border: 0; background: transparent; color: rgba(180,196,188,.7); font-size: 16px; line-height: 1; cursor: pointer; padding: 0 2px; }
.next-close:hover { color: #fff; }
.next-item {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  width: 100%; text-align: left; margin-bottom: 6px;
  border: 1px solid rgba(90,122,122,.35); border-radius: 8px;
  background: rgba(11,25,36,.6); color: rgba(230,241,251,.92);
  padding: 6px 8px; font: inherit; font-size: 12px; cursor: pointer;
}
.next-item:hover { border-color: #46C77F; }
.next-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.next-badge { font-size: 10px; padding: 2px 6px; border-radius: 999px; flex-shrink: 0; }
.next-badge.untouched { background: rgba(59,72,87,.6); color: rgba(214,224,218,.85); }
.next-badge.weak { background: rgba(192,85,79,.25); color: #E08A7A; }
.next-empty { margin: 0; font-size: 11px; color: rgba(180,196,188,.6); }

@media (max-width: 768px) {
  .graph2d { min-height: 420px; }
  .hud { display: none; }
  .legend { gap: 8px; padding: 6px 8px; font-size: 10px; }
  .next-card { right: 10px; top: 10px; min-width: 160px; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
</style>