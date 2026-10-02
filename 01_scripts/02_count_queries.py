import os
import time
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
import pymupdf


# =============================================================================
# PROJECT CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PDF_DIR = PROJECT_ROOT / "05_pdfs"
RESULTS_DIR = PROJECT_ROOT / "02_results"
LOGS_DIR = PROJECT_ROOT / "03_logs"

SAMPLE_FILE = RESULTS_DIR / "00_1_sample_selection.xlsx"
DOWNLOAD_STATUS_FILE = RESULTS_DIR / "01_1_download_status.xlsx"

OUTPUT_FILE = RESULTS_DIR / "02_1_query_counts.xlsx"
SUMMARY_FILE = RESULTS_DIR / "02_2_processing_summary.xlsx"
LOG_FILE = LOGS_DIR / "02_count_queries.log"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# PROCESSING CONFIGURATION
# =============================================================================

AI_PROVIDER = os.getenv("AI_PROVIDER", "none").strip().lower()
AI_MODEL = os.getenv("AI_MODEL", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()

MAX_AI_RETRIES = 4
BASE_WAIT_SECONDS = 15
PAUSE_BETWEEN_PDFS = 0.2


# =============================================================================
# LOGGING
# =============================================================================

LOG_LINES = []


def log(message=""):
    text = str(message)
    print(text)
    LOG_LINES.append(text)


def save_log():
    LOG_FILE.write_text(
        "\n".join(LOG_LINES) + "\n",
        encoding="utf-8"
    )


# =============================================================================
# TEXT UTILITIES
# =============================================================================

def normalize_text(text):
    text = str(text).lower()
    text = unicodedata.normalize("NFKD", text)

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def safe_integer(value):
    if pd.isna(value):
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def extract_procedure_code(pdf_path):
    match = re.match(
        r"^(\d+)",
        pdf_path.stem
    )

    if not match:
        return None

    return int(match.group(1))


# =============================================================================
# PDF TEXT EXTRACTION
# =============================================================================

def extract_pdf_text(pdf_path):
    document = pymupdf.open(pdf_path)

    try:
        pages = [
            page.get_text("text")
            for page in document
        ]

        page_count = len(document)

    finally:
        document.close()

    return "\n".join(pages), page_count


# =============================================================================
# NO-FORMULATION ACT DETECTION
# =============================================================================

def detect_no_formulation_act(text):
    normalized = normalize_text(text)

    patterns = (
        "acta de no formulacion",
        "no se formularon consultas",
        "no se registraron consultas",
        "no formulacion de consultas",
        "no se registraron formulacion de consultas",
        "no se registraron formulaciones de consultas",
        "no se registraron consultas y observaciones",
        "no se registraron consultas ni observaciones",
        "no se formularon consultas y observaciones",
        "no se formularon consultas ni observaciones",
    )

    if any(
        pattern in normalized
        for pattern in patterns
    ):
        return True

    has_query_context = (
        "consulta" in normalized
    )

    has_observation_context = (
        "observacion" in normalized
    )

    has_no_formulation = (
        "no formulacion" in normalized
        or "no se formularon" in normalized
        or "no se registro" in normalized
        or "no se registraron" in normalized
    )

    return (
        has_no_formulation
        and (
            has_query_context
            or has_observation_context
        )
    )


# =============================================================================
# LOCAL QUERY / OBSERVATION DETECTION
# =============================================================================

def detect_query_records(text):
    pattern = re.compile(
        r"""
        \bNro\.?
        \s*
        (\d+)
        \s*
        .{0,180}?
        \bConsulta
        \s*/\s*
        Observaci[oó]n
        \s*:
        """,
        re.IGNORECASE
        | re.DOTALL
        | re.VERBOSE
    )

    matches = pattern.findall(text)

    numbers = [
        int(number)
        for number in matches
    ]

    return sorted(set(numbers))


# =============================================================================
# LOCAL DOCUMENT ANALYSIS
# =============================================================================

def analyze_locally(pdf_path):
    try:
        text, page_count = extract_pdf_text(
            pdf_path
        )

    except Exception as error:
        return {
            "total": None,
            "document_type": None,
            "method": "PYMUPDF",
            "confidence": "LOW",
            "status": "READ_ERROR",
            "notes": (
                f"PDF read error: "
                f"{str(error)[:100]}"
            ),
            "pages": None,
        }

    if len(text.strip()) < 50:
        return {
            "total": None,
            "document_type": None,
            "method": "PYMUPDF",
            "confidence": "LOW",
            "status": "INSUFFICIENT_TEXT",
            "notes": (
                "PDF contains insufficient "
                "extractable text"
            ),
            "pages": page_count,
        }

    if detect_no_formulation_act(text):
        return {
            "total": 0,
            "document_type":
                "ACTA_NO_FORMULACION",
            "method": "PYMUPDF",
            "confidence": "HIGH",
            "status": "OK",
            "notes": (
                "No-formulation act verified "
                "from document text"
            ),
            "pages": page_count,
        }

    numbers = detect_query_records(text)

    if not numbers:
        return {
            "total": None,
            "document_type": None,
            "method": "PYMUPDF",
            "confidence": "LOW",
            "status": "NO_RECORDS_DETECTED",
            "notes": (
                "No query/observation records "
                "detected locally"
            ),
            "pages": page_count,
        }

    first_number = min(numbers)
    last_number = max(numbers)
    unique_count = len(numbers)

    expected_numbers = set(
        range(1, last_number + 1)
    )

    detected_numbers = set(numbers)

    missing_numbers = sorted(
        expected_numbers
        - detected_numbers
    )

    if (
        first_number == 1
        and unique_count == last_number
        and not missing_numbers
    ):
        return {
            "total": last_number,
            "document_type": "PLIEGO",
            "method": "PYMUPDF",
            "confidence": "HIGH",
            "status": "OK",
            "notes": (
                f"Complete sequential numbering "
                f"1-{last_number}"
            ),
            "pages": page_count,
        }

    return {
        "total": last_number,
        "document_type": "PLIEGO",
        "method": "PYMUPDF",
        "confidence": "MEDIUM",
        "status": "REVIEW_REQUIRED",
        "notes": (
            f"Incomplete numbering: "
            f"{unique_count} unique records "
            f"detected up to {last_number}; "
            f"{len(missing_numbers)} missing"
        ),
        "pages": page_count,
    }


# =============================================================================
# AI PROMPT
# =============================================================================

AI_PROMPT = """
You are analyzing an official Peruvian public-procurement document
from SEACE.

Determine:

1. The TOTAL number of queries and observations contained in the
   document.

2. The document type:
   - PLIEGO
   - ACTA_NO_FORMULACION
   - ACTA
   - OTRO

3. A brief note of no more than 100 characters.

Rules:

- For a standard Pliego de Absolucion de Consultas y Observaciones,
  use the highest sequential record number only when the document
  structure supports that interpretation.

- Return total = 0 ONLY when the document explicitly establishes
  that no queries or observations were submitted.

- If the total cannot be determined reliably, return null.

Return ONLY valid JSON:

{
  "total": <integer or null>,
  "tipo_documento":
      "<PLIEGO|ACTA_NO_FORMULACION|ACTA|OTRO>",
  "notas": "<brief note>"
}
"""


# =============================================================================
# GEMINI ADAPTER
# =============================================================================

def analyze_with_gemini(pdf_path):
    try:
        from google import genai
        from google.genai import types

    except ImportError:
        return {
            "total": None,
            "document_type": None,
            "method": "GEMINI",
            "confidence": "LOW",
            "status": "DEPENDENCY_MISSING",
            "notes": (
                "google-genai package is not installed"
            ),
        }

    if not AI_API_KEY:
        return {
            "total": None,
            "document_type": None,
            "method": "GEMINI",
            "confidence": "LOW",
            "status": "API_KEY_MISSING",
            "notes": "AI_API_KEY is not configured",
        }

    if not AI_MODEL:
        return {
            "total": None,
            "document_type": None,
            "method": "GEMINI",
            "confidence": "LOW",
            "status": "MODEL_MISSING",
            "notes": "AI_MODEL is not configured",
        }

    client = genai.Client(
        api_key=AI_API_KEY
    )

    remote_file = None

    try:
        remote_file = client.files.upload(
            file=str(pdf_path)
        )

        waiting_cycles = 0

        while (
            remote_file.state.name
            == "PROCESSING"
        ):
            time.sleep(2)

            remote_file = client.files.get(
                name=remote_file.name
            )

            waiting_cycles += 1

            if waiting_cycles > 30:
                return {
                    "total": None,
                    "document_type": None,
                    "method": "GEMINI",
                    "confidence": "LOW",
                    "status": "TIMEOUT",
                    "notes": (
                        "Timeout while processing PDF"
                    ),
                }

        if (
            remote_file.state.name
            == "FAILED"
        ):
            return {
                "total": None,
                "document_type": None,
                "method": "GEMINI",
                "confidence": "LOW",
                "status": "UPLOAD_FAILED",
                "notes": (
                    "AI provider could not process PDF"
                ),
            }

        response = (
            client.models.generate_content(
                model=AI_MODEL,
                contents=[
                    types.Part.from_uri(
                        file_uri=remote_file.uri,
                        mime_type="application/pdf",
                    ),
                    AI_PROMPT,
                ],
            )
        )

        response_text = (
            response.text.strip()
        )

        if "```" in response_text:
            parts = response_text.split("```")

            if len(parts) >= 2:
                response_text = parts[1]

                if response_text.startswith(
                    "json"
                ):
                    response_text = (
                        response_text[4:]
                    )

                response_text = (
                    response_text.strip()
                )

        data = json.loads(
            response_text
        )

        raw_total = data.get("total")

        if raw_total is None:
            total = None
        else:
            total = int(raw_total)

        document_type = str(
            data.get(
                "tipo_documento",
                "OTRO"
            )
        ).strip()

        notes = str(
            data.get(
                "notas",
                ""
            )
        ).strip()[:100]

        valid_types = {
            "PLIEGO",
            "ACTA_NO_FORMULACION",
            "ACTA",
            "OTRO",
        }

        if (
            document_type
            not in valid_types
        ):
            return {
                "total": None,
                "document_type":
                    document_type,
                "method": "GEMINI",
                "confidence": "LOW",
                "status":
                    "INVALID_RESPONSE",
                "notes": (
                    "Invalid document type "
                    "returned by AI"
                ),
            }

        if (
            total == 0
            and document_type
            != "ACTA_NO_FORMULACION"
        ):
            return {
                "total": None,
                "document_type":
                    document_type,
                "method": "GEMINI",
                "confidence": "LOW",
                "status":
                    "ZERO_NOT_VERIFIED",
                "notes": (
                    "Zero rejected because "
                    "absence was not documented"
                ),
            }

        if total is None:
            return {
                "total": None,
                "document_type":
                    document_type,
                "method": "GEMINI",
                "confidence": "LOW",
                "status":
                    "REVIEW_REQUIRED",
                "notes": (
                    notes
                    or
                    "AI could not determine "
                    "a reliable total"
                ),
            }

        if total < 0:
            return {
                "total": None,
                "document_type":
                    document_type,
                "method": "GEMINI",
                "confidence": "LOW",
                "status":
                    "INVALID_RESPONSE",
                "notes": (
                    "Negative total rejected"
                ),
            }

        return {
            "total": total,
            "document_type":
                document_type,
            "method": "GEMINI",
            "confidence": "HIGH",
            "status": "OK",
            "notes": notes,
        }

    except Exception as error:
        error_text = str(error)

        if (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):
            status = "RETRY_503"

        elif (
            "429" in error_text
            or "RESOURCE_EXHAUSTED"
            in error_text
        ):
            status = "RETRY_429"

        elif (
            "500" in error_text
            or "INTERNAL" in error_text
        ):
            status = "RETRY_500"

        else:
            status = "PERMANENT_ERROR"

        return {
            "total": None,
            "document_type": None,
            "method": "GEMINI",
            "confidence": "LOW",
            "status": status,
            "notes": error_text[:100],
        }

    finally:
        if remote_file is not None:
            try:
                client.files.delete(
                    name=remote_file.name
                )
            except Exception:
                pass


# =============================================================================
# AI ROUTER
# =============================================================================

def analyze_with_ai(pdf_path):
    if AI_PROVIDER in (
        "",
        "none",
        "off",
        "disabled",
    ):
        return {
            "total": None,
            "document_type": None,
            "method": "AI_DISABLED",
            "confidence": "LOW",
            "status": "AI_DISABLED",
            "notes": (
                "No AI fallback configured"
            ),
        }

    if AI_PROVIDER == "gemini":
        return analyze_with_gemini(
            pdf_path
        )

    return {
        "total": None,
        "document_type": None,
        "method": (
            AI_PROVIDER.upper()
        ),
        "confidence": "LOW",
        "status":
            "UNSUPPORTED_PROVIDER",
        "notes": (
            f"AI provider '{AI_PROVIDER}' "
            "does not yet have an adapter"
        ),
    }


def analyze_with_ai_retries(
    pdf_path
):
    for attempt in range(
        MAX_AI_RETRIES
    ):
        result = analyze_with_ai(
            pdf_path
        )

        if (
            result["status"]
            == "OK"
        ):
            return result

        if (
            result["status"]
            .startswith("RETRY_")
        ):
            wait_seconds = (
                BASE_WAIT_SECONDS
                * (attempt + 1)
            )

            log(
                f"      AI retry "
                f"{attempt + 1}/"
                f"{MAX_AI_RETRIES}: "
                f"{result['status']} -> "
                f"waiting {wait_seconds}s"
            )

            time.sleep(
                wait_seconds
            )

            continue

        return result

    return {
        "total": None,
        "document_type": None,
        "method": (
            AI_PROVIDER.upper()
        ),
        "confidence": "LOW",
        "status":
            "MAX_RETRIES_EXCEEDED",
        "notes": (
            "AI failed after all retries"
        ),
    }


# =============================================================================
# SAMPLE VALIDATION
# =============================================================================

def load_expected_procedures():
    if not SAMPLE_FILE.exists():
        raise FileNotFoundError(
            "Script 00 output not found: "
            f"{SAMPLE_FILE}"
        )

    sample = pd.read_excel(
        SAMPLE_FILE
    )

    if (
        "procedure_code"
        not in sample.columns
    ):
        raise KeyError(
            "Script 00 output is missing "
            "required column: "
            "procedure_code"
        )

    codes = []

    for value in (
        sample["procedure_code"]
        .dropna()
        .tolist()
    ):
        code = safe_integer(
            value
        )

        if code is not None:
            codes.append(code)

    if (
        len(codes)
        != len(set(codes))
    ):
        raise ValueError(
            "Script 00 output contains "
            "duplicate procedure codes."
        )

    return codes


# =============================================================================
# PDF DIRECTORY AUDIT
# =============================================================================

def audit_pdf_directory(
    expected_codes
):
    pdf_files = sorted(
        PDF_DIR.glob("*.pdf")
    )

    code_to_files = {}

    for pdf_path in pdf_files:
        code = extract_procedure_code(
            pdf_path
        )

        if code is None:
            continue

        code_to_files.setdefault(
            code,
            []
        ).append(pdf_path)

    expected_set = set(
        expected_codes
    )

    available_set = set(
        code_to_files
    )

    missing_codes = sorted(
        expected_set
        - available_set
    )

    unexpected_codes = sorted(
        available_set
        - expected_set
    )

    duplicate_codes = sorted(
        code
        for code, files
        in code_to_files.items()
        if len(files) > 1
    )

    return (
        pdf_files,
        code_to_files,
        missing_codes,
        unexpected_codes,
        duplicate_codes,
    )


# =============================================================================
# RESUMABLE PROCESSING
# =============================================================================

def load_previous_results():
    previous_results = {}

    if not OUTPUT_FILE.exists():
        return previous_results

    try:
        dataframe = pd.read_excel(
            OUTPUT_FILE
        )

        required_columns = {
            "procedure_code",
            "file_name",
            "count_status",
        }

        if not (
            required_columns
            .issubset(
                dataframe.columns
            )
        ):
            return previous_results

        for _, row in (
            dataframe.iterrows()
        ):
            if (
                row.get(
                    "count_status"
                )
                != "OK"
            ):
                continue

            file_name = str(
                row.get(
                    "file_name",
                    ""
                )
            ).strip()

            if file_name:
                previous_results[
                    file_name
                ] = row.to_dict()

    except Exception as error:
        log(
            "  Warning: previous "
            "Script 02 output could "
            "not be loaded: "
            f"{error}"
        )

    return previous_results


def save_partial_results(
    results
):
    dataframe = pd.DataFrame(
        results
    )

    dataframe.to_excel(
        OUTPUT_FILE,
        index=False
    )


# =============================================================================
# PROCESS ONE DOCUMENT
# =============================================================================

def process_document(
    pdf_path
):
    local_result = analyze_locally(
        pdf_path
    )

    log(
        "      Local: "
        f"total="
        f"{local_result['total']} | "
        f"type="
        f"{local_result['document_type']} | "
        f"confidence="
        f"{local_result['confidence']} | "
        f"status="
        f"{local_result['status']}"
    )

    if (
        local_result["status"]
        == "OK"
        and
        local_result["confidence"]
        == "HIGH"
    ):
        return local_result

    if AI_PROVIDER in (
        "",
        "none",
        "off",
        "disabled",
    ):
        return {
            **local_result,
            "status":
                "REVIEW_REQUIRED",
        }

    log(
        "      AI fallback: "
        f"{AI_PROVIDER}"
    )

    ai_result = (
        analyze_with_ai_retries(
            pdf_path
        )
    )

    log(
        "      AI: "
        f"total={ai_result['total']} | "
        f"type="
        f"{ai_result['document_type']} | "
        f"status="
        f"{ai_result['status']}"
    )

    if (
        ai_result["status"]
        == "OK"
    ):
        ai_result["pages"] = (
            local_result.get(
                "pages"
            )
        )

        return ai_result

    return {
        "total": None,
        "document_type": (
            local_result.get(
                "document_type"
            )
            or
            ai_result.get(
                "document_type"
            )
        ),
        "method": (
            f"PYMUPDF+"
            f"{AI_PROVIDER.upper()}"
        ),
        "confidence": "LOW",
        "status":
            "REVIEW_REQUIRED",
        "notes": (
            "Local analysis unresolved; "
            f"AI status: "
            f"{ai_result['status']}. "
            f"{ai_result['notes']}"
        )[:200],
        "pages": (
            local_result.get(
                "pages"
            )
        ),
    }


# =============================================================================
# PROCESSING SUMMARY
# =============================================================================

def save_processing_summary(
    dataframe
):
    method_summary = (
        dataframe[
            "processing_method"
        ]
        .value_counts(
            dropna=False
        )
        .rename_axis(
            "processing_method"
        )
        .reset_index(
            name="count"
        )
    )

    method_summary[
        "percentage"
    ] = (
        method_summary["count"]
        / len(dataframe)
        * 100
    ).round(2)

    status_summary = (
        dataframe[
            "count_status"
        ]
        .value_counts(
            dropna=False
        )
        .rename_axis(
            "count_status"
        )
        .reset_index(
            name="count"
        )
    )

    type_summary = (
        dataframe[
            "document_type"
        ]
        .value_counts(
            dropna=False
        )
        .rename_axis(
            "document_type"
        )
        .reset_index(
            name="count"
        )
    )

    successful = dataframe[
        dataframe[
            "count_status"
        ] == "OK"
    ].copy()

    descriptive_statistics = (
        successful[
            "queries_observations_count"
        ]
        .describe(
            percentiles=[
                0.25,
                0.50,
                0.75,
                0.90,
                0.95,
            ]
        )
        .rename(
            "value"
        )
        .reset_index()
        .rename(
            columns={
                "index":
                    "statistic"
            }
        )
    )

    with pd.ExcelWriter(
        SUMMARY_FILE,
        engine="openpyxl"
    ) as writer:
        method_summary.to_excel(
            writer,
            sheet_name="methods",
            index=False
        )

        status_summary.to_excel(
            writer,
            sheet_name="status",
            index=False
        )

        type_summary.to_excel(
            writer,
            sheet_name="document_types",
            index=False
        )

        descriptive_statistics.to_excel(
            writer,
            sheet_name="descriptive_stats",
            index=False
        )


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def main():
    log("=" * 78)
    log(
        "QUERY AND OBSERVATION COUNT "
        "- ROAD INFRASTRUCTURE TENDERS"
    )
    log("=" * 78)
    log(
        "Source documents: "
        "Script 01 SEACE acquisition output"
    )
    log(
        "Input directory: 05_pdfs"
    )
    log()

    # -------------------------------------------------------------------------
    # 1. Validate analytical sample
    # -------------------------------------------------------------------------

    log(
        "[1] Validating "
        "analytical sample..."
    )

    expected_codes = (
        load_expected_procedures()
    )

    log(
        "  Expected procedures "
        "from Script 00: "
        f"{len(expected_codes)}"
    )

    # -------------------------------------------------------------------------
    # 2. Audit PDF input
    # -------------------------------------------------------------------------

    log()
    log(
        "[2] Auditing "
        "Script 01 document output..."
    )

    (
        pdf_files,
        code_to_files,
        missing_codes,
        unexpected_codes,
        duplicate_codes,
    ) = audit_pdf_directory(
        expected_codes
    )

    represented_codes = (
        set(expected_codes)
        & set(code_to_files)
    )

    log(
        f"  PDF files found: "
        f"{len(pdf_files)}"
    )

    log(
        "  Expected procedures "
        "represented: "
        f"{len(represented_codes)}"
    )

    log(
        f"  Missing procedures: "
        f"{len(missing_codes)}"
    )

    log(
        f"  Unexpected procedures: "
        f"{len(unexpected_codes)}"
    )

    log(
        "  Duplicate procedure "
        "documents: "
        f"{len(duplicate_codes)}"
    )

    if missing_codes:
        log(
            "  Missing procedure codes: "
            + ", ".join(
                map(
                    str,
                    missing_codes
                )
            )
        )

    if unexpected_codes:
        log(
            "  Unexpected procedure codes: "
            + ", ".join(
                map(
                    str,
                    unexpected_codes
                )
            )
        )

    if duplicate_codes:
        log(
            "  Duplicate procedure codes: "
            + ", ".join(
                map(
                    str,
                    duplicate_codes
                )
            )
        )

    if (
        missing_codes
        or unexpected_codes
        or duplicate_codes
    ):
        raise RuntimeError(
            "05_pdfs does not match "
            "the Script 00 analytical "
            "sample. Resolve the document "
            "audit before counting."
        )

    # -------------------------------------------------------------------------
    # 3. Configure processing
    # -------------------------------------------------------------------------

    log()
    log(
        "[3] Configuring "
        "processing methods..."
    )

    log(
        "  Primary method: PyMuPDF"
    )

    if AI_PROVIDER in (
        "",
        "none",
        "off",
        "disabled",
    ):
        log(
            "  AI fallback: disabled"
        )

    else:
        log(
            "  AI fallback provider: "
            f"{AI_PROVIDER}"
        )

        log(
            "  AI model: "
            f"{AI_MODEL or 'NOT SET'}"
        )

        if not AI_API_KEY:
            log(
                "  Warning: AI_API_KEY "
                "is not configured."
            )

    previous_results = (
        load_previous_results()
    )

    log(
        "  Previous verified results: "
        f"{len(previous_results)}"
    )

    # -------------------------------------------------------------------------
    # 4. Process documents
    # -------------------------------------------------------------------------

    log()
    log(
        "[4] Processing "
        "PDF documents..."
    )

    results = []

    ordered_pdfs = [
        code_to_files[code][0]
        for code in expected_codes
    ]

    for index, pdf_path in enumerate(
        ordered_pdfs,
        start=1
    ):
        procedure_code = (
            extract_procedure_code(
                pdf_path
            )
        )

        file_name = (
            pdf_path.name
        )

        log()
        log(
            f"[{index}/"
            f"{len(ordered_pdfs)}] "
            f"Procedure "
            f"{procedure_code} | "
            f"{file_name}"
        )

        if (
            file_name
            in previous_results
        ):
            log(
                "      Existing verified "
                "count: reused"
            )

            results.append(
                previous_results[
                    file_name
                ]
            )

            continue

        result = process_document(
            pdf_path
        )

        # ---------------------------------------------------------------------
        # Filename/content consistency safeguard
        # ---------------------------------------------------------------------

        if (
            "_ACTA"
            in pdf_path.stem.upper()
        ):
            if not (
                result["status"]
                == "OK"
                and
                result[
                    "document_type"
                ]
                == "ACTA_NO_FORMULACION"
                and
                result["total"]
                == 0
            ):
                result = {
                    **result,
                    "total": None,
                    "confidence": "LOW",
                    "status":
                        "REVIEW_REQUIRED",
                    "notes": (
                        "Filename identifies "
                        "a no-formulation act, "
                        "but document content "
                        "did not verify it."
                    ),
                }

        results.append(
            {
                "procedure_code":
                    procedure_code,

                "file_name":
                    file_name,

                "document_type":
                    result.get(
                        "document_type"
                    )
                    or "",

                "queries_observations_count":
                    result.get(
                        "total"
                    ),

                "processing_method":
                    result.get(
                        "method"
                    )
                    or "",

                "confidence":
                    result.get(
                        "confidence"
                    )
                    or "",

                "count_status":
                    result.get(
                        "status"
                    )
                    or "",

                "pages":
                    result.get(
                        "pages"
                    ),

                "notes":
                    result.get(
                        "notes"
                    )
                    or "",
            }
        )

        if index % 10 == 0:
            save_partial_results(
                results
            )

            log(
                "      Partial results "
                "saved."
            )

        time.sleep(
            PAUSE_BETWEEN_PDFS
        )

    # -------------------------------------------------------------------------
    # 5. Save outputs
    # -------------------------------------------------------------------------

    log()
    log(
        "[5] Saving "
        "Script 02 outputs..."
    )

    dataframe = pd.DataFrame(
        results
    )

    dataframe.to_excel(
        OUTPUT_FILE,
        index=False
    )

    save_processing_summary(
        dataframe
    )

    log(
        f"  Counts workbook: "
        f"{OUTPUT_FILE.name}"
    )

    log(
        f"  Summary workbook: "
        f"{SUMMARY_FILE.name}"
    )

    # -------------------------------------------------------------------------
    # 6. Final audit
    # -------------------------------------------------------------------------

    successful = dataframe[
        dataframe[
            "count_status"
        ] == "OK"
    ].copy()

    review = dataframe[
        dataframe[
            "count_status"
        ] != "OK"
    ].copy()

    pliegos = successful[
        successful[
            "document_type"
        ] == "PLIEGO"
    ]

    no_formulation_acts = (
        successful[
            successful[
                "document_type"
            ]
            == "ACTA_NO_FORMULACION"
        ]
    )

    verified_zero = (
        successful[
            (
                successful[
                    "queries_observations_count"
                ] == 0
            )
            &
            (
                successful[
                    "document_type"
                ]
                == "ACTA_NO_FORMULACION"
            )
        ]
    )

    log()
    log("=" * 78)
    log(
        "QUERY / OBSERVATION "
        "COUNT AUDIT"
    )
    log("=" * 78)

    log(
        "Expected procedures:              "
        f"{len(expected_codes)}"
    )

    log(
        "PDF documents processed:          "
        f"{len(dataframe)}"
    )

    log(
        "Pliegos successfully processed:   "
        f"{len(pliegos)}"
    )

    log(
        "No-formulation acts:              "
        f"{len(no_formulation_acts)}"
    )

    log(
        "Successfully counted:             "
        f"{len(successful)}"
    )

    log(
        "Verified zero counts:             "
        f"{len(verified_zero)}"
    )

    log(
        "Manual review required:           "
        f"{len(review)}"
    )

    if len(review) > 0:
        log()
        log(
            "PROCEDURES REQUIRING REVIEW"
        )
        log("-" * 78)

        for _, row in (
            review.iterrows()
        ):
            log(
                f"  "
                f"{int(row['procedure_code'])}"
                f" | "
                f"{row['file_name']}"
                f" | "
                f"{row['count_status']}"
                f" | "
                f"{row['notes']}"
            )

    log()
    log("=" * 78)

    pipeline_complete = (
        len(dataframe)
        == len(expected_codes)
        and
        len(successful)
        == len(expected_codes)
        and
        len(review)
        == 0
    )

    if pipeline_complete:
        log(
            "PIPELINE STATUS: COMPLETE"
        )

    else:
        log(
            "PIPELINE STATUS: INCOMPLETE"
        )

    log("=" * 78)

    save_log()


# =============================================================================
# EXECUTION
# =============================================================================

if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        log()
        log("=" * 78)
        log(
            "PIPELINE FAILED"
        )
        log("=" * 78)

        log(
            f"{type(error).__name__}: "
            f"{error}"
        )

        save_log()

        raise
