<script setup>
/**
 * 题库审核工作台（WS-D v1）
 * Tab1 候选审核：批次 → 候选列表 → 题干/AI 分析 → PDF 原页对照 → 处置/建草稿
 * Tab2 题目发布：审核队列（draft/reviewed/published）→ 审核/发布
 */
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminReviewApi, unwrap } from '@/api/adminReview'
import ContentAIPartialBadge from '@/components/admin/ContentAIPartialBadge.vue'
import { renderMarkdown } from '@/utils/markdown'
import AdminShell from '@/components/shell/AdminShell.vue'

// 审核页的内容必须先按“普通文本 + Markdown + LaTeX”渲染。
// 旧实现把整段中文题干交给 KaTeX displayMode，导致题号、选项和公式互相吞并。
function renderMath(text) {
  if (!text) return ''
  return renderMarkdown(String(text))
}

const router = useRouter()
const activeTab = ref('candidates')
const loading = ref(false)
const importMode = ref('auto')
// 使用流程引导：首次进入显示，看完后可关闭（持久化到 localStorage）
const showHelp = ref(localStorage.getItem('adminReview_help_dismissed') !== '1')
const importing = ref(false)
const importTask = ref(null)
let importTaskTimer = null

// ── provider 能力状态 ──
const provider = ref(null)

// ── 批次 ──
const batches = ref([])
const batchId = ref('')
const batch = ref(null)
const stats = ref(null)
const BATCH_SELECTION_KEY = 'adminReview_selected_batch'

// ── 候选 ──
const candidates = ref([])
const selectedId = ref('')
const analysis = ref(null) // { latest, history }
const showRawContent = ref(false)
const gateFilter = ref('all')
const dispositionFilter = ref('all')
const selectedIds = ref([])

// ── AI 批量任务 ──
const task = ref(null)
let taskTimer = null

// ── PDF 预览 ──
const previewDocId = ref('')
const previewPage = ref(1)
const previewUrl = ref('')
const previewErr = ref('')
const sourceRegionPreviews = ref([])

// ── 候选在线编辑 ──
const questionTypes = ['choice', 'judge', 'numeric_fill', 'expression_fill', 'calculation', 'proof', 'short_answer']
const editing = ref(false)
const editedHint = ref('')
const editForm = reactive({ stem: '', options: '', answer: '', solution: '', type: 'choice', kp: '', difficulty: 3 })

function startEdit() {
  if (!selectedCand.value) return
  editing.value = true
  editForm.stem = selectedCand.value.stem || ''
  editForm.options = JSON.stringify(selectedCand.value.options || [], null, 1)
  editForm.answer = selectedCand.value.original_answer || ''
  editForm.solution = selectedCand.value.original_solution || ''
  editForm.type = selectedCand.value.detected_question_type || 'choice'
  editForm.kp = (selectedCand.value.suggested_knowledge_point_codes || []).join(',')
  editForm.difficulty = selectedCand.value.suggested_difficulty || 3
}

function cancelEdit() {
  editing.value = false
}

