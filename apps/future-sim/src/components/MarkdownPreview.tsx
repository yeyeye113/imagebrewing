// ============================================================
// MarkdownPreview — 报告页轻量渲染（无额外依赖）
// ============================================================

import { type ReactNode } from 'react'

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    return part
  })
}

function parseTableRow(line: string): string[] {
  return line
    .split('|')
    .map((c) => c.trim())
    .filter((_, i, arr) => i > 0 && i < arr.length - 1)
}

export function MarkdownPreview({ source }: { source: string }) {
  const lines = source.split('\n')
  const nodes: ReactNode[] = []
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]

    if (line.startsWith('# ')) {
      nodes.push(
        <h1 key={key++} className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-0 mb-4">
          {line.slice(2)}
        </h1>,
      )
      i++
      continue
    }
    if (line.startsWith('## ')) {
      nodes.push(
        <h2 key={key++} className="text-lg font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-3 pb-2 border-b border-gray-100 dark:border-gray-800">
          {line.slice(3)}
        </h2>,
      )
      i++
      continue
    }
    if (line.startsWith('### ')) {
      nodes.push(
        <h3 key={key++} className="text-base font-medium text-gray-900 mt-5 mb-2">
          {line.slice(4)}
        </h3>,
      )
      i++
      continue
    }
    if (line.startsWith('> ')) {
      nodes.push(
        <blockquote key={key++} className="border-l-4 border-amber-300 bg-amber-50/50 px-4 py-2 text-sm text-amber-900 my-3 rounded-r">
          {renderInline(line.slice(2))}
        </blockquote>,
      )
      i++
      continue
    }
    if (line.startsWith('|')) {
      const header = parseTableRow(line)
      i++
      if (lines[i]?.includes('---')) i++
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith('|')) {
        rows.push(parseTableRow(lines[i]))
        i++
      }
      nodes.push(
        <div key={key++} className="overflow-x-auto my-4">
          <table className="w-full text-sm border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800/80">
                {header.map((h) => (
                  <th key={h} className="text-left font-medium text-gray-600 dark:text-gray-400 px-3 py-2 border-b border-gray-200 dark:border-gray-700">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri} className="even:bg-gray-50/50 dark:even:bg-gray-800/30">
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-3 py-2 border-b border-gray-100 dark:border-gray-800 text-gray-700 dark:text-gray-300">
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }
    if (line.startsWith('- ')) {
      const items: string[] = []
      while (i < lines.length && lines[i].startsWith('- ')) {
        items.push(lines[i].slice(2))
        i++
      }
      nodes.push(
        <ul key={key++} className="list-disc list-inside space-y-1 text-sm text-gray-700 my-2 ml-1">
          {items.map((item) => (
            <li key={item}>{renderInline(item)}</li>
          ))}
        </ul>,
      )
      continue
    }
    if (line.trim() === '---') {
      nodes.push(<hr key={key++} className="my-6 border-gray-200" />)
      i++
      continue
    }
    if (line.trim() === '') {
      i++
      continue
    }
    nodes.push(
      <p key={key++} className="text-sm text-gray-700 leading-relaxed my-2">
        {renderInline(line)}
      </p>,
    )
    i++
  }

  return <article className="max-w-none">{nodes}</article>
}
