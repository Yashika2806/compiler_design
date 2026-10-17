import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchHistory } from '../api.js'
import SeverityBadge from '../components/SeverityBadge.jsx'

export default function Dashboard() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchHistory()
      .then(setHistory)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const totalScans = history.length
  const avgScore = totalScans
    ? Math.round(history.reduce((sum, h) => sum + h.security_score, 0) / totalScans)
    : null
  const totalFindings = history.reduce((sum, h) => sum + h.total_findings, 0)
  const criticalCount = history.reduce((sum, h) => sum + (h.severity_counts?.Critical || 0), 0)

  return (
    <div className="main">
      <h1>Dashboard</h1>
      <p className="subtitle">Overview of your smart contract security analyses.</p>

      {error && <div className="error-box">Couldn't reach the backend: {error}. Make sure the FastAPI server is running on port 8000.</div>}

      <div className="grid grid-4" style={{ marginBottom: 24 }}>
        <div className="stat-card">
          <div className="stat-label">Total Scans</div>
          <div className="stat-value">{loading ? '—' : totalScans}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Average Score</div>
          <div className="stat-value">{loading ? '—' : (avgScore ?? '—')}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Findings</div>
          <div className="stat-value">{loading ? '—' : totalFindings}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Critical Issues</div>
          <div className="stat-value" style={{ color: criticalCount > 0 ? '#d92d3f' : undefined }}>
            {loading ? '—' : criticalCount}
          </div>
        </div>
      </div>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ margin: 0 }}>Recent Scans</h2>
          <Link to="/analyze"><button>+ New Analysis</button></Link>
        </div>

        {!loading && history.length === 0 && (
          <div className="empty-state">No analyses yet. Run your first scan to see it here.</div>
        )}

        {history.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Contract</th>
                <th>Score</th>
                <th>Risk</th>
                <th>Findings</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {history.slice(0, 8).map((h) => (
                <tr key={h.id}>
                  <td><Link to={`/history/${h.id}`}>{h.contract_name}</Link></td>
                  <td>{h.security_score}/100</td>
                  <td><SeverityBadge severity={h.risk_level === 'Low' ? 'Low' : h.risk_level === 'Medium' ? 'Medium' : h.risk_level === 'High' ? 'High' : 'Critical'} /></td>
                  <td>{h.total_findings}</td>
                  <td>{new Date(h.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
