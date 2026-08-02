/* Every example in four languages, generated from one endpoint definition so
   the tabs can never drift apart. */

export const LANGUAGES = [
  { id: 'curl', label: 'cURL' },
  { id: 'python', label: 'Python' },
  { id: 'javascript', label: 'JavaScript' },
  { id: 'node', label: 'Node' },
]

const pretty = (body) => JSON.stringify(body, null, 2)

function curl({ base, key, method, path, body }) {
  const lines = [`curl -X ${method} "${base}${path}"`, `  -H "X-API-Key: ${key}"`]
  if (body) {
    lines.push('  -H "Content-Type: application/json"')
    lines.push(`  -d '${JSON.stringify(body)}'`)
  }
  return lines.join(' \\\n')
}

function python({ base, key, method, path, body }) {
  const call = method.toLowerCase()
  const args = [`"${base}${path}"`, `headers={"X-API-Key": "${key}"}`]
  if (body) args.push(`json=${pretty(body).replace(/true/g, 'True').replace(/false/g, 'False')}`)
  return [
    'import requests',
    '',
    `resp = requests.${call}(`,
    ...args.map((a) => `    ${a},`),
    ')',
    'resp.raise_for_status()',
    'print(resp.json())',
  ].join('\n')
}

function javascript({ base, key, method, path, body }) {
  const init = [`  method: '${method}',`, `  headers: {`,
    `    'X-API-Key': '${key}',`]
  if (body) init.push(`    'Content-Type': 'application/json',`)
  init.push('  },')
  if (body) init.push(`  body: JSON.stringify(${pretty(body).replace(/\n/g, '\n  ')}),`)
  return [
    `const resp = await fetch('${base}${path}', {`,
    ...init,
    '})',
    'if (!resp.ok) throw new Error(await resp.text())',
    'console.log(await resp.json())',
  ].join('\n')
}

function node({ base, key, method, path, body }) {
  return [
    "// Node 18+ has fetch built in",
    `const resp = await fetch('${base}${path}', {`,
    `  method: '${method}',`,
    '  headers: {',
    `    'X-API-Key': process.env.STATEJAR_KEY,`,
    ...(body ? ["    'Content-Type': 'application/json',"] : []),
    '  },',
    ...(body ? [`  body: JSON.stringify(${pretty(body).replace(/\n/g, '\n  ')}),`] : []),
    '})',
    'const data = await resp.json()',
    'console.log(data)',
  ].join('\n')
}

const BUILDERS = { curl, python, javascript, node }

export function snippetFor(language, spec) {
  return (BUILDERS[language] || curl)(spec)
}

export const SDK_SNIPPET = `import requests


class StateJar:
    """Minimal StateJar client — drop this into your project."""

    def __init__(self, api_key: str, base_url: str = "https://api.statejar.com"):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.session = requests.Session()
        self.session.headers["X-API-Key"] = api_key

    def _post(self, path: str, payload: dict) -> dict:
        resp = self.session.post(self.base + path, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def remember(self, session_tag: str, text: str) -> dict:
        """Extract and store structured state. Returns the new handle."""
        return self._post("/memory/ingest", {"session_tag": session_tag, "text": text})

    def recall(self, session_tag: str, query: str, audit: bool = True) -> dict:
        """The minimal subset this query needs — put THIS in your prompt."""
        return self._post(
            "/memory/query",
            {"session_tag": session_tag, "query": query, "audit": audit},
        )


jar = StateJar("sj_live_...")
jar.remember("user-42", "I prefer email, budget under 2000")
print(jar.recall("user-42", "What is my budget?")["subset"])`
