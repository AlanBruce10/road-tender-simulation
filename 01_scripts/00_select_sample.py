import sys
from pathlib import Path

import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "00_data"
RESULTS_DIR = PROJECT_ROOT / "02_results"
LOGS_DIR = PROJECT_ROOT / "03_logs"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_FILE = RESULTS_DIR / "sample_selection.xlsx"
FLOW_FILE = RESULTS_DIR / "sample_selection_flow.xlsx"
LOG_FILE = LOGS_DIR / "00_sample_selection.log"


# ============================================================
# STUDY PARAMETERS
# ============================================================

YEARS = range(2020, 2026)

MIN_REFERENCE_AMOUNT = 25_000_000

ROAD_KEYWORDS = (
    "VIAL|CARRETERA|PUENTE|CAMINO|PAVIMENT|"
    "ASFALTO|TRÁNSITO|TRANSITO|AUTOPISTA"
)

EXCLUSION_KEYWORDS = (
    "AGUA POTABLE|ALCANTARILLADO|SALUD|HOSPITAL|"
    "ESTABLECIMIENTO DE SALUD|REDES COMPLEMENTARIAS|"
    "MURO DE PROTECCIÓN|DRENAJE|FLUVIAL|"
    "ADQUISICION|ADQUISICIÓN|PRESA|IRRIGACIÓN|"
    "PUENTE PEATONAL"
)


# ============================================================
# LOGGING
# ============================================================

log_lines = []


def log(message=""):
    print(message)
    log_lines.append(str(message))


def save_log():
    LOG_FILE.write_text(
        "\n".join(log_lines),
        encoding="utf-8"
    )


# ============================================================
# SAMPLE-SELECTION FLOW
# ============================================================

selection_flow = []


def add_stage(stage, count):
    count = int(count)

    selection_flow.append(
        {
            "stage": stage,
            "count": count
        }
    )

    log(f"  -> {stage}: {count:,}")


# ============================================================
# SOURCE FILE DISCOVERY
# ============================================================

def find_source_file(prefix, year):
    pattern = f"{prefix}{year}_*.xlsx"
    matches = sorted(DATA_DIR.glob(pattern))

    if len(matches) == 0:
        raise FileNotFoundError(
            f"No source file found for {year}: {pattern}"
        )

    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple source files found for {year}: {pattern}\n"
            + "\n".join(f"  - {file.name}" for file in matches)
        )

    return matches[0]


# ============================================================
# DATA VALIDATION
# ============================================================

