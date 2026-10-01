<script setup>
/**
 * 知识范围选择器:单元 → 点进单元 → 按书本知识点勾选 的两级结构。
 * 替代把全部知识点平铺一页的做法;提交语义保持 chapter_ids ∪ knowledge_point_codes,
 * 「整单元」勾选写 chapter_ids,单个知识点勾选写 knowledge_point_codes(后端按并集出题)。
 */
import { computed, ref, watch } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'

const props = defineProps({
  chapters: { type: Array, default: () => [] },
  points: { type: Array, default: () => [] },
  chapterIds: { type: Array, default: () => [] },
  pointCodes: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:chapterIds', 'update:pointCodes'])

const openId = ref('')
/* 本地副本承接连续点选(props 在父组件重渲染前是旧值,直接叠加会互相覆盖) */
const localChapterIds = ref([...props.chapterIds])
const localPointCodes = ref([...props.pointCodes])
watch(() => props.chapterIds, (v) => { localChapterIds.value = [...(v || [])] })
watch(() => props.pointCodes, (v) => { localPointCodes.value = [...(v || [])] })

const byId = computed(() => new Map(props.chapters.map((c) => [c.id, c])))
const pointsByChapter = computed(() => {
  const map = new Map()
  for (const p of props.points) {
    if (!map.has(p.chapter_id)) map.set(p.chapter_id, [])
    map.get(p.chapter_id).push(p)
  }
  return map
})
/* 无 parent 信息时退化为平铺:每个章节各自成行 */
const units = computed(() => {
  const roots = props.chapters.filter((c) => !c.parent_id || !byId.value.has(c.parent_id))
  return roots.map((ch) => {
    const children = props.chapters.filter((c) => c.parent_id === ch.id)
    const groups = [
      { chapter: ch, points: pointsByChapter.value.get(ch.id) || [] },
      ...children.map((c) => ({ chapter: c, points: pointsByChapter.value.get(c.id) || [] })),
    ].filter((g) => g.points.length)
    const all = groups.flatMap((g) => g.points)
    return { chapter: ch, groups, total: all.length, codes: new Set(all.map((p) => p.code)) }
  })
})

const isWholeUnit = (u) => localChapterIds.value.includes(u.chapter.id)
const unitPickedCount = (u) => localPointCodes.value.filter((code) => u.codes.has(code)).length
function toggleOpen(u) { openId.value = openId.value === u.chapter.id ? '' : u.chapter.id }
function toggleWhole(u) {
  localChapterIds.value = localChapterIds.value.includes(u.chapter.id)
    ? localChapterIds.value.filter((id) => id !== u.chapter.id)
    : [...localChapterIds.value, u.chapter.id]
  emit('update:chapterIds', [...localChapterIds.value])
}
function togglePoint(code) {
  localPointCodes.value = localPointCodes.value.includes(code)
    ? localPointCodes.value.filter((c) => c !== code)
    : [...localPointCodes.value, code]
  emit('update:pointCodes', [...localPointCodes.value])
}
</script>
<template>
  <div class="krange">
    <article v-for="u in units" :key="u.chapter.id" class="unit" :class="{ open: openId === u.chapter.id, whole: isWholeUnit(u) }">
      <header class="unit-head" :aria-expanded="openId === u.chapter.id ? 'true' : 'false'" @click="toggleOpen(u)">
        <ChevronRight v-if="openId !== u.chapter.id" class="chev" :size="16" :stroke-width="1.75" aria-hidden="true" />
        <ChevronDown v-else class="chev" :size="16" :stroke-width="1.75" aria-hidden="true" />
        <strong>{{ u.chapter.name }}</strong>
        <span class="meta">{{ u.total }} 个知识点<template v-if="isWholeUnit(u)"> · 整单元</template><template v-else-if="unitPickedCount(u)"> · 已选 {{ unitPickedCount(u) }}</template></span>
        <label class="whole" @click.stop>
          <input type="checkbox" :checked="isWholeUnit(u)" @change="toggleWhole(u)" />
          <span>整单元</span>
        </label>
      </header>
      <div v-if="openId === u.chapter.id" class="unit-body">
        <section v-for="g in u.groups" :key="g.chapter.id">
          <h4 v-if="g.chapter.id !== u.chapter.id">{{ g.chapter.name }}</h4>
          <div class="chips">
            <label v-for="p in g.points" :key="p.code" class="chip" :class="{ on: localPointCodes.includes(p.code) }">
              <input type="checkbox" :checked="localPointCodes.includes(p.code)" @change="togglePoint(p.code)" />
              <span>{{ p.name }}</span>
            </label>
          </div>
        </section>
      </div>
    </article>
  </div>
</template>
<style scoped>
.krange{display:grid;gap:10px}
.unit{border:1px solid var(--border);border-radius:12px;background:var(--surface);transition:border-color .15s ease,background .15s ease}
.unit:hover{background:var(--surface-2)}
.unit.open{border-color:var(--border-strong);background:var(--surface);box-shadow:var(--shadow-1)}
.unit.whole{border-color:var(--brand);background:var(--brand-soft)}
.unit-head{display:flex;align-items:center;gap:10px;min-height:48px;padding:0 14px;cursor:pointer;user-select:none}
.chev{flex-shrink:0;color:var(--ink-3)}
.unit-head strong{font-size:14px;font-weight:600;color:var(--ink-1)}
.meta{color:var(--ink-3);font-size:13px}
.whole{margin-left:auto;display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid var(--border-strong);border-radius:var(--r-pill);font-size:12.5px;font-weight:500;color:var(--ink-2);cursor:pointer;transition:background .15s ease,color .15s ease,border-color .15s ease}
.whole:hover{color:var(--ink-1);border-color:var(--ink-4)}
.whole:has(input:checked){background:var(--brand-text);border-color:var(--brand-text);color:var(--surface)}
.unit-body{padding:4px 14px 14px;border-top:1px solid var(--border)}
.unit-body section{margin-top:10px}
.unit-body h4{margin:0 0 8px;font-size:13px;font-weight:600;color:var(--ink-2)}
.chips{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.chip{display:flex;align-items:center;gap:8px;min-height:38px;padding:7px 10px;border:1px solid var(--border);border-radius:10px;background:var(--surface);cursor:pointer;font-size:13.5px;color:var(--ink-1);transition:background .15s ease,border-color .15s ease}
.chip:hover{background:var(--surface-2)}
.chip.on{background:var(--accent-soft);border-color:var(--accent)}
.chip input{flex-shrink:0;accent-color:var(--accent)}
@media(max-width:600px){.chips{grid-template-columns:1fr}.unit-head{flex-wrap:wrap;padding:10px 12px}.whole{margin-left:0}}
</style>