async function saveEdit() {
  let options = null
  if (editForm.options.trim()) {
    try {
      options = JSON.parse(editForm.options)
    } catch {
      return ElMessage.error('选项 JSON 解析失败，请检查格式')
    }
  }
  const patch = {
    stem: editForm.stem,
    options,
    original_answer: editForm.answer,
    original_solution: editForm.solution,
    detected_question_type: editForm.type,
    suggested_knowledge_point_codes: editForm.kp.split(',').map((s) => s.trim()).filter(Boolean),
    suggested_difficulty: Number(editForm.difficulty) || 3,
  }
  try {
    await adminReviewApi.updateCandidate(batchId.value, selectedId.value, patch)
    ElMessage.success('已保存；内容已修改，建议重跑 AI 分析')
    editing.value = false
    editedHint.value = selectedId.value
    await loadCandidates()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ── 正式题队列 ──
const questions = ref([])
const qStatus = ref('')
const selectedQids = ref([])
const quality = ref({ summary: {}, issues: [], duplicate_groups: [] })
const feedback = ref([])
const history = ref(null)

async function uploadImport(event) {
  const input = event.target
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) return ElMessage.error('只支持 PDF 文件')
  importing.value = true
  try {
    const key = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    const data = unwrap(await adminReviewApi.createImport(file, importMode.value, key))
    batchId.value = data.batch.id
    localStorage.setItem(BATCH_SELECTION_KEY, batchId.value)
    ElMessage.success(data.created ? '导入批次已创建' : '已恢复同一导入批次')
    await loadBatches()
    if (data.batch.parse_task_id) pollImportTask(data.batch.parse_task_id)
  } catch (e) { ElMessage.error(e.message || '导入失败，请重试') }
  finally { importing.value = false }
}

function pollImportTask(taskId) {
  if (importTaskTimer) clearTimeout(importTaskTimer)
  const tick = async () => {
    try {
      importTask.value = unwrap(await adminReviewApi.getContentTask(taskId))
      if (['pending', 'running', 'retrying'].includes(importTask.value.status)) importTaskTimer = setTimeout(tick, 1500)
      else await loadBatches()
    } catch (e) { ElMessage.error(e.message || '无法读取解析进度') }
  }
  tick()
}

async function retryImport() {
  if (!batchId.value) return
  try {
    const data = unwrap(await adminReviewApi.retryImport(batchId.value))
    importTask.value = null
    ElMessage.info('已重新投递解析任务')
    pollImportTask(data.parse_task_id)
  } catch (e) {
    ElMessage.error(e.message || '重试失败')
  }
}

const importProgress = computed(() => Math.max(0, Math.min(100, Number(importTask.value?.progress?.percent || 0))))
const importStageLabel = computed(() => importTask.value?.progress?.stage_label || ({
  pending: '等待解析', running: '解析进行中', retrying: '等待重试', succeeded: '解析完成',
  partially_succeeded: '部分完成', failed: '解析失败', cancelled: '已取消',
}[importTask.value?.status] || '准备解析'))
const importProgressStatus = computed(() => {
  if (['failed', 'cancelled'].includes(importTask.value?.status)) return 'exception'
  if (['succeeded', 'partially_succeeded'].includes(importTask.value?.status)) return 'success'
  return undefined
})

async function cancelImportTask() {
  if (!importTask.value?.id) return
  await adminReviewApi.cancelTask(importTask.value.id)
  ElMessage.info('已请求取消解析任务')
}

const visibleCandidates = computed(() => {
  return candidates.value.filter((c) => {
    const g = latestGate(c.id)
    if (gateFilter.value !== 'all' && (g || 'none') !== gateFilter.value) return false
    const d = latestDisposition(c.id)
    if (dispositionFilter.value !== 'all' && (d || 'none') !== dispositionFilter.value) return false
    return true
  })
})

const selectedCand = computed(() => candidates.value.find((c) => c.id === selectedId.value) || null)

function latestRun(cid) {
  return analysis.value?.candidate_id === cid ? analysis.value.latest : null
}
function latestGate(cid) {
  const run = latestRun(cid)
  if (!run) return null
  return (run.gate || run.status || '').toUpperCase()
}
function latestDisposition(cid) {
  return latestRun(cid)?.human_disposition || null
}

// ── 加载 ──
async function loadBatches() {
  loading.value = true
  try {
    batches.value = unwrap(await adminReviewApi.listBatches()) || []
    if (batches.value.length) {
      if (!batchId.value || !batches.value.some((b) => b.id === batchId.value)) {
        const savedId = localStorage.getItem(BATCH_SELECTION_KEY)
        const savedBatch = batches.value.find((b) => b.id === savedId)
        const usableBatch = batches.value.find((b) => ['parsed', 'completed', 'parsing', 'pending'].includes(b.status))
        const preferredBatch = savedBatch && savedBatch.status !== 'failed' ? savedBatch : usableBatch
        batchId.value = preferredBatch?.id || savedBatch?.id || batches.value[0].id
      }
      localStorage.setItem(BATCH_SELECTION_KEY, batchId.value)
      await selectBatch()
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function selectBatch() {
  if (batchId.value) localStorage.setItem(BATCH_SELECTION_KEY, batchId.value)
  batch.value = batches.value.find((b) => b.id === batchId.value) || null
  previewDocId.value = batch.value?.source_document_id || ''
  selectedIds.value = []
  await Promise.all([loadCandidates(), loadStats(), loadProvider()])
}

async function loadCandidates() {
  try {
    candidates.value = unwrap(await adminReviewApi.listCandidates(batchId.value)) || []
    if (candidates.value.length) {
      if (!selectedId.value || !candidates.value.some((c) => c.id === selectedId.value)) {
        await selectCandidate(candidates.value[0].id)
      } else {
        await selectCandidate(selectedId.value)
      }
    } else {
      selectedId.value = ''
      analysis.value = null
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function loadStats() {
  try {
    stats.value = unwrap(await adminReviewApi.batchStats(batchId.value))
  } catch {
    stats.value = null
  }
}

async function loadProvider() {
  try {
    provider.value = unwrap(await adminReviewApi.providerStatus())
  } catch {
    provider.value = null
  }
}

async function selectCandidate(cid) {
  if (!cid) return
  editing.value = false
  showRawContent.value = false
  selectedId.value = cid
  const cand = candidates.value.find((c) => c.id === cid)
  if (cand) {
    previewPage.value = cand.source_page_start || 1
    await loadPage(previewPage.value)
    await loadSourceRegionPreviews(cand)
  }
  try {
    analysis.value = unwrap(await adminReviewApi.candidateAnalysis(cid))
  } catch (e) {
    analysis.value = { candidate_id: cid, latest: null, history: [] }
  }
}

function clearSourceRegionPreviews() {
  for (const item of sourceRegionPreviews.value) {
    if (item.url) URL.revokeObjectURL(item.url)
  }
  sourceRegionPreviews.value = []
}

async function loadSourceRegionPreviews(candidate) {
  clearSourceRegionPreviews()
  if (!previewDocId.value || !candidate) return
  const regions = (candidate.source_regions || []).filter((item) => item?.page && item?.bbox?.length === 4)
  const fallback = regions.length
    ? regions
    : (candidate.source_page_start && candidate.source_bbox?.length === 4
      ? [{ page: candidate.source_page_start, bbox: candidate.source_bbox }]
      : [])
  const loaded = []
  for (const region of fallback) {
    try {
      const resp = await adminReviewApi.fetchPagePreview(previewDocId.value, region.page, region.bbox)
      loaded.push({ page: region.page, url: URL.createObjectURL(resp.data) })
    } catch {
      // 题目截图失败时仍保留右侧整页预览，不阻塞审核。
    }
  }
  sourceRegionPreviews.value = loaded
}

// ── AI 批量分析（异步任务 + 轮询）──
async function runBatchAnalysis() {
  try {
    const data = unwrap(await adminReviewApi.startBatchAnalysis(batchId.value))
    ElMessage.success('已投递批量分析任务')
    pollTask(data.task_id)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function pollTask(taskId) {
  stopPolling()
  task.value = { task_id: taskId, status: 'running', analyzed: 0, total: 0 }
  taskTimer = setInterval(async () => {
    try {
      const t = unwrap(await adminReviewApi.getBatchTask(taskId))
      task.value = { ...task.value, ...t }
      if (['completed', 'failed', 'cancelled'].includes(t.status)) {
        stopPolling()
        ElMessage[t.status === 'completed' ? 'success' : 'warning'](
          `批量分析${t.status === 'completed' ? '完成' : t.status}（analyzed=${t.analyzed}）`
        )
        await Promise.all([loadCandidates(), loadStats()])
      }
    } catch (e) {
      stopPolling()
      ElMessage.error(e.message)
    }
  }, 2000)
}

function stopPolling() {
  if (taskTimer) {
    clearInterval(taskTimer)
    taskTimer = null
  }
}

// ── 单候选操作 ──
async function analyzeOne() {
  if (!selectedId.value) return
  try {
    await adminReviewApi.analyzeCandidate(selectedId.value)
    ElMessage.success('分析完成')
    await Promise.all([selectCandidate(selectedId.value), loadStats()])
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function reanalyzeOne() {
  if (!selectedId.value) return
  try {
    await adminReviewApi.reanalyzeCandidate(selectedId.value)
    ElMessage.success('已重新分析')
    await Promise.all([selectCandidate(selectedId.value), loadStats()])
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function setDisposition(disposition) {
  if (!selectedId.value) return
  try {
    await ElMessageBox.confirm(
      `确认将当前候选标记为「${dispositionLabel(disposition)}」？`,
      '人工处置',
      { type: disposition === 'reject' ? 'warning' : 'info', confirmButtonText: '确认', cancelButtonText: '取消' }
    )
    await adminReviewApi.setDisposition(selectedId.value, disposition)
    ElMessage.success('已处置')
    await Promise.all([selectCandidate(selectedId.value), loadStats()])
  } catch (e) {
    if (e !== 'cancel' && e?.message) ElMessage.error(e.message)
  }
}

async function createDraftOne() {
  if (!selectedId.value) return
  try {
    const res = unwrap(await adminReviewApi.createDraft(selectedId.value))
    ElMessage.success(`已创建草稿：${(res.created || []).join(', ') || '已存在'}`)
    await Promise.all([selectCandidate(selectedId.value), loadStats()])
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ── 批量操作（限低风险：批准仅对 AI PASS 候选生效）──
async function batchApprove() {
  const ids = [...selectedIds.value]
  if (!ids.length) return ElMessage.warning('请先勾选候选')
  const passIds = ids.filter((cid) => latestGate(cid) === 'PASS')
  const skipped = ids.filter((cid) => latestGate(cid) !== 'PASS')
  if (skipped.length) ElMessage.warning(`已跳过 ${skipped.length} 道非 PASS 候选（不允许批量批准存疑/失败题）`)
  if (!passIds.length) return
  try {
    await adminReviewApi.setDisposition(passIds[0], 'approved')
    for (let i = 1; i < passIds.length; i++) {
      await adminReviewApi.setDisposition(passIds[i], 'approved')
    }
    ElMessage.success(`已批量批准 ${passIds.length} 道`)
    await Promise.all([loadCandidates(), loadStats()])
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function batchCreateDrafts() {
  const ids = [...selectedIds.value]
  if (!ids.length) return ElMessage.warning('请先勾选候选')
  try {
    const res = unwrap(await adminReviewApi.batchCreateDrafts(ids))
    ElMessage.success(`创建草稿 ${(res.created || []).length} 道${(res.errors || []).length ? `，失败 ${res.errors.length}` : ''}`)
    if (res.errors?.length) {
      ElMessage.warning((res.errors || []).map((e) => `${e.candidate_id}: ${e.error}`).join('；').slice(0, 300))
    }
    await Promise.all([loadCandidates(), loadStats()])
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ── PDF 原页预览（blob + objectURL，带 token）──
async function loadPage(page) {
  if (!previewDocId.value) return
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  previewErr.value = ''
  previewPage.value = page
  try {
    const region = selectedCand.value?.source_regions?.find((item) => Number(item.page) === Number(page))
    const bbox = region?.bbox || (selectedCand.value?.source_page_start === page ? selectedCand.value?.source_bbox : null)
    const resp = await adminReviewApi.fetchPagePreview(previewDocId.value, page, bbox)
    previewUrl.value = URL.createObjectURL(resp.data)
  } catch {
    previewErr.value = `第 ${page} 页不存在或不可预览`
  }
}

function prevPage() {
  if (previewPage.value > 1) loadPage(previewPage.value - 1)
}
function nextPage() {
  loadPage(previewPage.value + 1)
}

// ── 正式题队列 ──
async function loadQuestions() {
  try {
    questions.value = unwrap(await adminReviewApi.listQuestions(qStatus.value || undefined)) || []
    selectedQids.value = []
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function reviewOne(qid) {
  try {
    await adminReviewApi.markReviewed(qid)
    ElMessage.success('已标记审核')
    await loadQuestions()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function publishOne(qid) {
  try {
    await adminReviewApi.publishQuestion(qid)
    ElMessage.success('已发布')
    await loadQuestions()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function batchPublish(ids) {
  if (!ids.length) return ElMessage.warning('请先勾选题目')
  try {
    const res = unwrap(await adminReviewApi.batchPublish(ids))
    ElMessage.success(`发布 ${(res.published || []).length} 道${(res.errors || []).length ? `，失败 ${res.errors.length}` : ''}`)
    if (res.errors?.length) {
      ElMessage.warning((res.errors || []).map((e) => `${e.question_id}: ${e.error}`).slice(0, 4).join('；'))
    }
    await loadQuestions()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function batchPublishRows() {
  const reviewed = questions.value.filter((item) => selectedQids.value.includes(item.id) && item.review_status === 'reviewed').map((item) => item.id)
  if (!reviewed.length) return ElMessage.warning('请仅选择“已审核”题目进行发布')
  await batchPublish(reviewed)
}

async function retireOne(qid) {
  try {
    const { value } = await ElMessageBox.prompt('请填写退役原因。历史作答不会被删除。', '退役题目', {
      confirmButtonText: '确认退役', cancelButtonText: '取消', inputValidator: (v) => !!v?.trim() || '原因不能为空',
    })
    await adminReviewApi.retireQuestion(qid, value.trim())
    ElMessage.success('题目已退役并退出新练习池')
    await loadQuestions()
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '退役失败') }
}

async function restoreOne(qid) {
  try {
    const { value } = await ElMessageBox.prompt('恢复后题目进入草稿，必须重新审核发布。', '恢复为草稿', {
      confirmButtonText: '恢复', cancelButtonText: '取消', inputValidator: (v) => !!v?.trim() || '原因不能为空',
    })
    await adminReviewApi.restoreQuestion(qid, value.trim()); await loadQuestions()
    ElMessage.success('已恢复为草稿')
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '恢复失败') }
}

async function showHistory(qid) {
  try { history.value = unwrap(await adminReviewApi.questionHistory(qid)) }
  catch (e) { ElMessage.error(e.message || '历史加载失败') }
}

async function reportIssue(qid) {
  try {
    const { value } = await ElMessageBox.prompt('描述发现的内容问题。', '提交问题反馈', {
      confirmButtonText: '提交', cancelButtonText: '取消', inputValidator: (v) => !!v?.trim() || '说明不能为空',
    })
    await adminReviewApi.createFeedback(qid, { issue_type: 'content_error', description: value.trim() })
    ElMessage.success('反馈已记录')
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '提交失败') }
}

async function loadOperations() {
  try {
    const [qa, fb] = await Promise.all([adminReviewApi.qualityAudit(), adminReviewApi.listFeedback('open')])
    quality.value = unwrap(qa) || quality.value
    feedback.value = unwrap(fb) || []
  } catch (e) { ElMessage.error(e.message || '运营数据加载失败') }
}

async function resolveIssue(item) {
  try {
    const { value } = await ElMessageBox.prompt('填写处置结果。', '处置反馈', {
      confirmButtonText: '完成处置', cancelButtonText: '取消', inputValidator: (v) => !!v?.trim() || '处置结果不能为空',
    })
    await adminReviewApi.resolveFeedback(item.id, value.trim()); await loadOperations()
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '处置失败') }
}

async function decideDuplicate(item, isDuplicate) {
  try {
    const other = item.duplicate_group?.find((id) => id !== item.question_id) || null
    const { value } = await ElMessageBox.prompt('填写判断依据。', isDuplicate ? '确认重复题' : '标记为非重复', {
      confirmButtonText: '保存判断', cancelButtonText: '取消', inputValidator: (v) => !!v?.trim() || '依据不能为空',
    })
    await adminReviewApi.setDuplicateDisposition(item.question_id, { duplicate_of: other, is_duplicate: isDuplicate, reason: value.trim() })
    ElMessage.success('判断已写入审计历史')
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '保存失败') }
}

// ── 展示辅助 ──
function gateType(gate) {
  return gate === 'PASS' ? 'success' : gate === 'DOUBTFUL' ? 'warning' : gate === 'FAILED' ? 'danger' : 'info'
}
function gateLabel(gate) {
  return gate || '未分析'
}
function dispositionLabel(d) {
  return { approved: '批准', doubtful: '存疑', reject: '拒绝' }[d] || '未处置'
}
function dispositionType(d) {
  return d === 'approved' ? 'success' : d === 'doubtful' ? 'warning' : d === 'reject' ? 'danger' : 'info'
}
function typeLabel(t) {
  return {
    choice: '选择', judge: '判断', numeric_fill: '数值填空', expression_fill: '表达式填空',
    calculation: '计算', proof: '证明', short_answer: '简答',
    fill: '填空（待细分）', fill_candidate: '填空（待细分）', text: '文本',
  }[t] || t || '未知'
}

const warningLabels = {
  contains_subquestions: '可能包含多个小问，需要确认题目边界',
  answer_match_key_incomplete: 'PDF 未提供可匹配的原答案（待人工补录）',
  answer_match_missing: 'PDF 未提供原答案（待人工补录）',
  answer_roster_incomplete: 'PDF 答案区不完整（待人工补录）',
  option_parse_uncertain: '选项切分不确定',
  possible_answer_leak: '题干中可能混入答案标记',
  fill_type_needs_review: '填空题类型需要人工确认',
  page_mapping_uncertain: '来源页码不确定',
  unrenderable_glyphs: 'PDF 中存在无法可靠渲染的字体字符，请对照原 PDF 修复',
  question_number_gap: '题号不连续，可能存在漏题或题目粘连',
  parser_fallback_mineru: '快速解析质量不足，已切换 MinerU 结果',
}
function warningLabel(code) {
  return warningLabels[code] || code
}
function isAnswerSourceWarning(code) {
  return ['answer_match_missing', 'answer_match_key_incomplete', 'answer_roster_incomplete', 'choice_answer_ambiguous'].includes(code)
}
function hasContentWarnings(warnings) {
  return (warnings || []).some((warning) => !isAnswerSourceWarning(warning))
}
function hasUnrenderableGlyphs(candidate) {
  return Boolean(candidate?.warnings?.includes('unrenderable_glyphs'))
}
function displayGateReasons(reasons) {
  return (reasons || []).filter((reason) => !/答案缺失|原答案.*(缺失|未提供)|ground truth/i.test(String(reason)))
}
function difficultyLabel(value) {
  return { 1: '简单', 2: '较简单', 3: '中等', 4: '较难', 5: '困难' }[value] || '未评估'
}
function verifierLabel(verifier) {
  return { pass: '验证通过', doubtful: '验证存疑', fail: '验证失败' }[verifier?.verdict] || '未验证'
}
function answerSpecLabel(spec) {
  if (!spec) return '—'
  if (spec.correct !== undefined) return String(spec.correct)
  if (spec.value !== undefined) return String(spec.value)
  return spec.canonical || '—'
}

function dismissHelp() {
  showHelp.value = false
  try { localStorage.setItem('adminReview_help_dismissed', '1') } catch {}
}
function statusLabel(s) {
  return { draft: '草稿', reviewed: '已审核', published: '已发布', retired: '已退役' }[s] || s
}
function statusType(s) {
  return s === 'published' ? 'success' : s === 'reviewed' ? 'warning' : 'info'
}

// ── 快捷键：← / → 切换候选 ──
function onKey(e) {
  if (activeTab.value !== 'candidates') return
  const tag = e.target?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
  const list = visibleCandidates.value
  if (!list.length) return
  const idx = list.findIndex((c) => c.id === selectedId.value)
  if (e.key === 'ArrowLeft' && idx > 0) selectCandidate(list[idx - 1].id)
  if (e.key === 'ArrowRight' && idx < list.length - 1) selectCandidate(list[idx + 1].id)
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
  loadBatches()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  stopPolling()
  if (importTaskTimer) clearTimeout(importTaskTimer)
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  clearSourceRegionPreviews()
})
</script>

<template>
  <AdminShell>
  <div class="wb">
    <header class="wb-header">
      <button class="wb-back" @click="router.push('/')">← 返回</button>
      <h1 class="wb-title">题库审核工作台</h1>
      <el-tag v-if="provider" :type="provider.available && provider.provider !== 'mock' ? 'success' : 'warning'" size="small">
        AI：{{ provider.provider }}（{{ provider.available ? (provider.provider === 'mock' ? 'Mock，禁止正式发布' : '可用') : '不可用' }}）
      </el-tag>
      <el-button size="small" text type="primary" @click="router.push('/admin/papers')">组卷</el-button>
      <el-button size="small" text type="primary" @click="router.push('/admin/readiness')">就绪度</el-button>
      <span class="wb-spacer" />
      <el-select v-model="importMode" size="small" style="width: 110px" aria-label="PDF 解析模式">
        <el-option label="智能按需解析" value="auto" /><el-option label="快速解析" value="quick" /><el-option label="MinerU" value="mineru" />
      </el-select>
      <label class="wb-upload" :class="{ 'is-disabled': importing }">
        {{ importing ? '上传中…' : '导入 PDF' }}
        <input type="file" accept="application/pdf,.pdf" :disabled="importing" @change="uploadImport" />
      </label>
      <el-select v-model="batchId" placeholder="选择批次" size="small" style="width: 260px" @change="selectBatch">
        <el-option v-for="b in batches" :key="b.id" :label="`${b.id.slice(0, 8)}… (${b.status}) ${(b.stats?.total_candidates ?? '')}`" :value="b.id" />
      </el-select>
      <el-button size="small" :loading="loading" @click="loadBatches">刷新</el-button>
    </header>
    <div v-if="importTask" class="wb-import-status" role="status" aria-live="polite">
      <div class="wb-import-status__head">
        <strong>PDF 解析进度</strong>
        <span>{{ importStageLabel }} · {{ importProgress }}%</span>
        <el-button v-if="['pending','running','retrying'].includes(importTask.status)" size="small" @click="cancelImportTask">取消</el-button>
        <el-button v-if="importTask.status === 'failed'" size="small" type="primary" @click="retryImport">重试解析</el-button>
      </div>
      <el-progress :percentage="importProgress" :status="importProgressStatus" :stroke-width="8" :show-text="false" />
      <div class="wb-import-status__meta">
        <span v-if="importTask.progress?.total_pages">已处理 {{ importTask.progress.pages || 0 }}/{{ importTask.progress.total_pages }} 页</span>
        <span v-if="importTask.progress?.questions">已识别 {{ importTask.progress.questions }} 道题</span>
        <span>任务状态：{{ importTask.status }}</span>
        <span v-if="importTask.error_message" class="wb-import-status__error" role="alert">{{ importTask.error_message }}</span>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="wb-tabs" @tab-change="(name) => name === 'operations' && loadOperations()">
      <!-- ════ Tab1 候选审核 ════ -->
      <el-tab-pane label="候选审核" name="candidates">
        <div v-if="task" class="wb-task">
          <el-progress
            :percentage="task.total ? Math.round((task.analyzed / task.total) * 100) : 0"
            :status="task.status === 'failed' || task.status === 'cancelled' ? 'exception' : undefined"
          />
          <span class="wb-task-text">
            批量分析：{{ task.analyzed }}/{{ task.total }}（{{ task.status }}）<a v-if="task.status === 'running'" href="#" @click.prevent="stopPolling()">停止轮询</a>
          </span>
        </div>

        <!-- 使用流程引导（首次阅读后即可隐藏） -->
        <div v-if="showHelp" class="wb-help" role="note">
          <span><b>使用流程：</b></span>
          <span class="wb-help__step"><span class="wb-help__num">1</span>上方「导入 PDF」上传题库</span>
          <span class="wb-help__step"><span class="wb-help__num">2</span>左侧选候选 · 中间看题干（LaTeX 已渲染）· 右侧对照 PDF 原页</span>
          <span class="wb-help__step"><span class="wb-help__num">3</span>点底部「AI 分析」→ 出现门禁（PASS / DOUBTFUL / FAILED）</span>
          <span class="wb-help__step"><span class="wb-help__num">4</span>PASS 点「批准」→「创建草稿」→ 切到「题目发布」tab → 审核 → 发布</span>
          <el-link type="primary" :underline="false" @click="dismissHelp" style="margin-left:auto">知道了</el-link>
        </div>

        <div class="wb-body">
          <!-- 左：候选列表 -->
          <aside class="wb-col wb-col--list">
            <div class="wb-filters">
              <el-select v-model="gateFilter" size="small" style="width: 108px">
                <el-option label="全部门禁" value="all" />
                <el-option label="PASS" value="PASS" />
                <el-option label="DOUBTFUL" value="DOUBTFUL" />
                <el-option label="FAILED" value="FAILED" />
                <el-option label="未分析" value="none" />
              </el-select>
              <el-select v-model="dispositionFilter" size="small" style="width: 108px">
                <el-option label="全部处置" value="all" />
                <el-option label="未处置" value="none" />
                <el-option label="批准" value="approved" />
                <el-option label="存疑" value="doubtful" />
                <el-option label="拒绝" value="reject" />
              </el-select>
            </div>
            <div class="wb-candlist">
              <button
                v-for="c in visibleCandidates"
                :key="c.id"
                class="wb-cand"
                :class="{ 'is-active': c.id === selectedId }"
                @click="selectCandidate(c.id)"
              >
                <el-checkbox
                  :model-value="selectedIds.includes(c.id)"
                  @click.stop
                  @change="(v) => (v ? selectedIds.push(c.id) : (selectedIds = selectedIds.filter((x) => x !== c.id)))"
                />
                <span class="wb-cand__idx">#{{ c.candidate_index }}</span>
                <span class="wb-cand__type">{{ typeLabel(c.detected_question_type) }}</span>
                <el-tag v-if="c.status === 'edited'" type="warning" size="small">已编辑</el-tag>
                <el-tag :type="gateType(latestGate(c.id))" size="small" effect="dark">{{ gateLabel(latestGate(c.id)) }}</el-tag>
                <el-tag v-if="latestDisposition(c.id)" :type="dispositionType(latestDisposition(c.id))" size="small">
                  {{ dispositionLabel(latestDisposition(c.id)) }}
                </el-tag>
              </button>
              <div v-if="!visibleCandidates.length" class="wb-empty">无候选</div>
            </div>
          </aside>

          <!-- 中：候选详情 -->
          <section class="wb-col wb-col--main">
            <template v-if="selectedId">
              <div class="wb-card">
                <h3 class="wb-card-title">
                  题目内容
                  <span class="wb-hint">（candidate #{{ selectedCand?.candidate_index }} · 页码 {{ selectedCand?.source_page_start }}）</span>
                  <span class="wb-spacer" />
                  <el-button size="small" text @click="showRawContent = !showRawContent">
                    {{ showRawContent ? '查看渲染' : '查看原文' }}
                  </el-button>
                  <el-button v-if="!editing" size="small" type="primary" plain @click="startEdit">编辑</el-button>
                  <el-button v-else size="small" @click="cancelEdit">取消</el-button>
                </h3>
                <template v-if="editing">
                  <div class="wb-edit-row"><label>题干</label><el-input v-model="editForm.stem" type="textarea" :rows="3" /></div>
                  <div class="wb-edit-row"><label>选项 JSON</label><el-input v-model="editForm.options" type="textarea" :rows="3" /></div>
                  <div class="wb-edit-row"><label>答案</label><el-input v-model="editForm.answer" /></div>
                  <div class="wb-edit-row"><label>解析</label><el-input v-model="editForm.solution" type="textarea" :rows="2" /></div>
                  <div class="wb-edit-row">
                    <label>题型</label>
                    <el-select v-model="editForm.type" size="small" style="width: 150px">
                      <el-option v-for="t in questionTypes" :key="t" :label="typeLabel(t)" :value="t" />
                    </el-select>
                    <label class="wb-edit-kp">知识点 code</label>
                    <el-input v-model="editForm.kp" size="small" placeholder="逗号分隔" style="width: 200px" />
                    <label class="wb-edit-kp">难度</label>
                    <el-input-number v-model="editForm.difficulty" :min="1" :max="5" size="small" />
                  </div>
                  <div class="wb-edit-actions">
                    <el-button type="primary" size="small" @click="saveEdit">保存</el-button>
                    <el-alert
                      v-if="editedHint === selectedId"
                      type="warning"
                      :closable="false"
                      show-icon
                      title="内容已修改，建议重跑 AI 分析"
                    />
                  </div>
                </template>
                <template v-else>
                  <div v-if="hasUnrenderableGlyphs(selectedCand)" class="wb-source-fallback">
                    <div class="wb-source-fallback__head">
                      <strong>原题图兜底</strong>
                      <span>PDF 字体映射异常，文本可能失真；以下显示原题高清裁剪图。</span>
                    </div>
                    <div v-if="sourceRegionPreviews.length" class="wb-source-fallback__list">
                      <figure v-for="item in sourceRegionPreviews" :key="`${selectedCand.id}-${item.page}`" class="wb-source-fallback__figure">
                        <figcaption>第 {{ item.page }} 页 · 当前题目区域</figcaption>
                        <img :src="item.url" class="wb-source-fallback__img" alt="当前题目原题裁剪图" />
                      </figure>
                    </div>
                    <img v-else-if="previewUrl" :src="previewUrl" class="wb-source-fallback__img" alt="原题高清裁剪图" />
                    <div v-else class="wb-muted">正在加载原题图…</div>
                  </div>
                  <div v-else-if="showRawContent" class="wb-raw-content">{{ selectedCand?.stem || '（空）' }}</div>
                  <div v-else class="wb-stem" v-html="renderMath(selectedCand?.stem) || '<span class=&quot;wb-empty-inline&quot;>（空）</span>'" />
                  <div v-if="selectedCand?.options?.length && !hasUnrenderableGlyphs(selectedCand)" class="wb-options">
                    <div v-for="o in selectedCand.options" :key="o.id" class="wb-option">
                      <strong>【{{ o.id }}】</strong><span v-if="!showRawContent" v-html="renderMath(o.text)" /><span v-else>{{ o.text }}</span>
                    </div>
                  </div>
                  <div class="wb-subsection">
                    <h4>原题信息</h4>
                    <div class="wb-row"><span class="wb-k">PDF 原答案</span><span class="wb-v" v-html="renderMath(selectedCand?.original_answer) || '未提供'" /></div>
                    <div class="wb-rich-value" v-if="selectedCand?.original_solution" v-html="renderMath(selectedCand.original_solution)" />
                    <div v-else class="wb-muted">原 PDF 未提供解析。答案不属于本阶段导入门禁，请在题目发布前人工补录并确认。</div>
                  </div>
                  <div class="wb-meta-grid">
                    <div><span>题型</span><strong>{{ typeLabel(selectedCand?.detected_question_type) }}</strong></div>
                    <div><span>来源页码</span><strong>第 {{ selectedCand?.source_page_start || '—' }} 页</strong></div>
                    <div><span>候选状态</span><strong>{{ selectedCand?.status || '—' }}</strong></div>
                    <div><span>候选知识点</span><strong>{{ selectedCand?.suggested_knowledge_point_codes?.join('、') || '待分析' }}</strong></div>
                  </div>
                  <div v-if="hasContentWarnings(selectedCand?.warnings)" class="wb-warn">
                    <strong>需要人工确认</strong>
                    <ul><li v-for="warning in selectedCand.warnings" v-show="!isAnswerSourceWarning(warning)" :key="warning">{{ warningLabel(warning) }}</li></ul>
                  </div>
                </template>
              </div>

              <div class="wb-card">
                <h3 class="wb-card-title">AI 分析
                  <el-tag v-if="analysis?.latest" :type="gateType((analysis.latest.gate || analysis.latest.status || '').toUpperCase())" size="small">
                    {{ gateLabel((analysis.latest.gate || analysis.latest.status || '').toUpperCase()) }}
                  </el-tag>
                  <el-tag v-if="analysis?.latest?.human_disposition" :type="dispositionType(analysis.latest.human_disposition)" size="small">
                    {{ dispositionLabel(analysis.latest.human_disposition) }}
                  </el-tag>
                  <ContentAIPartialBadge
                    v-if="analysis?.latest?.partial"
                    :reasons="analysis.latest.partial_reasons || []"
                  />
                </h3>
                <template v-if="analysis?.latest">
                  <div class="wb-row"><span class="wb-k">Provider</span><span class="wb-v">{{ analysis.latest.provider }} / {{ analysis.latest.model || '-' }}</span></div>
                  <div class="wb-row"><span class="wb-k">Attempt</span><span class="wb-v">#{{ analysis.latest.attempt_no }}（{{ analysis.latest.status }}）</span></div>
                  <div class="wb-row">
                    <span class="wb-k">门禁原因</span>
                    <span class="wb-v">{{ displayGateReasons(analysis.latest.gate_reasons).join('；') || '—' }}</span>
                  </div>
                  <div v-if="analysis.latest.partial" class="wb-row wb-partial-reasons">
                    <span class="wb-k">不完整原因</span>
                    <span class="wb-v">{{ (analysis.latest.partial_reasons || []).join('；') || 'AI 结果不完整，请人工复核' }}</span>
                  </div>
                  <div v-if="analysis.latest.error_message" class="wb-warn">✗ {{ analysis.latest.error_message }}</div>
                  <div v-if="analysis.latest.analysis_json" class="wb-json">
                    <div class="wb-row"><span class="wb-k">题型</span><span class="wb-v">{{ typeLabel(analysis.latest.analysis_json.question_type) }}</span></div>
                    <div class="wb-row"><span class="wb-k">难度</span><span class="wb-v">{{ difficultyLabel(analysis.latest.analysis_json.difficulty) }}（{{ analysis.latest.analysis_json.difficulty ?? '-' }} / 5）</span></div>
                    <div class="wb-row"><span class="wb-k">置信度</span><span class="wb-v">{{ Math.round((analysis.latest.analysis_json.confidence ?? 0) * 100) }}%</span></div>
                    <div class="wb-row">
                      <span class="wb-k">知识点</span>
                      <span class="wb-v">{{ (analysis.latest.analysis_json.knowledge_point_codes || []).join(', ') || '—' }}</span>
                    </div>
                    <div class="wb-subsection wb-ai-answer">
                      <h4>AI 结构化结果</h4>
                      <div class="wb-ai-grid">
                        <div class="wb-ai-field">
                          <span class="wb-ai-label">AI 建议答案</span>
                          <strong>{{ answerSpecLabel(analysis.latest.analysis_json.answer_spec) || '待人工确认' }}</strong>
                        </div>
                        <div class="wb-ai-field" :class="{ 'is-pending': !selectedCand?.original_answer }">
                          <span class="wb-ai-label">答案状态</span>
                          <strong>{{ selectedCand?.original_answer ? (analysis.latest.analysis_json.answer_check?.consistent ? '与原答案一致' : '需要人工核对') : 'PDF 未提供，待人工补录' }}</strong>
                        </div>
                      </div>
                      <div v-if="analysis.latest.analysis_json.answer_check?.reason" class="wb-muted wb-answer-note">{{ analysis.latest.analysis_json.answer_check.reason }}</div>
                      <div v-if="analysis.latest.analysis_json.analysis" class="wb-analysis-block">
                        <span class="wb-ai-label">解题过程</span>
                        <div class="wb-rich-value" v-html="renderMath(analysis.latest.analysis_json.analysis)" />
                      </div>
                      <div v-if="analysis.latest.analysis_json.common_mistakes?.length" class="wb-mistakes">
                        <span class="wb-ai-label">常见错误</span>
                        <ul><li v-for="(mistake, index) in analysis.latest.analysis_json.common_mistakes" :key="index" v-html="renderMath(typeof mistake === 'string' ? mistake : (mistake.description || mistake.reason || JSON.stringify(mistake)))" /></ul>
                      </div>
                      <div v-if="analysis.latest.verifier_json" class="wb-verifier">
                        <span>独立校验：{{ verifierLabel(analysis.latest.verifier_json) }}</span>
                        <span v-if="analysis.latest.verifier_json.issues?.length">{{ analysis.latest.verifier_json.issues.join('；') }}</span>
                      </div>
                      <div v-if="analysis.latest.analysis_json.flags?.length" class="wb-flags">风险标记：{{ analysis.latest.analysis_json.flags.join('、') }}</div>
                    </div>
                  </div>
                  <div v-if="analysis.history?.length > 1" class="wb-history">
                    <span class="wb-k">历史</span>
                    <el-tag v-for="r in analysis.history" :key="r.id" size="small" :type="gateType((r.gate || r.status || '').toUpperCase())" class="wb-history__tag">
                      #{{ r.attempt_no }} {{ gateLabel((r.gate || r.status || '').toUpperCase()) }}
                    </el-tag>
                  </div>
                </template>
                <div v-else class="wb-empty">尚未分析 —— 点击「AI 分析」或先跑批量分析</div>
              </div>
            </template>
            <div v-else class="wb-empty">请选择候选</div>
          </section>

          <!-- 右：PDF 原页预览 -->
          <aside class="wb-col wb-col--preview">
            <div class="wb-preview-head">
              <el-button size="small" :disabled="previewPage <= 1" @click="prevPage">←</el-button>
              <span>第 {{ previewPage }} 页</span>
              <el-button size="small" @click="nextPage">→</el-button>
            </div>
            <div class="wb-preview-body">
              <img v-if="previewUrl" :src="previewUrl" class="wb-preview-img" alt="PDF 原页" />
              <div v-else class="wb-empty">{{ previewErr || '暂无预览' }}</div>
            </div>
          </aside>
        </div>

        <!-- 底部操作条 -->
        <footer class="wb-actions">
          <el-button type="primary" :disabled="!selectedId" @click="analyzeOne">AI 分析</el-button>
          <el-button :disabled="!selectedId" @click="reanalyzeOne">重跑</el-button>
          <el-divider direction="vertical" />
          <el-button type="success" :disabled="!selectedId" @click="setDisposition('approved')">批准</el-button>
          <el-button type="warning" :disabled="!selectedId" @click="setDisposition('doubtful')">存疑</el-button>
          <el-button type="danger" :disabled="!selectedId" @click="setDisposition('reject')">拒绝</el-button>
          <el-divider direction="vertical" />
          <el-button type="primary" plain :disabled="!selectedId" @click="createDraftOne">创建草稿</el-button>
          <el-divider direction="vertical" />
          <el-button @click="runBatchAnalysis">批量 AI 分析（异步）</el-button>
          <el-button @click="batchApprove">批量批准（仅 PASS）</el-button>
          <el-button @click="batchCreateDrafts">批量建草稿</el-button>
        </footer>
      </el-tab-pane>

      <!-- ════ Tab2 题目发布 ════ -->
      <el-tab-pane label="题目发布" name="questions">
        <div class="wb-qbar">
          <el-radio-group v-model="qStatus" size="small" @change="loadQuestions">
            <el-radio-button label="">全部</el-radio-button>
            <el-radio-button label="draft">草稿</el-radio-button>
            <el-radio-button label="reviewed">已审核</el-radio-button>
            <el-radio-button label="published">已发布</el-radio-button>
            <el-radio-button label="retired">已退役</el-radio-button>
          </el-radio-group>
          <el-button size="small" @click="loadQuestions">刷新</el-button>
          <el-button size="small" type="primary" plain @click="batchPublishRows">批量发布选中</el-button>
        </div>
        <el-table :data="questions" size="small" border stripe @selection-change="(rows) => (selectedQids = rows.map((r) => r.id))">
          <el-table-column type="selection" width="40" />
          <el-table-column prop="id" label="ID" width="90" />
          <el-table-column prop="content" label="题干" min-width="240" show-overflow-tooltip />
          <el-table-column label="题型" width="100">
            <template #default="{ row }">{{ typeLabel(row.question_type) }}</template>
          </el-table-column>
          <el-table-column prop="difficulty" label="难度" width="60" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.review_status)" size="small">{{ statusLabel(row.review_status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="300">
            <template #default="{ row }">
              <el-button v-if="row.review_status === 'draft'" size="small" @click="reviewOne(row.id)">审核</el-button>
              <el-button v-if="row.review_status === 'reviewed'" size="small" type="success" @click="publishOne(row.id)">发布</el-button>
              <el-button v-if="row.review_status === 'published'" size="small" type="danger" plain @click="retireOne(row.id)">退役</el-button>
              <el-button v-if="row.review_status === 'retired'" size="small" @click="restoreOne(row.id)">恢复草稿</el-button>
              <el-button size="small" @click="showHistory(row.id)">历史</el-button>
              <el-button size="small" plain @click="reportIssue(row.id)">反馈</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!questions.length" class="wb-empty">暂无题目</div>
      </el-tab-pane>
      <el-tab-pane label="运营质量" name="operations">
        <section class="wb-ops" aria-label="内容质量运营">
          <div class="wb-metrics">
            <article v-for="(count, key) in quality.summary" :key="key" class="wb-metric">
              <span>{{ key }}</span><strong>{{ count }}</strong>
            </article>
            <div v-if="!Object.keys(quality.summary || {}).length" class="wb-empty">当前未发现质量问题</div>
          </div>
          <div class="wb-ops-grid">
            <section class="wb-card">
              <h2 class="wb-card-title">质量审计明细</h2>
              <el-table :data="quality.issues" size="small" max-height="420">
                <el-table-column prop="question_id" label="题目" width="130" />
                <el-table-column label="问题"><template #default="{ row }">{{ row.flags.join('、') }}</template></el-table-column>
                <el-table-column label="操作" width="160"><template #default="{ row }">
                  <template v-if="row.flags.includes('possible_duplicate')">
                    <el-button size="small" @click="decideDuplicate(row, true)">确认</el-button>
                    <el-button size="small" plain @click="decideDuplicate(row, false)">排除</el-button>
                  </template>
                </template></el-table-column>
              </el-table>
            </section>
            <section class="wb-card">
              <h2 class="wb-card-title">待处置反馈</h2>
              <el-table :data="feedback" size="small" max-height="420">
                <el-table-column prop="question_id" label="题目" width="120" />
                <el-table-column prop="description" label="说明" show-overflow-tooltip />
                <el-table-column label="操作" width="100"><template #default="{ row }"><el-button size="small" @click="resolveIssue(row)">处置</el-button></template></el-table-column>
              </el-table>
            </section>
          </div>
        </section>
      </el-tab-pane>
    </el-tabs>
    <el-drawer v-model="history" title="题目修订与审计历史" size="min(620px, 92vw)">
      <el-timeline v-if="history">
        <el-timeline-item v-for="item in history.audits" :key="item.id" :timestamp="item.created_at">
          <strong>{{ item.action }}</strong> {{ item.from_status || '—' }} → {{ item.to_status || '—' }}<p>{{ item.reason }}</p>
        </el-timeline-item>
      </el-timeline>
    </el-drawer>
  </div>
  </AdminShell>
</template>

<style scoped>
/* === 整体固定高度布局：header 固定 / 中部自适应 / footer 吸底 === */
.wb {
  display: flex;
  flex-direction: column;
  height: 100vh;        /* 锁定视口高度，使中部自适应、内部三列可独立滚动 */
  overflow: hidden;     /* 整页不再随内容滚动 */
  background: var(--bg);
  color: var(--ink-1);
  font-family: var(--font-ui);
}
.wb-header { display: flex; align-items: center; gap: 12px; padding: 14px 20px; background: var(--surface); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.wb-back { background: none; border: none; color: var(--accent); cursor: pointer; font-size: var(--type-sm); }
.wb-upload { min-height: 32px; display: inline-flex; align-items: center; padding: 0 12px; border-radius: var(--r-m); background: var(--accent); color: white; cursor: pointer; }
.wb-upload input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.wb-upload.is-disabled { opacity: .55; cursor: not-allowed; }
.wb-import-status { display: flex; flex-direction: column; gap: 6px; padding: 10px 20px; background: var(--surface); border-bottom: 1px solid var(--border); font-size: var(--type-sm); flex-shrink: 0; }
.wb-import-status__head, .wb-import-status__meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.wb-import-status__head { justify-content: space-between; color: var(--ink-1); }
.wb-import-status__head strong { color: var(--accent); }
.wb-import-status__meta { color: var(--ink-2); font-size: var(--type-xs); }
.wb-import-status__error { color: var(--danger); }
.wb-title { font-size: var(--type-lg); margin: 0; font-weight: 500; }
.wb-spacer { flex: 1; }
.wb-tabs { flex: 1 1 0; min-height: 0; padding: 0 20px; display: flex; flex-direction: column; overflow: hidden; }
/* el-tabs 内部三件套：content 必须允许内部滚动 */
.wb-tabs :deep(.el-tabs__content) { flex: 1; min-height: 0; overflow: hidden; }
.wb-tabs :deep(.el-tab-pane) { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.wb-ops { padding: 8px 0 24px; }
.wb-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.wb-metric { display: flex; justify-content: space-between; align-items: center; padding: 14px; border: 1px solid var(--border); border-radius: var(--r-m); background: var(--surface); }
.wb-metric span { color: var(--ink-2); font-size: var(--type-sm); }
.wb-metric strong { font-size: var(--type-xl); font-variant-numeric: tabular-nums; }
.wb-ops-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.wb-task { display: flex; align-items: center; gap: 12px; padding: 10px 0; }
.wb-task .el-progress { flex: 1; }
.wb-task-text { font-size: var(--type-sm); color: var(--ink-2); }
/* === 关键：body 内部三列各自滚动，不再被外面撑高 === */
.wb-body {
  display: grid;
  grid-template-columns: 280px 1fr 300px;
  gap: 12px;
  flex: 1 1 0;          /* 吃掉 header/footer 之外的所有空间 */
  min-height: 0;         /* flex 子项必备：允许内容被压缩触发内部 overflow */
  overflow: hidden;      /* 整 body 不再外溢 */
}
@media (max-width: 900px) {
  .wb-header { flex-wrap: wrap; }
  .wb-tabs { padding: 0 12px; }
  .wb-ops-grid { grid-template-columns: 1fr; }
  .wb-body { grid-template-columns: 1fr; min-height: 0; }
  .wb-col--preview { min-height: 360px; }
}
/* === 三列各自内部滚动（flex 内滚三件套） === */
.wb-col { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-m); padding: 10px; overflow: hidden; min-height: 0; }
.wb-col--list { display: flex; flex-direction: column; }
.wb-filters { display: flex; gap: 6px; margin-bottom: 8px; flex-shrink: 0; }
.wb-candlist { overflow-y: auto; flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 4px; }
.wb-cand { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--r-m); background: none; cursor: pointer; text-align: left; font-size: var(--type-sm); color: var(--ink-1); }
.wb-cand.is-active { border-color: var(--accent); background: var(--accent-soft); }
.wb-cand__idx { font-weight: 500; color: var(--ink-2); }
.wb-cand__type { color: var(--ink-2); }
.wb-col--main { overflow-y: auto; min-height: 0; }
.wb-card { border: 1px solid var(--border); border-radius: var(--r-m); padding: 12px; margin-bottom: 10px; }
.wb-card-title { margin: 0 0 8px; font-size: var(--type-md); font-weight: 500; display: flex; align-items: center; gap: 8px; }
.wb-partial-reasons { color: var(--amber); }
.wb-hint { font-size: var(--type-xs); color: var(--ink-3); font-weight: 400; }
.wb-stem { white-space: normal; margin: 0 0 14px; line-height: 1.85; font-size: 16px; color: var(--ink-1); }
.wb-stem :deep(.katex) { font-size: 1em; }
.wb-stem :deep(p), .wb-rich-value :deep(p) { margin: 0 0 8px; }
.wb-stem :deep(.katex-display), .wb-rich-value :deep(.katex-display) { overflow-x: auto; padding: 4px 0; }
.wb-source-fallback { margin: 0 0 14px; padding: 10px; border: 1px solid var(--amber); border-radius: var(--r-s); background: color-mix(in srgb, var(--amber) 8%, var(--surface)); }
.wb-source-fallback__head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; color: var(--ink-1); }
.wb-source-fallback__head span { color: var(--ink-2); font-size: var(--type-xs); }
.wb-source-fallback__list { display: grid; gap: 10px; }
.wb-source-fallback__figure { margin: 0; padding: 8px; background: #fff; border-radius: 4px; }
.wb-source-fallback__figure figcaption { margin-bottom: 6px; color: var(--ink-2); font-size: var(--type-xs); }
.wb-source-fallback__img { display: block; width: 100%; max-height: 520px; object-fit: contain; object-position: top center; background: #fff; border-radius: 4px; }
.wb-raw-content { white-space: pre-wrap; padding: 10px; background: var(--surface-2); border-radius: var(--r-s); color: var(--ink-2); font-family: var(--font-mono, monospace); line-height: 1.6; }
.wb-options { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.wb-option { display: flex; gap: 8px; align-items: flex-start; padding: 9px 12px; background: var(--surface-2); border-radius: var(--r-s); font-size: 15px; line-height: 1.75; }
.wb-option :deep(.katex) { font-size: 1em; }
.wb-solution { display: block; }
.wb-solution :deep(p) { margin: 4px 0; }
.wb-empty-inline { color: var(--ink-3); }
.wb-row { display: flex; gap: 8px; font-size: var(--type-sm); margin: 3px 0; align-items: flex-start; }
.wb-row :deep(.katex) { font-size: 1em; }
.wb-edit-row { display: flex; align-items: center; gap: 8px; margin: 6px 0; }
.wb-edit-row label { flex-shrink: 0; min-width: 84px; color: var(--ink-2); font-size: var(--type-sm); }
.wb-edit-row .el-input, .wb-edit-row .el-textarea { flex: 1; }
.wb-edit-kp { margin-left: 12px; }
.wb-edit-actions { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.wb-edit-actions .el-alert { flex: 1; margin-left: 4px; }
.wb-k { color: var(--ink-3); flex-shrink: 0; min-width: 90px; }
.wb-v { color: var(--ink-1); word-break: break-all; }
.wb-warn { margin-top: 10px; padding: 9px 10px; background: color-mix(in srgb, var(--amber) 16%, var(--surface)); color: var(--ink-1); border: 1px solid var(--amber); border-radius: var(--r-s); font-size: var(--type-sm); }
.wb-warn ul, .wb-mistakes ul { margin: 6px 0 0 18px; padding: 0; }
.wb-warn li, .wb-mistakes li { margin: 3px 0; }
.wb-subsection { margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border); }
.wb-subsection h4 { margin: 0 0 7px; font-size: var(--type-sm); color: var(--ink-2); }
.wb-rich-value { line-height: 1.8; font-size: 15px; color: var(--ink-1); }
.wb-rich-value :deep(p) { margin: 0 0 10px; }
.wb-rich-value :deep(ul), .wb-rich-value :deep(ol) { margin: 6px 0 10px 22px; }
.wb-rich-value :deep(.katex) { font-size: 1em; }
.wb-muted { color: var(--ink-3); font-size: var(--type-sm); }
.wb-meta-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.wb-meta-grid > div { padding: 8px; background: var(--surface-2); border-radius: var(--r-s); min-width: 0; }
.wb-meta-grid span, .wb-meta-grid strong { display: block; }
.wb-meta-grid span { color: var(--ink-3); font-size: var(--type-xs); margin-bottom: 3px; }
.wb-meta-grid strong { font-size: var(--type-sm); font-weight: 500; word-break: break-word; }
.wb-ai-answer { background: color-mix(in srgb, var(--accent-soft) 50%, var(--surface)); padding: 10px; border-radius: var(--r-s); border-top: 0; }
.wb-ai-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 8px 0; }
.wb-ai-field { padding: 10px 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-s); }
.wb-ai-field.is-pending { border-color: var(--amber); background: color-mix(in srgb, var(--amber) 10%, var(--surface)); }
.wb-ai-label { display: block; margin-bottom: 5px; color: var(--ink-2); font-size: var(--type-xs); font-weight: 600; letter-spacing: .02em; }
.wb-ai-field strong { font-size: 16px; font-weight: 600; }
.wb-answer-note { margin: 8px 0; padding: 7px 9px; background: var(--surface); border-radius: var(--r-s); }
.wb-analysis-block { margin-top: 10px; padding: 10px 12px; background: var(--surface); border-radius: var(--r-s); }
.wb-mistakes { margin-top: 8px; font-size: var(--type-sm); }
.wb-verifier { display: flex; flex-direction: column; gap: 3px; margin-top: 10px; padding: 8px; border-left: 3px solid var(--accent); background: var(--surface); font-size: var(--type-sm); }
.wb-flags { margin-top: 8px; color: var(--amber); font-size: var(--type-sm); }
.wb-json { margin-top: 8px; border-top: 1px dashed var(--border); padding-top: 6px; }
.wb-history { margin-top: 8px; }
.wb-history__tag { margin-right: 4px; }
.wb-empty { padding: 24px; text-align: center; color: var(--ink-3); font-size: var(--type-sm); }
.wb-col--preview { display: flex; flex-direction: column; }
.wb-preview-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; font-size: var(--type-sm); color: var(--ink-2); flex-shrink: 0; }
.wb-preview-body { flex: 1; min-height: 0; overflow: auto; background: var(--surface-2); border-radius: var(--r-m); }
.wb-preview-img { width: 100%; display: block; }
/* === 底部按钮固定吸底，padding-bottom 给 main 让出空间 === */
.wb-actions {
  display: flex; align-items: center; gap: 8px; padding: 10px 0;
  flex-shrink: 0;            /* 永远不被压缩 */
  background: var(--surface);
  border-top: 1px solid var(--border);
  position: sticky;          /* 即便 tab 内部有滚动也吸在视口内 */
  bottom: 0;
  z-index: 5;
  flex-wrap: wrap;
}
.wb-qbar { display: flex; align-items: center; gap: 12px; padding: 10px 0; flex-shrink: 0; }

/* === 流程引导卡：折叠即可 === */
.wb-help { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 8px 14px; background: var(--accent-soft); border: 1px dashed var(--accent); border-radius: var(--r-m); color: var(--ink-2); font-size: var(--type-sm); margin: 10px 0 4px; flex-shrink: 0; }
.wb-help b { color: var(--ink-1); }
.wb-help .wb-help__step { display: inline-flex; align-items: center; gap: 4px; }
.wb-help__num { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: var(--accent); color: #fff; font-size: 11px; font-weight: 600; }
</style>
