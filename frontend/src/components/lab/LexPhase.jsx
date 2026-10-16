import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// Phase 1: replays the backend's scan trace like we tokenize by hand.

const TYPE_ORDER = ['KEYWORD', 'IDENTIFIER', 'INTEGER_LITERAL', 'FLOAT_LITERAL', 'LITERAL', 'STRING_LITERAL',
  'CHAR_LITERAL', 'OPERATOR', 'PUNCTUATOR', 'PREPROCESSOR', 'ERROR']

function segClass(s, cur) {
  const status = s.index < cur ? 'done' : s.index === cur ? 'cur' : 'todo'
  const kind = s.kind === 'token' || s.kind === 'error' ? `t-${s.token_type}` : `k-${s.kind}`
  return `seg ${status} ${kind}`
}

function lookLabel(raw) {
  if (raw === 'end of file') return 'EOF'
  if (raw.includes('(space)')) return '␣'
  if (raw.includes('(newline)')) return '↵'
  if (raw.includes('(tab)')) return '⇥'
  return raw.replace(/^'/, '').replace(/'$/, '') || '∅'
}

function Chars({ step }) {
  if (step.kind === 'whitespace') return <div className="chars"><span className="ch wide">whitespace</span></div>
  const shown = [...step.lexeme].slice(0, 22)
  const more = [...step.lexeme].length > 22
  return (
    <div className="chars">
      {step.kind === 'eof'
        ? <span className="ch wide">end of file</span>
        : shown.map((c, i) => <span key={i} className="ch">{c === '\n' ? '↵' : c === ' ' ? '␣' : c}</span>)}
      {more && <span className="ch">…</span>}
      <span className="chars-sep">lookahead</span>
      <span className="ch look">{lookLabel(step.lookahead)}</span>
    </div>
  )
}

