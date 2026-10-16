const BASE_URL = 'http://127.0.0.1:8000'

async function handle(res) {
  if (!res.ok) {
    let detail = 'Request failed'
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch (_) {}
    throw new Error(detail)
  }
  return res.json()
}

export async function analyzeSource(contractName, sourceCode) {
  const res = await fetch(`${BASE_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contract_name: contractName || 'UnnamedContract', source_code: sourceCode }),
  })
  return handle(res)
}

export async function analyzeFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${BASE_URL}/analyze/upload`, { method: 'POST', body: formData })
  return handle(res)
}

export async function fetchHistory() {
  const res = await fetch(`${BASE_URL}/history`)
  return handle(res)
}

export async function fetchHistoryReport(id) {
  const res = await fetch(`${BASE_URL}/history/${id}`)
  return handle(res)
}

// ---------- Compiler Lab ----------
export async function fetchLanguages() {
  const res = await fetch(`${BASE_URL}/compile/languages`)
  return handle(res)
}

export async function compileSource(language, sourceCode) {
  const res = await fetch(`${BASE_URL}/compile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language, source_code: sourceCode }),
  })
  return handle(res)
}
