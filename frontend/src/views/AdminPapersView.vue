<script setup>
/**
 * 组卷工作台（admin，WS-C）：模板管理 → 预览（不落库）→ 生成试卷（快照固化）
 * → 试卷库（详情 / 教师版-学生版切换 / 打印）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminPaperApi, unwrapPaper } from '@/api/adminPaper'
import { renderMathBank } from '@/utils/mathBankRender'

const router = useRouter()
const activeTab = ref('compose')
const loading = ref(false)

// ── 模板 ──
const templates = ref([])
const templateId = ref('') // '' = 临时配置
const templateDialog = reactive({ visible: false, name: '', submitting: false })

// ── 组卷配置（临时配置模式） ──
const paperTitle = ref('')
const typeCounts = reactive({ choice: 5, judge: 2, numeric_fill: 2, expression_fill: 1 })
const scorePer = ref(10)
const useDifficulty = ref(false)
const difficultyCounts = reactive({ 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 })
const kpText = ref('')
const randomSeed = ref(0)

const totalQuestions = computed(() => Object.values(typeCounts).reduce((a, b) => a + Math.max(0, b), 0))
const totalScore = computed(() => (totalQuestions.value * (Number(scorePer.value) || 0)).toFixed(1))
const TYPE_LABELS = { choice: '单选', judge: '判断', numeric_fill: '数值填空', expression_fill: '表达式填空' }

function buildConfig() {
  const type_mix = {}
  for (const [kind, count] of Object.entries(typeCounts)) {
    if (count > 0) type_mix[kind] = count
  }
  if (!Object.keys(type_mix).length) throw new Error('至少配置一种题型的数量')
  const cfg = { type_mix, total: totalQuestions.value, score_per_question: Number(scorePer.value) || 10, random_seed: Number(randomSeed.value) || 0 }
  if (useDifficulty.value) {
    const difficulty = {}
    for (const [level, count] of Object.entries(difficultyCounts)) {
      if (count > 0) difficulty[level] = count
    }
    if (Object.keys(difficulty).length) cfg.difficulty = difficulty
  }
  const kpCodes = kpText.value.split(/[\n,，;；]/).map((s) => s.trim()).filter(Boolean)
  if (kpCodes.length) cfg.kp_codes = kpCodes
  return cfg
}

// ── 预览 ──
const preview = ref(null)
const previewing = ref(false)
async function runPreview() {
  try {
    previewing.value = true
    const payload = templateId.value ? { template_id: templateId.value } : { config: buildConfig() }
    preview.value = unwrapPaper(await adminPaperApi.preview(payload))
  } catch (e) { ElMessage.error(e.message || '预览失败') } finally { previewing.value = false }
}

// ── 生成 ──
const generating = ref(false)
async function runGenerate() {
  try {
    generating.value = true
    const payload = templateId.value
      ? { template_id: templateId.value, title: paperTitle.value || undefined }
      : { config: buildConfig(), title: paperTitle.value || undefined }
    const paper = unwrapPaper(await adminPaperApi.generate(payload))
    ElMessage.success(`试卷已生成：${paper.title}（${paper.questions.length} 题）`)
    paperTitle.value = ''
    await loadPapers()
    openDetail(paper.id)
  } catch (e) { ElMessage.error(e.message || '生成失败') } finally { generating.value = false }
}

// ── 模板 ──
async function loadTemplates() {
  try { templates.value = unwrapPaper(await adminPaperApi.listTemplates()) } catch { templates.value = [] }
}
async function saveTemplate() {
  if (!templateDialog.name.trim()) { ElMessage.warning('请输入模板名称'); return }
  try {
    templateDialog.submitting = true
    unwrapPaper(await adminPaperApi.createTemplate({ name: templateDialog.name.trim(), config: buildConfig() }))
    ElMessage.success('模板已保存，可在组卷时复用')
    templateDialog.visible = false
    templateDialog.name = ''
    await loadTemplates()
  } catch (e) { ElMessage.error(e.message || '保存模板失败') } finally { templateDialog.submitting = false }
}

// ── 试卷库 ──
const papers = ref([])
async function loadPapers() {
  try { papers.value = unwrapPaper(await adminPaperApi.listPapers()) } catch { papers.value = [] }
}

// ── 详情抽屉 ──
const detailVisible = ref(false)
const detail = ref(null)
const teacherMode = ref(true)
const detailLoading = ref(false)
async function openDetail(paperId) {
  try {
    detailLoading.value = true
    detail.value = unwrapPaper(await adminPaperApi.getPaper(paperId))
    detailVisible.value = true
  } catch (e) { ElMessage.error(e.message || '加载试卷失败') } finally { detailLoading.value = false }
}
function answerText(snapshot) {
  const spec = snapshot?.answer_spec || {}
  if (spec.kind === 'choice') return spec.correct
  if (spec.kind === 'judge') return spec.correct ? '对' : '错'
  if (spec.kind === 'numeric_fill') return spec.value
  if (spec.kind === 'expression_fill') return spec.canonical
  return '—'
}
function printPaper() { window.print() }

// ── 题目模板（§5.3 参数化变式题）──
const questionTemplates = ref([])
const qtScope = ref({ course_id: '', version_id: '' })
const qtDialog = reactive({
  visible: false, submitting: false,
  name: '', question_type: 'numeric_fill', difficulty: 2,
  paramsText: '{\n  "a": { "type": "int", "range": [1, 9] },\n  "b": { "type": "int", "range": [1, 9] }\n}',
  bodyText: '计算 ${{a}} \\times {{b}}$ 的值。',
  answerText: '{{a}}*{{b}}',
  optionsText: '[{"id":"A","text":"{{answer}}"},{"id":"B","text":"其他"}]',
  kpText: '',
})
const sampleState = reactive({ visible: false, loading: false, template: null, items: [] })

async function loadQuestionTemplates() {
  try { questionTemplates.value = unwrapPaper(await adminPaperApi.listQuestionTemplates()) } catch { questionTemplates.value = [] }
}
async function loadQtScope() {
  // 模板归属课程/版本：默认取当前练习课程（options 返回首个 active course）
  try {
    const resp = await import('@/api/practice').then((m) => m.practiceApi.options())
    const data = resp?.data?.data || resp?.data
    if (data?.course_id) qtScope.value = { course_id: data.course_id, version_id: data.version_id }
  } catch { /* 保持空，创建时提示 */ }
}
function openQtDialog() { qtDialog.visible = true }
async function submitQuestionTemplate() {
  try {
    qtDialog.submitting = true
    let paramsSchema
    try { paramsSchema = JSON.parse(qtDialog.paramsText) } catch { ElMessage.warning('参数定义不是合法 JSON'); return }
    let optionsTemplate
    if (qtDialog.question_type === 'choice') {
      try { optionsTemplate = JSON.parse(qtDialog.optionsText) } catch { ElMessage.warning('选项模板不是合法 JSON'); return }
    }
    const kpCodes = qtDialog.kpText.split(/[\n,，;；]/).map((s) => s.trim()).filter(Boolean)
    if (!kpCodes.length) { ElMessage.warning('请填写至少一个知识点代码'); return }
    if (!qtScope.value.course_id) { ElMessage.warning('课程信息加载失败，请刷新重试'); return }
    const created = unwrapPaper(await adminPaperApi.createQuestionTemplate({
      name: qtDialog.name.trim(), question_type: qtDialog.question_type,
      course_id: qtScope.value.course_id, version_id: qtScope.value.version_id,
      params_schema: paramsSchema, body_template: qtDialog.bodyText, answer_template: qtDialog.answerText,
      options_template: qtDialog.question_type === 'choice' ? optionsTemplate : undefined,
      knowledge_point_codes: kpCodes, difficulty: Number(qtDialog.difficulty) || 2,
    }))
    ElMessage.success(`模板「${created.name}」已创建（draft），请试生成样例核对后再发布`)
    qtDialog.visible = false
    await loadQuestionTemplates()
  } catch (e) { ElMessage.error(e.message || '创建模板失败') } finally { qtDialog.submitting = false }
}
async function runSample(row, count = 10) {
  try {
    sampleState.loading = true; sampleState.template = row; sampleState.visible = true; sampleState.items = []
    sampleState.items = unwrapPaper(await adminPaperApi.sampleQuestionTemplate(row.id, { count, seed: 0 }))
  } catch (e) { ElMessage.error(e.message || '试生成失败') } finally { sampleState.loading = false }
}
async function publishQuestionTemplate(row) {
  try {
    unwrapPaper(await adminPaperApi.publishQuestionTemplate(row.id))
    ElMessage.success('模板已发布：实例化题将进入组卷候选池')
    await loadQuestionTemplates()
  } catch (e) { ElMessage.error(e.message || '发布失败') }
}
async function retireQuestionTemplate(row) {
  try {
    unwrapPaper(await adminPaperApi.retireQuestionTemplate(row.id))
    ElMessage.success('模板已下架：不再生成新变式，已生成题不受影响')
    await loadQuestionTemplates()
  } catch (e) { ElMessage.error(e.message || '下架失败') }
}
const QT_STATUS_TAG = { draft: 'info', reviewed: 'warning', published: 'success', retired: 'danger' }

