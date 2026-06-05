const LATEX_COMMANDS = [
  '\\frac', '\\sqrt', '\\sum', '\\prod', '\\int', '\\lim', '\\oint',
  '\\iint', '\\iiint', '\\idotsint', '\\binom', '\\dfrac', '\\tfrac',
  '\\sin', '\\cos', '\\tan', '\\cot', '\\sec', '\\csc',
  '\\arcsin', '\\arccos', '\\arctan',
  '\\sinh', '\\cosh', '\\tanh', '\\coth',
  '\\log', '\\ln', '\\exp',
  '\\min', '\\max', '\\sup', '\\inf', '\\det', '\\dim', '\\ker', '\\hom',
  '\\arg', '\\deg', '\\gcd', '\\lcm',

  '\\alpha', '\\beta', '\\gamma', '\\delta', '\\epsilon', '\\zeta',
  '\\eta', '\\theta', '\\iota', '\\kappa', '\\lambda', '\\mu',
  '\\nu', '\\xi', '\\pi', '\\rho', '\\sigma', '\\tau',
  '\\upsilon', '\\phi', '\\chi', '\\psi', '\\omega',
  '\\Gamma', '\\Delta', '\\Theta', '\\Lambda', '\\Xi',
  '\\Pi', '\\Sigma', '\\Upsilon', '\\Phi', '\\Psi', '\\Omega',
  '\\infty', '\\partial', '\\nabla', '\\forall', '\\exists', '\\emptyset',

  '\\in', '\\notin', '\\subset', '\\supset', '\\subseteq', '\\supseteq',
  '\\cup', '\\cap', '\\land', '\\lor', '\\neg',
  '\\Rightarrow', '\\Leftarrow', '\\Leftrightarrow',
  '\\equiv', '\\approx', '\\neq', '\\leq', '\\geq',
  '\\sim', '\\simeq', '\\cong', '\\perp', '\\parallel',
  '\\cdot', '\\times', '\\div', '\\pm', '\\mp',
  '\\ldots', '\\cdots', '\\vdots', '\\ddots', '\\dots',

  '\\text', '\\mathrm', '\\mathbf', '\\mathcal', '\\mathbb',
  '\\textbf', '\\textrm', '\\textit', '\\mathrm',
  '\\vec', '\\hat', '\\bar', '\\tilde', '\\dot', '\\ddot',
  '\\widetilde', '\\widehat',
  '\\overline', '\\underline', '\\overbrace', '\\underbrace',
  '\\left', '\\right',
  '\\begin', '\\end',

  '\\quad', '\\qquad',
  ';', ':', ',', ' ', '!',
  '\\colon',
  '\\prime',
  '\\bm', '\\boldsymbol',
  '\\not',
  '\\cancel', '\\bcancel', '\\xcancel',
  '\\tag', '\\label', '\\ref', '\\nonumber',
  '\\big', '\\Big', '\\bigg', '\\Bigg',
  '\\bigl', '\\bigr', '\\Bigl', '\\Bigr', '\\biggl', '\\biggr', '\\Biggl', '\\Biggr',
  '\\matrix', '\\bmatrix', '\\vmatrix', '\\Vmatrix',
  '\\array', '\\cases', '\\aligned', '\\gathered',
  '\\operatorname', '\\DeclareMathOperator',
  '\\hline', '\\cline', '\\midrule', '\\toprule', '\\bottomrule',
  '\\hspace', '\\vspace',
  '\\rule',
  '\\color', '\\colorbox', '\\fcolorbox',
  '\\boxed',
  '\\over', '\\overwithdelims', '\\atop', '\\choose',
  '\\phantom', '\\smash',
  '\\href', '\\url',
  '\\toggle', '\\notag', '\\eqref',
  '\\overset', '\\underset',
  '\\stackrel',
  '\\substack',
  '\\sideset',
  '\\dotsc', '\\dotsb', '\\dotsm', '\\dotsi', '\\dotso',
  '\\mod', '\\bmod', '\\pod', '\\pmod',
]

const LATEX_COMMAND_SET = new Set(LATEX_COMMANDS)

