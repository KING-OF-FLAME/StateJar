<p align="center"><img src="docs/assets/logo.png" width="140"/></p>

<h1 align="center">StateJar</h1>

<p align="center"><i>Deterministic memory for AI that never forgets — or hallucinates its past.</i></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white"/>
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black"/>
  <img src="https://img.shields.io/badge/MySQL-8-4479A1?logo=mysql&logoColor=white"/>
  <img src="https://img.shields.io/badge/tests-65%20passing-6B9080"/>
  <img src="https://img.shields.io/badge/Patent-202621017626-E07856"/>
</p>

<p align="center">
  <b><a href="https://statejar.com">Live Demo</a></b> ·
  <a href="#-architecture">Architecture</a> ·
  <a href="#-the-10-patent-modules">Modules</a> ·
  <a href="#-local-setup">Setup</a> ·
  <a href="#-roadmap-round-2">Roadmap</a>
</p>

<p align="center">🏆 <b>Team Hello World</b> · Hack4Humanity 2026 · AI for Societal Good</p>

<p align="center"><img src="docs/gifs/m6_retrieval.gif" width="70%"/></p>

<table align="center">
  <tr>
    <td align="center"><b>~78%</b><br><sub>tokens saved</sub></td>
    <td align="center"><b>10</b><br><sub>patent modules</sub></td>
    <td align="center"><b>65</b><br><sub>tests passing</sub></td>
    <td align="center"><b>SHA-256</b><br><sub>deterministic</sub></td>
  </tr>
</table>

# 🚀 StateJar

**StateJar** is a **patent-pending deterministic memory architecture** for conversational AI.

Instead of making an AI model read long conversation histories every time a user asks a question, StateJar stores only the important information in a structured format. When the AI needs to remember something, it retrieves only the required information instead of the entire conversation.

This makes AI systems:

* **Faster**
* **More cost-efficient**
* **More accurate**
* **Able to remember across multiple sessions without replaying old chats**

---

# ❌ The Problem

Today's conversational AI systems typically remember users by sending previous chat history back to the LLM.

This creates several challenges:

* **High token usage** because large chat histories are sent repeatedly.
* **Slower responses** since the model processes a lot of unnecessary text.
* **Context window limitations** because LLMs can only process a limited amount of text at once.
* **Memory drift**, where important information may be forgotten or inconsistently recalled.
* **Poor auditability**, making it difficult to verify exactly what information the AI used.

---

# ✅ Our Solution

StateJar replaces conversation replay with **structured memory**.

Instead of storing everything the user says, StateJar keeps only the important facts in a deterministic format.

When the user asks a question, it retrieves only the information required for that query.

For example:

**Conversation**

* My name is Dhruv.
* I prefer Java.
* My budget is ₹20,000.

**User asks**

> "What's my budget?"

**Traditional approach**

* Reads a large portion of previous conversations to find the answer.

**StateJar**

* Directly retrieves:

  * Budget = ₹20,000

No unnecessary conversation is sent to the LLM.

---

# ⚙️ How StateJar Works

### 1. Extract

* Identify important facts from the conversation.
* Example:

  * Name
  * Preferences
  * Budget
  * Constraints

### 2. Canonicalize

* Convert the information into one standard format.
* Identical information always produces the same structured representation.

### 3. Store

* Generate a unique SHA-256 handle for the structured state.
* This creates a secure, deterministic reference without storing the full conversation.

### 4. Retrieve Minimum

* When the AI receives a new query, it retrieves only the fields needed to answer it.
* The LLM processes only relevant information instead of the entire chat history.

---

# 📈 Benefits

* **Up to 78% fewer tokens**
* **Lower inference cost**
* **Faster response time**
* **Reduced context window usage**
* **Consistent and deterministic memory**
* **Minimal information disclosure**
* **Complete audit trail**
* **Multi-session memory without replaying chat history**

---

# 🎯 In One Sentence

**StateJar is a patent-pending memory architecture that enables conversational AI to remember important information efficiently by storing structured state and retrieving only the exact data needed, instead of rereading entire conversations.**

---

## 🧬 Architecture

```mermaid
flowchart LR
    U[User message] --> E[Extractor]
    E --> C[Canonicalizer]
    C --> H["Handle generator\nshm_ + SHA-256"]
    H --> S[(MySQL\nappend-only states)]
    S --> V[Versioning + Conflicts]
    Q[User query] --> R[Retriever\nminimal subset]
    S --> R
    R --> G[LLM Gateway\nAES-256-GCM keys]
    G --> LLM[OpenRouter]
    G --> A[(Audit log\ndeterministic replay)]
```

<br>

---

## 📦 The 10 Patent Modules

| # | Module | File | What it does |
|---|--------|------|--------------|
| 1 | State Extraction | `backend/app/memory/extractor.py` | Text → structured state |
| 2 | Canonicalization | `backend/app/memory/canonicalizer.py` | Deterministic canonical JSON |
| 3 | Handle Generation | `backend/app/memory/handle.py` | Content-addressed `shm_` SHA-256 handles |
| 4 | Deduplicated Storage | `backend/app/memory/storage.py` | Identical meaning stored once |
| 5 | No Full Chat Replay | `backend/app/memory/storage.py` | Raw transcripts rejected at write time |
| 6 | Minimal Disclosure Retrieval | `backend/app/memory/retriever.py` | Sends only the fields needed |
| 7 | Append-Only Versioning | `backend/app/memory/versioning.py` | Updates create new handles; history immutable |
| 8 | Conflict Preservation | `backend/app/memory/conflict.py` | Contradictions recorded, never overwritten |
| 9 | Cross-Session Consistency | `backend/app/memory/routes.py` | New sessions use latest state |
| 10 | Audit + Replay | `backend/app/memory/audit.py` | Every LLM call logged, replayable |

