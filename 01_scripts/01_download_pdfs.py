import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright


# =============================================================================
# PROJECT PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RESULTS_DIR = PROJECT_ROOT / "02_results"
LOGS_DIR = PROJECT_ROOT / "03_logs"
PDFS_DIR = PROJECT_ROOT / "05_pdfs"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
PDFS_DIR.mkdir(parents=True, exist_ok=True)

INPUT_FILE = RESULTS_DIR / "00_1_sample_selection.xlsx"
STATUS_FILE = RESULTS_DIR / "01_1_download_status.xlsx"
LOG_FILE = LOGS_DIR / "01_download_pdfs.log"


# =============================================================================
# SEACE CONFIGURATION
# =============================================================================

SEACE_URL = (
    "https://prod2.seace.gob.pe/seacebus-uiwd-pub/"
    "buscadorPublico/buscadorPublico.xhtml"
)

PAUSE_BETWEEN_PROCEDURES = 3
DOWNLOAD_TIMEOUT_MS = 30000
PAGE_TIMEOUT_MS = 60000

# Script 00 standardized analytical schema
EXPECTED_INPUT_COLUMNS = {
    "procedure_code",
    "notice_date",
}


# =============================================================================
# LOGGING
# =============================================================================

log_lines = []


def log(message=""):
    line = str(message)
    print(line)
    log_lines.append(line)


def save_log():
    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )


# =============================================================================
# TEXT UTILITIES
# =============================================================================

def normalize_text(text):
    text = str(text).lower()
    text = unicodedata.normalize("NFKD", text)

    return "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )


# =============================================================================
# INPUT VALIDATION
# =============================================================================

