<template>
  <AppShell>
    <template #page-header>
      <div class="learning-header">
        <button type="button" @click="backToMap"><ArrowLeft :size="15" :stroke-width="1.75" />返回图谱</button>
        <div><p>知识点学习空间</p><h1>{{ content?.name || '加载中…' }}</h1></div>
        <button class="practice" type="button" :disabled="!content" @click="startPractice">正式练习</button>
      </div>
    </template>
    <main ref="bodyEl" class="learning">
      <div v-if="loading" class="state" role="status">正在加载学习内容…</div>
      <div v-else-if="error" class="state" role="alert">{{ error }} <button type="button" @click="load">重试</button></div>
      <template v-else-if="content">
        <section class="hero">
          <div class="hero-main">
            <span>难度 {{ content.difficulty }} / 5 · {{ content.course?.name }}</span>
            <h2>{{ content.description }}</h2>
            <p>从概念、例题到练习都在这一页完成；页内练习使用真实题库并计入掌握度。</p>
          </div>
          <div class="hero-stat" role="status" aria-label="当前掌握度">
            <div class="mastery-ring" :class="`is-${statStatus}`" :style="{ '--pct': masteryPercent }"><span>{{ masteryPercent }}%</span></div>
            <p>{{ statLabel }}</p>
          </div>
        </section>
        <div class="lesson-layout">
          <nav class="lesson-outline card" aria-label="本页学习顺序">
            <strong>学习路径</strong><a href="#objectives">1. 学习目标</a><a href="#prerequisites">2. 前置检查</a>
            <a v-for="(resource, index) in orderedResources" :key="resource.id" :href="`#resource-${resource.id}`">{{ index + 3 }}. {{ resource.title }}</a>
            <a href="#section-examples">{{ resourceCount + 3 }}. 典型例题</a>
            <a href="#section-practice">{{ resourceCount + 4 }}. 边学边练</a>
            <a href="#section-errors">{{ resourceCount + 5 }}. 错题与变式</a>
          </nav>
          <div class="lesson-flow">
            <section id="objectives" class="foundation-card card">
              <span>01 · 学习目标</span><h2>学完后，你应该能够</h2>
              <ul v-if="content.learning_objectives?.length"><li v-for="objective in content.learning_objectives" :key="objective">{{ objective }}</li></ul>
              <p v-else>准确说明核心概念，并在适用条件下完成相关计算。</p>
            </section>
            <section id="prerequisites" class="foundation-card card">
              <span>02 · 前置检查</span><h2>{{ prerequisiteLabels.length ? '开始前，确认这些前置知识' : '可以直接开始' }}</h2>
              <ul v-if="prerequisiteLabels.length"><li v-for="pre in prerequisiteLabels" :key="pre.code">{{ pre.name }}</li></ul>
              <p v-else>本知识点没有必须先完成的前置知识。</p>
            </section>
            <LearningResourceCard v-for="resource in orderedResources" :id="`resource-${resource.id}`" :key="resource.id" :resource="resource" :common-error="commonError" @ask-ai="askAi" @practice="startPractice" />
            <section id="section-examples" class="hub-card card">
              <span>典型例题</span><h2>真题带解析，先看懂再动手</h2>
              <p v-if="!examples.length">该知识点暂无已发布例题，直接进入下方练习也可以。</p>
              <article v-for="ex in examples" :key="ex.question_id" class="example-item">
                <div class="meta">难度 {{ ex.difficulty }}/5 · {{ questionTypeLabel(ex.question_type) }}</div>
                <div class="math" v-html="renderMarkdown(ex.content)" />
                <ul v-if="ex.options?.length" class="example-options">
                  <li v-for="o in ex.options" :key="o.id"><strong>{{ o.id }}.</strong> <span v-html="renderMarkdown(o.text)" /></li>
                </ul>
                <button type="button" class="reveal" :aria-expanded="revealed[ex.question_id] ? 'true' : 'false'" @click="toggleReveal(revealed, ex.question_id)">{{ revealed[ex.question_id] ? '收起答案与解析' : '看答案与解析' }}</button>
                <div v-if="revealed[ex.question_id]" class="worked-answer" role="status">
                  <p><strong>答案：{{ ex.answer }}</strong></p>
                  <div class="math" v-html="renderMarkdown(ex.analysis)" />
                </div>
              </article>
            </section>
            <section id="section-practice" class="hub-card card">
              <span>边学边练</span><h2>用 5 道真题即时检验</h2>
              <p>从正式题库抽取本知识点的题目，作答即时判分并计入掌握度。</p>
              <p v-if="practiceStore.error" role="alert" class="error">{{ practiceStore.error }}</p>
              <template v-if="activeRun === 'practice'">
                <PracticeRunner embedded @finished="onRunFinished" />
              </template>
              <div v-else-if="practiceSummary" class="run-summary" role="status">
                <strong>本次练习 {{ practiceSummary.correct }}/{{ practiceSummary.total }} 正确</strong>
                <p>掌握度已更新为 {{ masteryPercent }}%{{ statDelta ? `（${statDelta}）` : '' }}。</p>
                <div class="summary-actions">
                  <button type="button" class="primary-cta" @click="startInlinePractice">再练一组</button>
                  <button type="button" class="ghost" @click="goFullReport">查看完整报告</button>
                </div>
              </div>
              <button v-else class="primary-cta" type="button" :disabled="runStarting" @click="startInlinePractice">{{ runStarting ? '正在抽题…' : '开始 5 题小练习' }}</button>
            </section>
            <section id="section-errors" class="hub-card card">
              <span>错题与变式</span>
              <h2>{{ kpErrors.length ? `本知识点有 ${kpErrors.length} 道未掌握错题` : '本知识点暂无未掌握错题' }}</h2>
              <p v-if="statErrorHint">{{ statErrorHint }}</p>
              <p v-if="variantError" role="alert" class="error">{{ variantError }}</p>
              <template v-if="activeRun === 'variant'">
                <PracticeRunner embedded @finished="onRunFinished" />
              </template>
              <template v-else>
                <ul class="error-list">
                  <li v-for="item in kpErrors" :key="item.id">
                    <div class="error-head">
                      <span class="badge" :class="`state-${item.review_state}`">{{ reviewStateLabel(item.review_state) }}</span>
                      <span class="wrong-count">累计错 {{ item.wrong_attempt_count }} 次</span>
                    </div>
                    <div class="math" v-html="renderMarkdown(item.question)" />
                    <p v-if="item.error_reason" class="error-reason">错因：{{ item.error_reason }}</p>
                    <div class="error-actions">
                      <button type="button" class="reveal" :aria-expanded="errorRevealed[item.id] ? 'true' : 'false'" @click="toggleReveal(errorRevealed, item.id)">{{ errorRevealed[item.id] ? '收起答案' : '看正确答案' }}</button>
                      <button v-if="item.question_id && item.variant_supported !== false" type="button" class="ghost" :disabled="variantStartingId === item.id" @click="startVariant(item)">{{ variantStartingId === item.id ? '生成中…' : '变式练习' }}</button>
                    </div>
                    <div v-if="errorRevealed[item.id]" class="worked-answer" role="status">
                      <p><strong>正确答案：{{ item.correct_answer }}</strong></p>
                      <p v-if="item.original_answer">我当时的答案：{{ item.original_answer }}</p>
                    </div>
                  </li>
                </ul>
                <p v-if="!kpErrors.length" class="muted">做错的题会自动出现在这里，并支持一键生成变式练习帮助迁移。</p>
              </template>
            </section>
            <section class="completion-card card">
              <div><span>完成学习内容</span><h2>掌握度已就绪</h2><p>页内练习与正式练习都会更新服务端学习投影；返回图谱可查看最新状态与下一步。</p></div>
              <button type="button" :disabled="!content" @click="startPractice">{{ '进入正式练习' }}</button>
            </section>
          </div>
        </div>
      </template>
    </main>
  </AppShell>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import AppShell from '@/components/shell/AppShell.vue'
