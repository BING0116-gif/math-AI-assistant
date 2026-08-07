<template>
  <AppShell>
    <template #header>
      <div class="catalog-header"><div><p class="eyebrow">课程地图</p><h1>高等数学思维导图</h1></div><span v-if="tree" class="version-badge">{{ tree.version.name }}</span></div>
    </template>

    <main class="catalog" :aria-busy="loading">
      <div v-if="loading" class="loading-state">正在绘制课程地图…</div>
      <section v-else-if="error" class="error-state" role="alert">
        <h2>{{ requiresAuth ? '登录后即可查看课程地图' : '课程地图暂时无法加载' }}</h2><p>{{ error }}</p>
        <button v-if="requiresAuth" @click="authOpen = true">登录或注册</button><button v-else @click="loadCatalog">重试</button>
      </section>
      <template v-else-if="tree">
        <section class="map-toolbar" aria-label="课程地图说明"><span><i class="legend-dot root"></i>课程</span><span><i class="legend-dot branch"></i>章节分支</span><span><i class="legend-dot point"></i>知识点</span><p>点击任一分支或知识点，查看概念、公式、考点和练习入口。</p></section>
        <KnowledgeGalaxy :tree="tree" @select-point="selectPoint" @select-branch="selectBranch" />
      </template>
    </main>

    <el-drawer v-model="detailOpen" direction="rtl" size="min(500px, 94vw)" :title="detailTitle">
      <div v-if="pointLoading" class="loading-state">正在加载知识内容…</div>
      <article v-else-if="selectedPoint" class="point-detail">
        <p class="detail-description">{{ selectedPoint.description }}</p>
        <dl><dt>难度</dt><dd>{{ selectedPoint.difficulty }} / 5</dd></dl>
        <DetailSection title="核心概念" :items="selectedPoint.key_concepts" />
        <DetailSection title="常用公式" :items="selectedPoint.key_formulas" formula />
        <DetailSection title="常见考点" :items="selectedPoint.exam_focuses" />
        <DetailSection title="学习目标" :items="selectedPoint.learning_objectives" />
        <button class="practice-button" type="button" @click="openLearning(selectedPoint)">进入学习空间</button>
      </article>
      <article v-else-if="selectedBranch" class="branch-detail">
        <p>点击下方知识点卡片，查看对应概念、公式、考点与练习。</p>
        <button v-for="point in branchPoints" :key="point.id" class="branch-point" @click="selectPoint(point.id)">{{ point.name }} <span>查看详情</span></button>
      </article>
    </el-drawer>

    <el-dialog v-model="authOpen" width="min(420px, 92vw)" :close-on-click-modal="false" :title="authMode === 'login' ? '登录学习账号' : '创建学习账号'">
      <p class="auth-hint">{{ authMode === 'login' ? '登录后将自动打开课程地图。' : '注册完成后会自动登录并打开课程地图。' }}</p>
      <el-form label-position="top" @submit.prevent="submitAuth"><el-form-item label="用户名" required><el-input v-model.trim="authForm.username" autocomplete="username" minlength="3" maxlength="32" placeholder="3–32 个字母、数字或下划线" /></el-form-item><el-form-item label="密码" required><el-input v-model="authForm.password" type="password" show-password autocomplete="current-password" minlength="6" maxlength="64" placeholder="至少 6 位" /></el-form-item><p v-if="authError" class="auth-error" role="alert">{{ authError }}</p><el-button native-type="submit" type="primary" :loading="authSubmitting" class="auth-submit">{{ authMode === 'login' ? '登录并查看地图' : '注册并查看地图' }}</el-button></el-form>
      <template #footer><button class="mode-switch" type="button" @click="toggleAuthMode">{{ authMode === 'login' ? '没有账号？立即注册' : '已有账号？去登录' }}</button></template>
    </el-dialog>
  </AppShell>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppShell from '@/components/layout/AppShell.vue'
import KnowledgeGalaxy from '@/components/knowledge/KnowledgeGalaxy.vue'
import { getCourseTree, getKnowledgePoint, listCourses } from '@/api/knowledge'
import api from '@/api'

