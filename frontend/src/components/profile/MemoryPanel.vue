<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Download, Pencil, Trash2 } from 'lucide-vue-next'
import { confirmMemory, correctMemory, deleteMemory, exportMyMemories, listMyMemories } from '@/api/memory'

interface MemoryItem {
  id: number
  memory_type: string
  memory_kind: string
  category: string
  content: string
  status: string
  confidence: number
  memory_strength: number
  conflict_status: string
  superseded_by: number | null
  created_at: number
  last_confirmed_at: number | null
}

const KIND_LABELS: Record<string, string> = {
  preference: '偏好',
  fact: '事实',
  misconception: '曾犯的错',
  context: '上下文',
}

const KIND_CLASSES: Record<string, string> = {
  preference: 'kind-preference',
  fact: 'kind-fact',
  misconception: 'kind-misconception',
  context: 'kind-context',
}

const items = ref<MemoryItem[]>([])
const loading = ref(false)
const loadError = ref('')
const editingId = ref<number | null>(null)
const editDraft = ref('')
const busyId = ref<number | null>(null)

const visibleItems = computed(() => items.value.filter((item) => item.status === 'active' || item.status === 'archived'))

function formatDate(seconds?: number | null) {
  if (!seconds) return ''
  return new Date(seconds * 1000).toLocaleDateString()
}

function kindLabel(kind: string) {
  return KIND_LABELS[kind] || '上下文'
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    items.value = await listMyMemories({ include_deleted: false, page: 1, page_size: 50 })
  } catch (error: any) {
    loadError.value = error?.message || '记忆加载失败'
  } finally {
    loading.value = false
  }
}

async function onConfirm(item: MemoryItem) {
  busyId.value = item.id
  try {
    await confirmMemory(item.id)
    item.confidence = 0.9
    ElMessage.success('已确认，系统会更信任这条记忆')
  } catch (error: any) {
    ElMessage.error(error?.message || '确认失败')
  } finally {
    busyId.value = null
  }
}

function startEdit(item: MemoryItem) {
  editingId.value = item.id
  editDraft.value = item.content
}

async function onSaveEdit(item: MemoryItem) {
  if (!editDraft.value.trim()) return
  busyId.value = item.id
  try {
    await correctMemory(item.id, editDraft.value.trim())
    ElMessage.success('已记录你的纠正，旧记忆将被新记忆取代')
    editingId.value = null
    await load()
  } catch (error: any) {
    ElMessage.error(error?.message || '纠正失败')
  } finally {
    busyId.value = null
  }
}

async function onDelete(item: MemoryItem) {
  busyId.value = item.id
  try {
    await deleteMemory(item.id)
    ElMessage.success('已删除该记忆')
    await load()
  } catch (error: any) {
    ElMessage.error(error?.message || '删除失败')
  } finally {
    busyId.value = null
  }
}

async function onExport() {
  try {
    const data = await exportMyMemories()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `my-memories-${new Date().toISOString().slice(0, 10)}.json`
    anchor.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出我的记忆')
  } catch (error: any) {
    ElMessage.error(error?.message || '导出失败')
  }
}

onMounted(load)
</script>

