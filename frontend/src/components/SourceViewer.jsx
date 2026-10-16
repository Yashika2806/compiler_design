import { useEffect, useRef } from 'react'

export default function SourceViewer({ source, findings, activeLine }) {
  const lines = source.split('\n')
  const lineRefs = useRef({})

  // Map line number -> highest-severity finding on that line
  const severityByLine = {}
  const SEVERITY_RANK = { Critical: 0, High: 1, Medium: 2, Low: 3, Informational: 4 }
  for (const f of findings) {
    const existing = severityByLine[f.line]
    if (!existing || SEVERITY_RANK[f.severity] < SEVERITY_RANK[existing]) {
      severityByLine[f.line] = f.severity
    }
  }

  useEffect(() => {
    if (activeLine && lineRefs.current[activeLine]) {
      lineRefs.current[activeLine].scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [activeLine])

  return (
    <div className="code-viewer">
      {lines.map((line, idx) => {
        const lineNo = idx + 1
        const severity = severityByLine[lineNo]
        const isActive = lineNo === activeLine
        return (
          <div
            key={lineNo}
            ref={(el) => (lineRefs.current[lineNo] = el)}
            className={`code-line${severity ? ' flagged-' + severity : ''}`}
            style={isActive ? { outline: '1px solid #4f8cff' } : undefined}
          >
            <span className="code-line-num">{lineNo}</span>
            <span className="code-line-content">{line || ' '}</span>
          </div>
        )
      })}
    </div>
  )
}