import LearningResourceCard from '@/components/knowledge/LearningResourceCard.vue'
import PracticeRunner from '@/components/practice/PracticeRunner.vue'
import { useEntranceAnimation } from '@/composables/useEntranceAnimation'
import { getCourseLearningMap, getKnowledgePointExamples, getKnowledgePointLearning } from '@/api/knowledge'
import { unwrapPractice } from '@/api/practice'
import { createVariantSession } from '@/api/errorBook'
import { renderMarkdown } from '@/utils/markdown'
import { usePracticeStore } from '@/stores/practiceStore'
import { useErrorBookStore } from '@/stores/errorBookStore'

const route = useRoute(), router = useRouter(), content = ref(null), loading = ref(true), error = ref('')
const bodyEl = ref(null)
const playEntrance = useEntranceAnimation(()=>bodyEl.value??undefined,{autoplay:false})
const practiceStore = usePracticeStore()
const errorStore = useErrorBookStore()
const resourceOrder = ['lecture','intuition','concept','definition','formula','pitfalls','visual','animation','worked_example','example','common_error','exam_focus','checkpoint','exercise_set','exercise','summary','source_reference']
const orderedResources = computed(()=>[...(content.value?.resources||[])].sort((a,b)=>{const ai=resourceOrder.indexOf(a.type),bi=resourceOrder.indexOf(b.type);return(ai<0?99:ai)-(bi<0?99:bi)}))
const resourceCount = computed(()=>orderedResources.value.length)
const exerciseResource = computed(()=>orderedResources.value.find(resource=>['exercise','exercise_set'].includes(resource.type)))
const canPractice = computed(()=>Boolean(content.value))
const commonError = computed(()=>orderedResources.value.find(resource=>resource.type==='common_error')?.body||'')
// 前置检查优先显示后端解析的中文名；旧响应缺少映射时回退为 code。
const prerequisiteLabels = computed(()=>content.value?.prerequisite_points?.length?content.value.prerequisite_points:(content.value?.prerequisites||[]).map(code=>({code,name:code})))

