"""Acquire published SEACE schedules and query-response PDFs for Script 00 selection.

Place in 01_scripts/01_sample_and_data/. Default: up to 50 pending cases.
Use --all for one sequential pass over all pending cases; rerun to resume.
Search source year, previous year, next year only after PROCEDURE_NOT_FOUND.
An explicit --year restricts the search to that year. Search attempts are saved
in the document state and exported acquisition status. No manual-review inputs.
Canonical PDFs: 05_pdfs/<code>.pdf or <code>_ACTA.pdf.
Dependencies: pandas, openpyxl, playwright, pymupdf.
Dates remain labeled as schedules or document publications, not verified event dates.
No query/observation count is assigned here.
"""
import sys
import os
import hashlib
import shutil
import argparse
import json
import re
from datetime import datetime, timezone
import time
import unicodedata
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright


# =============================================================================
# PROJECT PATHS
# =============================================================================

# Paths are configured by main(); importing this module creates no directories.
PROJECT_ROOT = RESULTS_DIR = LOGS_DIR = PDFS_DIR = None
INPUT_FILE = STATUS_FILE = LOG_FILE = None
PILOT_ROW = None
BATCH_ROOT = STATE_DIR = RUN_DIR = None
PDF_INDEX = {}
EXISTING_ISSUES = []
CURRENT_NOMENCLATURE = ""
SCHEMA_VERSION = "1.2-automatic-year-fallback"
SCHEDULE_RESULT = {}
DOCUMENT_RECORDS = []
DOCUMENT_AUDIT = {}


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



# =============================================================================
# PDF VALIDATION
# =============================================================================

