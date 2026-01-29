# Workflows

**Data management workflows for Swiss federal real estate**

A web application providing data validation, enrichment, and conversion workflows for building and facility management data. Built for the Digital Real Estate and Support (DRES) department at the Swiss Federal Office for Buildings and Logistics (BBL).

![Swiss Federal Design](https://img.shields.io/badge/Design-Swiss%20Federal%20CD-DC0018)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green)

---

## Workflows

| Workflow | Type | Status | Description |
|----------|------|--------|-------------|
| **EGID/GWR Checker** | Validator | Productive | Validates building data against the Swiss GWR register |
| **IFC to Excel** | Converter | In Development | Converts IFC building models to Excel format |
| **CAFM-Basisplan Checker** | Validator | In Development | Validates CAFM floor plans against BBL requirements |

---

## EGID/GWR Checker

Validates and enriches building data against the official Swiss Gebäude- und Wohnungsregister (GWR):

- **EGID Validation** - Checks that building identifiers exist in the GWR
- **Address Matching** - Compares your addresses with official GWR data
- **Coordinate Validation** - Verifies WGS84 coordinates against GWR (50m tolerance)
- **Data Enrichment** - Fills in missing coordinates and address components from GWR
- **Match Scoring** - Generates evaluation scores (Match/Partial/Mismatch/Not Found)

### Export Format

Multi-tab Excel reports with:
- **Rules** - Description of validation rules applied
- **Meta** - Input/output column definitions
- **Input** - Original uploaded data
- **Output** - Enriched data with GWR results
- **Warnings** - Detailed error/warning list with row references

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11, FastAPI, Pandas |
| Frontend | Single HTML file (vanilla JS) |
| Styling | Swiss Federal Corporate Design |
| External APIs | geo.admin.ch GWR Feature Service |
| Deployment | Fly.io (Docker) |

---

## Quick Start

### Prerequisites
- Python 3.11+
- pip

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/workflows.git
   cd workflows
   ```

2. **Install dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Run the backend**
   ```bash
   uvicorn main:app --reload --port 8000
   ```

4. **Access the application**
   - Frontend: `http://localhost:8000`
   - API docs: `http://localhost:8000/docs`

---

## Project Structure

```
workflows/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── requirements.txt     # Python dependencies
│   └── validation/          # Validation engine & rules
│       ├── engine.py
│       ├── base.py
│       └── rules/
├── workflows/
│   ├── workflows.json       # Workflow definitions
│   └── address-validation/
│       └── workflow.py      # GWR enricher implementation
├── assets/
│   └── swiss-logo-*.svg     # Swiss federal logos
├── index.html               # Frontend (single file)
├── Dockerfile               # Container build
├── fly.toml                 # Fly.io configuration
└── docs/
    ├── REQUIREMENTS.md
    ├── ARCHITECTURE.md
    └── DESIGNGUIDE.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve frontend |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/workflows` | List available workflows |
| `GET` | `/api/workflows/{id}` | Get workflow details |
| `POST` | `/api/workflows/{id}/upload` | Upload file for processing |
| `POST` | `/api/workflows/{id}/sessions/{sid}/validate` | Run workflow |
| `GET` | `/api/workflows/{id}/sessions/{sid}/report` | Download Excel report |

Full API documentation available at `/docs` (Swagger UI).

---

## Deployment

### Fly.io

```bash
# Install flyctl
# https://fly.io/docs/hands-on/install-flyctl/

# Login
fly auth login

# Deploy
fly deploy
```

### Docker (Manual)

```bash
docker build -t workflows .
docker run -p 8080:8080 workflows
```

---

## Configuration

Environment variables (set in `fly.toml` or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_TIMEOUT_MINUTES` | 30 | Session expiry time |
| `MAX_FILE_SIZE_MB` | 50 | Maximum upload file size |

---

## License

MIT License - see [LICENSE](LICENSE)

---

## Acknowledgments

- [geo.admin.ch](https://geo.admin.ch) - Swiss Federal Geoportal
- [Swiss Federal Corporate Design](https://www.bk.admin.ch/bk/de/home/dokumentation/cd-bund.html)

Built by **Bundesamt für Bauten und Logistik (BBL)**, Abteilung Digital Real Estate und Support
