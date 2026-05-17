# EEG CSWL Analysis — EC vs EO QEEG

Process paired **CSWL** files (Eyes Closed / Eyes Open), generate band-wise metrics, and run **vertical** or **horizontal** QEEG statistical analysis with optional **Gemini** clinical narrative.

## Overview

| Input | Processing | Output |
|-------|------------|--------|
| Two `.cswl` files (EC + EO) | LORETA spectrum or montage parsing → section metrics | Metrics DOCX, Plotly charts, AI report (Streamlit) |
| Same via API | Optional upload to DigitalOcean Spaces | DOCX + ZIP URLs |

**Analysis modes (Streamlit)**

- **Vertical (EC vs EO)** — Condition comparison: subsection/band aggregates, % change, normalize Yes/No/NS, heatmaps, abnormal z-rates.
- **Horizontal (timeline / matrix)** — EC & EO as two timepoints: trajectory, statistical matrix (mean, SD, % abnormal), symptom pattern scores.

Supports **LORETA regional spectrum** (e.g. `EC.D1.cswl`) and **montage** (10–20) CSWL formats.

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/jayswalsatyam51-cloud/streamlit_EEG.git
cd streamlit_EEG
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment

```bash
cp .env.example .env
```

Edit `.env` (never commit this file):

| Variable | Required for | Description |
|----------|----------------|-------------|
| `GEMINI_API_KEY` | Streamlit AI report | Google Gemini API key |
| `GEMINI_MODEL` | Optional | Default `gemini-2.5-flash` |
| `DO_REGION`, `DO_ACCESS_KEY`, `DO_ACCESS_SECRET`, `DO_BUCKET_NAME` | API cloud upload | DigitalOcean Spaces |

### 3. Streamlit (recommended)

```bash
streamlit run streamlit_cswl.py
```

1. Upload **EC** and **EO** `.cswl` files → **Process CSWL files**
2. Choose **Vertical** or **Horizontal** analysis
3. **Run statistical + AI analysis** → view charts, tables, and Gemini narrative

### 4. API (optional)

```bash
uvicorn api:app --reload
```

- Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **POST** `/extraction` — form fields `cswl1`, `cswl2` → DOCX (+ ZIP) on Spaces when DO credentials are set

### 5. Tests

```bash
python -m unittest tests.test_cswl_calculations -v
```

Sample files: `sample file cswl/EC.D1.cswl`, `sample file cswl/EO.D1.cswl`.

---

## API

### POST `/extraction` (alias `/extraction/cswl`)

| Field | Type | Description |
|-------|------|-------------|
| `cswl1` | file | First condition (T1 Z / EC) |
| `cswl2` | file | Second condition (T2 Z / EO) |

**Response (200)**

```json
{
  "message": "CSWL files processed successfully",
  "cswl_format": "loreta_spectrum",
  "url": "https://.../archive.zip",
  "filename": "...",
  "doc_url": "https://.../report.docx",
  "doc_filename": "..."
}
```

**Errors:** `400` invalid CSWL, `413` file too large (20 MB), `500` processing or upload failure.

### GET `/`

Returns API name and endpoint list.

---

## Project layout

```
├── api.py                      # FastAPI — CSWL upload
├── streamlit_cswl.py           # Streamlit UI (EC/EO + analysis)
├── cswl_pipeline.py            # CSWL → section CSVs → DOCX
├── qeeg_statistical_analysis.py
├── qeeg_charts.py              # Plotly charts
├── ai_interpretation.py        # Gemini reports
├── report_builder.py
├── metrics_core.py
├── interpretation_diagnostics.py
├── upload_utils.py             # DigitalOcean Spaces
├── tests/
├── sample file cswl/           # Example EC/EO files
├── .env.example
├── .dockerignore
└── Dockerfile
```

---

## Docker

```bash
docker build -t eeg-cswl-api .
docker run -p 8000:8000 --env-file .env eeg-cswl-api
```

`.dockerignore` excludes `.env`, PDFs, virtualenvs, and local outputs from the image.

---

## Security

- **Do not commit** `.env`, API keys, or patient PDFs (`*.pdf` is gitignored).
- Use `.env.example` as the template for new environments.
- Set secrets in CapRover / hosting env vars, not in source control.
- CSWL sample data in the repo should be anonymized test exports only.

---

## Deployment (CapRover)

Set the same variables as in `.env.example` under **App Configs → Environment Variables**, then restart the app.

---

## License

See repository license. Use clinical outputs as decision support only — not a standalone diagnosis.
