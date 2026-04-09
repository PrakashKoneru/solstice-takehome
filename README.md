# ContentStudio — Pharma Slide Generation Platform

AI-powered slide deck creation for HCP audiences, built for FRUZAQLA. Multi-agent orchestration ensures every factual claim is grounded in approved Knowledge Base documents and brand guidelines are applied consistently.

---

## Prerequisites

- **Python 3.9+** (3.11 recommended — matches the deployment target)
- **Node.js 18+** (20+ recommended for Next.js 16)
- **PostgreSQL** running locally
- **Anthropic API key**

---

## Local Setup

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd SolisticeH
```

### 2. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> `pymupdf` is already pinned in `requirements.txt` — no extra install needed.

Create a `.env` file in `backend/` (you can copy `backend/.env.example`):

```
ANTHROPIC_API_KEY=your_key_here
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/solstice
SECRET_KEY=any-random-string
FLASK_APP=app.py
FLASK_ENV=development
UPLOAD_FOLDER=uploads
```

Create the database and run migrations:

```bash
createdb solstice
flask db upgrade
```

Start the backend:

```bash
python app.py
```

> **Important:** use `python app.py`, **not** `flask run`. The server uses Flask-SocketIO for realtime presence/collaboration and must be started via `socketio.run()` (invoked in `app.py`). `flask run` will start but presence features will silently break.

The backend will listen on **http://localhost:5001**. Health check: `GET /api/health`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The `.env.local` (already committed) points the frontend at `http://localhost:5001`. If your backend runs elsewhere, edit `frontend/.env.local` and set `NEXT_PUBLIC_API_URL`.