def validate_input_file():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Required Script 00 output not found: {INPUT_FILE.name}"
        )

    dataframe = pd.read_excel(INPUT_FILE)

    missing_columns = EXPECTED_INPUT_COLUMNS - set(dataframe.columns)

    if missing_columns:
        raise KeyError(
            "Input dataset is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    if dataframe["procedure_code"].isna().any():
        raise ValueError(
            "Input dataset contains missing procurement procedure codes."
        )

    duplicated_codes = (
        dataframe["procedure_code"]
        .duplicated()
        .sum()
    )

    if duplicated_codes > 0:
        raise ValueError(
            "Input dataset contains duplicated procurement procedure codes: "
            f"{duplicated_codes}"
        )

    dataframe["notice_date"] = pd.to_datetime(
        dataframe["notice_date"],
        errors="coerce",
    )

    missing_dates = dataframe["notice_date"].isna().sum()

    if missing_dates > 0:
        raise ValueError(
            "Input dataset contains invalid or missing procurement notice "
            f"dates: {missing_dates}"
        )

    dataframe["search_year"] = (
        dataframe["notice_date"]
        .dt.year
        .astype(int)
    )

    return dataframe


# =============================================================================
# PDF VALIDATION
# =============================================================================

def validate_pdf_content(pdf_path, expected_document_type):
    try:
        import fitz

        document = fitz.open(str(pdf_path))

        if len(document) == 0:
            document.close()
            return False, "EMPTY_PDF"

        text = ""

        for page_index in range(min(2, len(document))):
            text += document[page_index].get_text("text")

        document.close()

        normalized = normalize_text(text)

        if expected_document_type == "PLIEGO":
            valid_patterns = (
                "pliego de absolucion",
                "pliego absolutorio",
                "absolucion de consultas",
            )

            if any(pattern in normalized for pattern in valid_patterns):
                return True, "CONTENT_VERIFIED"

            return False, "PLIEGO_CONTENT_NOT_VERIFIED"

        if expected_document_type == "ACTA_NO_FORMULACION":
            # SEACE actas are not fully standardized in their wording.
            # Validate the document by combining evidence of:
            #   (a) an acta/no-formulation statement, or
            #   (b) an explicit statement that no queries/observations
            #       were registered/formulated.
            #
            # Example observed in SEACE:
            # "No se registraron Formulacion de consultas y observaciones
            #  en el procedimiento"
            acta_patterns = (
                "acta de no formulacion",
                "no se formularon consultas",
                "no se registraron consultas",
                "no formulacion de consultas",
                "no se registraron formulacion de consultas",
                "no se registraron formulaciones de consultas",
                "no se registraron consultas y observaciones",
                "no se formularon consultas y observaciones",
            )

            if any(pattern in normalized for pattern in acta_patterns):
                return True, "CONTENT_VERIFIED"

            # Robust semantic fallback for minor wording/layout variations.
            has_query_context = (
                "consulta" in normalized
                or "consultas" in normalized
            )
            has_observation_context = (
                "observacion" in normalized
                or "observaciones" in normalized
            )
            has_no_formulation = (
                "no formulacion" in normalized
                or "no se formularon" in normalized
                or "no se registro" in normalized
                or "no se registraron" in normalized
            )

            if (
                has_no_formulation
                and (has_query_context or has_observation_context)
            ):
                return True, "CONTENT_VERIFIED"

            return False, "ACTA_CONTENT_NOT_VERIFIED"

        return False, "UNKNOWN_DOCUMENT_TYPE"

    except Exception as error:
        return False, (
            "PDF_VALIDATION_ERROR: "
            f"{type(error).__name__}: {str(error)[:100]}"
        )


# =============================================================================
# SEACE NAVIGATION HELPERS
# =============================================================================

def wait_for_text(page, text, max_attempts=15, wait_seconds=1):
    for _ in range(max_attempts):
        try:
            element = page.get_by_text(
                text,
                exact=False,
            )

            if element.count() > 0:
                return element

        except Exception:
            pass

        time.sleep(wait_seconds)

    return None


def close_extra_pages(context, main_page):
    for current_page in list(context.pages):
        if current_page != main_page:
            try:
                current_page.close()
            except Exception:
                pass


# =============================================================================
# DOCUMENT SEARCH
# =============================================================================

def search_document_in_year(page, code, year):
    try:
        log(f"    Searching year {year}...")

        page.goto(
            SEACE_URL,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT_MS,
        )

        page.wait_for_timeout(4000)

        page.get_by_text(
            "Buscador de Procedimientos de Selección",
            exact=True,
        ).click()

        page.wait_for_timeout(2500)

        page.evaluate(
            """
            () => {
                const legends = document.querySelectorAll('legend');

                for (const legend of legends) {
                    if (
                        legend.textContent.includes(
                            'Búsqueda Avanzada'
                        )
                    ) {
                        legend.click();
                        return true;
                    }
                }

                return false;
            }
            """
        )

        page.wait_for_timeout(2500)

        # ---------------------------------------------------------------------
        # SELECT YEAR
        # ---------------------------------------------------------------------

        try:
            year_label = page.get_by_text(
                "Año de la Convocatoria",
                exact=False,
            ).first

            year_row = year_label.locator(
                "xpath=ancestor::tr[1]"
            )

            year_trigger = year_row.locator(
                ".ui-selectonemenu-trigger"
            )

            year_trigger.click()

            page.wait_for_timeout(700)

            options = page.locator(
                "li.ui-selectonemenu-item:visible"
            )

            year_option = options.filter(
                has_text=str(year)
            )

            if year_option.count() == 0:
                return {
                    "status": "YEAR_NOT_AVAILABLE",
                    "path": None,
                    "document_type": None,
                    "validation": None,
                    "source_filename": None,
                }

            year_option.first.click()

            page.wait_for_timeout(1200)

        except Exception:
            return {
                "status": "YEAR_SELECTION_ERROR",
                "path": None,
                "document_type": None,
                "validation": None,
                "source_filename": None,
            }

        # ---------------------------------------------------------------------
        # ENTER PROCEDURE CODE
        # ---------------------------------------------------------------------

        try:
            code_field = page.locator(
                "#tbBuscador\\:idFormBuscarProceso\\:"
                "numeroConvocatoria"
            )

            code_field.fill(str(code))

            page.wait_for_timeout(500)

        except Exception:
            return {
                "status": "CODE_FIELD_ERROR",
                "path": None,
                "document_type": None,
                "validation": None,
                "source_filename": None,
            }

        # ---------------------------------------------------------------------
        # SEARCH
        # ---------------------------------------------------------------------

        search_buttons = page.get_by_text(
            "Buscar",
            exact=True,
        )

        search_button = None

        for index in range(search_buttons.count()):
            if search_buttons.nth(index).is_visible():
                search_button = search_buttons.nth(index)
                break

        if search_button is None:
            return {
                "status": "SEARCH_BUTTON_NOT_FOUND",
                "path": None,
                "document_type": None,
                "validation": None,
                "source_filename": None,
            }

        search_button.click()

        page.wait_for_timeout(8000)

        page_text = page.locator("body").inner_text()

        if (
            "No se encontraron Datos" in page_text
            or "Mostrando de 0 a 0" in page_text
        ):
            return {
                "status": "PROCEDURE_NOT_FOUND",
                "path": None,
                "document_type": None,
                "validation": None,
                "source_filename": None,
            }

        # ---------------------------------------------------------------------
        # FIND RESULT ROW
        # ---------------------------------------------------------------------

        rows = page.locator("tr")

        result_row = None

        procedure_prefixes = (
            "LP-",
            "CP-",
            "AS-",
            "AM-",
            "AD-",
            "CD-",
        )

        for index in range(rows.count()):
            try:
                row_text = rows.nth(index).inner_text().strip()

                if (
                    any(
                        prefix in row_text
                        for prefix in procedure_prefixes
                    )
                    and len(row_text) > 50
                ):
                    result_row = rows.nth(index)
                    break

            except Exception:
                pass

        if result_row is None:
            return {
                "status": "RESULT_ROW_NOT_FOUND",
                "path": None,
                "document_type": None,
                "validation": None,
                "source_filename": None,
            }

        # ---------------------------------------------------------------------
        # OPEN PROCEDURE DETAILS
        # ---------------------------------------------------------------------

        candidates = result_row.locator(
            "img, input[type='image']"
        )

        procedure_control = None

        for index in range(candidates.count()):
            try:
                source = (
                    candidates.nth(index)
                    .get_attribute("src")
                    or ""
                ).lower()

                if "ficha" in source:
                    procedure_control = candidates.nth(index)
                    break

            except Exception:
                pass

        if procedure_control is None:
            return {
                "status": "PROCEDURE_ICON_NOT_FOUND",
                "path": None,
                "document_type": None,
                "validation": None,
                "source_filename": None,
            }

        pages_before = len(page.context.pages)

        procedure_control.click()

        page.wait_for_timeout(7000)

        pages_after = len(page.context.pages)

        detail_page = page

        if pages_after > pages_before:
            detail_page = page.context.pages[-1]

        # ---------------------------------------------------------------------
        # OPEN DOCUMENT SECTION
        # ---------------------------------------------------------------------

        documents_button = wait_for_text(
            detail_page,
            "Ver documentos por Etapa",
            max_attempts=15,
            wait_seconds=1,
        )

        if documents_button is None:
            if detail_page != page:
                try:
                    detail_page.close()
                except Exception:
                    pass

            return {
                "status": "DOCUMENT_SECTION_NOT_FOUND",
                "path": None,
                "document_type": None,
                "validation": None,
                "source_filename": None,
            }

        try:
            documents_button.first.click()
            detail_page.wait_for_timeout(4000)

        except Exception:
            if detail_page != page:
                try:
                    detail_page.close()
                except Exception:
                    pass

            return {
                "status": "DOCUMENT_SECTION_OPEN_ERROR",
                "path": None,
                "document_type": None,
                "validation": None,
                "source_filename": None,
            }

        # ---------------------------------------------------------------------
        # IDENTIFY TARGET DOCUMENT
        # ---------------------------------------------------------------------

        document_rows = detail_page.locator("tr")

        target_row = None
        document_type = None

        for index in range(document_rows.count()):
            try:
                row = document_rows.nth(index)
                cells = row.locator("td")

                if cells.count() < 4:
                    continue

                stage = normalize_text(
                    cells.nth(1).inner_text().strip()
                )

                document_name = normalize_text(
                    cells.nth(2).inner_text().strip()
                )

                if (
                    "absolucion de consultas" in stage
                    and "pliego de absolucion" in document_name
                ):
                    target_row = row
                    document_type = "PLIEGO"
                    break

                if (
                    "absolucion de consultas" in stage
                    and "acta de no formulacion" in document_name
                ):
                    target_row = row
                    document_type = "ACTA_NO_FORMULACION"
                    break

            except Exception:
                pass

        if target_row is None:
            if detail_page != page:
                try:
                    detail_page.close()
                except Exception:
                    pass

            return {
                "status": "TARGET_DOCUMENT_NOT_FOUND",
                "path": None,
                "document_type": None,
                "validation": None,
                "source_filename": None,
            }

        # ---------------------------------------------------------------------
        # IDENTIFY DOWNLOAD LINK
        # ---------------------------------------------------------------------

        links = target_row.locator("a")

        download_link = None

        for index in range(links.count()):
            try:
                element = links.nth(index)

                onclick = (
                    element.get_attribute("onclick")
                    or ""
                )

                if "descargaDocGeneral" in onclick:
                    download_link = element
                    break

            except Exception:
                pass

        if download_link is None:
            if detail_page != page:
                try:
                    detail_page.close()
                except Exception:
                    pass

            return {
                "status": "DOWNLOAD_LINK_NOT_FOUND",
                "path": None,
                "document_type": document_type,
                "validation": None,
                "source_filename": None,
            }

        # ---------------------------------------------------------------------
        # DOWNLOAD
        # ---------------------------------------------------------------------

        suffix = (
            ""
            if document_type == "PLIEGO"
            else "_ACTA"
        )

        output_filename = f"{code}{suffix}.pdf"
        output_path = PDFS_DIR / output_filename

        link_id = download_link.get_attribute("id")

        try:
            with detail_page.expect_download(
                timeout=DOWNLOAD_TIMEOUT_MS
            ) as download_info:

                detail_page.evaluate(
                    """
                    (id) => {
                        const element =
                            document.getElementById(id);

                        if (element) {
                            element.click();
                        }
                    }
                    """,
                    link_id,
                )

            download = download_info.value

            source_filename = (
                download.suggested_filename or ""
            )

            source_lower = source_filename.lower()

            if (
                source_lower.endswith(".zip")
                or source_lower.endswith(".rar")
            ):
                if detail_page != page:
                    try:
                        detail_page.close()
                    except Exception:
                        pass

                return {
                    "status": "UNSUPPORTED_DOWNLOAD_FORMAT",
                    "path": None,
                    "document_type": document_type,
                    "validation": "ZIP_OR_RAR",
                    "source_filename": source_filename,
                }

            download.save_as(str(output_path))

        except Exception as error:
            if detail_page != page:
                try:
                    detail_page.close()
                except Exception:
                    pass

            return {
                "status": "DOWNLOAD_ERROR",
                "path": None,
                "document_type": document_type,
                "validation": (
                    f"{type(error).__name__}: "
                    f"{str(error)[:100]}"
                ),
                "source_filename": None,
            }

        # ---------------------------------------------------------------------
        # VALIDATE DOWNLOADED PDF
        # ---------------------------------------------------------------------

        is_valid, validation_status = validate_pdf_content(
            output_path,
            document_type,
        )

        if not is_valid:
            if output_path.exists():
                output_path.unlink()

            if detail_page != page:
                try:
                    detail_page.close()
                except Exception:
                    pass

            return {
                "status": "PDF_VALIDATION_FAILED",
                "path": None,
                "document_type": document_type,
                "validation": validation_status,
                "source_filename": source_filename,
            }

        if detail_page != page:
            try:
                detail_page.close()
            except Exception:
                pass

        return {
            "status": "OK",
            "path": output_path,
            "document_type": document_type,
            "validation": validation_status,
            "source_filename": source_filename,
        }

    except Exception as error:
        return {
            "status": "GENERAL_ERROR",
            "path": None,
            "document_type": None,
            "validation": (
                f"{type(error).__name__}: "
                f"{str(error)[:150]}"
            ),
            "source_filename": None,
        }


# =============================================================================
# SEARCH STRATEGY
# =============================================================================

def download_with_year_search(page, code, base_year):
    candidate_years = [
        base_year,
        base_year + 1,
        base_year - 1,
        base_year + 2,
        base_year - 2,
    ]

    attempts = []

    for year in candidate_years:
        result = search_document_in_year(
            page,
            code,
            year,
        )

        attempts.append(
            f"{year}:{result['status']}"
        )

        log(
            f"      {year}: "
            f"{result['status']}"
        )

        if result["status"] == "OK":
            result["year_found"] = year
            result["attempts"] = " | ".join(attempts)
            return result

        if result["status"] in {
            "YEAR_NOT_AVAILABLE",
            "PROCEDURE_NOT_FOUND",
            "RESULT_ROW_NOT_FOUND",
        }:
            continue

        if result["status"] in {
            "DOCUMENT_SECTION_NOT_FOUND",
            "DOCUMENT_SECTION_OPEN_ERROR",
        }:
            log("      Retrying the same year once...")

            time.sleep(5)

            retry_result = search_document_in_year(
                page,
                code,
                year,
            )

            attempts.append(
                f"{year}:RETRY:{retry_result['status']}"
            )

            log(
                f"      {year} retry: "
                f"{retry_result['status']}"
            )

            if retry_result["status"] == "OK":
                retry_result["year_found"] = year
                retry_result["attempts"] = (
                    " | ".join(attempts)
                )
                return retry_result

        # If the procedure was found but the target document
        # could not be retrieved, preserve the evidence and stop
        # searching unrelated years.
        if result["status"] in {
            "TARGET_DOCUMENT_NOT_FOUND",
            "DOWNLOAD_LINK_NOT_FOUND",
            "UNSUPPORTED_DOWNLOAD_FORMAT",
            "DOWNLOAD_ERROR",
            "PDF_VALIDATION_FAILED",
            "PROCEDURE_ICON_NOT_FOUND",
            "CODE_FIELD_ERROR",
            "SEARCH_BUTTON_NOT_FOUND",
            "YEAR_SELECTION_ERROR",
            "GENERAL_ERROR",
        }:
            result["year_found"] = year
            result["attempts"] = " | ".join(attempts)
            return result

    return {
        "status": "PROCEDURE_NOT_FOUND_IN_SEARCH_YEARS",
        "path": None,
        "document_type": None,
        "validation": None,
        "source_filename": None,
        "year_found": None,
        "attempts": " | ".join(attempts),
    }


# =============================================================================
# OUTPUT
# =============================================================================

def save_status(results):
    dataframe = pd.DataFrame(results)

    dataframe.to_excel(
        STATUS_FILE,
        index=False,
    )


def print_final_summary(results, expected_count):
    dataframe = pd.DataFrame(results)

    successful = dataframe[
        dataframe["download_status"] == "OK"
    ]

    failed = dataframe[
        dataframe["download_status"] != "OK"
    ]

    pliegos = successful[
        successful["document_type"] == "PLIEGO"
    ]

    acts = successful[
        successful["document_type"]
        == "ACTA_NO_FORMULACION"
    ]

    log()
    log("=" * 78)
    log("FINAL DOWNLOAD AUDIT")
    log("=" * 78)

    log(
        f"Expected procedures:              "
        f"{expected_count:,}"
    )

    log(
        f"Successfully retrieved:           "
        f"{len(successful):,}"
    )

    log(
        f"Pliegos:                          "
        f"{len(pliegos):,}"
    )

    log(
        f"Acts of no formulation:           "
        f"{len(acts):,}"
    )

    log(
        f"Missing or failed:                "
        f"{len(failed):,}"
    )

    log(
        f"PDF files in 05_pdfs:             "
        f"{len(list(PDFS_DIR.glob('*.pdf'))):,}"
    )

    if len(failed) > 0:
        log()
        log("PROCEDURES REQUIRING REVIEW")
        log("-" * 78)

        for _, row in failed.iterrows():
            log(
                f"  {row['procedure_code']} | "
                f"{row['download_status']} | "
                f"{row['search_attempts']}"
            )

    log()
    log("=" * 78)

    if (
        len(successful) == expected_count
        and len(list(PDFS_DIR.glob("*.pdf")))
        == expected_count
    ):
        log("PIPELINE STATUS: COMPLETE")
    else:
        log("PIPELINE STATUS: INCOMPLETE")

    log("=" * 78)


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def main():
    log("=" * 78)
    log("SEACE DOCUMENT ACQUISITION - ROAD INFRASTRUCTURE TENDERS")
    log("=" * 78)
    log("Source: OECE-SEACE")
    log("Input: Script 00 sample-selection output")
    log()

    log("[1] Validating Script 00 output...")

    sample = validate_input_file()

    expected_count = len(sample)

    log(
        f"  Procedures to process: "
        f"{expected_count:,}"
    )

    log()
    log("[2] Preparing document directory...")

    existing_pdfs = list(PDFS_DIR.glob("*.pdf"))

    if existing_pdfs:
        log(
            f"  Existing PDFs detected: "
            f"{len(existing_pdfs):,}"
        )
        log(
            "  Existing valid filenames will be "
            "checked before downloading."
        )
    else:
        log("  No existing PDFs detected.")

    results = []

    log()
    log("[3] Starting automated SEACE acquisition...")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False
        )

        context = browser.new_context(
            viewport={
                "width": 1600,
                "height": 950,
            },
            accept_downloads=True,
        )

        page = context.new_page()

        for position, (_, row) in enumerate(
            sample.iterrows(),
            start=1,
        ):
            code = str(
                int(row["procedure_code"])
            )

            base_year = int(
                row["search_year"]
            )

            log()
            log(
                f"[{position}/{expected_count}] "
                f"Procedure {code} "
                f"(base year {base_year})"
            )

            existing_pliego = (
                PDFS_DIR / f"{code}.pdf"
            )

            existing_acta = (
                PDFS_DIR / f"{code}_ACTA.pdf"
            )

            existing_path = None
            existing_type = None

            if existing_pliego.exists():
                existing_path = existing_pliego
                existing_type = "PLIEGO"

            elif existing_acta.exists():
                existing_path = existing_acta
                existing_type = "ACTA_NO_FORMULACION"

            if existing_path is not None:
                valid, validation = validate_pdf_content(
                    existing_path,
                    existing_type,
                )

                if valid:
                    log(
                        f"      Existing verified PDF: "
                        f"{existing_path.name}"
                    )

                    results.append({
                        "procedure_code": code,
                        "base_year": base_year,
                        "year_found": "",
                        "document_type": existing_type,
                        "output_filename": existing_path.name,
                        "source_filename": "",
                        "content_validation": validation,
                        "download_status": "OK",
                        "acquisition_mode": "EXISTING_VERIFIED",
                        "search_attempts": "",
                    })

                    save_status(results)
                    continue

                log(
                    "      Existing PDF failed validation; "
                    "downloading again."
                )

                existing_path.unlink()

            result = download_with_year_search(
                page,
                code,
                base_year,
            )

            output_filename = ""

            if result["path"] is not None:
                output_filename = result["path"].name

            results.append({
                "procedure_code": code,
                "base_year": base_year,
                "year_found": (
                    result["year_found"]
                    if result["year_found"] is not None
                    else ""
                ),
                "document_type": (
                    result["document_type"]
                    if result["document_type"] is not None
                    else ""
                ),
                "output_filename": output_filename,
                "source_filename": (
                    result["source_filename"]
                    if result["source_filename"] is not None
                    else ""
                ),
                "content_validation": (
                    result["validation"]
                    if result["validation"] is not None
                    else ""
                ),
                "download_status": result["status"],
                "acquisition_mode": "DOWNLOADED",
                "search_attempts": result["attempts"],
            })

            # Save after every procedure so progress is preserved
            # if SEACE or the local execution is interrupted.
            save_status(results)

            close_extra_pages(
                context,
                page,
            )

            if position < expected_count:
                time.sleep(
                    PAUSE_BETWEEN_PROCEDURES
                )

        browser.close()

    log()
    log("[4] Saving acquisition audit...")

    save_status(results)

    log(
        f"  Status workbook: "
        f"{STATUS_FILE.name}"
    )

    log(
        f"  Log file: "
        f"{LOG_FILE.name}"
    )

    print_final_summary(
        results,
        expected_count,
    )

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
        log("PIPELINE FAILED")
        log("=" * 78)

        log(
            f"{type(error).__name__}: "
            f"{error}"
        )

        save_log()

        sys.exit(1)
