/* One definition per endpoint: schema tables and every language example are
   generated from this, so the docs cannot describe a shape the examples
   contradict. */

export const ENDPOINTS = [
  {
    id: 'ingest',
    method: 'POST',
    path: '/api/v1/memory/ingest',
    title: 'Ingest',
    description:
      'Turn conversation text into structured state. Identical state always ' +
      'produces an identical handle; new information for the same session ' +
      'mints a new handle whose parent points at the previous one.',
    request: [
      ['session_tag', 'string', true, 'Partitions a user\'s memory — "user-42", "ticket-991".'],
      ['text', 'string', true, 'The raw message to extract from.'],
    ],
    response: [
      ['handle', 'string', 'SHA-256 content address of the new state.'],
      ['parent_handle', 'string | null', 'The version this evolved from.'],
      ['state', 'object', 'The canonical stored state.'],
      ['conflicts', 'array', 'Contradictions kept rather than overwritten.'],
      ['extraction_source', 'string[]', 'Which tiers contributed: rules, gliner2, llm.'],
      ['extraction_origins', 'object', 'Field path → the tier that found it.'],
    ],
    body: {
      session_tag: 'user-42',
      text: 'My name is Ayaan, budget under 2000. I prefer email.',
    },
    example: {
      handle: 'shm_18c8fecaf5dacf38deda0914ecdb1b38b40566c1',
      parent_handle: null,
      state: {
        constraints: { budget_inr_max: 2000 },
        facts: { name: 'Ayaan' },
        preferences: { contact_mode: 'email' },
      },
      conflicts: [],
      extraction_source: ['rules'],
      extraction_origins: { 'facts.name': 'rules', 'preferences.contact_mode': 'rules' },
    },
  },
  {
    id: 'query',
    method: 'POST',
    path: '/api/v1/memory/query',
    title: 'Query',
    description:
      'Retrieve the minimum a question needs. The subset is what belongs in ' +
      'your model prompt — not the transcript, not the whole profile.',
    request: [
      ['session_tag', 'string', true, 'Which memory to read.'],
      ['query', 'string', true, 'The question about to be answered.'],
      ['audit', 'boolean', false, 'Record the disclosure. Default false.'],
    ],
    response: [
      ['handle_used', 'string', 'The memory version this was read from.'],
      ['subset', 'object', 'Only the fields the query needed.'],
      ['metadata.subset_keys', 'string[]', 'Dotted paths disclosed.'],
      ['metadata.retrieval_mode', 'string', 'intent_map | semantic_fallback | broad_fallback.'],
      ['metadata.token_estimate_saved_pct', 'number', 'Subset vs full state.'],
      ['audit_id', 'string | null', 'Present when audit was true.'],
    ],
    body: { session_tag: 'user-42', query: 'What is my budget?', audit: true },
    example: {
      handle_used: 'shm_18c8fecaf5dacf38deda0914ecdb1b38b40566c1',
      subset: { constraints: { budget_inr_max: 2000 } },
      metadata: {
        retrieval_mode: 'intent_map',
        subset_keys: ['constraints.budget_inr_max'],
        fields_dropped: 4,
        token_estimate_saved_pct: 73.9,
      },
      audit_id: '7272c2ea8d0c44e18c914184996bf843',
    },
  },
  {
    id: 'chat',
    method: 'POST',
    path: '/api/v1/chat',
    title: 'Chat',
    description:
      'Retrieval, prompt assembly, the model call and the audit row in one ' +
      'round trip. Needs a provider key saved in the console.',
    request: [
      ['session_tag', 'string', true, 'Which memory to read.'],
      ['query', 'string', true, 'The user message.'],
      ['model', 'string', false, 'provider/model id. Never whitelisted.'],
      ['provider', 'string', false, 'Fallback when the id carries no prefix.'],
    ],
    response: [
      ['response', 'string', 'The model reply, in plain language.'],
      ['handle_used', 'string', 'Memory version used.'],
      ['subset_keys', 'string[]', 'Exactly which fields reached the model.'],
      ['audit_id', 'string', 'Replay this later.'],
    ],
    body: {
      session_tag: 'user-42',
      query: 'Book my delivery with my usual preferences',
      model: 'meta-llama/llama-3.3-70b-instruct:free',
    },
    example: {
      response: "Booking with your saved preferences — I'll email the confirmation.",
      handle_used: 'shm_18c8fecaf5dacf38deda0914ecdb1b38b40566c1',
      subset_keys: ['preferences.contact_mode', 'constraints.budget_inr_max'],
      audit_id: '4b8e77c1a0d2f3e9',
    },
  },
  {
    id: 'versions',
    method: 'GET',
    path: '/api/v1/memory/versions?session_tag=user-42',
    title: 'Versions',
    description:
      'The handle chain for a session, oldest first. History is appended, ' +
      'never overwritten, so every past version stays addressable.',
    request: [['session_tag', 'string', true, 'Query-string parameter.']],
    response: [
      ['session_tag', 'string', 'Echoed back.'],
      ['versions', 'string[]', 'Handles, oldest first.'],
    ],
    body: null,
    example: {
      session_tag: 'user-42',
      versions: ['shm_18c8fec…', 'shm_22fa3ef…'],
    },
  },
  {
    id: 'audit',
    method: 'GET',
    path: '/api/v1/audit?limit=50',
    title: 'Audit',
    description:
      'What was disclosed, when, to which model. Supports session, provider, ' +
      'date-range and free-text filters plus offset paging.',
    request: [
      ['limit', 'integer', false, 'Page size, max 200. Default 50.'],
      ['offset', 'integer', false, 'Rows to skip.'],
      ['session_tag', 'string', false, 'One session only.'],
      ['provider', 'string', false, 'One provider only.'],
      ['search', 'string', false, 'Matches handle or request id.'],
      ['include_demo', 'boolean', false, 'Set false to hide demo rows.'],
    ],
    response: [
      ['entries', 'array', 'Audit rows, newest first.'],
      ['total', 'integer', 'Matching rows before paging.'],
      ['has_more', 'boolean', 'Whether another page exists.'],
    ],
    body: null,
    example: {
      entries: [
        {
          request_id: '7272c2ea8d0c44e1',
          handle_used: 'shm_18c8fec…',
          subset_keys: ['constraints.budget_inr_max'],
          provider: 'openrouter',
          model: 'llama-3.3-70b',
          session_tag: 'user-42',
          created_at: '2026-08-02T09:14:00+00:00',
          is_demo: false,
          disclosure_note: null,
        },
      ],
      total: 1,
      has_more: false,
    },
  },
  {
    id: 'models',
    method: 'GET',
    path: '/api/v1/models',
    title: 'Models',
    description:
      'Every provider you have configured, with its live catalog. A provider ' +
      'whose fetch fails returns an error and empty lists rather than ' +
      'failing the whole response.',
    request: [],
    response: [
      ['groups', 'array', 'One per configured provider.'],
      ['groups[].free', 'array', 'Models with no per-token cost.'],
      ['groups[].paid', 'array', 'Everything else.'],
      ['groups[].error', 'string?', 'Present only when that provider failed.'],
      ['source', 'string', 'live | fallback.'],
    ],
    body: null,
    example: {
      groups: [
        {
          provider: 'openrouter',
          label: 'OpenRouter',
          free: [{ id: 'meta-llama/llama-3.3-70b-instruct:free', is_free: true }],
          paid: [{ id: 'openrouter/anthropic/claude-sonnet-4.6', is_free: false }],
        },
      ],
      source: 'live',
    },
  },
  {
    id: 'usage',
    method: 'GET',
    path: '/api/v1/usage',
    title: 'Usage',
    description: 'Account totals for the current key owner.',
    request: [],
    response: [
      ['requests_today', 'integer', 'Audited disclosures since 00:00 UTC.'],
      ['total_states', 'integer', 'Memory versions stored.'],
      ['total_audit_rows', 'integer', 'Lifetime disclosures.'],
      ['est_tokens_saved', 'integer', 'Summed across every disclosure.'],
    ],
    body: null,
    example: {
      requests_today: 3,
      total_states: 1,
      total_audit_rows: 3,
      est_tokens_saved: 87,
    },
  },
]

