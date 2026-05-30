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

  while (end < text.length) {
    const ch = text[end]

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

        if (LATEX_COMMAND_SET.has(cmd) || cmd === '\\left' || cmd === '\\right' ||
            cmd === '\\begin' || cmd === '\\end') {
          if (!isInsideMathFromSegments(segments)) {
            const spanEnd = extractBareLatexSpan(text, i)
            const bareContent = text.substring(i, spanEnd)
            if (bareContent.trim().length > 0) {
              const isDisplay = shouldUseDisplayMode(bareContent, text, i)
              if (isDisplay) {
                segments.push({ type: 'math', content: '$$' + bareContent + '$$' })
              } else {
                segments.push({ type: 'math', content: '$' + bareContent + '$' })
              }
              i = spanEnd
              continue
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
        if (bareContent.length > 1) {
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
  const mathPattern = /(?<!\$)(?:\\(?:begin\{[\w]*\}|[a-zA-Z]+(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})?(?:[_^](?:\{[^{}]*\}|[\w\d]))*|(?:[_^](?:\{[^{}]*\}|[\w\d]))+))(?!\$)/g

  let result = text
  let match
  const processedRanges = []

  while ((match = mathPattern.exec(result)) !== null) {
    const matched = match[0]
    const pos = match.index

    if (matched.startsWith('\\begin') || matched.startsWith('\\end')) {
      continue
    }

    const beforePos = Math.max(0, pos - 10)
    const beforeText = result.substring(beforePos, pos)
    const dollarBefore = (beforeText.match(/\$/g) || []).length

    if (dollarBefore % 2 === 0) {
      const afterPos = Math.min(result.length, pos + matched.length + 10)
      const afterText = result.substring(pos + matched.length, afterPos)
      const dollarAfter = (afterText.match(/\$/g) || []).length

      if (dollarAfter % 2 === 0) {
        let overlaps = false
        for (const [start, end] of processedRanges) {
          if (!(pos >= end || pos + matched.length <= start)) {
            overlaps = true
            break
          }
        }
        if (!overlaps) {
          processedRanges.push([pos, pos + matched.length])
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
      result = fixDoubleEscape(result)
      result = normalizeDelimiters(result)
      result = fixSpecialCharacters(result)
      result = wrapBareLatex(result)
      result = catchAllWrap(result)
      result = fixStreamingIncomplete(result)
      result = fixUnclosedDelimiters(result)
      result = balanceDollarSigns(result)
    } catch (error) {
      console.error('[LatexPreprocessor] 处理异常:', error)
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
