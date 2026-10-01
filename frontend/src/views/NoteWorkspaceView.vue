<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { notesApi, unwrapNote } from '@/api/notes'
import { collectInkPoints, createStroke } from '@/features/handwriting/ink'
import { renderCanvas } from '@/features/handwriting/renderers/canvas2d'
import { RevisionSyncController, SyncStatus } from '@/features/handwriting/revisionSync'
import { loadNoteDraft } from '@/features/handwriting/noteDraftStorage'
import { useAuthStore } from '@/stores/authStore'

const route=useRoute(),router=useRouter(),auth=useAuthStore(),canvas=ref(null),fileInput=ref(null),title=ref(''),page=ref(null),pages=ref([]),strokes=ref([]),assets=ref([]),revision=ref(0),status=ref('loading'),error=ref(''),active=ref(null),conflict=ref(null),syncLog=ref([]),suggestions=ref([]),suggestionsLoading=ref(false),suggestionEdits=ref({})
let syncController
const statusText=computed(()=>({loading:'正在加载…',local:'已保存到本机，等待同步',syncing:'正在同步…',synced:'已同步',offline:'离线，已保存到本机，等待网络恢复',failed:'同步失败，可重试',conflict:'版本冲突，本地内容已保留',error:'笔记无法保存'}[status.value]||status.value))
function render(){if(canvas.value)renderCanvas(canvas.value,strokes.value,{x:0,y:0,scale:1})}
function snapshot(){return {strokes: JSON.parse(JSON.stringify(strokes.value))}}
function persistLocally(){
  if (!syncController) return
  return syncController.persist(snapshot()).catch((e)=>{ error.value=e.message||'本机草稿保存失败'; status.value='error' })
}
async function refreshConflict(){conflict.value=await syncController?.conflict();syncLog.value=(await loadNoteDraft({userId:auth.userId,noteId:route.params.noteId,pageId:page.value.page_id}))?.syncLog||[]}
async function loadSuggestions(){suggestionsLoading.value=true;try{suggestions.value=(await unwrapNote(await notesApi.aiSuggestions(route.params.noteId))).items||[]}catch(e){error.value=e.message||'AI 建议加载失败'}finally{suggestionsLoading.value=false}}
async function confirmSuggestion(item){try{const pointId=(suggestionEdits.value[item.link_id]||'').trim();await unwrapNote(await notesApi.confirmAiSuggestion(route.params.noteId,item.link_id,pointId?{knowledge_point_id:pointId}:{}));await loadSuggestions()}catch(e){error.value=e.message||'确认关联失败'}}
async function rejectSuggestion(item){try{await unwrapNote(await notesApi.rejectAiSuggestion(route.params.noteId,item.link_id));await loadSuggestions()}catch(e){error.value=e.message||'拒绝关联失败'}}
async function load(){status.value='loading';error.value='';conflict.value=null;try{const note=await unwrapNote(await notesApi.get(route.params.noteId));title.value=note.title;pages.value=(await unwrapNote(await notesApi.pages(note.note_id))).items;page.value=pages.value.find(item=>item.page_id===route.query.page)||note.page;const [current,assetData]=await Promise.all([unwrapNote(await notesApi.currentRevision(note.note_id,page.value.page_id)),unwrapNote(await notesApi.assets(note.note_id,page.value.page_id)),loadSuggestions()]);assets.value=assetData.items||[];syncController=new RevisionSyncController({scope:{userId:auth.userId,noteId:note.note_id,pageId:page.value.page_id},saveRevision:async(payload)=>unwrapNote(await notesApi.saveRevision(note.note_id,page.value.page_id,payload)),fetchCurrentRevision:async()=>unwrapNote(await notesApi.currentRevision(note.note_id,page.value.page_id)),onStatus:async(value)=>{status.value=value;if(value==='conflict')await refreshConflict()}});const restored=await syncController.restore(current.current_revision,current.stroke_payload);strokes.value=restored.payload.strokes||[];revision.value=restored.serverRevision;await refreshConflict();await nextTick();render()}catch(e){error.value=e.message||'笔记无法打开';status.value='error'}}
function openPage(target){if(target.page_id!==page.value?.page_id)router.replace({query:{page:target.page_id}}).then(load)}
async function addPage(){const created=await unwrapNote(await notesApi.createPage(route.params.noteId));pages.value.push(created);openPage(created)}
async function copyCurrent(){const copied=await unwrapNote(await notesApi.copyPage(route.params.noteId,page.value.page_id));pages.value.push(copied);openPage(copied)}
async function removeCurrent(){if(pages.value.length>1&&window.confirm('删除此页面？此操作无法撤销。')){await notesApi.removePage(route.params.noteId,page.value.page_id);pages.value=pages.value.filter(item=>item.page_id!==page.value.page_id);openPage(pages.value[0])}}
async function movePage(index, delta){const target=index+delta;if(target<0||target>=pages.value.length)return;const next=[...pages.value];[next[index],next[target]]=[next[target],next[index]];pages.value=(await unwrapNote(await notesApi.reorderPages(route.params.noteId,next.map(item=>item.page_id)))).items}
function point(event){const rect=canvas.value.getBoundingClientRect();return {x:event.clientX-rect.left,y:event.clientY-rect.top,pressure:event.pressure??.5,timestamp:event.timeStamp,tiltX:event.tiltX??0,tiltY:event.tiltY??0}}
function down(event){if(event.pointerType!=='pen')return;canvas.value.setPointerCapture?.(event.pointerId);active.value=createStroke(event,point(event));strokes.value=[...strokes.value,active.value]}
function move(event){if(!active.value)return;const rect=canvas.value.getBoundingClientRect();active.value.points.push(...collectInkPoints(event,rect));strokes.value=[...strokes.value];render();status.value='dirty'}
function up(){if(active.value){active.value=null;persistLocally()}}
async function save(){await persistLocally();syncController?.retry()}
async function rename(){try{await unwrapNote(await notesApi.update(route.params.noteId,{title:title.value}));}catch(e){error.value=e.message||'标题保存失败'}}
function retry(){syncController?.retry()}
async function keepServer(){const restored=await syncController?.keepServerVersion();if(restored){strokes.value=restored.payload.strokes||[];revision.value=restored.serverRevision;conflict.value=null;await refreshConflict();await nextTick();render()}}
async function copyLocalAsNewPage(){const branch=await syncController?.conflict();if(!branch)return;try{const copied=await unwrapNote(await notesApi.createPage(route.params.noteId));await unwrapNote(await notesApi.saveRevision(route.params.noteId,copied.page_id,{base_revision:0,idempotency_key:crypto.randomUUID(),stroke_payload:branch.localPayload}));pages.value.push({...copied,current_revision:1});await keepServer();await openPage(copied)}catch(e){error.value=e.message||'复制本地版本失败；本地冲突分支仍已保留'}}
async function uploadImage(event){const file=event.target.files?.[0];if(!file||!page.value)return;try{const asset=await unwrapNote(await notesApi.uploadAsset(route.params.noteId,page.value.page_id,file));assets.value=[...assets.value,asset]}catch(e){error.value=e.message||'图片上传失败'}finally{event.target.value=''}}
function returnToOrigin(){
  if (route.query.from === 'knowledge' && route.query.point) return router.push({ path: '/knowledge', query: { point: route.query.point } })
  if (route.query.from === 'learning' && route.query.point) return router.push(`/knowledge/points/${route.query.point}/learn`)
  return router.push('/notes')
}
function persistBeforeExit(){persistLocally()}
function onVisibilityChange(){if(document.visibilityState==='hidden')persistBeforeExit()}
watch(strokes,()=>nextTick(render),{deep:true});onMounted(async()=>{await load();window.addEventListener('online',retry);document.addEventListener('visibilitychange',onVisibilityChange);window.addEventListener('beforeunload',persistBeforeExit)});onBeforeUnmount(()=>{persistBeforeExit();syncController?.dispose();window.removeEventListener('online',retry);document.removeEventListener('visibilitychange',onVisibilityChange);window.removeEventListener('beforeunload',persistBeforeExit)})
</script>
<template><AppShell><template #topbar-title>手写笔记</template><main class="workspace"><header><button @click="returnToOrigin">{{ route.query.from ? '返回学习内容' : '返回笔记' }}</button><input v-model="title" maxlength="200" aria-label="笔记标题" @change="rename"><span :class="status" role="status">{{ statusText }}</span><input ref="fileInput" class="sr-only" type="file" accept="image/png,image/jpeg,image/gif,image/webp" @change="uploadImage"><button @click="fileInput?.click()">插入图片</button><button v-if="status==='failed'||status==='offline'" @click="retry">重试同步</button><button class="primary" :disabled="status==='loading'||status==='syncing'||status==='conflict'" @click="save">立即同步</button></header><section v-if="conflict" class="conflict-panel" role="alert"><strong>发现版本冲突</strong><p>此页已在另一台设备或窗口更新。服务器版本 {{ conflict.serverRevision }} 与本机未同步笔迹都已保留。选择保留服务器版本，或将本机版本复制为新页面。</p><button @click="keepServer">保留服务器版本</button><button class="primary" @click="copyLocalAsNewPage">复制本地版本为新页面</button></section><p v-if="error" class="error">{{error}}</p><details v-if="syncLog.length" class="sync-log"><summary>同步记录（最近 {{ syncLog.length }} 条）</summary><ol><li v-for="entry in syncLog" :key="`${entry.at}-${entry.event}`">{{ new Date(entry.at).toLocaleString() }}：{{ entry.event }}</li></ol></details><div class="layout"><aside class="pages" aria-label="页面管理"><button @click="addPage">新增页面</button><button :disabled="!page" @click="copyCurrent">复制页面</button><button :disabled="pages.length<=1" @click="removeCurrent">删除页面</button><article v-for="(item,index) in pages" :key="item.page_id" class="thumb" :class="{active:item.page_id===page?.page_id}"><button class="preview" @click="openPage(item)"><span>第 {{item.page_number}} 页</span><small>笔迹版本 {{item.current_revision}}</small></button><div><button :disabled="!index" :aria-label="`上移第 ${item.page_number} 页`" @click="movePage(index,-1)">↑</button><button :disabled="index===pages.length-1" :aria-label="`下移第 ${item.page_number} 页`" @click="movePage(index,1)">↓</button></div></article></aside><section class="canvas-wrap"><canvas ref="canvas" aria-label="单页手写画布，仅支持触控笔书写" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up"/><img v-for="asset in assets" :key="asset.asset_id" :src="asset.url" :alt="asset.filename" @error="error='图片加载失败，笔迹未受影响'"/></section></div><section class="suggestions" aria-labelledby="suggestions-title"><div><h2 id="suggestions-title">待确认的 AI 归类</h2><button :disabled="suggestionsLoading" @click="loadSuggestions">刷新</button></div><p v-if="suggestionsLoading" role="status">正在加载建议…</p><p v-else-if="!suggestions.some(item=>item.status==='suggested')">暂无待确认建议。低置信度结果不会自动归类。</p><article v-for="item in suggestions.filter(item=>item.status==='suggested')" :key="item.link_id"><strong>{{ item.knowledge_point_name || item.knowledge_point_code }}</strong><span>置信度 {{ Math.round(item.confidence * 100) }}%</span><label :for="`suggestion-${item.link_id}`">改为其他知识点 ID（可选）</label><input :id="`suggestion-${item.link_id}`" v-model="suggestionEdits[item.link_id]" placeholder="保留当前建议"><button class="primary" @click="confirmSuggestion(item)">确认</button><button class="danger" @click="rejectSuggestion(item)">拒绝</button></article><details v-if="suggestions.some(item=>item.status==='confirmed')"><summary>已确认关联（可撤销）</summary><article v-for="item in suggestions.filter(item=>item.status==='confirmed')" :key="item.link_id"><strong>{{ item.knowledge_point_name || item.knowledge_point_code }}</strong><span>{{ item.source==='manual' ? '人工确认' : 'AI 自动关联' }}</span><button class="danger" @click="rejectSuggestion(item)">撤销</button></article></details></section></main></AppShell></template>
<style scoped>
.workspace { max-width: 1280px; margin: auto; padding: 24px; }
.workspace header { display: flex; align-items: center; gap: 10px; }
.workspace header input { flex: 1; min-width: 0; min-height: 42px; padding: 0 14px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 17px; font-weight: 600; }
.workspace header input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.workspace button { min-height: 42px; padding: 0 14px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: background .15s ease, border-color .15s ease; }
.workspace button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent-text); }
.workspace button:disabled { opacity: .55; cursor: not-allowed; }
.workspace button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.workspace .primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.workspace .primary:hover:not(:disabled) { background: var(--accent-strong); border-color: var(--accent-strong); color: #fff; }
.workspace .danger { color: var(--rose); }
.workspace .danger:hover:not(:disabled) { border-color: var(--rose); color: var(--rose); }
.status { flex: 0 0 auto; color: var(--ink-2); font-size: 13px; font-weight: 600; }
.synced { color: var(--green); }
.syncing { color: var(--teal); }
.local, .offline { color: var(--amber); }
.failed, .conflict { color: var(--rose); }
.conflict-panel { margin-top: 16px; padding: 18px 20px; border: 1px solid var(--rose); border-radius: var(--r-m); background: var(--rose-soft); }
.conflict-panel strong { color: var(--rose); }
.conflict-panel p { margin: 8px 0 12px; color: var(--ink-2); line-height: 1.6; }
.sync-log { margin-top: 12px; color: var(--ink-2); font-size: 13px; }
.sync-log summary { cursor: pointer; }
.sync-log ol { margin: 8px 0 0; padding-left: 20px; line-height: 1.8; }
.layout { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 16px; margin-top: 16px; }
.pages { display: grid; align-content: start; gap: 8px; }
.pages > button { width: 100%; }
.thumb { display: grid; gap: 6px; padding: 6px; border: 1px solid var(--border); border-radius: var(--r-m); background: var(--surface); }
.thumb.active { border-color: var(--accent); background: var(--accent-soft); }
.thumb > div { display: flex; gap: 6px; }
.thumb > div button { flex: 1; min-height: 30px; padding: 0; }
.preview { width: 100%; min-height: 96px; display: grid; align-content: center; gap: 2px; padding: 8px; border: 1px solid var(--border); border-radius: var(--r-s); text-align: left; font: inherit; cursor: pointer; color: var(--ink-1); /* 纸面固定浅色:笔迹墨色为深色(#172554),不随主题翻转 */ background: radial-gradient(#d8dee6 1px, transparent 1px) 0 0/12px 12px, #fff; }
.preview small { color: var(--ink-3); }
.canvas-wrap { height: calc(100vh - 180px); min-height: 500px; border: 1px solid var(--border); border-radius: var(--r-l); overflow: hidden; box-shadow: var(--shadow-1); touch-action: none; /* 纸面固定浅色,理由同 .preview */ background: radial-gradient(#d8dee6 1px, transparent 1px) 0 0/20px 20px, #fff; }
.canvas-wrap canvas { height: 100%; width: 100%; display: block; touch-action: none; }
.canvas-wrap img { max-width: 40%; border: 1px solid var(--border); border-radius: var(--r-s); }
.suggestions { margin-top: 24px; border-top: 1px solid var(--border); padding-top: 16px; }
.suggestions > div { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.suggestions h2 { margin: 0; font-family: var(--font-disp); font-size: 20px; letter-spacing: -.02em; }
.suggestions article { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 10px; padding: 14px; border: 1px solid var(--border); border-radius: var(--r-m); background: var(--surface); }
.suggestions article > span { color: var(--ink-3); font-size: 13px; }
.suggestions label { flex-basis: 100%; color: var(--ink-2); font-size: 13px; }
.suggestions input { flex: 1 1 240px; min-height: 38px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; }
.suggestions input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.suggestions p { color: var(--ink-2); }
.error { margin: 12px 0; color: var(--rose); }
@media (max-width: 700px) { .workspace { padding: 12px; } .workspace header { flex-wrap: wrap; } .workspace header input { order: 3; flex-basis: 100%; } .layout { grid-template-columns: 1fr; } .pages { grid-template-columns: repeat(3, minmax(0, 1fr)); } .canvas-wrap { height: 65vh; min-height: 360px; } .suggestions article > * { flex-basis: 100%; } }
</style>