def require_columns(dataframe, columns, dataset_name):
    missing = [
        column
        for column in columns
        if column not in dataframe.columns
    ]

    if missing:
        raise KeyError(
            f"{dataset_name} is missing required columns: "
            + ", ".join(missing)
        )


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():

    log("=" * 72)
    log("SAMPLE SELECTION - ROAD INFRASTRUCTURE TENDERS")
    log("=" * 72)
    log("Source: OECE-SEACE Open Data Portal")
    log("Study period: 2020-2025")
    log(f"Minimum reference amount: PEN {MIN_REFERENCE_AMOUNT:,.0f}")
    log()

    # --------------------------------------------------------
    # 1. Load source datasets
    # --------------------------------------------------------

    log("[1] Reading OECE-SEACE source datasets...")

    procurement_notice_frames = []
    contract_award_frames = []

    for year in YEARS:

        notice_file = find_source_file(
            "CONOSCE_CONVOCATORIAS",
            year
        )

        award_file = find_source_file(
            "CONOSCE_ADJUDICACIONES",
            year
        )

        log()
        log(f"  {year}")
        log(f"    Procurement notices: {notice_file.name}")
        log(f"    Contract awards:      {award_file.name}")

        notice = pd.read_excel(notice_file)
        award = pd.read_excel(award_file)

        log(f"    Notice rows: {len(notice):,}")
        log(f"    Award rows:  {len(award):,}")

        procurement_notice_frames.append(notice)
        contract_award_frames.append(award)

    procurement_notices = pd.concat(
        procurement_notice_frames,
        ignore_index=True
    )

    contract_awards = pd.concat(
        contract_award_frames,
        ignore_index=True
    )

    log()
    log(
        f"  Total procurement notices: "
        f"{len(procurement_notices):,}"
    )

    log(
        f"  Total contract awards: "
        f"{len(contract_awards):,}"
    )

    add_stage(
        "Initial universe - Procurement notices 2020-2025",
        len(procurement_notices)
    )

    add_stage(
        "Initial universe - Contract awards 2020-2025",
        len(contract_awards)
    )

    # --------------------------------------------------------
    # 2. Validate required source columns
    # --------------------------------------------------------

    log()
    log("[2] Validating required source columns...")

    require_columns(
        procurement_notices,
        [
            "codigoconvocatoria",
            "n_item",
            "objetocontractual",
            "descripcion_proceso",
            "monto_referencial_item",
            "tipoprocesoseleccion",
            "fecha_convocatoria",
        ],
        "Procurement notice dataset"
    )

    require_columns(
        contract_awards,
        [
            "codigoconvocatoria",
            "n_item",
            "fechaintegracionbases",
            "fecha_buenapro",
        ],
        "Contract award dataset"
    )

    log("  Required columns verified.")

    # --------------------------------------------------------
    # 3. Merge procurement notices and contract awards
    # --------------------------------------------------------

    log()
    log(
        "[3] Merging procurement notices and contract awards "
        "by codigoconvocatoria + n_item..."
    )

    merged = pd.merge(
        procurement_notices,
        contract_awards,
        on=["codigoconvocatoria", "n_item"],
        how="inner",
        suffixes=("_conv", "_adj")
    )

    log(f"  Result: {len(merged):,} rows")

    add_stage(
        "After merge (procurement notices + contract awards)",
        len(merged)
    )

    # --------------------------------------------------------
    # 4. Contractual object filter
    # --------------------------------------------------------

    log()
    log("[4] Filtering contractual object = 'Obra'...")

    works_filter = merged[
        merged["objetocontractual_conv"]
        .astype(str)
        .str.upper()
        .str.contains("OBRA", na=False)
    ].copy()

    log(f"  Result: {len(works_filter):,}")

    add_stage(
        "Filter 1: Contractual object = 'Obra'",
        len(works_filter)
    )

    # --------------------------------------------------------
    # 5. Road-infrastructure keyword filter
    # --------------------------------------------------------

    log()
    log("[5] Filtering road-infrastructure keywords...")

    road_filter = works_filter[
        works_filter["descripcion_proceso_conv"]
        .astype(str)
        .str.contains(
            ROAD_KEYWORDS,
            case=False,
            na=False,
            regex=True
        )
    ].copy()

    log(f"  Result: {len(road_filter):,}")

    add_stage(
        "Filter 2: Road-infrastructure keywords",
        len(road_filter)
    )

    # --------------------------------------------------------
    # 6. Reference amount filter
    # --------------------------------------------------------

    log()
    log(
        "[6] Filtering reference amount > PEN 25,000,000..."
    )

    road_filter["monto_referencial_item"] = pd.to_numeric(
        road_filter["monto_referencial_item"],
        errors="coerce"
    )

    amount_filter = road_filter[
        road_filter["monto_referencial_item"]
        > MIN_REFERENCE_AMOUNT
    ].copy()

    log(f"  Result: {len(amount_filter):,}")

    add_stage(
        "Filter 3: Reference amount > PEN 25,000,000",
        len(amount_filter)
    )

    # --------------------------------------------------------
    # 7. Selection procedure filter
    # --------------------------------------------------------

    log()
    log(
        "[7] Filtering selection procedure = "
        "'Licitación Pública'..."
    )

    public_tender_filter = amount_filter[
        amount_filter["tipoprocesoseleccion_conv"]
        .astype(str)
        .str.contains(
            "LICITACIÓN PÚBLICA",
            case=False,
            na=False,
            regex=False
        )
    ].copy()

    log(f"  Result: {len(public_tender_filter):,}")

    add_stage(
        "Filter 4: Selection procedure = 'Licitación Pública'",
        len(public_tender_filter)
    )

    # --------------------------------------------------------
    # 8. Exclusion criteria
    # --------------------------------------------------------

    log()
    log("[8] Applying exclusion criteria...")

    exclusion_filter = public_tender_filter[
        ~public_tender_filter["descripcion_proceso_conv"]
        .astype(str)
        .str.contains(
            EXCLUSION_KEYWORDS,
            case=False,
            na=False,
            regex=True
        )
    ].copy()

    log(f"  Result: {len(exclusion_filter):,}")

    add_stage(
        "Filter 5: Exclusion criteria",
        len(exclusion_filter)
    )

    # --------------------------------------------------------
    # 9. Remove duplicate procurement procedures
    # --------------------------------------------------------

    log()
    log(
        "[9] Removing duplicate procurement procedures..."
    )

    filtered = exclusion_filter.drop_duplicates(
        subset=["codigoconvocatoria"],
        keep="first"
    ).copy()

    log(f"  Result: {len(filtered):,}")

    add_stage(
        "Filter 6: Unique procurement procedures",
        len(filtered)
    )

    # --------------------------------------------------------
    # 10. Award-time variables
    # --------------------------------------------------------

    log()
    log("[10] Calculating award-time variables...")

    filtered["fecha_convocatoria_conv"] = pd.to_datetime(
        filtered["fecha_convocatoria_conv"],
        errors="coerce",
        dayfirst=True
    )

    filtered["fechaintegracionbases"] = pd.to_datetime(
        filtered["fechaintegracionbases"],
        errors="coerce",
        dayfirst=True
    )

    filtered["fecha_buenapro"] = pd.to_datetime(
        filtered["fecha_buenapro"],
        errors="coerce",
        dayfirst=True
    )

    filtered["duracion_etapa_consultas_dias"] = (
        filtered["fechaintegracionbases"]
        - filtered["fecha_convocatoria_conv"]
    ).dt.days

    filtered["duracion_etapa_evaluacion_dias"] = (
        filtered["fecha_buenapro"]
        - filtered["fechaintegracionbases"]
    ).dt.days

    filtered["plazo_total_adjudicacion_dias"] = (
        filtered["fecha_buenapro"]
        - filtered["fecha_convocatoria_conv"]
    ).dt.days

    log("  Award-time variables calculated.")

    # --------------------------------------------------------
    # 11. Prepare reproducible output dataset
    # --------------------------------------------------------

    log()
    log("[11] Preparing output dataset...")

    final_columns = [
        "codigoconvocatoria",
        "descripcion_proceso_conv",
        "montoreferencial",
        "monto_referencial_item",
        "monto_adjudicado_item_soles",
        "fecha_convocatoria_conv",
        "fechaintegracionbases",
        "fecha_buenapro",
        "duracion_etapa_consultas_dias",
        "duracion_etapa_evaluacion_dias",
        "plazo_total_adjudicacion_dias",
    ]

    available_columns = [
        column
        for column in final_columns
        if column in filtered.columns
    ]

    final_dataset = filtered[
        available_columns
    ].copy()

    final_dataset.rename(
        columns={
            "codigoconvocatoria":
                "procedure_code",
            "descripcion_proceso_conv":
                "procedure_description",
            "montoreferencial":
                "reference_amount",
            "monto_referencial_item":
                "item_reference_amount",
            "monto_adjudicado_item_soles":
                "awarded_amount_pen",
            "fecha_convocatoria_conv":
                "notice_date",
            "fechaintegracionbases":
                "integrated_terms_date",
            "fecha_buenapro":
                "award_date",
            "duracion_etapa_consultas_dias":
                "query_stage_duration_days",
            "duracion_etapa_evaluacion_dias":
                "evaluation_stage_duration_days",
            "plazo_total_adjudicacion_dias":
                "total_award_time_days",
        },
        inplace=True
    )

    final_dataset[
        "queries_observations_count"
    ] = pd.NA

    final_dataset.sort_values(
        by="procedure_code",
        inplace=True
    )

    final_dataset.reset_index(
        drop=True,
        inplace=True
    )

    # --------------------------------------------------------
    # 12. Save reproducible outputs
    # --------------------------------------------------------

    log()
    log("[12] Saving reproducible outputs...")

    final_dataset.to_excel(
        SAMPLE_FILE,
        index=False
    )

    selection_flow_dataframe = pd.DataFrame(
        selection_flow
    )

    selection_flow_dataframe.to_excel(
        FLOW_FILE,
        index=False
    )

    log(f"  Dataset: {SAMPLE_FILE.name}")
    log(f"  Selection flow: {FLOW_FILE.name}")

    # --------------------------------------------------------
    # 13. Final summary
    # --------------------------------------------------------

    log()
    log("=" * 72)
    log("SAMPLE-SELECTION FLOW")
    log("=" * 72)

    for stage in selection_flow:
        log(
            f"  {stage['stage']}: "
            f"{stage['count']:,}"
        )

    log()
    log("=" * 72)
    log(
        f"FINAL SAMPLE: "
        f"{len(final_dataset):,} procedures"
    )
    log("=" * 72)

    save_log()


# ============================================================
# EXECUTION
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        log()
        log("=" * 72)
        log("PIPELINE FAILED")
        log("=" * 72)
        log(f"{type(error).__name__}: {error}")

        save_log()

        raise
