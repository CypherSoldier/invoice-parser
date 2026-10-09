# Invoice Parser

Invoice Parser is a lightweight Streamlit app that turns supplier invoices and receipt photos into clean, exportable CSV data. Built for boutique e-commerce operators, it reduces the time spent retyping line items, quantities, prices, and totals into a spreadsheet.

## Why this project exists

For small retailers and resellers, invoice data entry is mostly repetitive and error-prone. The work often happens when a shipment arrives or when a purchase needs to be reconciled against margin and cashflow data. Instead of manually copying values from every document, this app lets the user upload a PDF or image and quickly review the extracted invoice details before export.

## Features

- Upload invoice PDFs or receipt photos
- Extract supplier names, totals, and line items using Gemini vision
- Review extracted values in an editable table before export
- Download the result as a CSV for accounting or spreadsheet workflows
- Free-tier usage guardrail with an upgrade path to Pro
- Demo Pro checkout flow using the Payfast sandbox

## Tech stack

- Python 3.12+
- Streamlit
- Google Gemini API for OCR/vision extraction
- Pandas for review/export tables
- PDF conversion via pdf2image and Poppler
- Pillow for image handling

## Project structure

- `main.py` — Streamlit app and invoice extraction workflow
- `SPEC.md` — product/change notes and feature requirements
- `sample_invoices/` — sample invoice files for local testing
- `tests/` — automated tests covering the invoice workflow
- `pyproject.toml` — Python project metadata and dependencies

## Getting started

### 1. Clone the repository

```bash
git clone https://github.com/CypherSoldier/invoice-parser.git
cd invoice_parser
```

### 2. Install dependencies

If you use `uv`:

```bash
uv sync
```

Or with a standard virtual environment:

```bash
python -m venv .venv
. .venv\Scripts\activate
pip install .
```

This project uses the dependencies declared in `pyproject.toml`, so `uv sync` is the preferred option if available.

### 3. Configure API access

Create a `.env` file in the project root and add your Gemini API key:

```env
GEMINI_API_KEY="your_api_key_here"
```

### 4. Install Poppler for PDF processing

PDF uploads require Poppler on Windows. If `pdfinfo` and `pdftoppm` are not already available on the system, install Poppler and ensure its `Library\bin` directory is on the PATH or set `POPPLER_PATH` in your environment.

### 5. Run the app

```bash
streamlit run main.py
```

Then open the local Streamlit URL shown in the terminal.

## How it works

1. Upload a PDF invoice or an image of a receipt.
2. The app converts PDF pages to images when needed.
3. Gemini extracts supplier information, totals, and line items.
4. The extracted invoice is displayed in an editable table.
5. The user corrects any OCR mistakes and downloads the final data as a CSV.

## Free tier and Pro plan

The app includes a session-based free-tier model:

- Up to 3 invoices per session can be processed for free
- A Pro upgrade unlocks additional invoice processing within the current session
- The Pro flow is implemented as a demo Payfast sandbox checkout

## Example workflow

- Upload a supplier invoice PDF
- Verify the extracted description, quantity, unit price, and line total
- Download the cleaned CSV into Excel, Google Sheets, or your accounting system

## License

This project is provided as a local prototype/demo for invoice extraction workflows. Update the license before production use if you plan to distribute or commercialize it.

## Notes

This repository is designed for a small business workflow and is intentionally focused on a simple, practical user experience rather than a large-scale accounting platform. It is suitable for experimentation, validation, and extension into a full SaaS product.