<br>

---

## 🎬 Module Animations

*(M6 — Minimal Disclosure Retrieval — is the hero animation at the top.)*

<table>
  <tr>
    <td width="50%"><b>M1 — Structured Memory Capture</b><br><img src="docs/gifs/m1_extraction.gif" width="100%"/></td>
    <td width="50%"><b>M2 — Deterministic Canonicalization</b><br><img src="docs/gifs/m2_canonicalize.gif" width="100%"/></td>
  </tr>
  <tr>
    <td width="50%"><b>M3 — Content-Addressed Handles</b><br><img src="docs/gifs/m3_handle.gif" width="100%"/></td>
    <td width="50%"><b>M4 — Deduplicated Storage</b><br><img src="docs/gifs/m4_storage.gif" width="100%"/></td>
  </tr>
  <tr>
    <td width="50%"><b>M5 — No Full Chat Replay</b><br><img src="docs/gifs/m5_no_replay.gif" width="100%"/></td>
    <td width="50%"><b>M7 — Append-Only Versioning</b><br><img src="docs/gifs/m7_versioning.gif" width="100%"/></td>
  </tr>
  <tr>
    <td width="50%"><b>M8 — Conflict Preservation</b><br><img src="docs/gifs/m8_conflict.gif" width="100%"/></td>
    <td width="50%"><b>M9 — Cross-Session Consistency</b><br><img src="docs/gifs/m9_cross_session.gif" width="100%"/></td>
  </tr>
  <tr>
    <td width="50%"><b>M10 — Audit Trail + Deterministic Replay</b><br><img src="docs/gifs/m10_audit.gif" width="100%"/></td>
    <td width="50%"></td>
  </tr>
</table>

<br>

---

## 🌐 Live Demo

🔗 **[statejar.com](https://statejar.com)** — deployed on Vercel + Railway

### Screenshots

<table>
  <tr>
    <td width="50%"><b>Landing</b><br><img src="docs/screenshots/landing.png" width="100%" alt="Landing page"/></td>
    <td width="50%"><b>Playground — live memory inspector</b><br><img src="docs/screenshots/playground.png" width="100%" alt="Playground"/></td>
  </tr>
  <tr>
    <td width="50%"><b>Minimal retrieval (2 of 14 fields sent, ~78% tokens saved)</b><br><img src="docs/screenshots/retrieval.png" width="100%" alt="Retrieved context"/></td>
    <td width="50%"><b>Handle timeline — append-only versioning</b><br><img src="docs/screenshots/handles.png" width="100%" alt="Handles"/></td>
  </tr>
  <tr>
    <td width="50%"><b>Audit trail — provable provenance</b><br><img src="docs/screenshots/audit.png" width="100%" alt="Audit log"/></td>
    <td width="50%"><b>Dashboard</b><br><img src="docs/screenshots/dashboard.png" width="100%" alt="Dashboard"/></td>
  </tr>
</table>

<br>

---

## 🚀 Local Setup

<details>
<summary><b>🚀 Local Setup (click to expand)</b></summary>

Prereqs: Python 3.12+, Node 18+, XAMPP (MySQL running).

```bash
# 1. Clone
git clone https://github.com/KING-OF-FLAME/StateJar.git && cd StateJar

# 2. Database — import the schema into XAMPP MySQL
#    (phpMyAdmin → Import → db/migrations/001_init.sql, or:)
mysql -u root < db/migrations/001_init.sql

# 3. Backend
cd backend
pip install -r requirements.txt
copy .env.example .env        # then edit JWT_SECRET / AES_KEY

# 4. Run the API
uvicorn app.main:app --reload --port 8000

# 5. Verify
pytest                         # 65 passed
curl http://localhost:8000/api/v1/health

# 6. Frontend (new terminal)
cd frontend
npm install
npm run dev                    # → http://localhost:5173
```

Sign up → save an OpenRouter key in **API Keys** → open **Playground** → say
*"My name is Ayaan, I prefer email, budget ₹2000"* → start a **new session** → ask *"Book my delivery"* — watch it retrieve only the 3 fields it needs.

</details>

<br>

---

## 🧰 Tech Stack

- FastAPI
- SQLAlchemy 2.0
- MySQL
- Pydantic v2
- bcrypt + JWT Authentication
- AES-256-GCM Encryption
- React 18 + Vite
- OpenRouter Gateway
- pytest (65 tests)

## 📊 Benchmark

On the demo scenarios, minimal-disclosure retrieval sends **~48–78% fewer tokens** of context than full-state replay (per-request % is computed live and shown in the Playground). Formal benchmark suite lands in Round 2 — *see Roadmap*.

<br>

---

## 🧭 Roadmap (Round 2)

- **GLiNER2 as primary extractor** (rule-based becomes fallback) for open-domain extraction
- **Benchmark suite** — token savings & consistency vs. transcript-replay and vector-memory baselines
- **Multi-provider gateway** — native OpenAI / Anthropic / Gemini / Ollama alongside OpenRouter
- Audit-log UI, org/team workspaces, handle export API

## 📄 License

Proprietary · All Rights Reserved · Indian Patent 202621017626. Shared for Hack4Humanity 2026 evaluation. See [LICENSE](LICENSE).

<br>

---

<p align="center"><img src="docs/assets/logo.png" width="60"/></p>

<p align="center"><sub>Indian Patent No. 202621017626 </sub></p>

<p align="center">Built with ❤️ by <b>Team Hello World</b> — Yash Raj</p>

<p align="center">
  <a href="https://statejar.com">Demo</a> ·
  <a href="https://github.com/KING-OF-FLAME/StateJar/issues">GitHub Issues</a> ·
  <a href="LICENSE">License</a>
</p>
