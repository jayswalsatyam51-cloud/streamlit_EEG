# EEG Medical Record PDF Data Extraction & Comparison System

## Overview

This application is designed to streamline the extraction, processing, and comparison of EEG medical data from PDF files. It is particularly useful for clinicians and researchers who need to analyze and compare EEG reports efficiently.

- **Input:** Two PDF files (`pdf1` and `pdf2`)
- **Processing:** Extracts relevant data, applies calculations, and compares values between the two PDFs
- **Output:** Processed data in multiple formats (DOCX, HTML) with CSV files, all uploaded to DigitalOcean Spaces

The modular design allows for easy integration of new extraction rules and calculation methods, making it adaptable for various EEG data analysis tasks.

---

## Features

- 📄 **PDF Data Extraction:** Automatically extracts structured data from EEG report PDFs
- 🧮 **Automated Calculations:** Applies domain-specific calculations to the extracted data
- ⚖️ **Comparison Engine:** Compares results between two reports for quick analysis
- 📦 **Multiple Output Formats:** Supports DOCX and HTML output formats
- 🧾 **CSWL to DOCX:** Supports direct `.cswl` pair upload via API and generates styled DOCX output
- ☁️ **Cloud Storage Integration:** Automatically uploads results to DigitalOcean Spaces
- 🔌 **Extensible:** Easily add new extraction rules or calculation methods

---

## Getting Started

### 1. Clone the Repository

```bash
git clone <https://github.com/kwikedart/EEGmedicalrecord.git>
cd EEGmedicalrecord
```

### 2. Install Requirements

Make sure you have Python 3.8+ installed. Then, install the required dependencies:

```bash
pip install -r requirements.txt
```

### 3. Environment Setup

#### Local Development

Create a `.env` file in the project root with the following DigitalOcean Spaces credentials:

```env
DO_REGION=nyc3
DO_ACCESS_KEY=your_access_key_here
DO_ACCESS_SECRET=your_secret_key_here
DO_BUCKET_NAME=your_bucket_name_here
GEMINI_API_KEY=your_gemini_api_key_here
# Optional: GEMINI_MODEL=gemini-2.5-flash
```

#### CapRover Deployment

In CapRover, set the environment variables through the app settings:

1. Go to your CapRover dashboard
2. Select your app
3. Navigate to **App Configs** → **Environment Variables**
4. Add the following environment variables:

| Variable Name | Value |
|--------------|-------|
| `DO_REGION` | Your DigitalOcean Spaces region (e.g., `nyc3`) |
| `DO_ACCESS_KEY` | Your DigitalOcean Spaces access key |
| `DO_ACCESS_SECRET` | Your DigitalOcean Spaces secret key |
| `DO_BUCKET_NAME` | Your DigitalOcean Spaces bucket name |
| `GEMINI_API_KEY` | Google Gemini API key (required for AI interpretation DOCX on `/extraction`) |
| `GEMINI_MODEL` | Optional; defaults to `gemini-2.5-flash` |

**Important:** After adding environment variables, restart your app in CapRover for the changes to take effect.

### 4. Run the Application Locally

Start the FastAPI server using Uvicorn:

```bash
uvicorn api:app --reload
```