// ── 一站式学习枢纽状态 ──
const examples = ref([])              // 典型例题（published 真题，含答案解析）
const pointStat = ref(null)           // learning-map 中的本点投影（掌握度/错误计数）
const statBefore = ref(null)          // 本轮练习前的掌握度，用于展示增量
const activeRun = ref('')             // '' | 'practice' | 'variant'（同一时间只有一个运行器）
const runStarting = ref(false)
const practiceSummary = ref(null)
const revealed = ref({})              // 例题答案展开状态
const errorRevealed = ref({})         // 错题答案展开状态
const variantStartingId = ref('')
const variantError = ref('')

const statStatus = computed(() => pointStat.value?.status || 'untouched')
const masteryPercent = computed(() => Math.round((pointStat.value?.mastery || 0) * 100))
const statLabel = computed(() => ({untouched:'未开始', weak:'薄弱，从基础题开始', learning:'学习中，保持节奏', mastered:'已掌握，可以迁移'}[statStatus.value] || '未开始'))
const statDelta = computed(() => {
  if (statBefore.value === null || !pointStat.value) return ''
  const delta = Math.round((pointStat.value.mastery - statBefore.value) * 100)
  return delta === 0 ? '持平' : `${delta > 0 ? '+' : ''}${delta}%`
})
const statErrorHint = computed(() => {
  const stat = pointStat.value
  if (!stat) return ''
  if (stat.due_error_count > 0) return `有 ${stat.due_error_count} 道错题已到复习时间，优先复盘它们。`
  if (stat.open_error_count > 0) return `${stat.open_error_count} 道错题待巩固，可通过变式练习完成迁移。`
  return ''
})
const kpErrors = computed(() => {
  const code = content.value?.code
  if (!code) return []
  return errorStore.errors.filter(item => !item.is_mastered && (item.knowledge_point_codes || []).includes(code))
})

const QUESTION_TYPE_LABELS = { choice:'单选题', multi_choice:'多选题', judge:'判断题', numeric_fill:'数值填空', expression_fill:'表达式填空' }
const questionTypeLabel = (type) => QUESTION_TYPE_LABELS[type] || type
const REVIEW_STATE_LABELS = { new:'新错题', understanding:'已理解', consolidating:'巩固中', mastered:'已掌握' }
const reviewStateLabel = (state) => REVIEW_STATE_LABELS[state] || state || '待复盘'

function toggleReveal(map, id) { map.value[id] = !map.value[id] }
function scrollToSection(id) { document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }

async function refreshStat() {
  try {
    const { data } = await getCourseLearningMap(content.value.course.id)
    const entry = (data.points || []).find(point => point.code === content.value.code)
    pointStat.value = entry ? {
      mastery: entry.mastery,
      status: entry.status === 'unlearned' ? 'untouched' : entry.status,
      open_error_count: entry.open_error_count || 0,
      due_error_count: entry.due_error_count || 0,
    } : null
  } catch { pointStat.value = null }  // 未登录/无投影时展示未开始态，不影响内容学习
}

