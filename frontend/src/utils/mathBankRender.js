/**
 * 题库题目渲染：题干/选项可能带 $...$ LaTeX 标记（走 markdown+KaTeX），
 * 也可能是 PDF 解析器输出的纯 unicode 数学文本（整段 KaTeX displayMode，
 * 失败片段降级为可读文本，不显示红字错误）。
 */
import katex from 'katex'
import { renderMarkdown } from '@/utils/markdown'

export function renderMathBank(text) {
  if (!text) return ''
  const s = String(text)
  try {
    if (/\$/.test(s)) return renderMarkdown(s)
    let html = katex.renderToString(s, {
      displayMode: true,
      throwOnError: false,
      strict: 'ignore',
      output: 'html',
      errorColor: '',
      minRuleThickness: 0.04,
    })
    const openTag = '<span class="katex-error"'
    let result = ''
    let cursor = 0
    while (cursor < html.length) {
      const idx = html.indexOf(openTag, cursor)
      if (idx < 0) {
        result += html.slice(cursor)
        break
      }
      result += html.slice(cursor, idx)
      const endIdx = html.indexOf('</span>', idx)
      if (endIdx < 0) {
        result += html.slice(idx)
        break
      }
      const innerHTML = html.slice(idx, endIdx + 7)
      const innerText = innerHTML
        .replace(/<[^>]+title="[^"]*"[^>]*>/g, '')
        .replace(/<[^>]+>/g, '')
      result += innerText
      cursor = endIdx + 7
    }
    return result
  } catch {
    return s.replace(/[<>&"']/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c]))
  }
}
