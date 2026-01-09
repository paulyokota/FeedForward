# FeedForward Frontend

Streamlit dashboard for operational visibility into the FeedForward pipeline.

## Quick Start

```bash
# Terminal 1: Start the API
uvicorn src.api.main:app --reload --port 8000

# Terminal 2: Start the frontend
streamlit run frontend/app.py
```

Then open http://localhost:8501 in your browser.

## Pages

- **Dashboard** - Overview metrics, classification distribution, recent runs
- **Pipeline** - Kick off runs, configure parameters, monitor progress
- **Themes** - Browse trending themes, orphans, and singletons

## Architecture

```
frontend/
├── app.py              # Main entry point
├── api_client.py       # FastAPI client wrapper
└── pages/
    ├── 1_Dashboard.py  # Metrics overview
    ├── 2_Pipeline.py   # Run and monitor
    └── 3_Themes.py     # Theme browser
```

## API Endpoints Used

| Page      | Endpoints                                                 |
| --------- | --------------------------------------------------------- |
| Dashboard | `/api/analytics/dashboard`                                |
| Pipeline  | `/api/pipeline/run`, `/status`, `/history`, `/active`     |
| Themes    | `/api/themes/trending`, `/orphans`, `/singletons`, `/all` |

## Configuration

Set `API_URL` environment variable to change the API endpoint:

```bash
API_URL=http://api.example.com streamlit run frontend/app.py
```

Default: `http://localhost:8000`
