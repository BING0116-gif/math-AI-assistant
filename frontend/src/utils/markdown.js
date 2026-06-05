import MarkdownIt from 'markdown-it'
import { katex } from '@mdit/plugin-katex'
import DOMPurify from 'dompurify'
import latexPreprocessor from './latexPreprocessor'

// ============ markdown-it 实例（含 KaTeX 公式渲染） ============
// 核心变更：用官方 @mdit/plugin-katex 替代自建 latexPreprocessor + mathRender
// 原理：插件在 markdown 解析阶段直接调用 katex.renderToString()，
//       输出的 HTML 已包含完整渲染后的公式，无需二次处理

const md = new MarkdownIt({
  html: true,        // 允许 HTML（AI 输出可能包含）
  linkify: true,     // 自动识别链接
  breaks: true,      // 换行符转 <br>
  typographer: true  // 排版优化
})

// 注册 KaTeX 插件 — 自动识别 $...$ 和 $$...$$ 并渲染为 HTML
// 注意：delimiters 是字符串枚举 ("dollars"|"brackets"|"all")，不是 KaTeX auto-render 的数组格式
md.use(katex, {
  delimiters: 'dollars',  // $...$ 行内公式, $$...$$ 块级公式（默认值，显式声明）
  throwOnError: false,    // 渲染失败时显示原始文本而非报错
  strict: false           // 宽松模式，兼容 LLM 输出中的不严格 LaTeX
})

// ============ 代码块渲染（无语法高亮） ============
// 如需代码高亮，可安装 highlight.js 并配置 md.set({ highlight: ... })
md.renderer.code = function(tokens, idx) {
  const token = tokens[idx]
  const lang = (token.info || '').match(/\S*/)[0]
  return `<pre class="highlight"><code class="language-${md.utils.escape(lang)}">${md.utils.escapeHtml(token.content)}</code></pre>\n`
}

// ============ DOMPurify 配置 ============
// KaTeX 渲染产物包含大量 MathML/SVG 标签，必须在白名单中保留
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
    'sup', 'sub'
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
    'aria-label', 'role', 'semantics', 'namespace'
  ],
  ADD_ATTR: ['target'],
  // KaTeX 生成的数学公式标签白名单
  ADD_TAGS: [
    'math', 'mrow', 'mo', 'mi', 'mn', 'msup', 'msub', 'msubsup',
    'mfrac', 'mover', 'munder', 'munderover', 'msqrt', 'mroot',
    'menclose', 'mstyle', 'annotation', 'semantics', 'svg', 'path',
    'use', 'g', 'line', 'rect', 'polygon', 'circle', 'ellipse',
    'text', 'tspan', 'foreignObject', 'mglyph', 'mpadded', 'mphantom',
    'mtable', 'mtr', 'mtd', 'mlabeledtr', 'maction'
  ]
}

// 流式文本使用的简化版净化配置
const streamPurifyOptions = {
  ALLOWED_TAGS: [
    'p', 'br', 'h1', 'h2', 'h3',
    'strong', 'em', 'code',
    'div', 'span'
  ],
  ALLOWED_ATTR: ['class', 'style', 'xmlns', 'viewBox', 'd', 'fill',
    'stroke', 'stroke-width', 'cx', 'cy', 'r', 'x', 'y',
    'x1', 'y1', 'x2', 'y2', 'dx', 'dy', 'text-anchor',
    'font-family', 'font-size', 'font-style', 'font-weight',
    'line-height', 'spacing', 'accent', 'baseline-shift',
    'clip-path', 'depth', 'height', 'maxsize', 'minsize', 'size',
    'aria-label', 'role', 'semantics', 'width', 'id'],
  ADD_TAGS: ['math', 'mrow', 'mo', 'mi', 'mn', 'msup', 'msub', 'msubsup',
    'mfrac', 'mover', 'munder', 'munderover', 'msqrt', 'mroot',
    'menclose', 'mstyle', 'annotation', 'semantics', 'svg', 'path',
    'use', 'g', 'line', 'rect', 'polygon', 'circle', 'ellipse',
    'text', 'tspan', 'foreignObject', 'mglyph', 'mpadded', 'mphantom',
    'mtable', 'mtr', 'mtd', 'mlabeledtr', 'maction']
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
 * 使用 markdown-it + @mdit/plugin-katex 一站式完成：
 *   Markdown 解析 → KaTeX 公式渲染 → HTML 输出 → DOMPurify 净化
 * 无需额外的 latexPreprocessor 或 renderMathInElement 二次调用
 */
export function renderMarkdown(text) {
  if (!text) return ''

  try {
    // 预处理：给裸 LaTeX（无 $ 包裹的 \frac, \begin{pmatrix} 等）自动添加定界符
    const preprocessed = latexPreprocessor.process(text)
    let html = md.render(preprocessed)

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
    // 预处理：给裸 LaTeX 自动添加定界符（流式场景同样需要）
    const preprocessed = latexPreprocessor.process(text)
    let html = md.render(preprocessed)

    return DOMPurify.sanitize(html, streamPurifyOptions)
  } catch (error) {
    console.error('[markdown] 流式文本格式化异常:', error)
    return text
  }
}
