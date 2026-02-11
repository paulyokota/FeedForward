# FeedForward

LLM-powered pipeline that turns Intercom support conversations into sprint-ready stories for the Tailwind product backlog.

## What it does

Reads Intercom conversations, classifies them, extracts specific product themes, scores confidence, runs PM-style review, and produces stories with evidence bundles.

## Tech stack

- Python 3.11, FastAPI, Next.js
- OpenAI gpt-4o-mini
- PostgreSQL + pgvector
- pytest (~2,400 tests)

## Quick start

```bash
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8000  # API
cd webapp && npm run dev                        # Frontend at localhost:3000
```

API docs at [localhost:8000/docs](http://localhost:8000/docs).

## Documentation

| Document                                     | Purpose                             |
| -------------------------------------------- | ----------------------------------- |
| [CLAUDE.md](CLAUDE.md)                       | Development conventions             |
| [docs/architecture.md](docs/architecture.md) | System design and component details |
| [docs/status.md](docs/status.md)             | Current progress                    |
| [docs/changelog.md](docs/changelog.md)       | What has shipped                    |
