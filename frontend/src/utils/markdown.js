import { marked } from 'marked'
import DOMPurify from 'dompurify'

const renderer = new marked.Renderer()

renderer.code = function(code, infostring, escaped) {
  const lang = (infostring || '').match(/\S*/)[0]
  
  if (this.options.highlight) {
    const highlighted = this.options.highlight(code, lang)
    if (highlighted !== code) {
      escaped = true
      code = highlighted
    }
  }
  
  code = code.replace(/\n$/, '') + '\n'
  
  if (!lang) {
    return '<pre><code>' + (escaped ? code : escape(code)) + '</code></pre>\n'
  }
  
  return '<pre class="highlight"><code class="language-' + escape(lang) + '">' + (escaped ? code : escape(code)) + '</code></pre>\n'
}

const mathBlockRegex = /\$\$([\s\S]*?)\$\$/g
const mathInlineRegex = /\$([^\$\n]+?)\$/g

function extractMathBlocks(text) {
  const mathBlocks = []
  let processed = text
  
  processed = processed.replace(mathBlockRegex, (match, math) => {
    const idx = mathBlocks.length
    mathBlocks.push({ type: 'block', content: math.trim() })
    return `%%MATHBLOCK${idx}%%`
  })
  
  processed = processed.replace(mathInlineRegex, (match, math) => {
    const idx = mathBlocks.length
    mathBlocks.push({ type: 'inline', content: math.trim() })
    return `%%MATHINLINE${idx}%%`
  })
  
  return { processed, mathBlocks }
}

function restoreMathBlocks(html, mathBlocks) {
  let result = html
  
  for (let i = 0; i < mathBlocks.length; i++) {
    const block = mathBlocks[i]
    const placeholder = block.type === 'block' ? `%%MATHBLOCK${i}%%` : `%%MATHINLINE${i}%%`
    const mathHtml = block.type === 'block' 
      ? `<div class="math-display">$${block.content}$</div>`
      : `<span class="math-inline">$${block.content}$</span>`
    
    result = result.replace(new RegExp(placeholder.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), mathHtml)
  }
  
  return result
}

function escape(html) {
  return html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function renderMarkdown(text) {
  if (!text) return ''
  
  try {
    const { processed, mathBlocks } = extractMathBlocks(text)
    
    const options = {
      renderer: renderer,
      gfm: true,
      breaks: true,
      headerIds: false,
      mangle: false
    }
    
    let html = marked.parse(processed, options)
    
    html = restoreMathBlocks(html, mathBlocks)
    
    const cleanHtml = DOMPurify.sanitize(html, {
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
        'class', 'id',
        'start', 'type'
      ],
      ADD_ATTR: ['target']
    })
    
    return cleanHtml
  } catch (error) {
    console.error('Markdown render error:', error)
    return DOMPurify.sanitize(`<p>${escape(text)}</p>`)
  }
}

export function formatStreamText(text) {
  if (!text) return ''
  
  try {
    const { processed, mathBlocks } = extractMathBlocks(text)
    
    let formatted = processed
    
    formatted = formatted.replace(/\n\n+/g, '</p><p>')
    formatted = formatted.replace(/^### (.*)$/gm, '<h3>$1</h3>')
    formatted = formatted.replace(/^## (.*)$/gm, '<h2>$1</h2>')
    formatted = formatted.replace(/^# (.*)$/gm, '<h1>$1</h1>')
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>')
    formatted = formatted.replace(/`([^`\n]+)`/g, '<code>$1</code>')
    formatted = formatted.replace(/\n/g, '<br>')
    
    formatted = restoreMathBlocks(formatted, mathBlocks)
    
    return DOMPurify.sanitize(formatted, {
      ALLOWED_TAGS: [
        'p', 'br', 'h1', 'h2', 'h3',
        'strong', 'em', 'code',
        'div', 'span'
      ],
      ALLOWED_ATTR: ['class']
    })
  } catch (error) {
    console.error('Stream text format error:', error)
    return text
  }
}