<template>
  <section class="memory-panel" aria-labelledby="memory-panel-heading">
    <header class="memory-panel__head">
      <div>
        <h2 id="memory-panel-heading" class="memory-panel__title">我的记忆</h2>
        <p class="memory-panel__caption">系统对你的了解。你可以确认、纠正或删除任何一条。</p>
      </div>
      <button class="memory-panel__export" type="button" @click="onExport">
        <Download :size="14" /> 导出
      </button>
    </header>

    <p v-if="loadError" class="memory-panel__error">{{ loadError }}</p>
    <p v-else-if="loading" class="memory-panel__empty">加载中…</p>
    <p v-else-if="visibleItems.length === 0" class="memory-panel__empty">还没有记录。随着学习互动，系统会逐步形成对你的了解。</p>

    <ul v-else class="memory-panel__list">
      <li v-for="item in visibleItems" :key="item.id" class="memory-item" :class="{ 'memory-item--archived': item.status !== 'active' }">
        <div class="memory-item__meta">
          <span class="memory-item__kind" :class="KIND_CLASSES[item.memory_kind]">{{ kindLabel(item.memory_kind) }}</span>
          <span v-if="item.conflict_status === 'review'" class="memory-item__conflict">待复核</span>
          <span v-if="item.status === 'archived'" class="memory-item__conflict">已被取代</span>
          <span class="memory-item__date">{{ formatDate(item.created_at) }}</span>
        </div>

        <p v-if="editingId !== item.id" class="memory-item__content">{{ item.content }}</p>
        <div v-else class="memory-item__edit">
          <textarea v-model="editDraft" rows="3" aria-label="纠正后的记忆内容"></textarea>
          <div class="memory-item__edit-actions">
            <button type="button" class="memory-panel__action" :disabled="busyId === item.id" @click="onSaveEdit(item)">保存纠正</button>
            <button type="button" class="memory-panel__action memory-panel__action--ghost" @click="editingId = null">取消</button>
          </div>
        </div>

        <div class="memory-item__foot">
          <span class="memory-item__confidence" :title="`置信度 ${(item.confidence * 100).toFixed(0)}%`">
            <i class="memory-item__confidence-bar"><i :style="{ width: `${Math.round(item.confidence * 100)}%` }"></i></i>
            置信 {{ Math.round(item.confidence * 100) }}%
          </span>
          <div v-if="editingId !== item.id && item.status === 'active'" class="memory-item__actions">
            <button v-if="item.confidence < 0.9" type="button" class="memory-panel__action" :disabled="busyId === item.id" @click="onConfirm(item)">
              <Check :size="13" /> 确认
            </button>
            <button type="button" class="memory-panel__action" :disabled="busyId === item.id" @click="startEdit(item)">
              <Pencil :size="13" /> 纠正
            </button>
            <button type="button" class="memory-panel__action memory-panel__action--danger" :disabled="busyId === item.id" @click="onDelete(item)">
              <Trash2 :size="13" /> 删除
            </button>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.memory-panel {
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--surface);
  padding: var(--space-4);
  display: grid;
  gap: var(--space-3);
}
.memory-panel__head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-3); }
.memory-panel__title { margin: 0; font-size: 16px; font-weight: 700; color: var(--ink-1); }
.memory-panel__caption { margin: 4px 0 0; font-size: 12.5px; color: var(--ink-3); }
.memory-panel__export { display: inline-flex; align-items: center; gap: 4px; height: 28px; padding: 0 10px; border: 1px solid var(--border); border-radius: var(--r-s); background: transparent; color: var(--ink-2); font: inherit; font-size: 12.5px; cursor: pointer; }
.memory-panel__export:hover { color: var(--brand-text); border-color: var(--brand); }
.memory-panel__empty { margin: 0; font-size: 13px; color: var(--ink-3); }
.memory-panel__error { margin: 0; font-size: 13px; color: var(--rose); }
.memory-panel__list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
.memory-item { border: 1px solid var(--border); border-radius: var(--r-m); padding: var(--space-3); display: grid; gap: var(--space-2); background: var(--bg); }
.memory-item--archived { opacity: 0.62; }
.memory-item__meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.memory-item__kind { padding: 1px 8px; border-radius: 999px; font-size: 11.5px; font-weight: 600; }
.kind-fact { background: var(--brand-soft); color: var(--brand-text); }
.kind-preference { background: var(--amber-soft); color: var(--accent-text); }
.kind-misconception { background: var(--rose-soft); color: var(--rose); }
.kind-context { background: color-mix(in srgb, var(--ink-3) 12%, transparent); color: var(--ink-2); }
.memory-item__conflict { font-size: 11.5px; color: var(--amber); font-weight: 600; }
.memory-item__date { margin-left: auto; font-size: 11.5px; color: var(--ink-3); }
.memory-item__content { margin: 0; font-size: 13.5px; line-height: 1.6; color: var(--ink-1); white-space: pre-wrap; word-break: break-word; }
.memory-item__edit { display: grid; gap: 6px; }
.memory-item__edit textarea { width: 100%; border: 1px solid var(--border); border-radius: var(--r-s); padding: 8px; font: inherit; font-size: 13px; color: var(--ink-1); background: var(--surface); resize: vertical; }
.memory-item__edit textarea:focus { outline: 2px solid var(--brand); outline-offset: 1px; border-color: transparent; }
.memory-item__edit-actions { display: flex; gap: 8px; }
.memory-item__foot { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); flex-wrap: wrap; }
.memory-item__confidence { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--ink-3); }
.memory-item__confidence-bar { display: inline-block; width: 56px; height: 4px; border-radius: 999px; background: color-mix(in srgb, var(--ink-3) 20%, transparent); overflow: hidden; }
.memory-item__confidence-bar > i { display: block; height: 100%; border-radius: inherit; background: var(--brand); }
.memory-item__actions { display: flex; gap: 6px; }
.memory-panel__action { display: inline-flex; align-items: center; gap: 4px; height: 26px; padding: 0 9px; border: 1px solid var(--border); border-radius: var(--r-s); background: transparent; color: var(--ink-2); font: inherit; font-size: 12px; cursor: pointer; }
.memory-panel__action:hover:not(:disabled) { color: var(--brand-text); border-color: var(--brand); }
.memory-panel__action:disabled { opacity: 0.5; cursor: default; }
.memory-panel__action--ghost { border-color: transparent; }
.memory-panel__action--danger:hover:not(:disabled) { color: var(--rose); border-color: var(--rose); }

@media (max-width: 640px) {
  .memory-item__foot { flex-direction: column; align-items: flex-start; }
}
</style>
