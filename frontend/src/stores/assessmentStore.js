import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { assessmentApi, previewBlueprintStream, unwrapAssessment } from '@/api/assessment'

const key = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
const errorMessage = (e) => e?.response?.data?.detail?.message || e?.message || '操作失败，请重试'
// §5.4 蓝图桶微调幅度限制（±2 题，方案 §5.4）
const BUCKET_ADJUST_LIMIT = 2

export const useAssessmentStore = defineStore('assessment', () => {
  const readiness = ref(null), session = ref(null), result = ref(null)
  const loading = ref(false), error = ref(''), saveState = ref('saved'), currentIndex = ref(0)
  const answers = ref({}), versions = ref({}), dirty = new Set()
  // §5.4 流式蓝图预览与微调状态
  const blueprint = ref({ streaming: false, meta: null, buckets: [], done: false, error: '' })
  let saveChain = Promise.resolve()
  const config = ref({ goal: 'weakness_check', duration_minutes: 30, intensity: 'standard', question_count: 10, current_chapter_id: null, scope: { chapter_ids: [] } })
  const currentQuestion = computed(() => session.value?.questions?.[currentIndex.value] || null)
  const answeredList = computed(() => (session.value?.questions || []).filter((item) => {
    const value = answers.value[item.question_id]
    return Array.isArray(value) ? value.length > 0 : value !== null && value !== undefined && value !== ''
  }))
  const answeredCount = computed(() => answeredList.value.length)
  async function loadReadiness(courseId) { loading.value=true;error.value='';try{readiness.value=unwrapAssessment(await assessmentApi.readiness(courseId));if(!config.value.current_chapter_id)config.value.current_chapter_id=readiness.value.inferred_current_chapter_id||readiness.value.chapters?.[0]?.id||null;return readiness.value}catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  async function previewBlueprint() {
    blueprint.value = { streaming: true, meta: null, buckets: [], done: false, error: '' }
    const payload = { ...config.value, course_id: readiness.value.course_id, version_id: readiness.value.version_id }
    try {
      await previewBlueprintStream(payload, {
        onEvent(event, data) {
          if (event === 'meta') blueprint.value.meta = data
          else if (event === 'bucket') blueprint.value.buckets.push({ ...data, original_count: data.count, adjust: 0 })
          else if (event === 'done') { blueprint.value.done = true; blueprint.value.meta = { ...(blueprint.value.meta || {}), total: data.total, planning_source: data.planning_source, quota_summary: data.quota_summary } }
          else if (event === 'error') blueprint.value.error = data.message || '蓝图规划失败'
        },
      })
      blueprint.value.streaming = false
      if (!blueprint.value.done && !blueprint.value.error) blueprint.value.error = '连接中断，请重试或使用快速模式'
      return blueprint.value
    } catch (e) {
      blueprint.value.streaming = false
      blueprint.value.error = errorMessage(e)
      throw e
    }
  }
  function adjustBucket(index, delta) {
    const bucket = blueprint.value.buckets[index]
    if (!bucket || blueprint.value.done !== true) return
    const nextAdjust = Math.min(BUCKET_ADJUST_LIMIT, Math.max(-BUCKET_ADJUST_LIMIT, bucket.adjust + delta))
    const nextCount = (bucket.original_count || 0) + nextAdjust
    if (nextCount < 1) return
    bucket.adjust = nextAdjust
    bucket.count = nextCount
  }
  function removeBucket(index) { blueprint.value.buckets.splice(index, 1) }
  function resetBlueprint() { blueprint.value = { streaming: false, meta: null, buckets: [], done: false, error: '' } }
  async function create() {
    loading.value=true;error.value=''
    try{
      const bucketTotal = blueprint.value.buckets.reduce((sum, bucket) => sum + (bucket.count || 0), 0)
      const extra = blueprint.value.done && blueprint.value.buckets.length
        ? { blueprint_buckets: blueprint.value.buckets.map((bucket) => ({ quota_kind: bucket.quota_kind, knowledge_point_code: bucket.knowledge_point_code, count: bucket.count, difficulty_min: bucket.difficulty_min, difficulty_max: bucket.difficulty_max, reason_code: bucket.reason_code, reason: bucket.reason })) }
        : {}
      if (extra.blueprint_buckets) config.value.question_count = Math.min(30, Math.max(5, bucketTotal))
      session.value=unwrapAssessment(await assessmentApi.create({...config.value,...extra,course_id:readiness.value.course_id,version_id:readiness.value.version_id,idempotency_key:key()}))
      return session.value
    }catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  function hydrate(data) { session.value=data;answers.value={};versions.value={};dirty.clear();for(const q of data.questions||[]){answers.value[q.question_id]=q.draft_answer;versions.value[q.question_id]=q.draft_version||0} }
  async function load(id) { loading.value=true;try{hydrate(unwrapAssessment(await assessmentApi.get(id)));return session.value}catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  async function start() { hydrate(unwrapAssessment(await assessmentApi.start(session.value.session_id))) }
  function markDirty(questionId) { dirty.add(questionId);saveState.value='unsaved' }
  function save(questionId) {
    markDirty(questionId)
    saveChain=saveChain.catch(()=>{}).then(async()=>{
      if(!dirty.has(questionId)||session.value?.status!=='in_progress')return
      saveState.value='saving'
      try{
        const answer=answers.value[questionId]
        const saved=unwrapAssessment(await assessmentApi.saveDraft(session.value.session_id,questionId,{answer,expected_version:versions.value[questionId]||0}))
        // 服务端超时兜底：会话已被 finalize 时停止保存，交由视图跳转结果页
        if(saved?.completed){session.value.status='completed';dirty.clear();saveState.value='saved';return}
        versions.value[questionId]=saved.version
        if(answers.value[questionId]===answer)dirty.delete(questionId)
        saveState.value=dirty.size?'unsaved':'saved'
        if(dirty.has(questionId))save(questionId)
      }catch(e){saveState.value='error';error.value=errorMessage(e);throw e}
    })
    return saveChain
  }
  async function flushAll(){for(const id of [...dirty])await save(id);await saveChain}
  async function submit() { loading.value=true;try{await flushAll();result.value=unwrapAssessment(await assessmentApi.submit(session.value.session_id,key()));session.value.status='completed';return result.value}catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  async function loadResult(id) { loading.value=true;try{result.value=unwrapAssessment(await assessmentApi.result(id));return result.value}catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  return { readiness,session,result,loading,error,saveState,currentIndex,answers,versions,config,currentQuestion,answeredCount,answeredList,blueprint,previewBlueprint,adjustBucket,removeBucket,resetBlueprint,loadReadiness,create,load,start,markDirty,save,flushAll,submit,loadResult }
})