const DetailSection = defineComponent({ props: { title: String, items: Array, formula: Boolean }, setup: (props) => () => props.items?.length ? h('section', { class: 'detail-section' }, [h('h3', props.title), h('ul', { class: props.formula ? 'formula-list' : '' }, props.items.map(item => h('li', item)))]) : null })
const router = useRouter(); const tree = ref(null); const loading = ref(true); const error = ref(''); const requiresAuth = ref(false)
const detailOpen = ref(false); const selectedPoint = ref(null); const selectedBranch = ref(null); const pointLoading = ref(false)
const authOpen = ref(false); const authMode = ref('login'); const authSubmitting = ref(false); const authError = ref(''); const authForm = reactive({ username: '', password: '' })
const detailTitle = computed(() => selectedPoint.value?.name || selectedBranch.value?.name || '知识详情')
const branchPoints = computed(() => selectedBranch.value?.knowledge_points || selectedBranch.value?.children?.flatMap(section => section.knowledge_points || []) || [])

async function loadCatalog() { loading.value = true; error.value = ''; requiresAuth.value = false; try { const { data } = await listCourses(); if (!data.courses?.length) throw new Error('暂时没有可学习的已发布课程。'); tree.value = (await getCourseTree(data.courses[0].id)).data } catch (err) { requiresAuth.value = err.response?.status === 401; error.value = requiresAuth.value ? '课程地图只向已登录的学习用户开放。' : (err.response?.data?.detail || err.message || '课程地图加载失败，请稍后重试。') } finally { loading.value = false } }
function selectBranch(branch) { selectedPoint.value = null; selectedBranch.value = branch; detailOpen.value = true }
async function selectPoint(id) { detailOpen.value = true; selectedBranch.value = null; pointLoading.value = true; selectedPoint.value = null; try { selectedPoint.value = (await getKnowledgePoint(id)).data } catch { ElMessage.error('知识点详情加载失败，请重试。') } finally { pointLoading.value = false } }
function openLearning(point) { router.push(`/knowledge/points/${point.id}/learn`) }
function toggleAuthMode() { authMode.value = authMode.value === 'login' ? 'register' : 'login'; authError.value = '' }
async function submitAuth() { authError.value = ''; if (authForm.username.length < 3 || authForm.password.length < 6) { authError.value = '用户名至少 3 位，密码至少 6 位。'; return } authSubmitting.value = true; try { if (authMode.value === 'register') await api.post('/auth/register', authForm); const { data } = await api.post('/auth/login', authForm); localStorage.setItem('auth_token', data.data.access_token); localStorage.setItem('refresh_token', data.data.refresh_token); authOpen.value = false; ElMessage.success(authMode.value === 'login' ? '登录成功' : '注册并登录成功'); await loadCatalog() } catch (err) { authError.value = err.response?.data?.detail || '操作失败，请检查用户名和密码后重试。' } finally { authSubmitting.value = false } }
onMounted(loadCatalog)
</script>

