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

export function renderMathInElement(element) {
  if (!element) return
  
  const mathElements = element.querySelectorAll('.math-display, .math-inline')
  
  if (mathElements.length === 0 && !hasMathContent(element.textContent || '')) {
    return
  }

  if (mathElements.length > 0) {
    mathElements.forEach(el => {
      const mathContent = el.textContent || ''
      const isDisplay = el.classList.contains('math-display')
      
      if (mathContent.startsWith('$$') && mathContent.endsWith('$$')) {
        const formula = mathContent.slice(2, -2).trim()
        try {
          el.innerHTML = katex.renderToString(formula, {
            ...katexConfig,
            displayMode: true
          })
          el.classList.add('katex-rendered')
        } catch (error) {
          console.warn('KaTeX render error:', error)
          el.innerHTML = `<span class="math-error">${escapeHtml(mathContent)}</span>`
        }
      } else if (mathContent.startsWith('$') && mathContent.endsWith('$')) {
        const formula = mathContent.slice(1, -1).trim()
        try {
          el.innerHTML = katex.renderToString(formula, {
            ...katexConfig,
            displayMode: false
          })
          el.classList.add('katex-rendered')
        } catch (error) {
          console.warn('KaTeX render error:', error)
          el.innerHTML = `<span class="math-error">${escapeHtml(mathContent)}</span>`
        }
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
    try {
      return katex.renderToString(math.trim(), { ...katexConfig, displayMode: true })
    } catch {
      return `$$${math}$$`
    }
  })

  result = result.replace(/\$([^\$\n]+?)\$/g, (_, math) => {
    try {
      return katex.renderToString(math.trim(), { ...katexConfig, displayMode: false })
    } catch {
      return `$${math}$`
    }
  })

  result = result.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => {
    try {
      return katex.renderToString(math.trim(), { ...katexConfig, displayMode: true })
    } catch {
      return `\\[${math}\\]`
    }
  })

  result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => {
    try {
      return katex.renderToString(math.trim(), { ...katexConfig, displayMode: false })
    } catch {
      return `\\(${math}\\)`
    }
  })

  return result
}

export default katexConfig