function isInsideMathFromSegments(segments) {
  let dollarCount = 0
  for (const seg of segments) {
    if (seg.type === 'math') {
      for (let j = 0; j < seg.content.length; j++) {
        if (seg.content[j] === '$' && (j === 0 || seg.content[j - 1] !== '\\')) {
          dollarCount++
        }
      }
    }
  }
  return dollarCount % 2 !== 0
}

function findBraceEnd(text, startPos) {
  let depth = 0
  let i = startPos
  while (i < text.length) {
    const ch = text[i]
    if (ch === '\\' && i + 1 < text.length) {
      i += 2
      continue
    }
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth <= 0) return i + 1
    }
    i++
  }
  return text.length
}

function extractBareLatexSpan(text, startPos) {
  let end = startPos
  let braceDepth = 0
  let hasContent = false
  const MAX_SPAN_LENGTH = 80 // 防止过度提取：裸LaTeX span 最大长度

  while (end < text.length && end - startPos < MAX_SPAN_LENGTH) {
    const ch = text[end]

    // 安全检查：遇到连续3个以上相同字母时停止（如 AAAAA, yyyyy）
    if (end >= startPos + 2 && ch === text[end - 1] && ch === text[end - 2] && /[a-zA-Z]/.test(ch)) {
      // 检查是否为连续重复（3+个相同字符）
      let repeatCount = 3
      while (end + repeatCount - startPos < MAX_SPAN_LENGTH &&
             end + repeatCount < text.length &&
             text[end + repeatCount] === ch) {
        repeatCount++
      }
      // 如果是纯重复字母序列（3+个），停止提取
      if (repeatCount >= 3) break
    }

    // 遇到中文标点或中文+空格组合时停止
    if (/[\u4e00-\u9fa5，。！？、；：""''【】《》（）…—·]/.test(ch) && braceDepth === 0) {
      break
    }

    if (ch === '\\' && end + 1 < text.length) {
      const nextCh = text[end + 1]

      if (/[a-zA-Z]/.test(nextCh)) {
        let cmdEnd = end + 1
        while (cmdEnd < text.length && /[a-zA-Z]/.test(text[cmdEnd])) {
          cmdEnd++
        }
        const cmd = text.substring(end, cmdEnd)

        if (LATEX_COMMAND_SET.has(cmd) || cmd === '\\left' || cmd === '\\right' ||
            cmd === '\\begin' || cmd === '\\end' ||
            /^[a-zA-Z]+$/.test(cmd.substring(1)) && cmd.length > 2) {
          hasContent = true
          end = cmdEnd

          if (end < text.length && text[end] === '{') {
            const braceEnd = findBraceEnd(text, end)
            end = braceEnd
          } else if (end < text.length && /[\w\d]/.test(text[end])) {
            end++
          }
          continue
        }

        break
      }

      if (nextCh === '(' || nextCh === '[' || nextCh === ')' || nextCh === ']') {
        hasContent = true
        end += 2
        continue
      }

      if (nextCh === ' ') {
        end += 2
        continue
      }

      break
    }

    if (ch === '{') {
      braceDepth++
      hasContent = true
      end++
      continue
    }

    if (ch === '}') {
      braceDepth--
      end++
      if (braceDepth < 0) break
      continue
    }

    if (ch === '_' || ch === '^') {
      hasContent = true
      end++

      if (end < text.length && text[end] === '{') {
        const braceEnd = findBraceEnd(text, end)
        end = braceEnd
        continue
      }

      while (end < text.length && (/[\w\d]/.test(text[end]) || text[end] === '\\')) {
        if (text[end] === '\\' && end + 1 < text.length && /[a-zA-Z]/.test(text[end + 1])) {
          let ce = end + 1
          while (ce < text.length && /[a-zA-Z]/.test(text[ce])) ce++
          end = ce
          if (end < text.length && text[end] === '{') {
            end = findBraceEnd(text, end)
          }
        } else {
          end++
        }
      }
      continue
    }

    if (/[0-9]/.test(ch)) {
      if (braceDepth > 0 || hasContent) {
        end++
        continue
      }
      break
    }

    if (/[+\-=<>|,.\s]/.test(ch)) {
      if (hasContent || braceDepth > 0) {
        end++
        continue
      }
      break
    }

    if (/[a-zA-Z']/.test(ch)) {
      if (braceDepth > 0) {
        end++
        continue
      }
      break
    }

    if (ch === '!' || ch === '?') {
      if (hasContent) {
        end++
        continue
      }
      break
    }

    break
  }

  while (end > startPos && /[+\-=<>|,\s!?.]/.test(text[end - 1]) && braceDepth === 0) {
    end--
  }

  return Math.max(end, startPos + 1)
}

function fixDoubleEscape(text) {
  return text.replace(/\\\\([a-zA-Z]+)/g, (match, cmd) => {
    if (LATEX_COMMAND_SET.has('\\' + cmd)) {
      return '\\' + cmd
    }
    return match
  })
}

function wrapBareLatex(text) {
  const segments = []
  let i = 0

  while (i < text.length) {
    if (text[i] === '$') {
      let end = i + 1
      if (end < text.length && text[end] === '$') {
        end++
        let depth = 1
        while (end < text.length && depth > 0) {
          if (text[end] === '$' && text[end - 1] !== '\\') {
            depth--
            if (depth === 0) { end++; break }
          } else if (text[end] === '$' && end + 1 < text.length && text[end + 1] === '$' && depth === 1) {
            depth--
            end++
            if (depth === 0) { end++; break }
          }
          end++
        }
        if (depth > 0) end = text.length
      } else {
        while (end < text.length) {
          if (text[end] === '$' && text[end - 1] !== '\\') {
            end++
            break
          }
          end++
        }
      }
      segments.push({ type: 'math', content: text.substring(i, end) })
      i = end
      continue
    }

    if (text[i] === '\\' && i + 1 < text.length) {
      const nextCh = text[i + 1]

      if (/[a-zA-Z]/.test(nextCh)) {
        let cmdEnd = i + 1
        while (cmdEnd < text.length && /[a-zA-Z]/.test(text[cmdEnd])) {
          cmdEnd++
        }
        const cmd = text.substring(i, cmdEnd)

        // 提高门槛：只对已知LaTeX命令进行包裹，避免误识别普通文本
        if (LATEX_COMMAND_SET.has(cmd) || cmd === '\\left' || cmd === '\\right' ||
            cmd === '\\begin' || cmd === '\\end') {
          if (!isInsideMathFromSegments(segments)) {
            const spanEnd = extractBareLatexSpan(text, i)
            const bareContent = text.substring(i, spanEnd)
            // 增加最小内容质量门槛：至少包含一个已知的LaTeX命令或特殊字符
            const hasSubstantialMathContent = /\\(frac|sqrt|sum|prod|int|lim|sin|cos|tan|log|ln|exp|alpha|beta|gamma|delta|theta|lambda|pi|sigma|phi|psi|omega|infty|partial|nabla|left|right|begin|end|cdot|times|pm|mp|ldots|cdots|vdots|ddots|dots|text|mathrm|mathbf|mathcal|mathbb|vec|hat|bar|tilde|dot|overline|underline)/.test(bareContent)
              || /[_^{}]/.test(bareContent)

            if (bareContent.trim().length > 0 && hasSubstantialMathContent) {
              // 额外质量检查：LaTeX命令占比不能太低（防止长文本中夹杂单个命令被整体包裹）
              const latexCmdCount = (bareContent.match(/\\[a-zA-Z]+/g) || []).length
              const totalLength = bareContent.length
              // 要求：每20个字符至少有1个LaTeX命令，或总长度不超过30
              const latexDensityOk = totalLength <= 30 || (latexCmdCount / (totalLength / 20)) >= 1

              if (latexDensityOk) {
                const isDisplay = shouldUseDisplayMode(bareContent, text, i)
                if (isDisplay) {
                  segments.push({ type: 'math', content: '$$' + bareContent + '$$' })
                } else {
                  segments.push({ type: 'math', content: '$' + bareContent + '$' })
                }
                i = spanEnd
                continue
              }
              // LaTeX密度不足，不包裹，作为普通文本处理
            }
          }
        }
      }

      if ((nextCh === '(' || nextCh === ')' || nextCh === '[' || nextCh === ']') &&
          !isInsideMathFromSegments(segments)) {
        let delimEnd = i + 2
        const isDisplay = nextCh === '[' || nextCh === ']'
        const closeChar = (nextCh === '(') ? ')' : (nextCh === '[') ? ']' : (nextCh === ')') ? '(' : '['

        let depth = 1
        while (delimEnd < text.length && depth > 0) {
          if (text[delimEnd] === '\\' && delimEnd + 1 < text.length) {
            delimEnd += 2
            continue
          }
          if (text[delimEnd] === closeChar) {
            depth--
            if (depth === 0) { delimEnd++; break }
          } else if (text[delimEnd] === nextCh) {
            depth++
          }
          delimEnd++
        }

        const content = text.substring(i, delimEnd)
        if (isDisplay) {
          segments.push({ type: 'math', content: '$$' + content.replace(/\\[\(\)]/g, '').replace(/\\[\[\]]/g, '') + '$$' })
        } else {
          segments.push({ type: 'math', content: '$' + content.replace(/\\[\(\)]/g, '') + '$' })
        }
        i = delimEnd
        continue
      }
    }

    if ((text[i] === '^' || text[i] === '_') && !isInsideMathFromSegments(segments)) {
      if (i + 1 < text.length && /[\{\\a-zA-Z\d]/.test(text[i + 1])) {
        const spanEnd = extractBareLatexSpan(text, i)
        const bareContent = text.substring(i, spanEnd)
        // 严格门槛：_ ^ 触发的包裹必须包含实际LaTeX命令（不仅仅是字母+下标）
        // 最小长度3且必须包含反斜杠命令或花括号
        const hasRealMathContent = /\\[a-zA-Z]+/.test(bareContent) || /\{[^{}]+\}/.test(bareContent)
        if (bareContent.length >= 3 && hasRealMathContent) {
          segments.push({ type: 'math', content: '$' + bareContent + '$' })
          i = spanEnd
          continue
        }
      }
    }

    if (segments.length === 0) {
      segments.push({ type: 'text', content: text[i] })
    } else if (segments[segments.length - 1].type === 'text') {
      segments[segments.length - 1].content += text[i]
    } else {
      segments.push({ type: 'text', content: text[i] })
    }
    i++
  }

  return segments.map(s => s.content).join('')
}

function shouldUseDisplayMode(match, fullText, position) {
  if (/\\begin\{/.test(match)) return true

  if (/^\$\$/.test(match) || match.includes('$$')) return true

  const lineStart = fullText.lastIndexOf('\n', position - 1)
  const lineEnd = fullText.indexOf('\n', position)
  const currentLine = fullText.substring(lineStart + 1, lineEnd === -1 ? fullText.length : lineEnd).trim()

  if (/^\\(begin|\[|\()/ .test(currentLine) || /^(\$|\.\.\.)/.test(currentLine)) {
    return true
  }

  if (match.length > 50) return true

  if (/\\\\/.test(match)) return true

  if ((match.match(/\\frac/g) || []).length > 1) return true

  if (match.includes('\\begin{matrix}') || match.includes('\\begin{pmatrix}') ||
      match.includes('\\begin{bmatrix}') || match.includes('\\begin{vmatrix}') ||
      match.includes('\\begin{Vmatrix}') || match.includes('\\begin{cases}')) {
    return true
  }

  return false
}

function normalizeDelimiters(text) {
  let result = text

  result = result.replace(/\\\[/g, '$$')
  result = result.replace(/\\\]/g, '$$')
  result = result.replace(/\\\(/g, '$')
  result = result.replace(/\\\)/g, '$')

  return result
}

function fixSpecialCharacters(text) {
  let result = text

  result = result.replace(/(?<!\\)(\d)%/g, '$1\\%')
  result = result.replace(/&nbsp;/g, ' ')

  return result
}

function fixUnclosedDelimiters(text) {
  let result = text

  const openBrace = (result.match(/\{/g) || []).length
  const closeBrace = (result.match(/\}/g) || []).length
  if (openBrace > closeBrace) {
    result += '}'.repeat(openBrace - closeBrace)
  }

  return result
}

function balanceDollarSigns(text) {
  let dollarPositions = []
  let inEscape = false

  for (let i = 0; i < text.length; i++) {
    if (text[i] === '\\' && !inEscape) {
      inEscape = true
      continue
    }
    if (text[i] === '$' && !inEscape) {
      dollarPositions.push(i)
    }
    inEscape = false
  }

  if (dollarPositions.length % 2 !== 0) {
    const lastDollar = dollarPositions[dollarPositions.length - 1]
    return text.substring(0, lastDollar + 1) + '$' + text.substring(lastDollar + 1)
  }

  return text
}

function fixStreamingIncomplete(text) {
  let result = text

  const beginMatches = [...result.matchAll(/\\begin\{(\w+)\}/g)]
  const beginCount = beginMatches.length
  const endCount = (result.match(/\\end\{/g) || []).length

  if (beginCount > endCount) {
    const envStack = beginMatches.map(m => m[1])
    for (let i = endCount; i < beginCount; i++) {
      const env = envStack[i]
      if (env) {
        result += `\\end{${env}}`
      }
    }
  }

  return result
}

function catchAllWrap(text) {
  // 跳过已经在 $...$ 或 $$...$$ 定界符内的内容，避免双重包裹
  const segments = []
  const delimiterRegex = /\$\$[\s\S]*?\$\$|\$[^\$\n]+?\$/g
  let lastIndex = 0
  let match

  while ((match = delimiterRegex.exec(text)) !== null) {
    // 将定界符之前的部分作为普通文本段
    if (match.index > lastIndex) {
      segments.push({ type: 'text', start: lastIndex, end: match.index })
    }
    // 标记已包裹的数学段
    segments.push({ type: 'math', start: match.index, end: match.index + match[0].length })
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    segments.push({ type: 'text', start: lastIndex, end: text.length })
  }

  // 只对非数学段（type: 'text'）应用 catchAllWrap 逻辑
  let result = text
  // 从后往前替换，避免索引偏移
  const processedRanges = []

  for (const seg of segments) {
    if (seg.type !== 'math') {
      const segmentText = text.substring(seg.start, seg.end)

      const mathPattern = /\\(?:begin\{[\w]*\}|end\{[\w]*\})|[a-zA-Z]*(?:\\(?:frac|sqrt|sum|prod|int|lim|sin|cos|tan|log|ln|exp|alpha|beta|gamma|delta|theta|lambda|pi|sigma|phi|psi|omega|infty|partial|nabla|left|right|cdot|times|pm|mp|ldots|cdots|vdots|ddots|dots|text|mathrm|mathbf|mathcal|mathbb|vec|hat|bar|tilde|dot|overline|underline|overbrace|underbrace|quad|qquad|prime|bm|boldsymbol|cancel|bcancel|xcancel|boxed|overset|underset|stackrel|substack|sideset|dotsc|dotsb|dotsm|dotsi|dotso|mod|bmod|pod|pmod|operatorname|DeclareMathOperator)[a-zA-Z]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})*(?:[_^](?:\{[^{}]*\}|[\w\d]))*)+|[a-zA-Z]_(?:\{[^{}]*\}|[\w\d])|[a-zA-Z]\^(?:\{[^{}]*\}|[\w\d])|\\\([^)]+\)|\\\[[^\]]+\]/g

      let segMatch
      while ((segMatch = mathPattern.exec(segmentText)) !== null) {
        const matched = segMatch[0]
        // 过滤太短的匹配（单个反斜杠命令但无实质内容）
        if (matched.trim().length <= 2) continue

        // 过滤纯单字母/短字母数字匹配（如 "A", "AB", "B2" — 这些不是有意义的裸LaTeX）
        if (/^[a-zA-Z][a-zA-Z\d]?$/.test(matched.trim())) continue

        // 过滤重复字符主导的匹配（如 AAAAAAA, yyyyyyy）
        const repeatPattern = /(.)\1{4,}/  // 5+个相同字符连续出现
        if (repeatPattern.test(matched)) {
          // 检查是否超过30%的长度是重复字符
          const repeatMatches = matched.match(/(.)\1{2,}/g) || []
          const repeatLength = repeatMatches.reduce((sum, m) => sum + m.length, 0)
          if (repeatLength > matched.length * 0.3) continue
        }

        const absPos = seg.start + segMatch.index

        // 检查是否已经在 $ 定界符附近（前后各看5个字符）
        const beforeArea = text.substring(Math.max(0, absPos - 5), absPos)
        const afterArea = text.substring(absPos + matched.length, Math.min(text.length, absPos + matched.length + 5))

        // 如果前后已经有未闭合的 $ 符号，跳过
        const dollarBefore = (beforeArea.match(/\$/g) || []).length
        const dollarAfter = (afterArea.match(/\$/g) || []).length
        if (dollarBefore % 2 !== 0 || dollarAfter % 2 !== 0) continue

        // 检查不与已有范围重叠
        let overlaps = false
        for (const [start, end] of processedRanges) {
          if (!(absPos >= end || absPos + matched.length <= start)) {
            overlaps = true
            break
          }
        }
        if (!overlaps && matched.trim().length > 1) {
          processedRanges.push([absPos, absPos + matched.length])
        }
      }
    }
  }

  processedRanges.sort((a, b) => b[0] - a[0])

  for (const [start, end] of processedRanges) {
    const content = result.substring(start, end).trim()
    if (content.length > 1) {
      const wrapped = '$' + content + '$'
      result = result.substring(0, start) + wrapped + result.substring(end)
    }
  }

  return result
}

export class LatexPreprocessor {
  constructor(config = {}) {
    this.config = {
      enableLogging: config.enableLogging || false,
      ...config,
    }
    this.stats = {
      totalProcessed: 0,
      wrappedCount: 0,
      fixedCount: 0,
    }
  }

  process(text) {
    if (!text || typeof text !== 'string') return text || ''

    const startTime = this.config.enableLogging ? performance.now() : 0
    this.stats.totalProcessed++

    let result = text

    try {
      // 记录原始文本长度用于调试
      const originalLength = result.length

      result = fixDoubleEscape(result)
      result = normalizeDelimiters(result)
      result = fixSpecialCharacters(result)
      result = wrapBareLatex(result)

      // 防止双重包裹：检查并修复已被重复包裹的定界符
      result = this.fixDoubleWrappedDelimiters(result)

      result = catchAllWrap(result)
      result = fixStreamingIncomplete(result)
      result = fixUnclosedDelimiters(result)
      result = balanceDollarSigns(result)

      // 后处理清理：移除无效的单字符 $X$ 包裹（单个字母/数字不是有意义的裸LaTeX公式）
      // 例如: $A$, $B$, $x$, $1$ → A, B, x, 1
      // 保留包含反斜杠命令、下标、上标、或花括号的有效公式
      result = result.replace(/\$([a-zA-Z\d])\$/g, '$1')

      // 验证处理结果没有明显变长（可能表示过度包裹）
      if (result.length > originalLength * 3) {
        console.warn('[LatexPreprocessor] 处理后文本异常增长', {
          originalLength,
          processedLength: result.length,
          ratio: (result.length / originalLength).toFixed(2),
          preview: result.substring(0, 200)
        })
      }
    } catch (error) {
      console.error('[LatexPreprocessor] 处理异常:', error, '\n输入文本预览:', text.substring(0, 200))
      return text
    }

    if (this.config.enableLogging) {
      const duration = performance.now() - startTime
      if (duration > 5) {
        console.log(`[LatexPreprocessor] 处理耗时: ${duration.toFixed(2)}ms`)
      }
    }

    return result
  }

  /**
   * 修复被重复包裹的定界符，例如 $$...$ 或 $...$$ 变为正确的 $...$
   */
  fixDoubleWrappedDelimiters(text) {
    // 修复连续三个或更多 $ 符号
    let result = text.replace(/\${3,}/g, (match) => {
      const count = match.length
      if (count % 2 === 0) {
        return '$$'.repeat(count / 2)
      }
      return '$' + '$$'.repeat(Math.floor(count / 2))
    })

    // 修复交错模式如 $...$$...$ 或 $$...$...$
    // 简单策略：将相邻的 $ 和 $$ 合并

    return result
  }

  getStats() {
    return { ...this.stats }
  }

  resetStats() {
    this.stats = {
      totalProcessed: 0,
      wrappedCount: 0,
      fixedCount: 0,
    }
  }
}

const preprocessor = new LatexPreprocessor()

export default preprocessor
