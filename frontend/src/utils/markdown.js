import MarkdownIt from 'markdown-it'
import { katex } from '@mdit/plugin-katex'
import DOMPurify from 'dompurify'

/**
 * 给没有 $ 包裹的题干做 LaTeX 启发式标记化。
 *
 * PDF 解析(PyMuPDF)输出的题干常是「1．下列选项中两个函数相同的是（ ）B
 * 2  2A  y = arcsin x + arccos x」—— 公式以 LaTeX 命令形式散落但没 $ 包裹，
 * markdown-it + KaTeX 插件 (delimiters: 'dollars') 不识别。手工预处理：
 * 1. 用占位符把已经存在的 $...$ / $$...$$ 保护起来，避免重复包裹
 * 2. 对 LaTeX 命令 (\frac \sqrt \sum \int \lim \log \ln \sin \cos \tan \arcsin
 *    \arccos \arctan \lg 等) 及其后跟随的 {...} 参数 / 上下标包成 $...$
 * 3. 行内分数 a/b 用正则识别（仅限两边是简单 ASCII 字母/数字/空格）
 * 4. 还原占位符
 */
function autoWrapLatex(text) {
  if (!text) return ''
  const placeholders = []
  const stash = (s) => {
    const i = placeholders.push(s) - 1
    return `\x00MATH${i}\x00`
  }
  // 1. 保护已有公式
  let s = text.replace(/\$\$[\s\S]*?\$\$/g, (m) => stash(m))
  s = s.replace(/\$[^\$\n]+?\$/g, (m) => stash(m))
  // 2. 常见 LaTeX 命令 + 它的 {...} / 上下标 参数
  const cmd = 'frac|sqrt|sum|int|lim|log|ln|sin|cos|tan|arcsin|arccos|arctan|lg|tan|sec|csc|cot|sinh|cosh|tanh|overline|underline|vec|hat|bar|tilde|cdot|times|div|pm|mp|leq|geq|neq|approx|equiv|infty|partial|nabla|to|rightarrow|leftarrow|Rightarrow|Leftarrow|in|notin|subset|supset|cup|cap|forall|exists|mathbf|mathrm|mathit|mathcal|mathbb|text|operatorname'
  // 2a. \cmd{...}{...}（一或两个 {...}）
  s = s.replace(new RegExp(`(\\\\(?:${cmd})(?:\\s*\\{[^}\\n]{1,80}\\}){1,3})`, 'g'), (m) => `$${m}$`)
  // 2b. \cmd 单独出现（前后是空格/标点）
  s = s.replace(new RegExp(`(\\\\(?:${cmd}))(?=[\\s,，。.;；!！?？:：)\\]）]|$)`, 'gm'), (m) => `$${m}$`)
  // 3. 行内分数 a/b（a/b 都是 1-4 位的字母/数字）
  s = s.replace(/(^|[^A-Za-z0-9\u4e00-\u9fa5]|[（(])([A-Za-z0-9\u4e00-\u9fa5]{1,4})\s*[／/]\s*([A-Za-z0-9\u4e00-\u9fa5]{1,4})(?=$|[^A-Za-z0-9\u4e00-\u9fa5])/g,
    (m, pre, a, b) => `${pre}$${a}/${b}$`)
  // 4. 还原占位符
  s = s.replace(/\x00MATH(\d+)\x00/g, (_, i) => placeholders[Number(i)])
  return s
}

// ============ markdown-it 实例（含 KaTeX 公式渲染） ============
// 使用 @mdit/plugin-katex 一站式完成 Markdown 解析 + KaTeX 公式渲染
// 插件在 markdown 解析阶段直接调用 katex.renderToString()，
// 输出的 HTML 已包含完整渲染后的公式，无需二次处理

const md = new MarkdownIt({
  html: true,
  linkify: true,
  breaks: true,
  typographer: true,
})

// 注册 KaTeX 插件 — 自动识别 $...$ 和 $$...$$ 并渲染为 HTML
md.use(katex, {
  delimiters: 'dollars',
  throwOnError: false,
  strict: false,
})

// ============ 代码块渲染 ============
md.renderer.code = function (tokens, idx) {
  const token = tokens[idx]
  const lang = (token.info || '').match(/\S*/)[0]
  return `<pre class="highlight"><code class="language-${md.utils.escape(lang)}">${md.utils.escapeHtml(token.content)}</code></pre>\n`
}

// ============ DOMPurify 配置 ============
const purifyOptions = {
  ALLOWED_TAGS: [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'hr',
    'ul', 'ol', 'li',
    'strong', 'em', 'b', 'i', 'u', 's', 'del',
    'blockquote', 'pre', 'code',
    'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'div', 'span',
    'sup', 'sub',
  ],
  ALLOWED_ATTR: [
    'href', 'target', 'rel',
    'src', 'alt', 'title', 'width', 'height',
    'class', 'id', 'style',
    'start', 'type',
    'xmlns', 'viewBox', 'd', 'fill', 'stroke', 'stroke-width',
    'cx', 'cy', 'r', 'x', 'y', 'x1', 'y1', 'x2', 'y2',
    'dx', 'dy', 'text-anchor', 'font-family', 'font-size', 'font-style',
    'font-weight', 'line-height', 'spacing', 'accent', 'baseline-shift',
    'clip-path', 'depth', 'maxsize', 'minsize', 'size',
    'aria-label', 'role', 'semantics', 'namespace',
  ],
  ADD_ATTR: ['target'],
  ADD_TAGS: [
    'math', 'mrow', 'mo', 'mi', 'mn', 'msup', 'msub', 'msubsup',
    'mfrac', 'mover', 'munder', 'munderover', 'msqrt', 'mroot',
    'menclose', 'mstyle', 'annotation', 'semantics', 'svg', 'path',
    'use', 'g', 'line', 'rect', 'polygon', 'circle', 'ellipse',
    'text', 'tspan', 'foreignObject', 'mglyph', 'mpadded', 'mphantom',
    'mtable', 'mtr', 'mtd', 'mlabeledtr', 'maction',
  ],
}

const streamPurifyOptions = {
  ALLOWED_TAGS: [
    'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'em', 'b', 'i', 'u', 's', 'del',
    'code', 'blockquote',
    'ul', 'ol', 'li',
    'div', 'span',
    'sup', 'sub',
    'hr',
  ],
  ALLOWED_ATTR: ['class', 'style', 'xmlns', 'viewBox', 'd', 'fill',
    'stroke', 'stroke-width', 'cx', 'cy', 'r', 'x', 'y',
    'x1', 'y1', 'x2', 'y2', 'dx', 'dy', 'text-anchor',
    'font-family', 'font-size', 'font-style', 'font-weight',
    'line-height', 'spacing', 'accent', 'baseline-shift',
    'clip-path', 'depth', 'height', 'maxsize', 'minsize', 'size',
    'aria-label', 'role', 'semantics', 'width', 'id',
    'xmlns:xlink', 'href'],
  ADD_TAGS: ['math', 'mrow', 'mo', 'mi', 'mn', 'msup', 'msub', 'msubsup',
    'mfrac', 'mover', 'munder', 'munderover', 'msqrt', 'mroot',
    'menclose', 'mstyle', 'annotation', 'semantics', 'svg', 'path',
    'use', 'g', 'line', 'rect', 'polygon', 'circle', 'ellipse',
    'text', 'tspan', 'foreignObject', 'mglyph', 'mpadded', 'mphantom',
    'mtable', 'mtr', 'mtd', 'mlabeledtr', 'maction', 'katex-block'],
}

/**
 * 转义 HTML 特殊字符（降级兜底）
 */
function escape(html) {
  return html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 渲染 Markdown 文本为安全的 HTML（含数学公式）
 *
 * 流程：自动包裹 LaTeX 命令 → Markdown 解析 + KaTeX 公式渲染 → DOMPurify 净化
 * 若文本里没有 $ 标记，会先用 autoWrapLatex 启发式把 \frac \sqrt \sin 等命令包起来
 */
export function renderMarkdown(text) {
  if (!text) return ''

  try {
    const wrapped = autoWrapLatex(String(text))
    let html = md.render(wrapped)
    const cleanHtml = DOMPurify.sanitize(html, purifyOptions)
    return cleanHtml
  } catch (error) {
    console.error('[markdown] 渲染异常:', error)
    return DOMPurify.sanitize(`<p>${escape(text)}</p>`)
  }
}

/**
 * 格式化流式输出文本（轻量版）
 *
 * 用于 AI 打字机效果场景，在内容持续变化时提供快速格式化。
 * 同样使用 markdown-it + KaTeX 插件，确保公式一致性。
 */
export function formatStreamText(text) {
  if (!text) return ''

  try {
    let html = md.render(text)
    return DOMPurify.sanitize(html, streamPurifyOptions)
  } catch (error) {
    console.error('[markdown] 流式文本格式化异常:', error)
    return text
  }
}