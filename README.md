# 🛡️ Self-Healing AI Automation System

> **Code-E-Fiesta 2026 — Problem Statement 4**  
> Domain: AI Engineering | Intelligent Monitoring

Autonomous error detection, root-cause diagnosis, and automated patch execution for mission-critical workflows.

---

## 🎯 What It Does

This system demonstrates an end-to-end **self-healing pipeline**:

1. **🔍 Detect** — Monitors workflow execution and catches failures in real time
2. **🧠 Diagnose** — AI-powered root-cause analysis classifies errors and identifies affected fields
3. **💊 Heal** — Generates corrective payload patches and schema transformations
4. **🔁 Retry** — Validates the fix and re-executes the workflow, with optional human approval

## 📸 Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Workflow    │    │   Monitor    │    │  Diagnostic  │    │   Healing    │
│   Observer    │───▶│  & Detector  │───▶│    Agent     │───▶│ Synthesizer  │
│   & Runner   │    │              │    │   (AI/Rules) │    │              │
└──────────────┘    └──────────────┘    └──────────────┘    └──────┬───────┘
                                                                   │
                    ┌──────────────┐    ┌──────────────┐          │
                    │  Real-Time   │◀───│ Verification │◀─────────┘
                    │  Dashboard   │    │ & Retry      │
                    │  (WebSocket) │    │  Pipeline    │
                    └──────────────┘    └──────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- pip

### Setup

```bash
# 1. Navigate to the project
cd self-healing-ai

# 2. Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Configure environment
copy .env.example .env
# Edit .env to add your Gemini API key for AI-powered diagnosis

# 5. Run!
python main.py
```

### Open the Dashboard
Navigate to **http://localhost:8000** in your browser.

## 🧪 Demo Guide

### One-Click Demo
1. Open the dashboard
2. Click any **Quick Demo** button (e.g., "Order + Missing Field")
3. Watch the full cycle: Fault Injection → Detection → Diagnosis → Healing → Retry

### Manual Demo
1. Select a **Workflow** and **Fault Type** from the dropdowns
2. Click **"🧪 Inject Fault & Run"**
3. Observe the pipeline stages animate in real time
4. If the fix confidence is below 90%, you'll be prompted to **Approve** or **Reject** the fix

### Normal Run
Click **"▶️ Run Normal"** to run a workflow without faults (validates everything works correctly)

## 🔧 Supported Workflows

| Workflow | Description | Steps |
|----------|-------------|-------|
| 🛒 Order Processing | E-commerce order pipeline | Validate → Inventory → Payment → Confirmation |
| 📊 Data ETL | Data extraction & loading | Extract → Transform → Validate Schema → Load |
| 👤 User Onboarding | User registration flow | Validate → Create Account → Welcome Email → Preferences |

## 💥 Supported Fault Types

| Fault | Description | Example |
|-------|-------------|---------|
| 🗑️ Missing Field | Removes a required field | `customer_id` removed from order |
| 🔀 Schema Mismatch | Renames fields (API version change) | `total_amount` → `totalAmt` |
| 💥 Bad Payload | Corrupts data types/structure | `items` set to string instead of list |
| 🔤 Type Error | Changes field types | `total_amount` set to `"one-hundred"` |
| ⚠️ Invalid Value | Sets invalid/edge-case values | Negative amount, empty list |

## 🤖 AI Provider

The system supports two diagnosis modes:

- **Rule-based** (default): Fast, deterministic analysis using pattern matching — works out of the box
- **Gemini AI**: Uses Google's Gemini API for more nuanced analysis — set `AI_PROVIDER=gemini` and add your `GEMINI_API_KEY` in `.env`

## 📁 Project Structure

```
self-healing-ai/
├── main.py                 # FastAPI app, REST API, WebSocket
├── config.py               # Configuration & environment
├── models.py               # Pydantic data models
├── store.py                # In-memory data store & event bus
├── workflow_engine.py      # Simulated business workflows
├── fault_injector.py       # Failure injection module
├── monitor.py              # Error detection & incident creation
├── diagnostics.py          # AI/rule-based root cause analysis
├── healer.py               # Fix generation & payload patching
├── retry_pipeline.py       # Verification & retry logic
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
└── static/
    ├── index.html          # Dashboard UI
    ├── style.css           # Styles
    └── app.js              # Frontend logic
```

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Dashboard |
| `WS` | `/ws` | Real-time event stream |
| `GET` | `/api/workflows/templates` | List workflow templates |
| `GET` | `/api/faults` | List fault types |
| `POST` | `/api/workflows/run` | Run a workflow |
| `POST` | `/api/demo/full-cycle` | Run full demo cycle |
| `GET` | `/api/incidents` | List incidents |
| `GET` | `/api/incidents/{id}` | Incident detail |
| `POST` | `/api/incidents/{id}/approve` | Approve a fix |
| `POST` | `/api/incidents/{id}/reject` | Reject a fix |
| `GET` | `/api/stats` | System statistics |

## 🏗️ Tech Stack

- **Backend**: Python, FastAPI, Pydantic
- **Real-time**: WebSocket
- **AI**: Google Gemini API (optional) + Rule-based fallback
- **Frontend**: Vanilla HTML/CSS/JS (no build step needed)
- **Architecture**: Event-driven, async pipeline

---

**Built for Code-E-Fiesta 2026 — Problem Statement 04** | AI Engineering & Intelligent Monitoring