<style lang="scss" scoped>
.catalog { overflow:auto; padding:24px 28px 36px; width:100%; }.catalog-header { display:flex; justify-content:space-between; align-items:center; flex:1; gap:16px; }.catalog-header h1 { margin:0; font-size:20px; color:var(--text-primary); }.eyebrow { margin:0 0 4px; font-size:12px; font-weight:700; letter-spacing:.08em; color:var(--primary); }.version-badge { padding:7px 10px; border-radius:999px; background:var(--primary-ghost); color:var(--primary); font-size:12px; font-weight:600; }.map-toolbar { max-width:1200px; margin:0 auto 16px; display:flex; flex-wrap:wrap; align-items:center; gap:16px; color:var(--text-secondary); font-size:13px; }.map-toolbar p { margin:0 0 0 auto; }.legend-dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; }.root { background:var(--primary); }.branch { background:#0ea5e9; }.point { background:#f59e0b; }.map-scroll { max-width:1200px; min-height:600px; margin:auto; overflow:auto; border:1px solid var(--border-light); border-radius:24px; background:radial-gradient(circle at center, var(--primary-ghost), transparent 48%), var(--bg-card); }.mind-map { min-width:980px; padding:56px 44px 60px; display:flex; flex-direction:column; align-items:center; }.course-root,.chapter-node,.section-node,.point-node { font:inherit; cursor:pointer; text-align:left; transition:transform .2s ease, box-shadow .2s ease, border-color .2s ease; }.course-root { width:260px; border:0; border-radius:20px; padding:20px; color:#fff; background:linear-gradient(135deg, var(--primary), var(--primary-hover)); box-shadow:0 14px 30px rgba(99,102,241,.25); text-align:center; }.course-root small,.course-root span { display:block; opacity:.84; font-size:13px; }.course-root strong { display:block; font-size:24px; margin:5px 0; }.chapter-branch { width:100%; display:flex; flex-direction:column; align-items:center; }.connector { width:2px; background:var(--border-default); }.root-connector { height:38px; }.chapter-node { border:2px solid #0ea5e9; background:var(--bg-card); color:var(--text-primary); border-radius:999px; padding:12px 26px; font-weight:750; }.sections-row { width:100%; display:flex; justify-content:space-around; gap:28px; position:relative; padding-top:38px; }.sections-row::before { content:''; position:absolute; top:18px; left:14%; right:14%; height:2px; background:var(--border-default); }.section-branch { position:relative; width:30%; min-width:230px; display:flex; flex-direction:column; align-items:center; }.section-connector { position:absolute; height:20px; top:-20px; }.section-node { width:100%; border:2px solid var(--primary); background:var(--primary-ghost); border-radius:16px; color:var(--text-primary); padding:14px 16px; }.section-node strong,.section-node span { display:block; }.section-node span { font-size:12px; margin-top:4px; color:var(--text-secondary); }.points-stack { width:100%; margin-top:22px; display:flex; flex-direction:column; gap:10px; }.point-node { width:100%; min-height:54px; padding:10px 12px; border:1px solid var(--border-light); border-radius:12px; background:var(--bg-card); color:var(--text-primary); display:flex; justify-content:space-between; align-items:center; gap:8px; }.point-node small { color:var(--text-tertiary); white-space:nowrap; }.course-root:hover,.chapter-node:hover,.section-node:hover,.point-node:hover { transform:translateY(-3px); box-shadow:var(--shadow-md); border-color:var(--primary); }.course-root:focus-visible,.chapter-node:focus-visible,.section-node:focus-visible,.point-node:focus-visible,button:focus-visible { outline:3px solid var(--primary); outline-offset:3px; }.loading-state,.error-state { padding:64px 20px; text-align:center; color:var(--text-secondary); }.error-state h2 { color:var(--text-primary); }.error-state button,.practice-button { min-height:44px; border:0; border-radius:10px; padding:0 18px; background:var(--primary); color:#fff; font:inherit; font-weight:700; cursor:pointer; }.point-detail,.branch-detail { color:var(--text-secondary); line-height:1.65; }.detail-description { font-size:16px; }.point-detail dl { display:flex; gap:12px; padding:12px 0; border-block:1px solid var(--border-light); }.point-detail dt,.detail-section h3 { color:var(--text-primary); font-weight:750; }.point-detail dd { margin:0; }.detail-section { border-bottom:1px solid var(--border-light); padding:16px 0; }.detail-section h3 { margin:0 0 8px; font-size:16px; }.detail-section ul { margin:0; padding-left:20px; }.formula-list li { font-family:ui-monospace,Consolas,monospace; }.practice-button { width:100%; margin-top:24px; background:linear-gradient(135deg, var(--primary), var(--primary-hover)); }.branch-point { width:100%; margin:8px 0; padding:14px; border:1px solid var(--border-light); border-radius:10px; background:var(--bg-card); color:var(--text-primary); text-align:left; cursor:pointer; }.branch-point span { float:right; color:var(--primary); }.auth-hint { margin:0 0 20px; color:var(--text-secondary); }.auth-error { color:var(--danger); }.auth-submit { width:100%; min-height:44px; }.mode-switch { border:0; background:transparent; color:var(--primary); cursor:pointer; font:inherit; font-weight:700; } @media (max-width:768px) { .catalog { padding:18px 12px; }.map-toolbar p { width:100%; margin:0; }.map-scroll { min-height:500px; }.mind-map { padding:40px 28px; }.sections-row { justify-content:flex-start; }.catalog-header h1 { font-size:18px; } } @media (prefers-reduced-motion:reduce) { * { transition:none !important; } }
</style>
