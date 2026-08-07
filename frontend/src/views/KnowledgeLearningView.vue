<template>
  <AppShell><template #header><div class="learning-header"><button type="button" @click="router.push('/knowledge')">返回图谱</button><div><p>知识点学习空间</p><h1>{{ content?.name || '加载中…' }}</h1></div><button class="practice" type="button" :disabled="!content" @click="startPractice">开始巩固练习</button></div></template>
    <main class="learning"><div v-if="loading" class="state">正在加载学习内容…</div><div v-else-if="error" class="state">{{ error }} <button @click="load">重试</button></div><template v-else-if="content"><section class="hero"><span>难度 {{ content.difficulty }} / 5</span><h2>{{ content.description }}</h2><p>按“概念 → 公式 → 例题 → 练习”的顺序完成本知识点学习。</p></section><el-tabs v-model="activeTab" class="resource-tabs"><el-tab-pane v-for="tab in tabs" :key="tab.type" :label="tab.label" :name="tab.type"><article v-for="resource in resourcesByType(tab.type)" :key="resource.id" class="resource-card"><h3>{{ resource.title }}</h3><p>{{ resource.body }}</p><button v-if="resource.type === 'exercise'" type="button" @click="startPractice">进入练习</button></article><div v-if="!resourcesByType(tab.type).length" class="empty">该类学习资源正在建设中。</div></el-tab-pane></el-tabs></template></main>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '@/components/layout/AppShell.vue'
import { getKnowledgePointLearning } from '@/api/knowledge'
const route = useRoute(); const router = useRouter(); const content = ref(null); const loading = ref(true); const error = ref(''); const activeTab = ref('concept')
const tabs = [{ type: 'concept', label: '概念' }, { type: 'formula', label: '公式' }, { type: 'exam_focus', label: '考点' }, { type: 'example', label: '例题' }, { type: 'exercise', label: '练习' }]
function resourcesByType(type) { return content.value?.resources?.filter(resource => resource.type === type) || [] }
async function load() { loading.value = true; error.value = ''; try { content.value = (await getKnowledgePointLearning(route.params.pointId)).data } catch (err) { error.value = err.response?.data?.detail || '学习内容加载失败。' } finally { loading.value = false } }
function startPractice() { sessionStorage.setItem('practice_knowledge_point', JSON.stringify({ code: content.value.code, name: content.value.name, prompt: `请为我生成「${content.value.name}」的针对性练习：先出 3 道由易到难的题目，不要立即给答案；每题覆盖核心概念或公式，并在我作答后逐题讲解。` })); router.push('/chat') }
onMounted(load)
</script>

<style scoped lang="scss">
.learning { max-width:980px; width:100%; margin:0 auto; padding:28px; overflow:auto; }.learning-header { display:flex; align-items:center; gap:16px; flex:1; }.learning-header p,.learning-header h1 { margin:0; }.learning-header p { color:var(--primary); font-size:12px; font-weight:700; }.learning-header h1 { color:var(--text-primary); font-size:19px; }.learning-header>button { min-height:40px; border:1px solid var(--border-light); border-radius:9px; background:var(--bg-card); color:var(--text-secondary); padding:0 12px; cursor:pointer; }.learning-header .practice { margin-left:auto; border:0; color:#fff; background:var(--primary); font-weight:700; }.hero { padding:30px; border-radius:20px; color:#e0e7ff; background:radial-gradient(circle at top right,rgba(129,140,248,.55),transparent 42%),#172554; }.hero span { font-size:13px; }.hero h2 { margin:12px 0 8px; font-size:22px; }.hero p { margin:0; color:#c7d2fe; }.resource-tabs { margin-top:24px; }.resource-card { padding:22px; margin:12px 0; border:1px solid var(--border-light); border-radius:16px; background:var(--bg-card); }.resource-card h3 { margin:0 0 10px; color:var(--text-primary); }.resource-card p { margin:0; white-space:pre-line; line-height:1.7; color:var(--text-secondary); }.resource-card button { margin-top:16px; min-height:42px; border:0; border-radius:9px; padding:0 14px; background:var(--primary); color:#fff; font-weight:700; cursor:pointer; }.state,.empty { padding:60px 20px; text-align:center; color:var(--text-secondary); } @media(max-width:768px){.learning{padding:18px 14px}.learning-header{gap:9px}.learning-header h1{font-size:16px}.learning-header>button{padding:0 9px}.hero{padding:22px}}
</style>
