# DevCopilot: AI-Powered Multi-Agent Codebase Assistant

An intelligent system that transforms how developers explore, understand, and contribute to complex software repositories through advanced AI and graph-based knowledge representation.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![React](https://img.shields.io/badge/React-18-61dafb)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-ff6b35)
![FAISS](https://img.shields.io/badge/FAISS-Vector--Search-yellow)

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐
│  React Frontend │────▶│           FastAPI Backend                │
│  (Vite + React) │◀────│                                          │
└─────────────────┘     │  ┌──────────┐  ┌───────────────────┐     │
                        │  │ Ingestion│  │ Knowledge Graph   │     │
                        │  │ (Clone,  │─▶│ (NetworkX DiGraph)│     │
                        │  │  Parse,  │  └───────────────────┘     │
                        │  │  Chunk)  │  ┌───────────────────┐     │
                        │  └──────────┘─▶│ Vector Store      │     │
                        │                │ (FAISS + Sentence │     │
                        │                │  Transformers)    │     │
                        │                └───────────────────┘     │
                        │  ┌──────────────────────────────────┐    │
                        │  │    LangGraph Multi-Agent System  │    │
                        │  │  ┌────┐ ┌───────┐ ┌───┐ ┌────┐  │    │
                        │  │  │ QA │ │CodeGen│ │LLD│ │ PR │  │    │
                        │  │  └────┘ └───────┘ └───┘ └────┘  │    │
                        │  └──────────────────────────────────┘    │
                        │  ┌──────────────────────────────────┐    │
                        │  │     Explainability Engine         │    │
                        │  └──────────────────────────────────┘    │
                        └──────────────────────────────────────────┘
```

## 🚀 Four Specialized AI Agents

| Agent | Purpose |
|-------|---------|
| **💬 Q&A Agent** | Answers technical and architectural questions via graph traversal + semantic search |
| **⚙️ Code Generation Agent** | Generates code aligned with existing architecture, style, and dependencies |
| **📐 LLD Planning Agent** | Creates detailed technical plans and component breakdowns |
| **🔀 PR Analysis Agent** | Reviews pull requests, traces impact, and identifies risks |

## 🛠️ Tech Stack

- **Backend**: Python, FastAPI, LangGraph, LangChain, Gemini 2.0 Flash
- **Graph**: NetworkX directed graph for code structure modeling
- **Search**: FAISS vector index with sentence-transformers embeddings
- **Frontend**: React 18, Vite, React Markdown, Syntax Highlighter
- **Parsing**: Regex-based multi-language code parser (Python, JS, Java, etc.)

## 📦 Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Gemini API Key ([Get one here](https://aistudio.google.com/apikey))
- GitHub Token (optional, for private repos / PR analysis)

### Backend Setup

```bash
cd backend
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY and GITHUB_TOKEN
```

### Frontend Setup

```bash
cd frontend
npm install
```

### Running the Application

**Terminal 1 — Backend:**
```bash
cd backend
python main.py
# API runs at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
# UI runs at http://localhost:5173
```

## 📖 Usage

1. **Ingest a Repository**: Paste a GitHub URL in the sidebar and click "Ingest Repository"
2. **Ask Questions**: Use the chat to ask about the codebase (auto-routes to the right agent)
3. **Select Agent**: Optionally pick a specific agent (Q&A, Code Gen, LLD, PR Analysis)
4. **View Explanations**: Click "Explainability Log" on any response to see the reasoning trace

## 🔍 Explainability

Every response includes a detailed explainability log with:
- Graph nodes visited during reasoning
- FAISS chunks retrieved with similarity scores
- Intermediate conclusions drawn by the agent
- Complete reasoning trace from query to answer

## 📁 Project Structure

```
Major-Project/
├── backend/
│   ├── main.py                  # FastAPI application
│   ├── config.py                # Central configuration
│   ├── requirements.txt         # Python dependencies
│   ├── api/
│   │   └── routes.py            # REST API endpoints
│   ├── ingestion/
│   │   ├── cloner.py            # Repository cloning
│   │   ├── parser.py            # Code parsing & extraction
│   │   └── chunker.py           # Code chunking for embeddings
│   ├── knowledge_graph/
│   │   ├── graph_builder.py     # NetworkX graph construction
│   │   └── graph_query.py       # Graph traversal utilities
│   ├── vector_store/
│   │   ├── embedder.py          # Sentence-transformer embeddings
│   │   └── faiss_store.py       # FAISS index operations
│   ├── agents/
│   │   ├── state.py             # Shared LangGraph state
│   │   ├── orchestrator.py      # LangGraph workflow router
│   │   ├── qa_agent.py          # Q&A agent
│   │   ├── codegen_agent.py     # Code generation agent
│   │   ├── lld_agent.py         # LLD planning agent
│   │   └── pr_agent.py          # PR analysis agent
│   └── explainability/
│       └── logger.py            # Explainability logging
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── index.css
│       ├── services/
│       │   └── api.js           # API client
│       └── components/
│           ├── Sidebar.jsx
│           ├── ChatInterface.jsx
│           └── ExplainabilityLog.jsx
└── README.md
```

## 📜 License

This project is for educational and research purposes.