Open [http://localhost:3000](http://localhost:3000).

### 4. Inspecting the database

The backend exposes **Flask-Admin** at [http://localhost:5001/admin](http://localhost:5001/admin) — browse/edit all tables (sessions, messages, knowledge items, design systems, assets) directly through a web UI. No setup required; it's registered automatically in `app.py`.

Alternative: connect any Postgres client (TablePlus, DBeaver, `psql`, etc.) with the `DATABASE_URL` from your `.env`.

```bash
psql postgresql://postgres:postgres@localhost:5432/solstice
\dt              # list tables
\d messages      # describe the messages table
```

Uploaded files (KB PDFs, design system PDFs, extracted assets) live in `backend/uploads/` and are served at `/uploads/<filename>`.

---

## Usage

1. **Design System** — Go to `/design-system`, upload the FRUZAQLA Style Guide PDF. The system extracts brand tokens, guidelines, component patterns, and brand assets automatically. Watch the progress UI — each step is a separate extraction pipeline.
2. **Knowledge Base** — Go to `/knowledge-base`, upload the FRUZAQLA Prescribing Information PDF. The uploader runs a claim extraction pipeline that pulls every factual statement into an approvable claim catalog.
3. **Create** — Go to `/create`, start a new session. Select your design system and KB doc(s) from the top bar, then chat to generate slides. Use the edit button in the output panel to hand-edit individual slides; manual edits save automatically and trigger a fresh compliance review.

---

## Architecture (brief)

### Multi-Agent Orchestration

Every user message is routed by an orchestrator agent, then passed to the right specialist:

| Agent | Model | Role |
|---|---|---|
| Orchestrator | Haiku | Reads user intent, picks generate/edit/chat for the turn |
| Narrative Planner | Haiku | Plans the slide arc for a new deck |
| Claim Selector | Haiku | Picks approved claims per slide from the catalog |
| Slide Builder | Sonnet | Structures each slide's layout + claim wiring |
| Content Renderer | Opus | Renders the structured spec as brand-compliant HTML |
| Spec Editor | Sonnet | Applies targeted edits to an existing deck |
| Review Agent | Opus | Compliance-checks claims against KB (soft checks) |
| Chat Agent | Opus | Conversational guidance, planning, summaries |
| Token Extractor | Opus | Extracts design tokens from style guide PDF |
| Brand Guidelines Extractor | Opus + Vision | Extracts brand rules from PDF pages |
| Component Patterns Extractor | Sonnet + Vision | Identifies layout/component patterns from PDF |
| Asset Classifier | Haiku + Vision | Classifies extracted images as logo/icon/image |
| Claim Extractor | Opus | Pulls factual claims from KB PDFs |

### Why this approach

- **Compliance by architecture, not by prompt.** The slide pipeline is designed so that factual text can't drift from the source: the claim selector can only pick from an enum of approved claim IDs (enforced at the tool-schema level), and the renderer receives pre-resolved claim text that it's instructed to emit verbatim. This is stronger than a "don't hallucinate" system prompt because the model never sees a blank field where it could improvise a number — it sees a claim ID and a fixed string. No KB docs selected = no generation, no exceptions.
- **Claim-grounded generation.** Every factual element in a slide traces back to an approved `Claim` row in the DB with source page and citation. The compliance trace is deterministic.
- **Streaming pipeline.** Slide generation runs in parallel across slides and streams HTML chunks to the browser via Server-Sent Events, so the preview fills in progressively instead of blocking on the full render.
- **Maker-Checker pattern.** Every generation is reviewed by a separate Review Agent against the same KB. Manual edits trigger an HTML-drift detector that flags any rendered text that no longer matches its approved claim.
- **Version history.** Every generation, edit, manual save, and restore is a new `Message` row with the full deck HTML attached — a complete undo trail with no branching.
- **Realtime collaboration.** Socket.IO presence tracks which users are viewing/editing the session; slide-level edit locks prevent conflicts.

### Tech Stack

- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4
- **Backend:** Flask 3, Flask-SocketIO, SQLAlchemy, Alembic (flask-migrate)
- **Database:** PostgreSQL (via psycopg3)
- **LLM:** Anthropic Claude API (Haiku 4.5, Sonnet 4.6, Opus 4.6)
- **PDF processing:** PyMuPDF (fitz)
- **Realtime:** Socket.IO (flask-socketio + socket.io-client)

---

## Data Model

```
ChatSession
  ├── id
  ├── title
  ├── selected_ds_id    → DesignSystem.id
  ├── selected_doc_ids  → [KnowledgeItem.id, ...]   (JSON)
  ├── created_at, updated_at
  └── messages → Message[]

Message
  ├── id
  ├── session_id        → ChatSession.id
  ├── role              ('user' | 'assistant')
  ├── content           (plain text — user prompt or chat reply)
  ├── html_content      (full slide deck HTML | null)
  ├── review_report     (JSON: verdict, flags, trace, spec | null)
  └── created_at

KnowledgeItem                         (uploaded KB PDFs)
  ├── id
  ├── title, filename, file_path
  ├── text_content      (extracted PDF text)
  ├── doc_type
  ├── extraction_status ('pending' | 'extracting' | 'complete' | 'failed')
  ├── total_pages
  └── claims → Claim[]

Claim                                  (approved factual claims from KB)
  ├── id                 (stable: "{drug}_{type}_{study}_{seq}")
  ├── knowledge_id       → KnowledgeItem.id
  ├── text               (verbatim, immutable after approval)
  ├── claim_type         (efficacy | safety | dosing | moa | isi |
  │                       boilerplate | stat | study_design |
  │                       indication | nccn)
  ├── source_citation
  ├── page_number
  ├── numeric_values     (JSON: [{value, unit, label}, ...])
  ├── tags               (JSON: [string, ...])
  ├── is_approved
  └── created_at

DesignSystem                            (uploaded style guide + extracted rules)
  ├── id
  ├── name, pdf_filename
  ├── tokens              (JSON — colors, fonts, spacing, etc.)
  ├── brand_guidelines    (JSON — tone, personality, audience rules, etc.)
  ├── component_patterns  (JSON — per-component layout rules)
  ├── extraction_status
  ├── extraction_step
  ├── is_default
  └── assets → DesignSystemAsset[]

DesignSystemAsset                       (logos, icons, images from PDF)
  ├── id
  ├── design_system_id    → DesignSystem.id
  ├── name
  ├── asset_type          ('logo' | 'icon' | 'image')
  ├── file_url
  ├── filename
  ├── source              ('raster' | 'page_render')
  └── created_at
```

The `Message.review_report` JSON embeds the full slide `spec` used to generate the HTML, so every version in the trail is self-contained and can be restored without reconstructing context.
