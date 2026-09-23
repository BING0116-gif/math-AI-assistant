<template>
  <AppShell>
    <template #page-header>
      <div class="learning-header">
        <button type="button" @click="backToMap">返回图谱</button>
        <div><p>知识点学习空间</p><h1>{{ content?.name || '加载中…' }}</h1></div>
        <button class="practice" type="button" :disabled="!canPractice" @click="startPractice">开始正式练习</button>
      </div>
    </template>
    <main class="learning">
      <div v-if="loading" class="state" role="status">正在加载学习内容…</div>
      <div v-else-if="error" class="state" role="alert">{{ error }} <button type="button" @click="load">重试</button></div>
      <template v-else-if="content">
        <section class="hero">
          <span>难度 {{ content.difficulty }} / 5 · {{ content.course?.name }}</span>
          <h2>{{ content.description }}</h2>
          <p>按教学顺序完成学习；自检不会改变掌握度，只有正式练习会产生作答证据。</p>
        </section>
        <div class="lesson-layout">
          <nav class="lesson-outline" aria-label="本页学习顺序">
            <strong>学习路径</strong><a href="#objectives">1. 学习目标</a><a href="#prerequisites">2. 前置检查</a>
            <a v-for="(resource, index) in orderedResources" :key="resource.id" :href="`#resource-${resource.id}`">{{ index + 3 }}. {{ resource.title }}</a>
          </nav>
          <div class="lesson-flow">
            <section id="objectives" class="foundation-card">
              <span>01 · 学习目标</span><h2>学完后，你应该能够</h2>
              <ul v-if="content.learning_objectives?.length"><li v-for="objective in content.learning_objectives" :key="objective">{{ objective }}</li></ul>
              <p v-else>准确说明核心概念，并在适用条件下完成相关计算。</p>
            </section>
            <section id="prerequisites" class="foundation-card">
              <span>02 · 前置检查</span><h2>{{ prerequisiteLabels.length ? '开始前，确认这些前置知识' : '可以直接开始' }}</h2>
              <ul v-if="prerequisiteLabels.length"><li v-for="pre in prerequisiteLabels" :key="pre.code">{{ pre.name }}</li></ul>
              <p v-else>本知识点没有必须先完成的前置知识。</p>
            </section>
            <LearningResourceCard v-for="resource in orderedResources" :id="`resource-${resource.id}`" :key="resource.id" :resource="resource" :common-error="commonError" @ask-ai="askAi" @practice="startPractice" />
            <section class="completion-card">
              <div><span>完成学习内容</span><h2>用正式练习检验掌握情况</h2><p>返回图谱后将重新读取服务端学习投影，展示最新状态与下一步。</p></div>
              <button type="button" :disabled="!canPractice" @click="startPractice">{{ canPractice ? '进入正式练习' : '暂无可用练习' }}</button>
            </section>
          </div>
        </div>
      </template>
    </main>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import LearningResourceCard from '@/components/knowledge/LearningResourceCard.vue'
import { getKnowledgePointLearning } from '@/api/knowledge'
const route=useRoute(), router=useRouter(), content=ref(null), loading=ref(true), error=ref('')
const resourceOrder=['intuition','concept','definition','formula','visual','animation','worked_example','example','common_error','exam_focus','checkpoint','exercise_set','exercise','summary','source_reference']
const orderedResources=computed(()=>[...(content.value?.resources||[])].sort((a,b)=>{const ai=resourceOrder.indexOf(a.type),bi=resourceOrder.indexOf(b.type);return(ai<0?99:ai)-(bi<0?99:bi)}))
const exerciseResource=computed(()=>orderedResources.value.find(resource=>['exercise','exercise_set'].includes(resource.type)))
const canPractice=computed(()=>Boolean(content.value&&exerciseResource.value))
const commonError=computed(()=>orderedResources.value.find(resource=>resource.type==='common_error')?.body||'')
// 前置检查优先显示后端解析的中文名；旧响应缺少映射时回退为 code。
const prerequisiteLabels=computed(()=>content.value?.prerequisite_points?.length?content.value.prerequisite_points:(content.value?.prerequisites||[]).map(code=>({code,name:code})))
async function load(){loading.value=true;error.value='';try{content.value=(await getKnowledgePointLearning(route.params.pointId)).data}catch(err){error.value=err.response?.data?.detail||'学习内容加载失败。'}finally{loading.value=false}}
function backToMap(){router.push({path:'/knowledge',query:{point:content.value?.id||route.params.pointId,refresh:Date.now()}})}
function startPractice(){if(canPractice.value)router.push({path:'/apply/practice',query:{knowledge_point:content.value.code,question_count:5,return_to:`/knowledge/points/${content.value.id}/learn`}})}
function askAi(resource){router.push({path:'/chat',query:{q:`请针对“${content.value.name}”的“${resource.title}”进行讲解。先诊断我卡住的步骤，再给提示，不要直接替我完成正式练习。`,course_id:content.value.course.id,version_id:content.value.version.id,knowledge_point:content.value.code,learning_resource:resource.id}})}
watch(()=>route.params.pointId,(next,previous)=>{if(next!==previous)load()})
onMounted(load)
</script>