onMounted(async () => {
  loading.value = true
  await Promise.all([loadTemplates(), loadPapers(), loadQuestionTemplates(), loadQtScope()])
  loading.value = false
})
</script>

<template>
  <div class="wb">
    <header class="wb-header no-print">
      <button class="wb-back" @click="router.push('/')">← 返回</button>
      <h1 class="wb-title">组卷工作台</h1>
      <span class="wb-spacer" />
      <el-button size="small" text type="primary" @click="router.push('/admin/review')">题库审核</el-button>
      <el-button size="small" text type="primary" @click="router.push('/admin/readiness')">就绪度</el-button>
    </header>

    <div class="wb-tabs no-print">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="组卷" name="compose">
          <div class="compose">
            <section class="card">
              <h3>① 组卷方式</h3>
              <el-select v-model="templateId" style="width: 320px" aria-label="组卷模板">
                <el-option label="临时配置（本次手填）" value="" />
                <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
              </el-select>
              <el-button size="small" @click="templateDialog.visible = true" :disabled="!templateId && !totalQuestions">存为模板</el-button>
              <p v-if="templates.length" class="hint">已有 {{ templates.length }} 个模板；模板固定题型/难度规则，生成时可再换随机种子。</p>
            </section>

            <section v-if="!templateId" class="card">
              <h3>② 试卷规则</h3>
              <div class="rule-grid">
                <div v-for="(label, kind) in TYPE_LABELS" :key="kind" class="rule-item">
                  <label>{{ label }}</label>
                  <el-input-number v-model="typeCounts[kind]" :min="0" :max="50" size="small" />
                </div>
                <div class="rule-item">
                  <label>每题分值</label>
                  <el-input-number v-model="scorePer" :min="1" :max="100" size="small" />
                </div>
                <div class="rule-item">
                  <label>随机种子</label>
                  <el-input-number v-model="randomSeed" :min="0" :max="2147483647" size="small" />
                </div>
              </div>
              <el-checkbox v-model="useDifficulty">约束难度分布（可选，不足时自动从同题型补足）</el-checkbox>
              <div v-if="useDifficulty" class="rule-grid">
                <div v-for="level in [1, 2, 3, 4, 5]" :key="level" class="rule-item">
                  <label>难度 {{ level }}</label>
                  <el-input-number v-model="difficultyCounts[level]" :min="0" :max="50" size="small" />
                </div>
              </div>
              <el-input v-model="kpText" type="textarea" :rows="2" placeholder="限定知识点代码（可选，逗号或换行分隔，如 limit, derivative）" style="margin-top: 8px" />
              <p class="hint">共 {{ totalQuestions }} 题 · 总分 {{ totalScore }} 分；只使用已发布、可自动判分的正式题。</p>
            </section>

            <section class="card">
              <h3>{{ templateId ? '②' : '③' }} 预览与生成</h3>
              <div class="ops">
                <el-input v-model="paperTitle" placeholder="试卷标题（可选）" style="width: 260px" />
                <el-button :loading="previewing" @click="runPreview">预览选题（不落库）</el-button>
                <el-button type="primary" :loading="generating" :disabled="!templateId && !totalQuestions" @click="runGenerate">生成试卷</el-button>
              </div>
              <div v-if="preview" class="preview">
                <p class="hint">预览共 {{ preview.total }} 题（刷新会重新抽题）：</p>
                <ol class="preview-list">
                  <li v-for="(q, i) in preview.questions" :key="q.question_id + i">
                    <el-tag size="small" type="info">{{ TYPE_LABELS[q.question_type] || q.question_type }}</el-tag>
                    <el-tag size="small">难度 {{ q.difficulty ?? '—' }}</el-tag>
                    <span class="stem" v-html="renderMathBank(q.content)" />
                  </li>
                </ol>
              </div>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="`题目模板（${questionTemplates.length}）`" name="qtemplates">
          <div class="qt">
            <div class="ops" style="margin-bottom:12px">
              <el-button type="primary" size="small" @click="openQtDialog">新建参数化模板</el-button>
              <span class="hint">模板 = 参数定义 + 题干/答案占位符；发布后实例化题自动进入组卷候选池，缓解题荒知识点。</span>
            </div>
            <el-table :data="questionTemplates" v-loading="loading" size="small" border>
              <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
              <el-table-column label="题型" width="100">
                <template #default="{ row }">{{ TYPE_LABELS[row.question_type] || row.question_type }}</template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="{ row }"><el-tag size="small" :type="QT_STATUS_TAG[row.review_status] || 'info'">{{ row.review_status }}</el-tag></template>
              </el-table-column>
              <el-table-column label="知识点" min-width="120" show-overflow-tooltip>
                <template #default="{ row }">{{ (row.knowledge_point_codes || []).join(', ') }}</template>
              </el-table-column>
              <el-table-column prop="difficulty" label="难度" width="60" align="center" />
              <el-table-column prop="generation_count" label="已生成" width="70" align="center" />
              <el-table-column label="操作" width="230" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" text type="primary" @click="runSample(row)">试生成样例</el-button>
                  <el-button v-if="row.review_status !== 'published'" size="small" text type="success" :disabled="row.review_status === 'retired'" @click="publishQuestionTemplate(row)">发布</el-button>
                  <el-button v-else size="small" text type="danger" @click="retireQuestionTemplate(row)">下架</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="`试卷库（${papers.length}）`" name="papers">
          <el-table :data="papers" v-loading="loading" size="small" border>
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column prop="question_total" label="题数" width="70" align="center" />
            <el-table-column prop="total_score" label="总分" width="70" align="center" />
            <el-table-column label="创建时间" width="170">
              <template #default="{ row }">{{ (row.created_at || '').replace('T', ' ').slice(0, 19) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="openDetail(row.id)">查看 / 打印</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 新建模板对话框 -->
    <el-dialog v-model="templateDialog.visible" title="保存为组卷模板" width="420px" class="no-print">
      <el-input v-model="templateDialog.name" placeholder="模板名称，如「高数期中·基础卷」" maxlength="60" show-word-limit />
      <p class="hint" style="margin-top: 8px">将按当前{{ templateId ? '模板' : '手填' }}规则保存：题型配额 / 难度分布 / 知识点范围。</p>
      <template #footer>
        <el-button @click="templateDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="templateDialog.submitting" @click="saveTemplate">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建参数化题目模板（§5.3） -->
    <el-dialog v-model="qtDialog.visible" title="新建参数化变式题模板" width="640px" class="no-print" top="6vh">
      <div class="qt-form">
        <div class="qt-row">
          <el-input v-model="qtDialog.name" placeholder="模板名称，如「乘法口算·两位数」" maxlength="60" />
          <el-select v-model="qtDialog.question_type" style="width: 140px" aria-label="生成题型">
            <el-option v-for="(label, kind) in TYPE_LABELS" :key="kind" :label="label" :value="kind" />
          </el-select>
          <el-input-number v-model="qtDialog.difficulty" :min="1" :max="5" size="small" aria-label="难度" />
        </div>
        <label class="qt-label">参数定义（JSON：int/float/enum，range 或 values）</label>
        <el-input v-model="qtDialog.paramsText" type="textarea" :rows="4" spellcheck="false" />
        <label class="qt-label" v-pre>题干模板（用 {{a}} 占位，支持 LaTeX）</label>
        <el-input v-model="qtDialog.bodyText" type="textarea" :rows="2" spellcheck="false" />
        <label class="qt-label" v-pre>答案模板（Python 风格表达式，如 {{a}}*{{b}}；choice 填正确选项 id 占位）</label>
        <el-input v-model="qtDialog.answerText" type="textarea" :rows="2" spellcheck="false" />
        <template v-if="qtDialog.question_type === 'choice'">
          <label class="qt-label">选项模板（JSON 数组，id/text 支持占位符）</label>
          <el-input v-model="qtDialog.optionsText" type="textarea" :rows="3" spellcheck="false" />
        </template>
        <label class="qt-label">知识点代码（逗号分隔，如 limit, deriv）</label>
        <el-input v-model="qtDialog.kpText" placeholder="limit, deriv" />
        <p class="hint">创建后为 draft：先「试生成样例」人工核对，确认无误再「发布」入池；同参数组合不会重复生成。</p>
      </div>
      <template #footer>
        <el-button @click="qtDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="qtDialog.submitting" @click="submitQuestionTemplate">创建模板</el-button>
      </template>
    </el-dialog>

    <!-- 试生成样例（人工抽检） -->
    <el-dialog v-model="sampleState.visible" :title="`试生成样例 — ${sampleState.template?.name || ''}`" width="720px" class="no-print" top="6vh">
      <div v-if="sampleState.loading" v-loading="sampleState.loading" style="min-height: 200px" />
      <template v-else>
        <p class="hint">共 {{ sampleState.items.length }} 个样例（seed=0 可复现）。请核对题干与答案后再发布模板。</p>
        <ol class="qt-samples">
          <li v-for="(item, index) in sampleState.items" :key="index">
            <div class="qt-sample-head">
              <el-tag size="small" type="info">参数 {{ JSON.stringify(item.params) }}</el-tag>
            </div>
            <div class="stem" v-html="renderMathBank(item.body)" />
            <p class="qt-sample-answer">答案：{{ JSON.stringify(item.answer_spec) }}</p>
          </li>
        </ol>
      </template>
      <template #footer>
        <el-button @click="sampleState.visible = false">关闭</el-button>
        <el-button v-if="sampleState.template && sampleState.template.review_status !== 'published'" type="success" @click="publishQuestionTemplate(sampleState.template)">核对无误，发布</el-button>
      </template>
    </el-dialog>

    <!-- 试卷详情抽屉（可打印） -->
    <el-drawer v-model="detailVisible" size="62%" :title="detail?.title || '试卷详情'" class="paper-drawer">
      <div v-if="detailLoading" v-loading="detailLoading" style="min-height: 200px" />
      <div v-else-if="detail" class="paper">
        <div class="paper-toolbar no-print">
          <el-switch v-model="teacherMode" active-text="教师版（含答案解析）" inactive-text="学生版" />
          <el-button size="small" type="primary" @click="printPaper">打印 / 导出 PDF</el-button>
        </div>
        <h2 class="paper-title">{{ detail.title }}</h2>
        <p class="paper-meta">共 {{ detail.questions.length }} 题 · 每题 {{ detail.questions[0]?.score ?? '—' }} 分 · 满分 {{ detail.questions.reduce((a, q) => a + (q.score || 0), 0) }} 分</p>
        <ol class="paper-questions">
          <li v-for="pq in detail.questions" :key="pq.question_id + pq.position" class="paper-q">
            <div class="paper-q-head">
              <el-tag size="small" type="info">{{ TYPE_LABELS[pq.snapshot.question_type] || pq.snapshot.question_type }}</el-tag>
              <el-tag size="small">难度 {{ pq.snapshot.difficulty ?? '—' }}</el-tag>
              <el-tag v-if="teacherMode && (pq.snapshot.knowledge_point_codes || []).length" size="small" type="warning">{{ pq.snapshot.knowledge_point_codes.join(' / ') }}</el-tag>
            </div>
            <div class="stem" v-html="renderMathBank(pq.snapshot.content)" />
            <div v-if="pq.snapshot.question_type === 'choice'" class="options">
              <div v-for="o in pq.snapshot.options || []" :key="o.id" class="option" :class="{ right: teacherMode && pq.snapshot.answer_spec?.correct === o.id }">{{ o.id }}. <span v-html="renderMathBank(o.text)" /></div>
            </div>
            <div v-else-if="pq.snapshot.question_type === 'judge'" class="options">
              <div class="option" :class="{ right: teacherMode && pq.snapshot.answer_spec?.correct === true }">对</div>
              <div class="option" :class="{ right: teacherMode && pq.snapshot.answer_spec?.correct === false }">错</div>
            </div>
            <div v-if="teacherMode" class="answer">
              <p><b>参考答案：</b><span v-html="renderMathBank(String(answerText(pq.snapshot)))" /></p>
              <p v-if="pq.snapshot.analysis"><b>解析：</b><span class="stem" v-html="renderMathBank(pq.snapshot.analysis)" /></p>
            </div>
          </li>
        </ol>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.wb { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.wb-header { display: flex; align-items: center; gap: 12px; padding: 14px 20px; background: var(--surface); border-bottom: 1px solid var(--border-subtle); flex-shrink: 0; }
.wb-back { background: none; border: none; color: var(--accent); cursor: pointer; font-size: var(--font-size-sm); }
.wb-title { font-size: var(--font-size-lg); margin: 0; font-weight: 500; }
.wb-spacer { flex: 1; }
.wb-tabs { flex: 1; min-height: 0; padding: 0 20px; display: flex; flex-direction: column; overflow: hidden; }
.wb-tabs :deep(.el-tabs__content) { flex: 1; min-height: 0; overflow: auto; }
.wb-tabs :deep(.el-tab-pane) { display: flex; flex-direction: column; }
.compose { max-width: 860px; display: grid; gap: 14px; padding-bottom: 32px; }
.card { background: var(--surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 16px; }
.card h3 { margin: 0 0 12px; font-size: var(--font-size-base); font-weight: 500; }
.hint { color: var(--text-tertiary); font-size: var(--font-size-sm); margin: 8px 0 0; }
.rule-grid { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
.rule-item { display: flex; align-items: center; gap: 8px; }
.rule-item label { color: var(--text-secondary); font-size: var(--font-size-sm); min-width: 62px; }
.ops { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.preview { margin-top: 12px; border-top: 1px dashed var(--border-subtle); padding-top: 10px; }
.preview-list { margin: 0; padding-left: 20px; display: grid; gap: 8px; }
.preview-list li { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.preview-list .stem { flex: 1; min-width: 260px; line-height: 1.6; }
/* 试卷详情 */
.paper { padding: 4px 8px; }
.paper-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.paper-title { margin: 0; text-align: center; }
.paper-meta { text-align: center; color: var(--text-secondary); font-size: var(--font-size-sm); }
.paper-questions { margin: 16px 0 0; padding-left: 22px; display: grid; gap: 18px; }
.paper-q-head { display: flex; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.stem { line-height: 1.75; overflow-wrap: anywhere; }
.stem :deep(.katex) { font-size: 1.02em; }
.options { display: grid; gap: 6px; margin-top: 8px; }
.option { padding: 4px 10px; border-radius: var(--radius-xs); background: var(--surface-muted); font-size: var(--font-size-sm); }
.option.right { background: var(--accent-soft); outline: 1px solid var(--accent); }
.answer { margin-top: 10px; padding: 10px 12px; border-left: 3px solid var(--accent); background: var(--surface-muted); border-radius: var(--radius-xs); font-size: var(--font-size-sm); }
.answer p { margin: 0 0 6px; }
.qt { max-width: 960px; padding-bottom: 32px; display: flex; flex-direction: column; }
.qt-form { display: grid; gap: 8px; }
.qt-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.qt-label { color: var(--text-secondary); font-size: var(--font-size-sm); margin-top: 4px; }
.qt-samples { margin: 8px 0 0; padding-left: 20px; display: grid; gap: 14px; max-height: 56vh; overflow: auto; }
.qt-samples li { display: grid; gap: 6px; }
.qt-sample-head { display: flex; gap: 6px; flex-wrap: wrap; }
.qt-sample-answer { margin: 0; color: var(--text-secondary); font-size: var(--font-size-sm); }
/* 打印：只输出试卷内容 */
@media print {
  .no-print { display: none !important; }
  .paper-drawer :deep(.el-drawer__body) { overflow: visible !important; }
}
</style>