export default function LexPhase({ data, source }) {
  const { steps, tokens, issues, stats } = data
  const [cur, setCur] = useState(-1)
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(5)
  const [showWs, setShowWs] = useState(false)

  const lastIdx = steps.length - 1
  const playable = useMemo(
    () => steps.filter((s) => showWs || s.kind !== 'whitespace').map((s) => s.index), [steps, showWs])
  const nextOf = useCallback((c) => playable.find((i) => i > c) ?? c, [playable])
  const prevOf = useCallback((c) => {
    for (let k = playable.length - 1; k >= 0; k--) if (playable[k] < c) return playable[k]
    return -1
  }, [playable])

  // auto-play
  useEffect(() => {
    if (!playing) return undefined
    const id = setInterval(() => setCur((c) => nextOf(c)), 1000 / speed)
    return () => clearInterval(id)
  }, [playing, speed, nextOf])
  useEffect(() => { if (playing && cur >= lastIdx) setPlaying(false) }, [cur, playing, lastIdx])

  // keep the current lexeme / newest table row in view
  const boxRef = useRef(null)
  const curRef = useRef(null)
  const tableRef = useRef(null)
  useEffect(() => {
    const el = curRef.current, box = boxRef.current
    if (!el || !box) return
    if (el.offsetTop < box.scrollTop + 10 || el.offsetTop > box.scrollTop + box.clientHeight - 50) {
      box.scrollTop = Math.max(0, el.offsetTop - 50)
    }
  }, [cur])

  const stepOfToken = useMemo(() => {
    const m = {}
    steps.forEach((s) => { if (s.token_index >= 0) m[s.token_index] = s.index })
    return m
  }, [steps])
  const revealed = tokens.filter((t) => stepOfToken[t.index] <= cur)
  useEffect(() => {
    if (tableRef.current) tableRef.current.scrollTop = tableRef.current.scrollHeight
  }, [revealed.length])

  const step = cur >= 0 ? steps[cur] : null
  const finished = cur >= lastIdx
  const jump = (i) => { setPlaying(false); setCur(i) }
  const jumpToIssue = (iss) => {
    const s = steps.find((x) => x.line === iss.line && x.col === iss.col && (x.kind === 'error' || x.kind === 'comment'))
    if (s) jump(s.index)
  }

  return (
    <section className="lab-card" id="phase-1">
      <div className="lab-card-head">
        <span className="phase-badge on">1</span>
        <h2>Lexical Analysis</h2>
        <div className="head-stats">
          <span className="stat-chip">{stats.total_tokens} tokens</span>
          <span className={'stat-chip' + (stats.errors ? ' bad' : '')}>{stats.errors} errors</span>
          {stats.warnings > 0 && <span className="stat-chip warn">{stats.warnings} warnings</span>}
          <span className="stat-chip">backend {stats.elapsed_ms} ms</span>
        </div>
      </div>
      <p className="lab-hint">
        The scanner reads the code left to right, picks the rule that matches the current character,
        keeps reading while the rule still fits, then cuts out one token. Whitespace and comments are skipped.
      </p>

      {issues.length > 0 && (
        <div className="issue-box">
          {issues.map((iss, i) => (
            <div key={i} className={'issue ' + iss.severity} onClick={() => jumpToIssue(iss)}>
              <b>{iss.severity}</b> line {iss.line}, col {iss.col}: {iss.message}
            </div>
          ))}
        </div>
      )}

      <div className="controls">
        <button onClick={() => { setPlaying(false); setCur(-1) }}>⏮ Restart</button>
        <button onClick={() => { setPlaying(false); setCur(prevOf) }} disabled={cur < 0}>◀ Back</button>
        <button className="primary" onClick={() => {
          if (finished) { setCur(-1); setPlaying(true) } else setPlaying(!playing)
        }}>{playing ? '⏸ Pause' : finished ? '↻ Replay' : '▶ Play'}</button>
        <button onClick={() => { setPlaying(false); setCur(nextOf) }} disabled={finished}>Next ▶</button>
        <button onClick={() => { setPlaying(false); setCur(lastIdx) }} disabled={finished}>⏭ Skip to end</button>
        <label className="speed">Speed
          <input type="range" min="1" max="30" value={speed} onChange={(e) => setSpeed(+e.target.value)} />
          <span>{speed}/sec</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={showWs} onChange={(e) => setShowWs(e.target.checked)} /> show whitespace steps
        </label>
      </div>
      <div className="progress"><div style={{ width: `${((cur + 1) / steps.length) * 100}%` }} /></div>

      <div className="lex-grid">
        <div>
          <h3 className="sub">Source code</h3>
          <div className="lab-source-box" ref={boxRef}>
            <pre className="lab-source">
              {steps.map((s) => (
                <span key={s.index} className={segClass(s, cur)} ref={s.index === cur ? curRef : null}>{s.lexeme}</span>
              ))}
            </pre>
          </div>
        </div>

        <div>
          <h3 className="sub">What the scanner is doing{step ? ` (step ${step.index + 1} of ${steps.length})` : ''}</h3>
          <div className={'scan-log' + (speed >= 7 ? ' fast' : '')}>
            {!step && <p className="muted">Press <b>Play</b> or <b>Next</b> to start scanning from the first character.</p>}
            {step && (
              <div key={step.index}>
                <div className="log-top">
                  <span className={`pill t-${step.token_type || 'none'}`}>
                    {step.kind === 'whitespace' ? 'SKIP · whitespace'
                      : step.kind === 'comment' ? 'SKIP · comment'
                        : step.token_type}
                  </span>
                  <span className="muted">line {step.line}, col {step.col}</span>
                </div>
                <Chars step={step} />
                <div className="rule-line"><b>Rule:</b> {step.rule} <code>{step.pattern}</code></div>
                <ol className="explain">
                  {step.explain.map((line, i) => (
                    <li key={i} style={{ '--i': i }}>{line}</li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        </div>
      </div>

      <h3 className="sub">Token table <span className="muted">({revealed.length} of {tokens.length})</span></h3>
      <div className="token-table-box" ref={tableRef}>
        <table className="token-table">
          <thead>
            <tr><th>#</th><th>Lexeme</th><th>Token type</th><th>Details</th><th>Line:Col</th></tr>
          </thead>
          <tbody>
            {revealed.length === 0 && <tr><td colSpan="5" className="muted">Tokens appear here as the scanner finds them.</td></tr>}
            {revealed.map((t) => (
              <tr key={t.index} className={(stepOfToken[t.index] === cur ? 'latest ' : '') + (t.type === 'ERROR' ? 'err' : '')}
                  onClick={() => jump(stepOfToken[t.index])}>
                <td className="muted">{t.index + 1}</td>
                <td><code className={`lexeme t-${t.type}`}>{t.type === 'EOF' ? '<EOF>' : t.lexeme}</code></td>
                <td><span className={`t-${t.type} type-name`}>{t.type}</span></td>
                <td className="muted">{t.subtype}{t.value && t.value !== t.lexeme ? ` · value ${t.value}` : ''}</td>
                <td className="muted">{t.line}:{t.col}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {finished && (
        <div className="summary">
          <b>Scan complete.</b> {stats.total_tokens} tokens from {stats.lines} lines ({stats.characters} characters),
          {' '}{stats.unique_identifiers} distinct identifiers, {stats.comments_skipped} comments skipped.
          <div className="summary-chips">
            {TYPE_ORDER.filter((t) => stats.by_type[t]).map((t) => (
              <span key={t} className={`pill t-${t}`}>{t} × {stats.by_type[t]}</span>
            ))}
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            {stats.errors === 0
              ? 'No lexical errors, so the token list is ready to be handed to Phase 2 (syntax analysis).'
              : 'Lexical errors found. A real compiler would report them and still continue scanning, as done here.'}
          </div>
        </div>
      )}
    </section>
  )
}
