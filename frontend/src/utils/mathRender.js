import katex from 'katex'

const katexConfig = {
  delimiters: [
    { left: '$$', right: '$$', display: true },
    { left: '$', right: '$', display: false },
    { left: '\\(', right: '\\)', display: false },
    { left: '\\[', right: '\\[', display: true }
  ],
  throwOnError: false,
  errorColor: '#cc0000',
  strict: false,
  trust: true,
  macros: {
    "\\R": "\\mathbb{R}",
    "\\N": "\\mathbb{N}",
    "\\Z": "\\mathbb{Z}",
    "\\Q": "\\mathbb{Q}",
    "\\C": "\\mathbb{C}"
  }
}

function cleanFormula(formula) {
  return formula
    .replace(/&nbsp;/g, ' ')
    .replace(/<br\s*\/?>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function tryRenderFormula(formula, displayMode, originalContent) {
  const cleanedFormula = cleanFormula(formula)

  try {
    const result = katex.renderToString(cleanedFormula, {
      ...katexConfig,
      displayMode
    })
    return { success: true, html: result }
  } catch (error) {
    console.warn('KaTeX render failed:', {
      formula: cleanedFormula.substring(0, 100),
      error: error.message
    })

    const simplifiedFormula = cleanedFormula
      .replace(/\\left/g, '')
      .replace(/\\right/g, '')
      .replace(/\\(?:text|mathrm)\{[^}]*\}/g, '')

    if (simplifiedFormula !== cleanedFormula) {
      try {
        const fallbackResult = katex.renderToString(simplifiedFormula, {
          ...katexConfig,
          displayMode
        })
        return { success: true, html: fallbackResult, fallback: true }
      } catch (fallbackError) {
        console.warn('KaTeX fallback render also failed:', fallbackError.message)
      }
    }

    return {
      success: false,
      html: `<span class="math-error" title="${escapeHtml(error.message)}">${escapeHtml(originalContent)}</span>`
    }
  }
}

export function renderMathInElement(element) {
  if (!element) return

  const mathElements = element.querySelectorAll('.math-display, .math-inline')

  if (mathElements.length === 0 && !hasMathContent(element.textContent || '')) {
    return
  }

  if (mathElements.length > 0) {
    mathElements.forEach(el => {
      const mathContent = el.textContent || ''

      if (mathContent.startsWith('$$') && mathContent.endsWith('$$')) {
        const formula = mathContent.slice(2, -2).trim()
        const result = tryRenderFormula(formula, true, mathContent)
        el.innerHTML = result.html
        if (result.success) el.classList.add('katex-rendered')
      } else if (mathContent.startsWith('$') && mathContent.endsWith('$')) {
        const formula = mathContent.slice(1, -1).trim()
        const result = tryRenderFormula(formula, false, mathContent)
        el.innerHTML = result.html
        if (result.success) el.classList.add('katex-rendered')
      } else if (mathContent.trim()) {
        const result = tryRenderFormula(mathContent.trim(), false, mathContent)
        el.innerHTML = result.html
        if (result.success) el.classList.add('katex-rendered')
      }
    })

    return
  }

  try {
    katex.renderMathInElement(element, katexConfig)
  } catch (error) {
    console.error('KaTeX global render error:', error)
  }
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

export function hasMathContent(text) {
  if (!text) return false
  const patterns = [
    /\$[^$]+\$/,
    /\\\([^)]+\\\)/,
    /\$\$[^$]+\$\$/,
    /\\\[[^\]]+\\\]/,
    /\\[a-zA-Z]+/,
    /\\frac\{/,
    /\\sqrt/,
    /\\int/,
    /\\sum/,
    /\\lim/,
    /\\alpha/,
    /\\beta/,
    /\\gamma/,
    /\\theta/,
    /\\infty/
  ]
  return patterns.some(p => p.test(text))
}

export function renderMathSync(text) {
  if (!text) return text

  let result = text

  result = result.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => {
    const renderResult = tryRenderFormula(math.trim(), true, `$$${math}$$`)
    return renderResult.success ? renderResult.html : `$$${math}$$`
  })

  result = result.replace(/\$([^\$\n]+?)\$/g, (_, math) => {
    const renderResult = tryRenderFormula(math.trim(), false, `$${math}$`)
    return renderResult.success ? renderResult.html : `$${math}$`
  })

  result = result.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => {
    const renderResult = tryRenderFormula(math.trim(), true, `\\[${math}\\]`)
    return renderResult.success ? renderResult.html : `\\[${math}\\]`
  })

  result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => {
    const renderResult = tryRenderFormula(math.trim(), false, `\\(${math}\\)`)
    return renderResult.success ? renderResult.html : `\\(${math}\\)`
  })

  return result
}

export default katexConfig