<style scoped lang="scss">
.learning{width:100%;margin:0 auto;padding:28px clamp(16px,3vw,42px) 60px;overflow:auto}.learning-header{display:flex;align-items:center;gap:16px;flex:1;min-width:0}.learning-header p,.learning-header h1{margin:0}.learning-header p{color:var(--primary);font-size:12px;font-weight:700}.learning-header h1{color:var(--text-primary);font-size:19px}.learning-header>button,.completion-card button{min-height:44px;border:1px solid var(--border-light);border-radius:9px;background:var(--bg-card);color:var(--text-secondary);padding:0 14px;cursor:pointer}.learning-header>button:focus-visible,.completion-card button:focus-visible,a:focus-visible{outline:3px solid var(--primary);outline-offset:3px}.learning-header .practice{margin-left:auto;border:0;color:#fff;background:var(--primary);font-weight:700}.learning-header .practice:disabled,.completion-card button:disabled{cursor:not-allowed;opacity:.55}.hero{max-width:1180px;margin:0 auto;padding:30px;border-radius:20px;color:#e0e7ff;background:radial-gradient(circle at top right,rgba(129,140,248,.55),transparent 42%),#172554}.hero span{font-size:13px}.hero h2{margin:12px 0 8px;font-size:clamp(21px,2vw,28px)}.hero p{margin:0;color:#c7d2fe;line-height:1.65}.lesson-layout{display:grid;grid-template-columns:minmax(180px,230px) minmax(0,820px);justify-content:center;align-items:start;gap:28px;margin:28px auto 0;max-width:1180px}.lesson-outline{position:sticky;top:18px;display:grid;max-height:calc(100vh - 40px);gap:3px;padding:16px;overflow:auto;border:1px solid var(--border-light);border-radius:14px;background:var(--bg-card)}.lesson-outline strong{padding:6px 9px 10px;color:var(--text-primary)}.lesson-outline a{min-height:40px;padding:9px;border-radius:8px;color:var(--text-secondary);text-decoration:none;line-height:1.45}.lesson-outline a:hover{background:var(--bg-secondary);color:var(--primary)}.lesson-flow{display:grid;gap:18px;min-width:0}.foundation-card{scroll-margin-top:20px;padding:24px;border:1px solid var(--border-light);border-radius:18px;background:var(--bg-card)}.foundation-card span,.completion-card span{color:var(--primary);font-size:12px;font-weight:700;letter-spacing:.08em}.foundation-card h2,.completion-card h2{margin:6px 0 12px;color:var(--text-primary);font-size:20px}.foundation-card ul{margin:0;padding-left:22px;color:var(--text-secondary);line-height:1.8}.foundation-card p,.completion-card p{margin:0;color:var(--text-secondary);line-height:1.7}.completion-card{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:26px;border-radius:18px;background:var(--bg-secondary)}.completion-card button{flex:none;border:0;background:var(--primary);color:#fff;font-weight:700}.state{padding:60px 20px;text-align:center;color:var(--text-secondary)}
@media(max-width:900px){.lesson-layout{grid-template-columns:1fr}.lesson-outline{position:static;display:flex;max-width:100%;gap:6px;overflow:auto}.lesson-outline strong,.lesson-outline a{flex:none}.learning-header{gap:9px;flex-wrap:wrap}.learning-header h1{font-size:16px}.learning-header .practice{margin-left:0}}
@media(max-width:600px){.learning{padding:18px 12px 44px}.hero{padding:22px 18px}.lesson-layout{gap:16px;margin-top:16px}.lesson-outline{margin-inline:-2px}.foundation-card{padding:20px 16px}.completion-card{align-items:stretch;flex-direction:column;padding:20px 16px}.completion-card button{width:100%}}
</style>