The application will be available at [http://127.0.0.1:8000].

### Web UI (optional)

Open **[http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui)** in a browser to upload two PDFs and receive download links for the ZIP, summary DOCX, and AI interpretation (v1), or HTML output (v2). You can set a different API base URL if the page is served from another origin.

### Streamlit (CSWL → DOCX only)

Runs **standalone** — no `uvicorn` or separate API process. It uses the same CSWL → DOCX logic as **`POST /extraction/cswl`**, but builds the file locally and offers a download (no cloud upload).

```bash
streamlit run streamlit_cswl.py
```

Open the URL Streamlit prints (default **http://localhost:8501**).

---

## API Documentation

### Base URL

```
http://127.0.0.1:8000
```

### Endpoints

#### 1. Root Endpoint

**GET** `/`

Returns API information and available endpoints.

**Request:**
```bash
curl http://127.0.0.1:8000/
```

**Response:**
```json
{
  "message": "Welcome to PDF Data Extraction API",
  "endpoints": {
    "/extraction": "POST - Upload and process PDF files (returns DOCX)",
    "/extraction/v2": "POST - Upload and process PDF files (returns HTML format only)",
    "/docs": "GET - API documentation"
  }
}
```

---

#### 2. PDF Extraction (v1 - DOCX Format)

**POST** `/extraction`

Uploads two PDF files, extracts data, performs calculations, and returns DOCX format summary plus an **AI interpretation** DOCX (when `GEMINI_API_KEY` is set). The pipeline first computes **structured diagnostics** (per-section aggregates, top % changes, Set 1 vs Set 2 direction counts) in `eeg_interpretation_diagnostics.json`, then Gemini generates **multiple interpretation candidates** and one deterministic rule-based interpretation in a sectioned narrative (Executive Summary, Descriptive overview, Set 1 vs Set 2 highlights, Cross-section patterns, Limitations)—similar in spirit to tabbed clinical stats UIs, but for two-PDF comparison rather than longitudinal sessions.

**Request Format:**
- **Method:** `POST`
- **Content-Type:** `multipart/form-data`
- **Parameters:**
  - `pdf1` (file, required): First PDF file
  - `pdf2` (file, required): Second PDF file

**Example using cURL:**
```bash
curl -X POST "http://127.0.0.1:8000/extraction" \
  -F "pdf1=@report1.pdf" \
  -F "pdf2=@report2.pdf"
```

**Example using Python requests:**
```python
import requests

url = "http://127.0.0.1:8000/extraction"
files = {
    'pdf1': open('report1.pdf', 'rb'),
    'pdf2': open('report2.pdf', 'rb')
}

response = requests.post(url, files=files)
print(response.json())
```

**Response Format:**
```json
{
  "message": "File processed and uploaded successfully to DigitalOcean Spaces",
  "url": "https://bucket.region.cdn.digitaloceanspaces.com/timestamp_uuid.zip",
  "filename": "20250101_120000_abc12345.zip",
  "doc_url": "https://bucket.region.cdn.digitaloceanspaces.com/timestamp_uuid.docx",
  "doc_filename": "20250101_120000_abc12345.docx",
  "interpretation_url": "https://bucket.region.cdn.digitaloceanspaces.com/timestamp_uuid.docx",
  "interpretation_filename": "20250101_120000_abc12345.docx",
  "interpretation_note": "Optional: present when AI interpretation was skipped or failed"
}
```

**Response Fields:**
- `message` (string): Success message
- `url` (string): CDN URL to the ZIP file containing all CSV files (includes `eeg_ai_interpretation.docx` and `eeg_interpretation_diagnostics.json` when AI interpretation succeeds)
- `filename` (string): Unique filename of the ZIP file
- `doc_url` (string): CDN URL to the DOCX summary document (`eeg_analysis_summary.docx`)
- `doc_filename` (string): Unique filename of the DOCX file
- `interpretation_url` (string|null): CDN URL to download the **AI interpretation** DOCX; `null` if `GEMINI_API_KEY` is missing or generation failed
- `interpretation_filename` (string|null): Unique filename for the interpretation file
- `interpretation_note` (string, optional): Explains why interpretation was skipped (e.g. missing API key) or failed

**Error Responses:**
- `400 Bad Request`: Invalid file type (not PDF)
  ```json
  {
    "detail": "File filename.pdf is not a PDF"
  }
  ```
- `500 Internal Server Error`: Processing error
  ```json
  {
    "detail": "Error message"
  }
  ```

---

#### 3. PDF Extraction (v2 - HTML Format)

**POST** `/extraction/v2`

Uploads two PDF files, extracts data, performs calculations, and returns HTML format summary (body content only).

**Request Format:**
- **Method:** `POST`
- **Content-Type:** `multipart/form-data`
- **Parameters:**
  - `pdf1` (file, required): First PDF file
  - `pdf2` (file, required): Second PDF file

**Example using cURL:**
```bash
curl -X POST "http://127.0.0.1:8000/extraction/v2" \
  -F "pdf1=@report1.pdf" \
  -F "pdf2=@report2.pdf"
```

**Example using Python requests:**
```python
import requests

url = "http://127.0.0.1:8000/extraction/v2"
files = {
    'pdf1': open('report1.pdf', 'rb'),
    'pdf2': open('report2.pdf', 'rb')
}

response = requests.post(url, files=files)
print(response.json())
```

**Response Format:**
```json
{
  "message": "File processed and uploaded successfully to DigitalOcean Spaces (v2 - HTML format)",
  "url": "https://bucket.region.cdn.digitaloceanspaces.com/timestamp_uuid.zip",
  "filename": "20250101_120000_abc12345.zip",
  "html_url": "https://bucket.region.cdn.digitaloceanspaces.com/timestamp_uuid.html",
  "html_filename": "20250101_120000_abc12345.html"
}
```

**Response Fields:**
- `message` (string): Success message
- `url` (string): CDN URL to the ZIP file containing all CSV files
- `filename` (string): Unique filename of the ZIP file
- `html_url` (string): CDN URL to the HTML summary document (body content only)
- `html_filename` (string): Unique filename of the HTML file

**Error Responses:**
- `400 Bad Request`: Invalid file type (not PDF)
- `500 Internal Server Error`: Processing error

---

#### 4. CSWL Extraction (DOCX Format)

**POST** `/extraction/cswl`

Uploads two `.cswl` files, computes band-wise metrics, and returns a DOCX summary using the same report style as PDF extraction.

**Request Format:**
- **Method:** `POST`
- **Content-Type:** `multipart/form-data`
- **Parameters:**
  - `cswl1` (file, required): First CSWL file
  - `cswl2` (file, required): Second CSWL file

**Example using cURL:**
```bash
curl -X POST "http://127.0.0.1:8000/extraction/cswl" \
  -F "cswl1=@EC.D1.cswl" \
  -F "cswl2=@EO.D1.cswl"
```

**Response Format:**
```json
{
  "message": "CSWL files processed and uploaded successfully",
  "url": "https://bucket.region.cdn.digitaloceanspaces.com/timestamp_uuid.zip",
  "filename": "20250101_120000_abc12345.zip",
  "doc_url": "https://bucket.region.cdn.digitaloceanspaces.com/timestamp_uuid.docx",
  "doc_filename": "20250101_120000_abc12345.docx"
}
```

---

#### 5. Calculation Endpoint

**POST** `/calculation`

Accepts a CSV file and section type, returns band-wise absolute sums.

**Request Format:**
- **Method:** `POST`
- **Content-Type:** `multipart/form-data`
- **Parameters:**
  - `csv_file` (file, required): CSV file to process
  - `section_type` (string, required): Type of section

**Example using cURL:**
```bash
curl -X POST "http://127.0.0.1:8000/calculation" \
  -F "csv_file=@data.csv" \
  -F "section_type=Z Scored FFT Absolute Power"
```

**Response Format:**
```json
{
  "summary": {
    "section_type": "Z Scored FFT Absolute Power",
    "subsections": {
      "Subsection1": {
        "Band1": {
          "T1_sum": 123.45,
          "T2_sum": 234.56
        },
        "Band2": {
          "T1_sum": 345.67,
          "T2_sum": 456.78
        }
      }
    }
  }
}
```

---

#### 6. File Download Endpoint

**GET** `/download/{timestamp}/{filename}`

Downloads a file from the uploads directory (for local file access).

**Request Format:**
- **Method:** `GET`
- **Path Parameters:**
  - `timestamp` (string): Timestamp directory name
  - `filename` (string): Name of the file to download

**Example:**
```bash
curl "http://127.0.0.1:8000/download/20250101_120000/eeg_analysis_summary.docx"
```

**Response:**
- Returns the file as a download
- `404 Not Found`: File doesn't exist

---

#### 7. API Documentation (Swagger UI)

**GET** `/docs`

Interactive API documentation using Swagger UI.

Access at: `http://127.0.0.1:8000/docs`

---

## Output Formats

### DOCX Format (v1)
- Full document with styling
- Includes all sections with metrics
- Suitable for printing and sharing

### HTML Format (v2)
- Body content only (no HTML structure tags)
- Follows Dart Editor HTML guide format
- Uses semantic HTML tags:
  - `<strong>` for bold text
  - `<h1>`, `<h2>` for headings
  - `<pre>` for section headers
  - `<p>` for paragraphs
  - Bullet points for metrics

### CSV Files
The ZIP file contains individual CSV files for each section:
- `Z Scored FFT Absolute Power.csv`
- `Z Scored FFT Power Ratio.csv`
- `Z Scored Peak Frequency.csv`
- `Z Scored FFT Coherence.csv`
- `Z Scored FFT Phase Lag.csv`

---

## Usage Examples

### Complete Workflow Example

```python
import requests

# Upload and process PDFs
url = "http://127.0.0.1:8000/extraction/v2"
files = {
    'pdf1': open('eeg_report_1.pdf', 'rb'),
    'pdf2': open('eeg_report_2.pdf', 'rb')
}

response = requests.post(url, files=files)
result = response.json()

if response.status_code == 200:
    print(f"Success! HTML file available at: {result['html_url']}")
    print(f"ZIP file available at: {result['url']}")
else:
    print(f"Error: {result['detail']}")
```

---

## Project Structure

```
EEGmedicalrecord/
│
├── api.py                    # FastAPI application entry point
├── calc.py                   # Calculation logic
├── pdf_extraction.py         # PDF extraction utilities
├── upload_utils.py           # DigitalOcean Spaces upload utilities
├── uploads/                  # Directory for uploaded files (local)
├── requirements.txt          # Python dependencies
├── Dockerfile                # Docker configuration
├── .env                      # Environment variables (not in repo)
└── README.md                 # Project documentation
```

---

## Environment Variables

Required environment variables (set in `.env` file):

| Variable | Description | Example |
|----------|-------------|---------|
| `DO_REGION` | DigitalOcean Spaces region | `nyc3` |
| `DO_ACCESS_KEY` | DigitalOcean Spaces access key | `your_access_key` |
| `DO_ACCESS_SECRET` | DigitalOcean Spaces secret key | `your_secret_key` |
| `DO_BUCKET_NAME` | DigitalOcean Spaces bucket name | `your_bucket_name` |
| `GEMINI_API_KEY` | Gemini API key for AI interpretation on `/extraction` | `your_gemini_key` |
| `GEMINI_MODEL` | Optional Gemini model name | `gemini-2.5-flash` |

---

## Security Considerations

- All file uploads are validated for PDF format
- File size limits are enforced (default: 500MB)
- Path traversal protection implemented
- HTML content is properly escaped to prevent XSS
- Credentials are stored in environment variables (never in code)
- CORS is configured (currently allows all origins - adjust for production)

---

## Error Handling

The API returns standard HTTP status codes:

- `200 OK`: Request successful
- `400 Bad Request`: Invalid input (e.g., non-PDF file)
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server processing error

All errors return JSON format:
```json
{
  "detail": "Error message description"
}
```

---

## Development

### Running in Development Mode

```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### Running with Docker

```bash
docker build -t eeg-extraction-api .
docker run -p 8000:8000 --env-file .env eeg-extraction-api
```

---

## License

[Add your license information here]

---

## Support

For issues and questions, please open an issue on the GitHub repository.