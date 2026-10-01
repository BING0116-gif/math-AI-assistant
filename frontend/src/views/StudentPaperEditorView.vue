<script setup>
import { onBeforeUnmount,onMounted,ref } from 'vue'
import { onBeforeRouteLeave,useRoute,useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { renderMarkdown } from '@/utils/markdown'
import { useStudentPaperStore } from '@/stores/studentPaperStore'
const route=useRoute(),router=useRouter(),store=useStudentPaperStore(),title=ref(''),dirty=ref(false),busy=ref('')
onMounted(async()=>{const data=await store.load(route.params.paperId);title.value=data.title})
onBeforeRouteLeave(()=>!dirty.value||globalThis.confirm('试卷名称尚未保存，确定离开吗？'))
onBeforeUnmount(()=>{})
async function saveTitle(){if(!title.value.trim())return;busy.value='title';await store.rename(title.value.trim());dirty.value=false;busy.value=''}
async function act(type,item){busy.value=item.item_id;try{if(type==='replace')await store.replace(item.item_id);else if(type==='remove')await store.remove(item.item_id);else await store.move(item.item_id,type)}finally{busy.value=''}}
async function finalize(){busy.value='finalize';try{await saveTitle();await store.finalize();router.push(`/apply/papers/${store.paper.paper_id}`)}finally{busy.value=''}}
</script>
<template><AppShell><template #topbar-title>编辑试卷</template><main class="page"><button class="back" @click="router.push('/apply/papers')">返回我的试卷</button><p v-if="store.error" class="error">{{store.error}}</p><template v-if="store.paper"><header><div><label>试卷名称<input v-model="title" maxlength="200" @input="dirty=true" @blur="saveTitle"></label><p>{{store.paper.question_count}}题 · {{store.paper.total_score}}分 · 预计{{store.paper.estimated_minutes}}分钟</p></div><button class="primary" :disabled="!!busy||!store.paper.questions.length" @click="finalize">保存并完成</button></header><ol class="questions"><li v-for="item in store.paper.questions" :key="item.item_id"><div class="position">{{item.position}}</div><div class="body"><div class="meta">{{item.question_type}} · 难度 {{item.difficulty}} · {{item.score}} 分 · {{(item.knowledge_point_codes||[]).join('、')}}</div><div v-html="renderMarkdown(item.content)"/></div><div class="actions"><button :disabled="!!busy||item.position===1" aria-label="上移" @click="act(-1,item)">↑</button><button :disabled="!!busy||item.position===store.paper.questions.length" aria-label="下移" @click="act(1,item)">↓</button><button :disabled="!!busy" @click="act('replace',item)">替换</button><button class="danger" :disabled="!!busy" @click="act('remove',item)">删除</button></div></li></ol></template><p v-else>正在加载试卷…</p></main></AppShell></template>
<style scoped>
.page { max-width: 1050px; margin: auto; padding: 32px 24px 72px; }
.back { border: 0; background: none; color: var(--accent-text); padding: 0; min-height: 0; font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; }
.back:hover { color: var(--accent); }
.page > header { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; margin: 20px 0; }
.page label { display: grid; gap: 7px; color: var(--ink-2); font-size: 13px; font-weight: 600; }
input { min-width: min(520px, 80vw); min-height: 44px; padding: 0 12px; border: 1px solid var(--border-strong); border-radius: var(--r-m); font: inherit; font-size: 20px; font-weight: 600; background: var(--surface); color: var(--ink-1); }
input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
header p, .meta { color: var(--ink-3); }
.questions { display: grid; gap: 14px; padding: 0; list-style: none; }
.questions li { display: grid; grid-template-columns: 42px 1fr auto; gap: 16px; padding: 20px; border: 1px solid var(--border); border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-1); }
.position { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; background: var(--accent-soft); color: var(--accent-text); font-weight: 700; font-variant-numeric: tabular-nums; }
.body { min-width: 0; }
.meta { font-size: 13px; }
.actions { display: flex; gap: 6px; align-items: flex-start; flex-wrap: wrap; }
button { min-height: 40px; padding: 0 12px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: background .15s ease, border-color .15s ease; }
button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent-text); }
button:disabled { opacity: .55; cursor: not-allowed; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.primary:hover:not(:disabled) { background: var(--accent-strong); border-color: var(--accent-strong); color: #fff; }
.danger { color: var(--rose); }
.danger:hover:not(:disabled) { border-color: var(--rose); color: var(--rose); }
.error { color: var(--rose); }
@media (max-width: 760px) { .page > header { align-items: flex-start; flex-direction: column; } .questions li { grid-template-columns: 36px 1fr; } .actions { grid-column: 2; } }
</style>
