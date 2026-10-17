import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { analyzeSource, analyzeFile } from '../api.js'

const SAMPLE = `pragma solidity ^0.8.0;

contract VulnerableBank {
    mapping(address => uint256) public balances;

    function deposit() public payable {
        balances[msg.sender] = balances[msg.sender] + msg.value;
    }

    function withdraw(uint256 amount) public {
        require(balances[msg.sender] >= amount);
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success);
        balances[msg.sender] = balances[msg.sender] - amount;
    }
}`

export default function Analyze() {
  const [mode, setMode] = useState('paste')
  const [contractName, setContractName] = useState('')
  const [sourceCode, setSourceCode] = useState('')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      let report
      if (mode === 'paste') {
        if (!sourceCode.trim()) throw new Error('Please paste some Solidity source code.')
        report = await analyzeSource(contractName, sourceCode)
      } else {
        if (!file) throw new Error('Please choose a .sol file to upload.')
        report = await analyzeFile(file)
      }
      navigate('/results', { state: { report, source: mode === 'paste' ? sourceCode : await file.text() } })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="main">
      <h1>Analyze Contract</h1>
      <p className="subtitle">Paste Solidity source code or upload a .sol file to run a static security analysis.</p>

      <div className="tabs">
        <button type="button" className={`tab-btn${mode === 'paste' ? ' active' : ''}`} onClick={() => setMode('paste')}>Paste Code</button>
        <button type="button" className={`tab-btn${mode === 'upload' ? ' active' : ''}`} onClick={() => setMode('upload')}>Upload File</button>
      </div>

      {error && <div className="error-box">{error}</div>}

      <form onSubmit={handleSubmit} className="card">
        {mode === 'paste' ? (
          <>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', marginBottom: 6, fontSize: 13, color: 'var(--text-dim)' }}>Contract name (optional)</label>
              <input type="text" value={contractName} onChange={(e) => setContractName(e.target.value)} placeholder="e.g. MyToken" />
            </div>
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <label style={{ fontSize: 13, color: 'var(--text-dim)' }}>Solidity source code</label>
                <button type="button" className="secondary" style={{ padding: '3px 10px', fontSize: 12 }} onClick={() => setSourceCode(SAMPLE)}>
                  Load sample vulnerable contract
                </button>
              </div>
              <textarea rows={16} value={sourceCode} onChange={(e) => setSourceCode(e.target.value)} placeholder="pragma solidity ^0.8.0;&#10;&#10;contract MyContract { ... }" />
            </div>
          </>
        ) : (
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', marginBottom: 6, fontSize: 13, color: 'var(--text-dim)' }}>Upload .sol file</label>
            <input type="file" accept=".sol" onChange={(e) => setFile(e.target.files[0])} />
          </div>
        )}

        <button type="submit" disabled={loading}>{loading ? 'Analyzing...' : 'Analyze Contract'}</button>
      </form>
    </div>
  )
}
