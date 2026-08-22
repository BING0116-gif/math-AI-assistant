import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { assessmentApi, unwrapAssessment } from '@/api/assessment'

const key = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
const errorMessage = (e) => e?.response?.data?.detail?.message || e?.message || '操作失败，请重试'

export const useAssessmentStore = defineStore('assessment', () => {
  const readiness = ref(null), session = ref(null), result = ref(null)
  const loading = ref(false), error = ref(''), saveState = ref('saved'), currentIndex = ref(0)
  const answers = ref({}), versions = ref({})
  const config = ref({ goal: 'weakness_check', duration_minutes: 30, intensity: 'standard', question_count: 10, scope: { chapter_ids: [] } })
  const currentQuestion = computed(() => session.value?.questions?.[currentIndex.value] || null)
  async function loadReadiness(courseId) { loading.value=true;error.value='';try{readiness.value=unwrapAssessment(await assessmentApi.readiness(courseId));return readiness.value}catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  async function create() { loading.value=true;error.value='';try{session.value=unwrapAssessment(await assessmentApi.create({...config.value,course_id:readiness.value.course_id,version_id:readiness.value.version_id,idempotency_key:key()}));return session.value}catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  function hydrate(data) { session.value=data;answers.value={};versions.value={};for(const q of data.questions||[]){answers.value[q.question_id]=q.draft_answer;versions.value[q.question_id]=q.draft_version||0} }
  async function load(id) { loading.value=true;try{hydrate(unwrapAssessment(await assessmentApi.get(id)));return session.value}catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  async function start() { hydrate(unwrapAssessment(await assessmentApi.start(session.value.session_id))) }
  async function save(questionId) { saveState.value='saving';try{const saved=unwrapAssessment(await assessmentApi.saveDraft(session.value.session_id,questionId,{answer:answers.value[questionId],expected_version:versions.value[questionId]||0}));versions.value[questionId]=saved.version;saveState.value='saved'}catch(e){saveState.value='error';error.value=errorMessage(e);throw e} }
  async function submit() { loading.value=true;try{result.value=unwrapAssessment(await assessmentApi.submit(session.value.session_id,key()));return result.value}catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  async function loadResult(id) { loading.value=true;try{result.value=unwrapAssessment(await assessmentApi.result(id));return result.value}catch(e){error.value=errorMessage(e);throw e}finally{loading.value=false} }
  return { readiness,session,result,loading,error,saveState,currentIndex,answers,versions,config,currentQuestion,loadReadiness,create,load,start,save,submit,loadResult }
})
