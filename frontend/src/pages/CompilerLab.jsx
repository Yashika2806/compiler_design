import { useEffect, useRef, useState } from 'react'
import { fetchLanguages, compileSource } from '../api.js'
import LexPhase from '../components/lab/LexPhase.jsx'
import { PHASES, PhasePipeline, PhasePlaceholder } from '../components/lab/Phases.jsx'
import '../lab.css'

export default function CompilerLab() {
  const [languages, setLanguages] = useState([])
  const [langId, setLangId] = useState('c')
  const [source, setSource] = useState('')
  const [result, setResult] = useState(null)
  const [runId, setRunId] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const lastSample = useRef('')

  useEffect(() => {
    fetchLanguages()
      .then((list) => {
        setLanguages(list)
        const first = list.find((l) => l.id === 'c') || list[0]
        if (first) { setLangId(first.id); setSource(first.sample); lastSample.current = first.sample }
      })
      .catch((e) => setError(friendly(e)))
  }, [])

  function friendly(e) {
    return e.message === 'Failed to fetch'
      ? 'Cannot reach the backend at http://127.0.0.1:8000. Start it with: uvicorn api.main:app --reload (inside the backend folder).'
      : e.message
  }

  function changeLanguage(id) {
    setLangId(id)
    const lang = languages.find((l) => l.id === id)
    // only swap the code if the user hasn't edited the previous sample
    if (lang && (source.trim() === '' || source === lastSample.current)) {
      setSource(lang.sample)
      lastSample.current = lang.sample
    }
    setResult(null)
  }

  function loadSample() {
    const lang = languages.find((l) => l.id === langId)
    if (lang) { setSource(lang.sample); lastSample.current = lang.sample; setResult(null) }
  }

  async function run() {
    setError('')
    setLoading(true)
    try {
      const res = await compileSource(langId, source)
      setResult(res)
      setRunId((n) => n + 1)
      setTimeout(() => document.getElementById('phase-1')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    } catch (e) {
      setError(friendly(e))
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Tab') {
      e.preventDefault()
      const t = e.target, s = t.selectionStart, en = t.selectionEnd
      setSource(source.slice(0, s) + '    ' + source.slice(en))
      requestAnimationFrame(() => { t.selectionStart = t.selectionEnd = s + 4 })
    } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      run()
    }
  }

  const lang = languages.find((l) => l.id === langId)

  return (
    <div className="main lab-main">
      <h1>Compiler Lab</h1>
      <p className="subtitle">Type code, press Compile, and watch every phase of the compiler work on it, step by step.</p>

      <div className="lab-card">
        <div className="toolbar">
          <label>Language
            <select value={langId} onChange={(e) => changeLanguage(e.target.value)} disabled={!languages.length}>
              {languages.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
          {lang && <span className="muted">{lang.notes}</span>}
          <button onClick={loadSample} disabled={!lang}>Load sample</button>
          <button className="primary big" onClick={run} disabled={loading || !source.trim()}>
            {loading ? 'Compiling…' : '▶ Compile'}
          </button>
          <span className="muted">Ctrl + Enter also works</span>
        </div>
        <textarea
          className="editor"
          value={source}
          spellCheck={false}
          onChange={(e) => setSource(e.target.value)}
          onKeyDown={onKeyDown}
          rows={14}
          placeholder="Write or paste your code here…"
        />
        {error && <div className="issue-box"><div className="issue error">{error}</div></div>}
      </div>

      <PhasePipeline available={result ? result.available_phases : []} />

      {result && <LexPhase key={runId} data={result.phases.lexical} source={source} />}
      {!result && (
        <section className="lab-card locked" id="phase-1">
          <div className="lab-card-head"><span className="phase-badge">1</span><h2>Lexical Analysis</h2></div>
          <p className="lab-hint">Press Compile to see your code being broken into tokens, one by one.</p>
        </section>
      )}
      {PHASES.slice(1).map((p) => <PhasePlaceholder key={p.key} phase={p} />)}
    </div>
  )
}