async function loadExamples() {
  try {
    const { data } = await getKnowledgePointExamples(content.value.id, 3)
    examples.value = data.examples || []
  } catch { examples.value = [] }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    content.value = (await getKnowledgePointLearning(route.params.pointId)).data
    await nextTick()
    if (content.value) {
      playEntrance()
      await Promise.all([refreshStat(), loadExamples(), errorStore.loadErrors().catch(() => {})])
      const step = String(route.query.step || '')
      if (step === 'practice') scrollToSection('section-practice')
      else if (step === 'variant' || step === 'review') scrollToSection('section-errors')
    }
  } catch (err) {
    error.value = err.response?.data?.detail || '学习内容加载失败。'
  } finally {
    loading.value = false
  }
}
function backToMap(){router.push({path:'/knowledge',query:{point:content.value?.id||route.params.pointId,refresh:Date.now()}})}
function startPractice(){if(canPractice.value)router.push({path:'/apply/practice',query:{knowledge_point:content.value.code,question_count:5,return_to:`/knowledge/points/${content.value.id}/learn`}})}
function askAi(resource){router.push({path:'/chat',query:{q:`请针对“${content.value.name}”的“${resource.title}”进行讲解。先诊断我卡住的步骤，再给提示，不要直接替我完成正式练习。`,course_id:content.value.course.id,version_id:content.value.version.id,knowledge_point:content.value.code,learning_resource:resource.id}})}

// ── 页内练习：真实练习会话 + 内嵌运行器 ──
async function startInlinePractice() {
  if (runStarting.value) return
  runStarting.value = true
  variantError.value = ''
  try {
    statBefore.value = pointStat.value?.mastery ?? null
    practiceStore.reset()
    await practiceStore.create({
      course_id: content.value.course.id,
      version_id: content.value.version.id,
      knowledge_point_codes: [content.value.code],
      question_count: 5,
      behavior: 'immediate',
      idempotency_key: `kp-learn:${content.value.code}:${Date.now()}`,
    })
    await practiceStore.start()
    practiceSummary.value = null
    activeRun.value = 'practice'
    await nextTick()
    scrollToSection('section-practice')
  } catch { /* store.error 已带可读信息，模板内展示 */ } finally { runStarting.value = false }
}

async function startVariant(item) {
  if (variantStartingId.value) return
  variantStartingId.value = item.id
  variantError.value = ''
  try {
    statBefore.value = pointStat.value?.mastery ?? null
    practiceStore.reset()
    const payload = unwrapPractice(await createVariantSession(item.id, { idempotency_key: `kp-variant:${item.id}:${Date.now()}` }))
    await practiceStore.loadSession(payload.session_id)
    if (practiceStore.session.status === 'created') await practiceStore.start()
    practiceSummary.value = null
    activeRun.value = 'variant'
    await nextTick()
    scrollToSection('section-errors')
  } catch (err) {
    variantError.value = err?.response?.data?.detail?.message || '变式练习生成失败，请稍后再试。'
  } finally { variantStartingId.value = '' }
}

async function onRunFinished() {
  const kind = activeRun.value
  const feedbackList = Object.values(practiceStore.feedback).filter(item => !item.feedback_deferred)
  if (kind === 'practice') {
    practiceSummary.value = {
      total: practiceStore.session?.questions?.length || 0,
      correct: feedbackList.filter(item => item.correct).length,
    }
  }
  activeRun.value = ''
  await refreshStat()
  await errorStore.loadErrors().catch(() => {})
  await nextTick()
  scrollToSection(kind === 'variant' ? 'section-errors' : 'section-practice')
}

function goFullReport() {
  if (practiceStore.session?.session_id) router.push(`/apply/practice/sessions/${practiceStore.session.session_id}/result`)
}

watch(()=>route.params.pointId,(next,previous)=>{if(next!==previous)load()})
onMounted(load)
</script>

