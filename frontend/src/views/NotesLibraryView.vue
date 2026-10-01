<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { notesApi, unwrapNote } from '@/api/notes'

const route = useRoute(), router = useRouter(), items = ref([]), loading = ref(false), error = ref(''), statusFilter=ref(sessionStorage.getItem('notes-status')||'active'), courseId=ref(sessionStorage.getItem('notes-course')||''), knowledgePointId=ref(route.query.knowledge_point_id || sessionStorage.getItem('notes-kp')||''), offset=ref(Number(sessionStorage.getItem('notes-offset')||0)), total=ref(0), limit=20
const canNext=computed(()=>offset.value+limit<total.value)
async function load() { loading.value = true; error.value = ''; try { const data=await unwrapNote(await notesApi.list({limit,offset:offset.value,status:statusFilter.value,course_id:courseId.value||undefined,knowledge_point_id:knowledgePointId.value||undefined})); items.value=data.items;total.value=data.total } catch (e) { error.value = e.message || '笔记加载失败' } finally { loading.value = false } }
function move(delta){offset.value=Math.max(0,offset.value+delta*limit);load()}
async function create() { loading.value = true; try { const note = await unwrapNote(await notesApi.create({ title: '未命名笔记' })); router.push(`/notes/${note.note_id}`) } catch (e) { error.value = e.message || '新建笔记失败' } finally { loading.value = false } }
async function archive(note){try{await unwrapNote(await notesApi.archive(note.note_id));await load()}catch(e){error.value=e.message||'归档失败'}}
async function remove(note){if(!window.confirm('移至回收站？可在保留期内恢复。'))return;try{await notesApi.remove(note.note_id);await load()}catch(e){error.value=e.message||'删除失败'}}
async function restore(note){try{await unwrapNote(await notesApi.restore(note.note_id));await load()}catch(e){error.value=e.message||'恢复失败'}}
function applyFilters(){offset.value=0;load()}watch([statusFilter,courseId,knowledgePointId,offset],()=>{sessionStorage.setItem('notes-status',statusFilter.value);sessionStorage.setItem('notes-course',courseId.value);sessionStorage.setItem('notes-kp',knowledgePointId.value);sessionStorage.setItem('notes-offset',String(offset.value));sessionStorage.setItem('notes-scroll',String(document.querySelector('.shell-content')?.scrollTop||0))});onMounted(async()=>{await load();requestAnimationFrame(()=>{const container=document.querySelector('.shell-content');if(container)container.scrollTop=Number(sessionStorage.getItem('notes-scroll')||0)})})
</script>
<template><AppShell><template #topbar-title>智能笔记</template><main class="page"><header><div><h1>我的笔记</h1><p>最近编辑的手写笔记。</p></div><button class="primary" :disabled="loading" @click="create">新建笔记</button></header><div class="filters"><label>状态 <select v-model="statusFilter" @change="applyFilters"><option value="active">进行中</option><option value="archived">已归档</option><option value="deleted">回收站</option></select></label><label>课程 ID <input v-model.trim="courseId" @change="applyFilters"></label><label>知识点 ID <input v-model.trim="knowledgePointId" @change="applyFilters"></label></div><p v-if="error" class="error">{{ error }}</p><p v-if="loading">正在加载…</p><section v-else class="notes"><article v-for="note in items" :key="note.note_id" class="note"><button @click="router.push(`/notes/${note.note_id}`)"><strong>{{ note.title }}</strong><span>版本 {{ note.current_revision }} · {{ new Date(note.updated_at).toLocaleString() }}</span></button><div class="actions"><button v-if="statusFilter==='active'" @click="archive(note)">归档</button><button v-if="statusFilter==='active'" @click="remove(note)">移至回收站</button><button v-if="statusFilter!=='active'" class="primary" @click="restore(note)">恢复笔记</button></div></article><div v-if="!items.length" class="empty"><h2>{{statusFilter==='deleted'?'回收站为空':'还没有笔记'}}</h2><p>{{statusFilter==='deleted'?'删除的笔记会在保留期后永久清理。':'从一页手写笔记开始。'}}</p><button v-if="statusFilter==='active'" class="primary" @click="create">新建第一篇笔记</button></div></section><nav v-if="total>limit" class="pager"><button :disabled="!offset" @click="move(-1)">上一页</button><span>{{offset+1}}–{{Math.min(offset+limit,total)}} / {{total}}</span><button :disabled="!canNext" @click="move(1)">下一页</button></nav></main></AppShell></template>
<style scoped>
.page { max-width: 960px; margin: auto; padding: 36px 24px 72px; }
.page > header { display: flex; justify-content: space-between; align-items: center; gap: 20px; }
.page h1 { margin: 0; font-family: var(--font-disp); font-size: clamp(26px, 3vw, 34px); letter-spacing: -.03em; }
.page > header p { margin: 6px 0 0; color: var(--ink-2); }
button { min-height: 42px; padding: 0 14px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: background .15s ease, border-color .15s ease, box-shadow .15s ease; }
button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent-text); }
button:disabled { opacity: .55; cursor: not-allowed; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.primary:hover:not(:disabled) { background: var(--accent-strong); border-color: var(--accent-strong); color: #fff; }
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; margin-top: 18px; padding: 14px 16px; border: 1px solid var(--border); border-radius: var(--r-m); background: var(--surface); box-shadow: var(--shadow-1); }
.filters label { display: inline-flex; align-items: center; gap: 8px; color: var(--ink-2); font-size: 13px; font-weight: 600; }
.filters select, .filters input { min-height: 38px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; }
.filters select:focus-visible, .filters input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.notes { display: grid; gap: 12px; margin-top: 24px; }
.note { display: grid; gap: 8px; padding: 18px; border: 1px solid var(--border); border-radius: var(--r-m); background: var(--surface); box-shadow: var(--shadow-1); transition: box-shadow .15s ease, transform .15s ease; }
.note:hover { box-shadow: var(--shadow-2); transform: translateY(-1px); }
.note > button { min-height: 0; padding: 0; border: 0; background: none; display: grid; gap: 6px; text-align: left; font: inherit; cursor: pointer; }
.note > button:hover:not(:disabled) { border-color: transparent; color: var(--accent-text); }
.note strong { color: var(--ink-1); font-size: 16px; }
.note span { color: var(--ink-3); font-size: 13px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.actions button { min-height: 34px; padding: 0 12px; font-size: 13px; }
.empty { text-align: center; padding: 56px 32px; border: 1px dashed var(--border-strong); border-radius: var(--r-l); }
.empty h2 { margin: 0; font-family: var(--font-disp); letter-spacing: -.02em; }
.empty p { margin: 8px 0 18px; color: var(--ink-3); }
.pager { display: flex; align-items: center; justify-content: center; gap: 14px; margin-top: 22px; }
.pager span { color: var(--ink-2); font-size: 13.5px; font-variant-numeric: tabular-nums; }
.error { color: var(--rose) !important; }
@media (max-width: 600px) { .page { padding: 24px 16px 56px; } .page > header { align-items: flex-start; flex-direction: column; } }
@media (prefers-reduced-motion: reduce) { .note, .note:hover { transition: none; transform: none; } }
</style>