def validate_pdf_content(pdf_path, expected_document_type):
    try:
        import pymupdf as fitz

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
        matching_rows = []
        for index in range(rows.count()):
            row = rows.nth(index)
            if row.locator("tr").count():
                continue
            controls = row.locator("img, input[type='image']")
            if any("ficha" in (controls.nth(j).get_attribute("src") or "").lower() for j in range(controls.count())):
                if row.is_visible():
                    matching_rows.append(row)
        if len(matching_rows) != 1:
            return {"status": "AMBIGUOUS_OR_MISSING_RESULT", "path": None,
                    "document_type": None, "validation": f"detail_rows={len(matching_rows)}",
                    "source_filename": None}
        result_row = matching_rows[0]
        global CURRENT_NOMENCLATURE
        search_cells = result_row.locator(":scope > td").all_inner_texts()
        search_text = result_row.inner_text()
        (RESULTS_DIR / "search_result.txt").write_text(search_text, encoding="utf-8")
        CURRENT_NOMENCLATURE = search_cells[3].strip() if len(search_cells) > 3 else ""
        expected_description = compact(PILOT_ROW.get("procedure_description", ""))
        actual_description = compact(search_cells[6]) if len(search_cells) > 6 else ""
        expected_entity = compact(PILOT_ROW.get("entity_name", ""))
        actual_entity = compact(search_cells[1]) if len(search_cells) > 1 else ""
        identity_ok = (expected_description and actual_description == expected_description
                       and expected_entity and actual_entity == expected_entity
                       and CURRENT_NOMENCLATURE)
        if not identity_ok:
            return {"status": "SEARCH_IDENTITY_NOT_VERIFIED", "path": None,
                    "document_type": None, "validation": "Source description/entity mismatch or missing nomenclature",
                    "source_filename": None}

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

        capture_schedule(detail_page, code, year)

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
            # SEACE can open the fieldset expanded. Clicking an expanded
            # legend collapses it, leaving hidden DOM rows readable but
            # preventing genuine paginator interaction.
            document_box = detail_page.locator('[id="tbFicha:dtDocumentos"]')
            if not document_box.is_visible():
                legend = detail_page.locator("legend").filter(has_text="Ver documentos por Etapa")
                if legend.count() != 1:
                    raise RuntimeError("Document fieldset legend is missing or ambiguous")
                legend.click()
            document_box.wait_for(state="visible", timeout=15000)

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

        try:
            collect_document_publications(detail_page)
        except Exception as exc:
            DOCUMENT_AUDIT["status"] = "INCOMPLETE"
            DOCUMENT_AUDIT["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            log(f"    Document-list audit incomplete: {exc}")
        save_pilot_outputs(None)

        reused = reuse_existing_pdf(code, CURRENT_NOMENCLATURE)
        if reused is not None:
            return reused

        # ---------------------------------------------------------------------
        # IDENTIFY TARGET DOCUMENT
        # ---------------------------------------------------------------------

        document_rows = detail_page.locator('[id="tbFicha:dtDocumentos_data"] > tr')

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

            download.save_as(str(RESULTS_DIR / output_filename))

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
            RESULTS_DIR / output_filename,
            document_type,
        )

        if not is_valid:
            # Retain acquired evidence even if text validation is inconclusive.
            pass

            if detail_page != page:
                try:
                    detail_page.close()
                except Exception:
                    pass

            return {
                "status": "PDF_VALIDATION_FAILED",
                "path": RESULTS_DIR / output_filename,
                "document_type": document_type,
                "validation": validation_status,
                "source_filename": source_filename,
            }

        if detail_page != page:
            try:
                detail_page.close()
            except Exception:
                pass

        acquired = RESULTS_DIR / output_filename
        identity = pdf_identity(acquired, CURRENT_NOMENCLATURE)
        if identity == "MISMATCH":
            return {"status": "PDF_IDENTITY_MISMATCH", "path": acquired,
                    "document_type": document_type, "validation": identity,
                    "source_filename": source_filename}
        install_pdf(acquired, output_path)
        return {
            "status": "OK",
            "identity_validation": identity,
            "sha256": digest(output_path),
            "acquisition_mode": "DOWNLOADED",
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



# =============================================================================
# OUTPUT
# =============================================================================






# =============================================================================
# PILOT SCHEDULE EXTRACTION
# =============================================================================
DATE_TOKEN = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\b")
STAGE_WORDS = ("convocatoria", "registro de participantes", "consulta", "observacion",
               "absolucion", "integracion", "presentacion de", "evaluacion", "calificacion", "buena pro")


def extract_schedule_rows(tables):
    """Read stage/start/end rows, excluding layout tables and document listings."""
    records = []
    stage_prefix = re.compile(r"^(?:convocatoria|registro de participantes|formulacion de consultas|absolucion de consultas|integracion de (?:las )?bases|presentacion de (?:ofertas|propuestas)|evaluacion|calificacion|otorgamiento de la buena pro)\b")
    for table_index, rows in enumerate(tables):
        for row_index, cells in enumerate(rows):
            if len(cells) != 3:
                continue
            label = " ".join(cells[0].split())
            if len(label) > 220 or DATE_TOKEN.search(label):
                continue
            if not stage_prefix.search(normalize_text(label)):
                continue
            start = DATE_TOKEN.fullmatch(cells[1].strip())
            end = DATE_TOKEN.fullmatch(cells[2].strip())
            if start is None or end is None:
                continue
            records.append({"table_index": table_index, "row_index": row_index,
                            "stage_label": label, "cells": cells,
                            "raw_text": " | ".join(cells),
                            "date_tokens": [start.group(0), end.group(0)]})
    return records


def unique_boundary(records, predicate, last=False):
    values = []
    for record in records:
        if predicate(normalize_text(record.get("stage_label", record["raw_text"]))):
            dates = record["date_tokens"]
            values.append(dates[-1] if last else dates[0])
    distinct = list(dict.fromkeys(values))
    return distinct[0] if len(distinct) == 1 else None


def capture_schedule(page, code, year):
    global SCHEDULE_RESULT
    page.wait_for_load_state("domcontentloaded")
    text = page.locator("body").inner_text()
    (RESULTS_DIR / "procedure_detail.txt").write_text(text, encoding="utf-8")
    (RESULTS_DIR / "procedure_detail.html").write_text(page.content(), encoding="utf-8")
    try:
        page.screenshot(path=str(RESULTS_DIR / "procedure_detail.png"), full_page=True)
    except Exception as exc:
        log(f"    Screenshot unavailable: {type(exc).__name__}")
    tables = page.locator("table").evaluate_all("""tables => tables.map(table =>
        Array.from(table.rows).filter(row => row.closest('table') === table)
        .map(row => Array.from(row.cells).map(cell => cell.innerText.trim())))""")
    records = extract_schedule_rows(tables)
    (RESULTS_DIR / "schedule_raw.json").write_text(json.dumps(
        {"procedure_code": code, "search_year": year, "url": page.url,
         "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "tables": tables,
         "schedule_rows": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not CURRENT_NOMENCLATURE or compact(CURRENT_NOMENCLATURE) not in compact(text):
        raise RuntimeError("Detail nomenclature does not match the verified search row")
    # Search description/entity and detail nomenclature establish the identity chain.
    source_entity = normalize_text(PILOT_ROW.get("entity_name", ""))
    normalized_page = normalize_text(text)
    code_seen = bool(re.search(r"(?<!\d)" + re.escape(code) + r"(?!\d)", text))
    entity_seen = bool(source_entity and source_entity != "nan" and source_entity in normalized_page)
    SCHEDULE_RESULT = {
        "procedure_code": code, "identity_code_seen": code_seen,
        "identity_entity_seen": entity_seen,
        "identity_status": "source_search_and_detail_matched",
        "nomenclature": CURRENT_NOMENCLATURE,
        "schedule_status": "EXTRACTED" if records else "SCHEDULE_NOT_LOCATED",
        "query_open_raw": unique_boundary(records, lambda t: "formulacion" in t and ("consulta" in t or "observacion" in t)),
        "query_close_raw": unique_boundary(records, lambda t: "formulacion" in t and ("consulta" in t or "observacion" in t), last=True),
        "absolution_raw": unique_boundary(records, lambda t: "absolucion" in t, last=True),
        "integration_raw": unique_boundary(records, lambda t: "integracion" in t, last=True),
        "award_raw": unique_boundary(records, lambda t: "otorgamiento" in t and "buena pro" in t, last=True),
        "date_nature": "published_schedule_not_verified_actual_events",
        "schedule_rows": len(records),
    }
    # Calendar-day differences remain schedule-based until verified externally.
    for field in ("query_open", "query_close", "absolution", "integration", "award"):
        raw = SCHEDULE_RESULT[field + "_raw"]
        SCHEDULE_RESULT[field + "_date"] = pd.to_datetime(raw, dayfirst=True, errors="coerce")
    for name, start, end in [("query_to_award_calendar_days", "query_close", "award"),
                             ("absolution_calendar_days", "query_close", "absolution"),
                             ("integration_calendar_days", "absolution", "integration"),
                             ("post_integration_calendar_days", "integration", "award")]:
        first, last = SCHEDULE_RESULT[start + "_date"], SCHEDULE_RESULT[end + "_date"]
        SCHEDULE_RESULT[name] = (last.normalize() - first.normalize()).days if pd.notna(first) and pd.notna(last) else None
    SCHEDULE_RESULT["chronology_alert"] = any(
        value is not None and value < 0 for key, value in SCHEDULE_RESULT.items() if key.endswith("calendar_days"))
    atomic_json(RESULTS_DIR / "schedule_summary.json", SCHEDULE_RESULT)
    save_pilot_outputs(None)
    log(f"    Schedule rows extracted: {len(records)}; evidence saved before PDF acquisition.")


def publication_records(cells_rows, page_number):
    records = []
    for cells in cells_rows:
        if len(cells) < 6 or not cells[0].strip().isdigit():
            continue
        tokens = DATE_TOKEN.findall(cells[4])
        records.append({"page_number": page_number, "document_number": cells[0].strip(),
                        "stage": cells[1].strip(), "document_name": cells[2].strip(),
                        "publication_raw": cells[4].strip(),
                        "publication_date": pd.to_datetime(tokens[0], dayfirst=True, errors="coerce") if len(tokens) == 1 else pd.NaT,
                        "date_nature": "document_publication_not_automatically_event_date"})
    return records


def collect_document_publications(page):
    global DOCUMENT_RECORDS
    box = page.locator('[id="tbFicha:dtDocumentos"]')
    box.wait_for(state="visible", timeout=15000)
    data = box.locator('tbody[id$="_data"]')
    def move(control):
        before = data.inner_text()
        control.click()
        page.wait_for_function("""previous => {
            const body = document.getElementById('tbFicha:dtDocumentos_data');
            return body && body.innerText !== previous;
        }""", arg=before, timeout=15000)
    first = box.locator('.ui-paginator-first').first
    if first.count() and 'ui-state-disabled' not in (first.get_attribute('class') or ''):
        move(first)
    seen = set()
    DOCUMENT_RECORDS = []
    completed = False
    pages = 0
    try:
        for page_number in range(1, 101):
            raw = data.inner_text()
            if raw in seen:
                raise RuntimeError("Repeated document page; pagination did not advance")
            seen.add(raw)
            pages = page_number
            cells = data.locator('tr').evaluate_all("rows => rows.map(row => Array.from(row.cells).map(c => c.innerText.trim()))")
            DOCUMENT_RECORDS.extend(publication_records(cells, page_number))
            (RESULTS_DIR / f"document_list_page_{page_number:03d}.html").write_text(box.inner_html(), encoding="utf-8")
            next_button = box.locator('.ui-paginator-next').first
            if not next_button.count() or 'ui-state-disabled' in (next_button.get_attribute('class') or ''):
                completed = True
                break
            move(next_button)
    finally:
        DOCUMENT_AUDIT.update(status="COMPLETE" if completed else "INCOMPLETE", pages_read=pages, documents=len(DOCUMENT_RECORDS))
        (RESULTS_DIR / "document_publications.json").write_text(json.dumps(
            {"audit": DOCUMENT_AUDIT, "documents": DOCUMENT_RECORDS}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        # Return to the target document's page before reusing the working downloader.
        first = box.locator('.ui-paginator-first').first
        if first.count() and 'ui-state-disabled' not in (first.get_attribute('class') or ''):
            move(first)
        targets = [r for r in DOCUMENT_RECORDS if 'absolucion de consultas' in normalize_text(r['stage'])
                   and ('pliego de absolucion' in normalize_text(r['document_name']) or 'acta de no formulacion' in normalize_text(r['document_name']))]
        if targets:
            target_page = targets[0]['page_number']
            for _ in range(1, target_page):
                move(box.locator('.ui-paginator-next').first)
    log(f"    Document-list pages: {pages}; documents: {len(DOCUMENT_RECORDS)}; status: {DOCUMENT_AUDIT['status']}")


def save_pilot_outputs(download):
    payload = {"schema_version": SCHEMA_VERSION, "procedure_code": str(PILOT_ROW["procedure_code"]),
               "schedule": SCHEDULE_RESULT, "document_list": DOCUMENT_AUDIT,
               "publications": DOCUMENT_RECORDS, "document": download,
               "evidence_directory": str(RESULTS_DIR), "updated_at_utc": utc_now()}
    atomic_json(RESULTS_DIR / "acquisition.json", payload)


# =============================================================================
# DURABLE STATE, EXISTING FILE AUDIT, AND RESUMABLE BATCH EXECUTION
# =============================================================================
def utc_now():
    return datetime.now(timezone.utc).isoformat()


def compact(value):
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"[^a-z0-9]", "", normalize_text(value))


def json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if value is pd.NA or value is pd.NaT:
        return None
    if hasattr(value, 'item'):
        return value.item()
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                   default=json_default), encoding='utf-8')
    os.replace(temporary, path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def pdf_identity(path, nomenclature):
    import pymupdf
    try:
        with pymupdf.open(path) as doc:
            text = '\n'.join(doc[i].get_text() for i in range(min(3, len(doc))))
        if compact(nomenclature) in compact(text):
            return 'NOMENCLATURE_MATCH'
        # Compare only explicitly labeled nomenclatures, not unrelated procedure references.
        match = re.search(r'nomenclatura\s*:?\s*([A-Z]{2,4}[-\w./]+)', text, re.I)
        if match and compact(match.group(1)) != compact(nomenclature):
            return 'MISMATCH'
        return 'NOT_IDENTIFIABLE_FROM_TEXT'
    except Exception:
        return 'UNREADABLE'


def build_pdf_index(selected_codes):
    index = {}
    for path in sorted(PDFS_DIR.rglob('*')):
        if not path.is_file() or path.suffix.lower() != '.pdf' or 'unverified_existing' in path.parts:
            continue
        match = re.fullmatch(r'(\d+)(_ACTA)?(?:\s*\(\d+\))?', path.stem, flags=re.I)
        if not match:
            EXISTING_ISSUES.append({'path': str(path), 'issue': 'UNRECOGNIZED_FILENAME'})
            continue
        code = match.group(1)
        if code not in selected_codes:
            EXISTING_ISSUES.append({'path': str(path), 'issue': 'CODE_OUTSIDE_CURRENT_SELECTION'})
            continue
        index.setdefault(code, []).append((path, 'ACTA_NO_FORMULACION' if match.group(2) else 'PLIEGO'))
    return index


def install_pdf(source, destination):
    if source.resolve() == destination.resolve():
        return
    # Preserve bytes of an earlier file even when it has the wrong contents.
    if destination.exists():
        if digest(source) == digest(destination):
            return
        archive = PDFS_DIR / 'unverified_existing'
        archive.mkdir(exist_ok=True)
        backup = archive / (destination.stem + '_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.pdf')
        shutil.copy2(destination, backup)
    staged = destination.with_suffix('.pdf.part')
    shutil.copy2(source, staged)
    os.replace(staged, destination)


def reuse_existing_pdf(code, nomenclature):
    # Prefer a nomenclature match; retain content-only files with explicit identity alert.
    reusable = []
    for path, document_type in PDF_INDEX.get(code, []):
        valid, validation = validate_pdf_content(path, document_type)
        identity = pdf_identity(path, nomenclature)
        if not valid or identity in {'MISMATCH', 'UNREADABLE'}:
            EXISTING_ISSUES.append({'procedure_code': code, 'path': str(path),
                                    'issue': validation if not valid else identity})
            continue
        reusable.append((identity != 'NOMENCLATURE_MATCH', path, document_type, validation, identity))
    if not reusable:
        return None
    _, source, document_type, validation, identity = sorted(reusable, key=lambda r: (r[0], str(r[1])))[0]
    canonical = PDFS_DIR / (f'{code}_ACTA.pdf' if document_type == 'ACTA_NO_FORMULACION' else f'{code}.pdf')
    install_pdf(source, canonical)
    log(f'    Reused existing document: {canonical.name} | {identity}')
    return {'status': 'OK', 'path': canonical, 'document_type': document_type,
            'validation': validation, 'identity_validation': identity,
            'source_filename': source.name, 'acquisition_mode': 'EXISTING_REUSED',
            'sha256': digest(canonical)}


def source_signature(row):
    fields = ['procedure_code', 'procedure_description', 'entity_name', 'notice_date']
    text = json.dumps({k: str(row.get(k, '')) for k in fields}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def load_state(code):
    path = STATE_DIR / f'{code}.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def document_still_available(state):
    doc = state.get('document') or {}
    path = Path(doc.get('path') or '')
    return doc.get('status') == 'OK' and path.is_file() and digest(path) == doc.get('sha256')


def fiche_complete(state):
    return (state.get('schedule', {}).get('schedule_status') == 'EXTRACTED'
            and state.get('schedule', {}).get('identity_status') == 'source_search_and_detail_matched'
            and state.get('document_list', {}).get('status') == 'COMPLETE')


def restore_fiche(state):
    global SCHEDULE_RESULT, DOCUMENT_AUDIT, DOCUMENT_RECORDS, CURRENT_NOMENCLATURE
    SCHEDULE_RESULT = state.get('schedule', {})
    DOCUMENT_AUDIT = state.get('document_list', {})
    DOCUMENT_RECORDS = state.get('publications', [])
    CURRENT_NOMENCLATURE = SCHEDULE_RESULT.get('nomenclature', '')


def export_status(codes):
    records, stage_rows, publications = [], [], []
    for code in codes:
        state = load_state(code)
        if not state:
            records.append({'procedure_code': code, 'acquisition_status': 'NOT_ATTEMPTED'})
            continue
        doc = state.get('document') or {}
        schedule = state.get('schedule') or {}
        flat = {'procedure_code': code, 'acquisition_status': state.get('acquisition_status'),
                'attempts': state.get('attempts'), 'updated_at_utc': state.get('updated_at_utc'),
                'document_list_status': state.get('document_list', {}).get('status'),
                'evidence_directory': state.get('evidence_directory'), 'error': state.get('error', '')}
        flat.update(schedule)
        flat.update({'document_' + k: str(v) if isinstance(v, Path) else v for k, v in doc.items()})
        records.append(flat)
        evidence = Path(state.get('evidence_directory', '')) / 'schedule_raw.json'
        if evidence.is_file():
            for r in json.loads(evidence.read_text(encoding='utf-8')).get('schedule_rows', []):
                dates = r['date_tokens']
                stage_rows.append({'procedure_code': code, 'stage': r.get('stage_label'),
                                   'start_raw': dates[0], 'end_raw': dates[-1],
                                   'start_date': pd.to_datetime(dates[0], dayfirst=True, errors='coerce'),
                                   'end_date': pd.to_datetime(dates[-1], dayfirst=True, errors='coerce'),
                                   'raw_text': r['raw_text']})
        publications.extend({'procedure_code': code, **r} for r in state.get('publications', []))
    # CSV and JSON remain available even if Excel is open in Windows.
    pd.DataFrame(records).to_csv(BATCH_ROOT / '01_1_acquisition_status.csv', index=False, encoding='utf-8-sig')
    atomic_json(BATCH_ROOT / '01_4_existing_pdf_audit.json', EXISTING_ISSUES)
    target = BATCH_ROOT / '01_1_acquisition_status.xlsx'
    temporary = BATCH_ROOT / '01_1_acquisition_status.tmp.xlsx'
    try:
        with pd.ExcelWriter(temporary, engine='openpyxl') as writer:
            for name, rows in [('procedure_status', records), ('schedule_stages', stage_rows),
                               ('document_publications', publications), ('existing_pdf_audit', EXISTING_ISSUES)]:
                pd.DataFrame(rows).to_excel(writer, sheet_name=name, index=False)
        os.replace(temporary, target)
    except PermissionError:
        log('    Close acquisition Excel to refresh it; JSON checkpoints and CSV are saved.')
    return records


def search_with_year_fallback(context, code, year, exact_year=False):
    """Retry adjacent years only after a completed search with no result."""
    global SCHEDULE_RESULT, DOCUMENT_AUDIT, DOCUMENT_RECORDS, CURRENT_NOMENCLATURE
    attempts = []
    years = [year] if exact_year else [year, year - 1, year + 1]
    for candidate in years:
        SCHEDULE_RESULT = {}; DOCUMENT_AUDIT = {}; DOCUMENT_RECORDS = []
        CURRENT_NOMENCLATURE = ''
        page = context.new_page()
        try:
            result = search_document_in_year(page, code, candidate)
        finally:
            if not page.is_closed():
                page.close()
        attempts.append({'year': candidate, 'status': result.get('status')})
        if result.get('status') != 'PROCEDURE_NOT_FOUND':
            break
    result = dict(result)
    result['search_origin_year'] = year
    result['search_attempts'] = attempts
    result['search_year_used'] = candidate
    return result



def main():
    global PROJECT_ROOT, BATCH_ROOT, STATE_DIR, RUN_DIR, RESULTS_DIR, LOGS_DIR, PDFS_DIR
    global INPUT_FILE, STATUS_FILE, LOG_FILE, PILOT_ROW, PDF_INDEX
    global SCHEDULE_RESULT, DOCUMENT_AUDIT, DOCUMENT_RECORDS, CURRENT_NOMENCLATURE
    parser = argparse.ArgumentParser(description='Resumable SEACE schedule and target-PDF acquisition. Does not count queries.')
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--batch-size', type=int, default=50, help='Maximum pending procedures attempted in this execution')
    parser.add_argument('--all', action='store_true', help='Attempt all pending procedures sequentially')
    parser.add_argument('--procedure-code', help='Restrict this execution to one selected code')
    parser.add_argument('--year', type=int, help='Search year override; requires --procedure-code')
    parser.add_argument('--refresh-fiches', action='store_true', help='Revisit fiches even when saved; reuse PDFs')
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error('batch-size must be positive')
    if args.year and not args.procedure_code:
        parser.error('--year requires --procedure-code')
    PROJECT_ROOT = args.project_root.resolve() if args.project_root else next(
        (p for p in Path(__file__).resolve().parents if (p / '00_data').is_dir()), None)
    if PROJECT_ROOT is None:
        parser.error('Cannot locate project root; use --project-root PATH')
    INPUT_FILE = PROJECT_ROOT / '02_results' / '01_sample_and_data' / '00_1_sample_selection.xlsx'
    BATCH_ROOT = PROJECT_ROOT / '02_results' / '01_sample_and_data' / '01_acquisition'
    STATE_DIR = BATCH_ROOT / 'state'
    LOGS_DIR = PROJECT_ROOT / '03_logs' / '01_sample_and_data'
    PDFS_DIR = PROJECT_ROOT / '05_pdfs'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    RUN_DIR = BATCH_ROOT / 'runs' / stamp
    for folder in (STATE_DIR, RUN_DIR, LOGS_DIR, PDFS_DIR):
        folder.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOGS_DIR / f'01_download_pdfs_{stamp}.log'
    lock = BATCH_ROOT / 'acquisition.lock'
    # OS-owned locks release automatically after a crash or power interruption.
    lock_stream = lock.open('a+b')
    lock_stream.seek(0, os.SEEK_END)
    if lock_stream.tell() == 0:
        lock_stream.write(b'0'); lock_stream.flush()
    lock_stream.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock_stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock_stream.close()
        raise RuntimeError('Another acquisition instance is already running for this project') from exc
    try:
        sample = pd.read_excel(INPUT_FILE, dtype={'procedure_code': 'string'})
        required = {'procedure_code', 'notice_date', 'procedure_description', 'entity_name'}
        if not required.issubset(sample.columns):
            raise ValueError(f'Missing input columns: {sorted(required-set(sample.columns))}')
        sample['procedure_code'] = sample.procedure_code.str.strip().str.replace(r'\.0$', '', regex=True)
        if sample.procedure_code.isna().any() or sample.procedure_code.duplicated().any() or not sample.procedure_code.str.fullmatch(r'\d+').all():
            raise ValueError('Procedure codes must be unique, nonmissing digits')
        codes = sample.procedure_code.tolist()
        PDF_INDEX = build_pdf_index(set(codes))
        prior_audit = BATCH_ROOT / '01_4_existing_pdf_audit.json'
        if prior_audit.exists():
            EXISTING_ISSUES.extend(json.loads(prior_audit.read_text(encoding='utf-8')))
        todo = []
        for _, row in sample.iterrows():
            code = row.procedure_code
            if args.procedure_code and code != args.procedure_code:
                continue
            state = load_state(code)
            unchanged = state.get('source_signature') == source_signature(row)
            if unchanged and fiche_complete(state) and document_still_available(state) and not args.refresh_fiches:
                continue
            todo.append(row.to_dict())
        if args.procedure_code and args.procedure_code not in codes:
            raise ValueError('Requested procedure is not in the Script 00 selection')
        # Never let repeated failures at the start starve unattempted procedures.
        todo.sort(key=lambda row: (load_state(row['procedure_code']).get('attempts', 0), row['procedure_code']))
        if not args.all:
            todo = todo[:args.batch_size]
        log(f'SEACE ACQUISITION | {SCHEMA_VERSION} | selected={len(codes)} | to attempt={len(todo)}')
        log(f'Canonical PDF directory: {PDFS_DIR}')
        if todo:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=args.headless)
                try:
                    for position, row in enumerate(todo, 1):
                        code = row['procedure_code']; PILOT_ROW = row
                        previous = load_state(code)
                        RESULTS_DIR = RUN_DIR / code; RESULTS_DIR.mkdir()
                        STATUS_FILE = RESULTS_DIR / 'unused.xlsx'
                        SCHEDULE_RESULT = {}; DOCUMENT_AUDIT = {}; DOCUMENT_RECORDS = []; CURRENT_NOMENCLATURE = ''
                        state = {'procedure_code': code, 'source_signature': source_signature(row),
                                 'attempts': previous.get('attempts', 0) + 1, 'acquisition_status': 'IN_PROGRESS',
                                 'updated_at_utc': utc_now(), 'evidence_directory': str(RESULTS_DIR)}
                        atomic_json(STATE_DIR / f'{code}.json', {**previous, **state})
                        context = None
                        log(f'[{position}/{len(todo)}] {code}')
                        try:
                            # A completed fiche remains reusable even if only the PDF failed.
                            if (previous.get('source_signature') == source_signature(row)
                                    and fiche_complete(previous) and not args.refresh_fiches):
                                restore_fiche(previous)
                                result = reuse_existing_pdf(code, CURRENT_NOMENCLATURE)
                                if result is not None:
                                    state['evidence_directory'] = previous['evidence_directory']
                                else:
                                    result = None
                            else:
                                result = None
                            if result is None:
                                notice = pd.to_datetime(row.get('notice_date'), errors='coerce')
                                year = args.year if args.year else int(notice.year) if pd.notna(notice) else None
                                if year is None:
                                    raise ValueError('Notice year unavailable: rerun this code with --year YYYY')
                                context = browser.new_context(viewport={'width': 1600, 'height': 950}, accept_downloads=True)
                                result = search_with_year_fallback(context, code, year, exact_year=args.year is not None)
                                # An existing verified document remains usable even when the live site fails.
                                if result.get('status') != 'OK' and document_still_available(previous):
                                    state['live_document_error'] = result
                                    result = previous['document']
                            state.update(schedule=SCHEDULE_RESULT, document_list=DOCUMENT_AUDIT,
                                         publications=DOCUMENT_RECORDS, document=result)
                            if not fiche_complete(state) and fiche_complete(previous) and previous.get('source_signature') == state['source_signature']:
                                state.update(schedule=previous['schedule'], document_list=previous['document_list'],
                                             publications=previous['publications'], evidence_directory=previous['evidence_directory'])
                            technical_done = fiche_complete(state) and result.get('status') == 'OK'
                            state['acquisition_status'] = 'ACQUIRED' if technical_done else 'PARTIAL_OR_FAILED'
                            state['document_identity_review'] = result.get('identity_validation') != 'NOMENCLATURE_MATCH'
                            state['updated_at_utc'] = utc_now()
                            atomic_json(STATE_DIR / f'{code}.json', state)
                            log(f"    {state['acquisition_status']} | PDF={result.get('status')} | identity={result.get('identity_validation', '')}")
                        except Exception as exc:
                            # Recovery evidence is written before any global Excel export.
                            state.update(schedule=SCHEDULE_RESULT, document_list=DOCUMENT_AUDIT,
                                         publications=DOCUMENT_RECORDS, acquisition_status='PARTIAL_OR_FAILED',
                                         error=f'{type(exc).__name__}: {exc}', updated_at_utc=utc_now())
                            atomic_json(STATE_DIR / f'{code}.json', state)
                            log(f'    FAILED: {exc}')
                        finally:
                            if context:
                                context.close()
                            save_log()
                        if position % 10 == 0:
                            export_status(codes)
                        if position < len(todo):
                            time.sleep(PAUSE_BETWEEN_PROCEDURES)
                finally:
                    browser.close()
        records = export_status(codes)
        done = sum(r.get('acquisition_status') == 'ACQUIRED' for r in records)
        log(f'ACQUIRED: {done}/{len(codes)} | Remaining or failed: {len(codes)-done}')
        log(f'Status workbook: {BATCH_ROOT / "01_1_acquisition_status.xlsx"}')
        log('Run the same command to continue. No query counts are assigned in this script.')
    finally:
        save_log()
        if os.name == 'nt':
            import msvcrt
            lock_stream.seek(0)
            msvcrt.locking(lock_stream.fileno(), msvcrt.LK_UNLCK, 1)
        lock_stream.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted. Saved per-procedure checkpoints will be used on restart.', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f'PIPELINE FAILED: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
