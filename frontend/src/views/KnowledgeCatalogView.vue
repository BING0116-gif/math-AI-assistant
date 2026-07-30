<template>
  <LayoutDefault>
    <template #header>
      <div class="catalog-header">
        <div>
          <p class="eyebrow">学习目录</p>
          <h1>课程知识目录</h1>
        </div>
        <span v-if="tree" class="version-badge">{{ tree.version.name }} · v{{ tree.version.version }}</span>
      </div>
    </template>

    <main class="catalog" aria-busy="loading">
      <div v-if="loading" class="loading-state">正在加载课程目录…</div>
      <div v-else-if="error" class="error-state" role="alert">
        <p>{{ error }}</p><button @click="loadCatalog">重试</button>
      </div>
      <template v-else-if="tree">
        <section class="course-intro" aria-labelledby="course-title">
          <p class="course-subject">{{ tree.course.subject }}</p>
          <h2 id="course-title">{{ tree.course.name }}</h2>
          <p>{{ tree.course.description }}</p>
        </section>
        <section class="tree-panel" aria-label="课程章节与知识点">
          <el-tree
            :data="tree.chapters" node-key="id" default-expand-all :expand-on-click-node="false"
            :props="{ children: 'children', label: 'name' }" @node-click="handleNodeClick"
          >
            <template #default="{ data }">
              <div class="chapter-node"><span>{{ data.name }}</span><small v-if="data.knowledge_points?.length">{{ data.knowledge_points.length }} 个知识点</small></div>
              <button v-for="point in data.knowledge_points" :key="point.id" class="point-row" type="button" @click.stop="selectPoint(point.id)">
                <span>{{ point.name }}</span><small>难度 {{ point.difficulty }}/5</small>
              </button>
            </template>
          </el-tree>
        </section>
      </template>
    </main>

    <el-drawer v-model="detailOpen" direction="rtl" size="min(440px, 92vw)" :title="selectedPoint?.name || '知识点详情'">
      <div v-if="pointLoading" class="loading-state">正在加载详情…</div>
      <article v-else-if="selectedPoint" class="point-detail">
        <p>{{ selectedPoint.description }}</p>
        <dl><dt>难度</dt><dd>{{ selectedPoint.difficulty }} / 5</dd></dl>
        <h3>学习目标</h3>
        <ul><li v-for="objective in selectedPoint.learning_objectives" :key="objective">{{ objective }}</li></ul>
      </article>
    </el-drawer>
  </LayoutDefault>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import LayoutDefault from '@/components/layout/LayoutDefault.vue'
import { getCourseTree, getKnowledgePoint, listCourses } from '@/api/knowledge'

const tree = ref(null); const loading = ref(true); const error = ref('')
const detailOpen = ref(false); const selectedPoint = ref(null); const pointLoading = ref(false)

async function loadCatalog() {
  loading.value = true; error.value = ''
  try {
    const { data } = await listCourses()
    if (!data.courses?.length) throw new Error('暂时没有可学习的已发布课程。')
    tree.value = (await getCourseTree(data.courses[0].id)).data
  } catch (err) { error.value = err.response?.data?.detail || err.message || '课程目录加载失败，请稍后重试。' }
  finally { loading.value = false }
}
function handleNodeClick() { /* chapter nodes expand through Element Plus */ }
async function selectPoint(id) {
  detailOpen.value = true; pointLoading.value = true; selectedPoint.value = null
  try { selectedPoint.value = (await getKnowledgePoint(id)).data }
  finally { pointLoading.value = false }
}
onMounted(loadCatalog)
</script>

<style lang="scss" scoped>
.catalog { overflow: auto; padding: 32px; max-width: 980px; width: 100%; margin: 0 auto; }
.catalog-header { display:flex; align-items:center; justify-content:space-between; flex:1; gap:16px; }.catalog-header h1 { margin:0; font-size:20px; color:var(--text-primary); }.eyebrow,.course-subject { margin:0 0 4px; font-size:12px; font-weight:700; letter-spacing:.08em; color:var(--primary); }.version-badge { padding:7px 10px; border-radius:999px; background:var(--primary-ghost); color:var(--primary); font-size:12px; font-weight:600; }.course-intro,.tree-panel { background:var(--bg-card); border:1px solid var(--border-light); border-radius:16px; }.course-intro { padding:28px; margin-bottom:20px; }.course-intro h2 { margin:0 0 8px; color:var(--text-primary); }.course-intro p:last-child { margin:0; color:var(--text-secondary); line-height:1.65; }.tree-panel { padding:16px; }.chapter-node { display:flex; align-items:center; gap:12px; min-height:36px; font-weight:650; color:var(--text-primary); }.chapter-node small,.point-row small { color:var(--text-tertiary); font-weight:500; }.point-row { width:100%; min-height:44px; border:0; border-top:1px solid var(--border-light); background:transparent; padding:10px 8px; display:flex; justify-content:space-between; gap:12px; text-align:left; color:var(--text-secondary); font:inherit; cursor:pointer; }.point-row:hover { color:var(--primary); background:var(--primary-ghost); }.point-row:focus-visible,button:focus-visible { outline:3px solid var(--primary); outline-offset:2px; }.loading-state,.error-state { padding:48px 20px; text-align:center; color:var(--text-secondary); }.error-state button { min-height:44px; padding:0 18px; border:0; border-radius:8px; background:var(--primary); color:#fff; cursor:pointer; }.point-detail { color:var(--text-secondary); line-height:1.65; }.point-detail dl { display:flex; gap:12px; padding:12px 0; border-block:1px solid var(--border-light); }.point-detail dt { color:var(--text-primary); font-weight:700; }.point-detail dd { margin:0; }.point-detail h3 { color:var(--text-primary); margin-top:24px; } @media (max-width:768px) { .catalog { padding:20px 16px; }.catalog-header { align-items:flex-start; }.version-badge { white-space:nowrap; } } @media (prefers-reduced-motion:reduce) { * { transition:none !important; } }
</style>
