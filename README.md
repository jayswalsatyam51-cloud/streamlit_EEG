# EEG Medical Record PDF Data Extraction & Comparison System

## Overview

This application is designed to streamline the extraction, processing, and comparison of EEG medical data from PDF files. It is particularly useful for clinicians and researchers who need to analyze and compare EEG reports efficiently.

- **Input:** Two PDF files (`pdf1` and `pdf2`)
- **Processing:** Extracts relevant data, applies calculations, and compares values between the two PDFs
- **Output:** A ZIP file containing:
  - CSV files with extracted and processed data
  - A summary document highlighting key findings and comparisons

The modular design allows for easy integration of new extraction rules and calculation methods, making it adaptable for various EEG data analysis tasks.

---

## Features

- 📄 **PDF Data Extraction:** Automatically extracts structured data from EEG report PDFs.
- 🧮 **Automated Calculations:** Applies domain-specific calculations to the extracted data.
- ⚖️ **Comparison Engine:** Compares results between two reports for quick analysis.
- 📦 **Comprehensive Output:** Exports results as CSV files and a summary document, all packaged in a ZIP file.
- 🔌 **Extensible:** Easily add new extraction rules or calculation methods.

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

### 3. Run the Application Locally

Start the FastAPI server using Uvicorn:

```bash
uvicorn api:app --reload
```

The application will be available at [http://127.0.0.1:8000].

---

## Usage

1. **Upload PDFs:** Use the provided API endpoint or UI (if available) to upload two PDF files (`pdf1` and `pdf2`).
2. **Processing:** The system will extract data, perform calculations, and compare the results.
3. **Download Results:** Receive a ZIP file containing:
   - CSV files with extracted/calculated data
   - A summary document with key findings

---

## Example

1. Upload `report1.pdf` and `report2.pdf`
2. Download `results.zip`

---

## Project Structure

EEGmedicalrecord/
│
├── api.py # FastAPI application entry point
├── calc.py # Calculation logic
├── pdf_extraction.py # PDF extraction utilities
├── upload_utils.py # File upload and handling utilities
├── uploads/ # Directory for uploaded files
├── requirements.txt # Python dependencies
└── README.md # Project documentation