import { ref } from 'vue'
import { defineStore } from 'pinia'
import { studentPaperApi,unwrapStudentPaper } from '@/api/studentPapers'
const key=()=>globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random()}`
const message=(e)=>e?.response?.data?.detail?.message||e?.message||'操作失败，请重试'
export const useStudentPaperStore=defineStore('studentPapers',()=>{
  const items=ref([]),paper=ref(null),loading=ref(false),saving=ref(false),error=ref('')
  async function list(){loading.value=true;error.value='';try{const data=unwrapStudentPaper(await studentPaperApi.list());items.value=data.items||[];return items.value}catch(e){error.value=message(e);throw e}finally{loading.value=false}}
  async function load(id){loading.value=true;error.value='';try{paper.value=unwrapStudentPaper(await studentPaperApi.get(id));return paper.value}catch(e){error.value=message(e);throw e}finally{loading.value=false}}
  async function create(payload){saving.value=true;error.value='';try{paper.value=unwrapStudentPaper(await studentPaperApi.create(payload));return paper.value}catch(e){error.value=message(e);throw e}finally{saving.value=false}}
  async function rename(title){paper.value=unwrapStudentPaper(await studentPaperApi.update(paper.value.paper_id,{title,expected_revision:paper.value.revision}));return paper.value}
  async function replace(itemId){paper.value=unwrapStudentPaper(await studentPaperApi.replaceQuestion(paper.value.paper_id,itemId));return paper.value}
  async function remove(itemId){paper.value=unwrapStudentPaper(await studentPaperApi.removeQuestion(paper.value.paper_id,itemId));return paper.value}
  async function move(itemId,delta){const rows=[...paper.value.questions],from=rows.findIndex(x=>x.item_id===itemId),to=from+delta;if(from<0||to<0||to>=rows.length)return;[rows[from],rows[to]]=[rows[to],rows[from]];paper.value=unwrapStudentPaper(await studentPaperApi.reorder(paper.value.paper_id,{item_ids:rows.map(x=>x.item_id),expected_revision:paper.value.revision}));return paper.value}
  async function finalize(){paper.value=unwrapStudentPaper(await studentPaperApi.finalize(paper.value.paper_id,{expected_revision:paper.value.revision}));return paper.value}
  async function launch(mode,duration=45){return unwrapStudentPaper(await studentPaperApi.launch(paper.value.paper_id,{mode,behavior:'adaptive',duration_minutes:mode==='test'?duration:null,idempotency_key:key()}))}
  return{items,paper,loading,saving,error,list,load,create,rename,replace,remove,move,finalize,launch}
})