<style scoped lang="scss">
.learning{width:100%;margin:0 auto;padding:28px clamp(16px,3vw,42px) 60px;overflow:auto}
.learning-header{display:flex;align-items:center;gap:16px;flex:1;min-width:0}
.learning-header p,.learning-header h1{margin:0}
.learning-header p{color:var(--brand-text);font-size:12px;font-weight:700;letter-spacing:.04em}
.learning-header h1{color:var(--ink-1);font-size:19px}
.learning-header>button,.completion-card button{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:44px;border:1px solid var(--border-strong);border-radius:10px;background:var(--surface);color:var(--ink-2);padding:0 14px;font:inherit;font-size:13.5px;font-weight:600;cursor:pointer;transition:color .15s,border-color .15s,background .15s}
.learning-header>button:hover{color:var(--brand-text);border-color:var(--brand);background:var(--brand-soft)}
.learning-header>button:focus-visible,.completion-card button:focus-visible,a:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
.learning-header .practice{margin-left:auto;border-color:var(--accent);color:#fff;background:var(--accent)}
.learning-header .practice:hover{background:var(--accent-strong);border-color:var(--accent-strong);box-shadow:var(--glow)}
.learning-header .practice:disabled,.completion-card button:disabled{cursor:not-allowed;opacity:.55}
.hero{max-width:1180px;margin:0 auto;padding:30px;border-radius:var(--r-xl);border:1px solid var(--border);background:radial-gradient(circle at top right,var(--brand-soft),transparent 42%),var(--surface);box-shadow:var(--shadow-2);display:flex;align-items:center;justify-content:space-between;gap:24px}
.hero-main{min-width:0}
.hero-stat{flex:none;text-align:center;padding:14px 18px;border-radius:var(--r-l);border:1px solid var(--border);background:var(--surface)}
.mastery-ring{--ring:var(--brand);width:84px;height:84px;margin:0 auto;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--ring) calc(var(--pct,0)*1%),var(--border) 0);position:relative}
.mastery-ring::before{content:'';position:absolute;inset:7px;border-radius:50%;background:var(--surface)}
.mastery-ring span{position:relative;font-size:17px;font-weight:700;color:var(--ink-1);font-variant-numeric:tabular-nums}
.mastery-ring.is-weak{--ring:var(--rose)}
.mastery-ring.is-learning{--ring:var(--brand)}
.mastery-ring.is-mastered{--ring:var(--green)}
.hero-stat p{margin:8px 0 0;color:var(--ink-2);font-size:12.5px;font-weight:600}
.hero span{font-size:13px;color:var(--brand-text);font-weight:600}
.hero h2{margin:12px 0 8px;font-size:clamp(21px,2vw,28px);line-height:1.35;letter-spacing:-.01em;color:var(--ink-1)}
.hero p{margin:0;color:var(--ink-2);line-height:1.65;font-size:14px}
.lesson-layout{display:grid;grid-template-columns:minmax(180px,230px) minmax(0,820px);justify-content:center;align-items:start;gap:28px;margin:28px auto 0;max-width:1180px}
.lesson-outline{position:sticky;top:18px;display:grid;max-height:calc(100vh - 40px);gap:3px;padding:16px;overflow:auto}
.lesson-outline strong{padding:6px 9px 10px;color:var(--ink-1)}
.lesson-outline a{min-height:40px;padding:9px;border-radius:8px;color:var(--ink-2);text-decoration:none;line-height:1.45;transition:background .15s,color .15s}
.lesson-outline a:hover{background:var(--brand-soft);color:var(--brand-text)}
.lesson-flow{display:grid;gap:18px;min-width:0}
.foundation-card{scroll-margin-top:20px;padding:24px}
.foundation-card span,.completion-card span{color:var(--brand-text);font-size:12px;font-weight:700;letter-spacing:.08em}
.foundation-card h2,.completion-card h2{margin:6px 0 12px;color:var(--ink-1);font-size:20px}
.foundation-card ul{margin:0;padding-left:22px;color:var(--ink-2);line-height:1.8}
.foundation-card p,.completion-card p{margin:0;color:var(--ink-2);line-height:1.7}
.completion-card{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:26px;background:var(--surface-2)}
.completion-card button{flex:none;border:0;background:var(--accent);color:#fff}
.completion-card button:hover{background:var(--accent-strong);border-color:var(--accent-strong);box-shadow:var(--glow)}
.state{padding:60px 20px;text-align:center;color:var(--ink-2)}
@media(max-width:900px){.lesson-layout{grid-template-columns:1fr}.lesson-outline{position:static;display:flex;max-width:100%;gap:6px;overflow:auto}.lesson-outline strong,.lesson-outline a{flex:none}.learning-header{gap:9px;flex-wrap:wrap}.learning-header h1{font-size:16px}.learning-header .practice{margin-left:0}}
@media(max-width:600px){.learning{padding:18px 12px 44px}.hero{padding:22px 18px}.lesson-layout{gap:16px;margin-top:16px}.lesson-outline{margin-inline:-2px}.foundation-card{padding:20px 16px}.completion-card{align-items:stretch;flex-direction:column;padding:20px 16px}.completion-card button{width:100%}}
@media (prefers-reduced-motion: reduce){*{transition:none!important;animation:none!important}}

/* ── 一站式学习枢纽新增区块 ── */
.hub-card{scroll-margin-top:20px;padding:24px}
.hub-card>span{color:var(--brand-text);font-size:12px;font-weight:700;letter-spacing:.08em}
.hub-card h2{margin:6px 0 12px;color:var(--ink-1);font-size:20px}
.hub-card>p{margin:0 0 6px;color:var(--ink-2);line-height:1.7}
.hub-card .error{color:var(--rose)}
.hub-card .muted{color:var(--ink-3)}
.example-item{margin-top:14px;padding:18px;border:1px solid var(--border);border-radius:12px;background:var(--surface-2)}
.example-item .meta{color:var(--ink-3);font-size:13px;margin-bottom:10px}
.example-item .math{color:var(--ink-1)}
.example-options{display:grid;gap:6px;margin:12px 0 0;padding:0;list-style:none;color:var(--ink-2)}
.example-options strong{color:var(--ink-1);margin-right:4px}
.reveal{display:inline-flex;align-items:center;min-height:38px;margin-top:12px;padding:0 14px;border:1px solid var(--border-strong);border-radius:10px;background:var(--surface);color:var(--ink-2);font:inherit;font-size:13.5px;font-weight:600;cursor:pointer;transition:color .15s,border-color .15s,background .15s}
.reveal:hover,.reveal[aria-expanded='true']{color:var(--brand-text);border-color:var(--brand);background:var(--brand-soft)}
.worked-answer{margin-top:12px;padding:14px;border-left:4px solid var(--brand);border-radius:8px;background:var(--brand-soft);color:var(--ink-2);line-height:1.75}
.worked-answer p{margin:0 0 8px}
.worked-answer strong{color:var(--ink-1)}
.primary-cta{display:inline-flex;align-items:center;justify-content:center;min-height:46px;margin-top:8px;padding:0 22px;border:1px solid var(--accent);border-radius:10px;background:var(--accent);color:#fff;font:inherit;font-size:14px;font-weight:600;cursor:pointer;box-shadow:var(--glow);transition:background .15s}
.primary-cta:hover:not(:disabled){background:var(--accent-strong);border-color:var(--accent-strong)}
.primary-cta:disabled{opacity:.6;cursor:not-allowed}
.ghost{display:inline-flex;align-items:center;justify-content:center;min-height:38px;margin-top:12px;padding:0 14px;border:1px solid var(--border-strong);border-radius:10px;background:var(--surface);color:var(--ink-2);font:inherit;font-size:13.5px;font-weight:600;cursor:pointer;transition:color .15s,border-color .15s,background .15s}
.ghost:hover{color:var(--brand-text);border-color:var(--brand);background:var(--brand-soft)}
.run-summary{margin-top:14px;padding:18px;border:1px solid var(--border);border-radius:12px;background:var(--accent-soft)}
.run-summary strong{color:var(--ink-1);font-size:16px}
.run-summary p{margin:6px 0 0;color:var(--ink-2)}
.summary-actions{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.summary-actions .primary-cta{margin-top:0}
.summary-actions .ghost{margin-top:0}
.error-list{display:grid;gap:14px;margin:14px 0 0;padding:0;list-style:none}
.error-list li{padding:16px;border:1px solid var(--border);border-radius:12px;background:var(--surface-2)}
.error-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}
.badge{display:inline-flex;align-items:center;min-height:24px;padding:0 10px;border-radius:var(--r-pill);font-size:12px;font-weight:600;background:var(--amber-soft);color:var(--amber)}
.badge.state-understanding{background:var(--brand-soft);color:var(--brand-text)}
.badge.state-consolidating{background:var(--accent-soft);color:var(--accent-text)}
.badge.state-mastered{background:var(--green-soft,var(--brand-soft));color:var(--green,var(--brand-text))}
.wrong-count{color:var(--ink-3);font-size:12.5px}
.error-reason{margin:10px 0 0;color:var(--rose);font-size:13.5px}
.error-actions{display:flex;gap:10px;flex-wrap:wrap}
@media(max-width:900px){.hero{flex-direction:column;align-items:flex-start}.hero-stat{display:flex;align-items:center;gap:14px;width:100%}.mastery-ring{margin:0}}
@media(max-width:600px){.hub-card{padding:18px 16px}.example-item{padding:14px}.hub-card h2{font-size:17px}.summary-actions .primary-cta,.summary-actions .ghost{flex:1}}
</style>
