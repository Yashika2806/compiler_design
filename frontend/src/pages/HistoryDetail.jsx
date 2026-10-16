import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { fetchHistoryReport } from '../api.js'
import ScoreGauge from '../components/ScoreGauge.jsx'
import SeverityBadge from '../components/SeverityBadge.jsx'

export default function HistoryDetail() {
  const { id } = useParams()
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [expandedId, setExpandedId] = useState(null)

  useEffect(() => {
    fetchHistoryReport(id).then(setReport).catch((e) => setError(e.message))
  }, [id])

  if (error) return <div className="main"><div className="error-box">{error}</div></div>
  if (!report) return <div className="main"><div className="empty-state">Loading…</div></div>

  const findings = report.detailed_findings

  return (
    <div className="main">
      <Link to="/history">&larr; Back to History</Link>
      <h1 style={{ marginTop: 12 }}>{report.contract_name}</h1>
      <p className="subtitle">Solidity {report.solidity_version} &middot; Analyzed {report.analysis_date}</p>

      <div className="grid grid-2" style={{ marginBottom: 20 }}>
        <div className="card" style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
          <ScoreGauge score={report.security_score} riskLevel={report.risk_level} />
          <div>
            <div className="stat-label">Risk Level</div>
            <div className={`stat-value risk-${report.risk_level}`}>{report.risk_level}</div>
            <p style={{ color: 'var(--text-dim)', fontSize: 13, marginTop: 8 }}>{report.executive_summary}</p>
          </div>
        </div>
        <div className="card">
          <h2>Severity Breakdown</h2>
          {Object.entries(report.vulnerability_summary.by_severity).map(([sev, count]) => (
            <div key={sev} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
              <SeverityBadge severity={sev} />
              <span style={{ fontWeight: 600 }}>{count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>Findings ({findings.length})</h2>
        {findings.length === 0 && <div className="empty-state">No issues detected.</div>}
        {findings.map((f, i) => (
          <div key={i} className="finding-card" onClick={() => setExpandedId(expandedId === i ? null : i)}>
            <SeverityBadge severity={f.severity} />
            <div className="finding-title">{f.title}</div>
            <div className="finding-meta">{f.function_name}() &middot; line {f.line} &middot; {f.rule_id}</div>
            {expandedId === i && (
              <>
                <div className="finding-section">
                  <div className="finding-section-label">Vulnerable code</div>
                  <div className="finding-snippet">{f.code_snippet}</div>
                </div>
                <div className="finding-section">
                  <div className="finding-section-label">Explanation</div>
                  <div>{f.explanation}</div>
                </div>
                <div className="finding-section">
                  <div className="finding-section-label">Recommended fix</div>
                  <div>{f.recommendation}</div>
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      <div className="card">
        <h2>Final Assessment</h2>
        <p style={{ margin: 0 }}>{report.final_assessment}</p>
      </div>
    </div>
  )
}