export const ERROR_CODES = [
  ['400', 'Bad request', 'A required field is missing, or no provider key is saved for the model you chose. The message names which.'],
  ['401', 'Unauthorised', 'Missing, unknown, revoked or expired X-API-Key. An expired key says so, with the date.'],
  ['403', 'Forbidden', 'The credential is valid but not for this resource — usually an API key on a console-only route.'],
  ['404', 'Not found', 'No state exists for this user or session yet, or the handle is unknown to you.'],
  ['429', 'Rate limited', 'Over the limit for that endpoint. Wait and retry; see Rate limits below.'],
  ['502', 'Upstream failed', "The model provider rejected or could not serve the call. The provider's own message is passed through."],
]

export const RATE_LIMITS = [
  ['POST /api/v1/chat', '60 / hour', 'API key (or user)'],
  ['POST /api/v1/auth/login', '5 / minute', 'IP'],
  ['POST /api/v1/auth/signup', '10 / hour', 'IP'],
  ['Everything else', 'unlimited', '—'],
]

export const CONCEPTS = [
  {
    id: 'handles',
    title: 'Deterministic handles',
    body:
      'A handle is a SHA-256 digest of the canonical state, not a random id. ' +
      'The same meaning always produces the same handle, so two users with ' +
      'identical state share one — and any change mints a new one.',
    diagram: 'state ──canonicalize──▶ bytes ──SHA-256──▶ shm_18c8fec…',
  },
  {
    id: 'canonical',
    title: 'Canonical normalization',
    body:
      'Before hashing, keys are sorted at every level, numbers and dates are ' +
      'normalised, and empty values are dropped. Without this, {a,b} and ' +
      '{b,a} would be two different memories.',
    diagram: '{"b":1,"a":2}  ─▶  {"a":2,"b":1}  ─▶  one handle',
  },
  {
    id: 'retrieval',
    title: 'Minimum-sufficient retrieval',
    body:
      'A query returns only the fields it needs. Asking about budget does not ' +
      'disclose a name. This is what makes the token saving real rather than ' +
      'a compression trick.',
    diagram: '12 fields stored  ─▶  query  ─▶  2 fields sent',
  },
  {
    id: 'versioning',
    title: 'Versioning & parent handles',
    body:
      'Updating state never overwrites it. A new handle is minted with ' +
      'parent_handle pointing at the previous version, so the whole chain ' +
      'stays addressable and auditable.',
    diagram: 'shm_a ──▶ shm_b ──▶ shm_c   (a and b still readable)',
  },
  {
    id: 'conflicts',
    title: 'Conflict preservation',
    body:
      'When a new statement contradicts an old one, both are kept and the ' +
      'contradiction is recorded. Memory that silently overwrites is memory ' +
      'you cannot audit.',
    diagram: 'budget 2000 → 2500   keeps both + a conflict record',
  },
  {
    id: 'replay',
    title: 'Audit & replay',
    body:
      'Every disclosure logs the handle and the exact fields sent. Replay ' +
      're-derives the handle from the stored state, so a match proves the ' +
      'bytes behind that answer are unchanged.',
    diagram: 'audit row ─▶ fetch state ─▶ re-hash ─▶ byte-identical ✓',
  },
]
