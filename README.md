# ContentStudio — Pharma Slide Generation Platform

AI-powered slide deck creation for HCP audiences, built for FRUZAQLA. Multi-agent orchestration ensures every claim is grounded in approved Knowledge Base documents and brand guidelines are applied consistently.

---

## Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL running locally
- Anthropic API key
- PyMuPDF: `pip install pymupdf`

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
pip install pymupdf
```

Create a `.env` file in `backend/`:

```
ANTHROPIC_API_KEY=your_key_here
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/solstice
SECRET_KEY=any-random-string
```

Create the database and run migrations:

```bash
createdb solstice
flask db upgrade
```

Start the backend:

```bash
flask run --port 5001
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Usage

1. **Design System** — Go to `/design-system`, upload the FRUZAQLA Style Guide PDF. The system extracts brand tokens, guidelines, slide templates, and assets automatically.
2. **Knowledge Base** — Go to `/knowledge-base`, upload the FRUZAQLA Prescribing Information PDF.
3. **Create** — Go to `/create`, start a new session. Select your design system and KB doc from the top bar, then chat to generate slides.

---

## Architecture

### Multi-Agent Orchestration

Every user message passes through an orchestrator (Claude Haiku) that decides which agents to invoke:

| Agent | Model | Role |
|---|---|---|
| Orchestrator | Haiku | Reads user intent, routes to correct agents |
| Content Agent | Sonnet | Generates branded HTML slides |
| Review Agent | Sonnet | Compliance-checks every claim against KB |
| Chat Agent | Sonnet | Conversational guidance and planning |
| Token Extractor | Sonnet | Extracts design tokens from PDF |
| Brand Guidelines Extractor | Sonnet + Vision | Extracts brand rules from PDF pages |
| Slide Templates Extractor | Sonnet + Vision | Identifies layout templates from PDF |
| Asset Classifier | Haiku + Vision | Classifies extracted images as logo/icon/image |

### Why this approach

**Compliance by architecture, not by prompt.** The Content Agent is physically incapable of inventing claims — it only has access to text explicitly extracted from uploaded KB documents. No KB docs selected = no HTML generated, no exceptions.

**Selective context injection.** Brand guidelines and design tokens only go to the Content Agent. The Orchestrator and Chat Agent receive a slim history (HTML replaced with `[slides generated]`) to avoid token waste and prevent HTML leaking into chat responses.

**Maker-Checker pattern.** Every generation is immediately reviewed by a separate Review Agent that reads the same KB and flags unverified claims. The review report is stored alongside the HTML and surfaces a compliance verdict in the UI.

**Version history.** Every generation, edit, and restore is a new `Message` row. The full deck state is stored as `html_content` on each message, giving a complete undo trail without branching complexity.

### Data Model

```
ChatSession
  ├── selected_ds_id → DesignSystem
  ├── selected_doc_ids → KnowledgeItem[]
  └── messages → Message[]
        ├── role (user | assistant)
        ├── content (plain text)
        ├── html_content (slide HTML | null)
        └── review_report (JSON | null)

DesignSystem
  ├── tokens (JSON)
  ├── brand_guidelines (JSON)
  ├── slide_templates (JSON)
  └── assets → DesignSystemAsset[]

KnowledgeItem
  └── text_content (extracted PDF text)
```

### Tech Stack

- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS
- **Backend:** Flask, SQLAlchemy, Alembic
- **Database:** PostgreSQL
- **LLM:** Anthropic Claude API (Haiku + Sonnet)
- **PDF processing:** PyMuPDF (fitz)
