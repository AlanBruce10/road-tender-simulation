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
    text = str(message)
    print(text)
    log_lines.append(text)


def save_log():
    LOG_FILE.write_text(
        "\n".join(log_lines),
        encoding="utf-8"
    )


# ============================================================
# FILE DISCOVERY
# ============================================================

def find_source_file(prefix, year):
    matches = sorted(
        DATA_DIR.glob(f"{prefix}{year}_*.xlsx")
    )

    if len(matches) == 0:
        raise FileNotFoundError(
            f"No source file found for pattern: "
            f"{prefix}{year}_*.xlsx"
        )

    if len(matches) > 1:
        names = ", ".join(file.name for file in matches)

        raise RuntimeError(
            f"Multiple source files found for {prefix}{year}: "
            f"{names}"
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
            f"{', '.join(missing)}"
        )


# ============================================================
# RECORD-LINKAGE FUNCTIONS
# ============================================================

LINKAGE_KEYS = [
    "codigoconvocatoria",
    "n_item"
]


def unique_keys(dataframe):
    return (
        dataframe[LINKAGE_KEYS]
        .dropna()
        .drop_duplicates()
        .copy()
    )


def count_key_duplicates(dataframe):
    valid = dataframe.dropna(
        subset=LINKAGE_KEYS
    )

    return int(
        valid.duplicated(
            subset=LINKAGE_KEYS,
            keep=False
        ).sum()
    )


def build_linkage_audit(
    procurement_notices,
    contract_awards
):
    notice_keys = unique_keys(procurement_notices)
    award_keys = unique_keys(contract_awards)

    common_keys = pd.merge(
        notice_keys,
        award_keys,
        on=LINKAGE_KEYS,
        how="inner"
    )

    notice_only = pd.merge(
        notice_keys,
        award_keys,
        on=LINKAGE_KEYS,
        how="left",
        indicator=True
    )

    notice_only = notice_only[
        notice_only["_merge"] == "left_only"
    ][LINKAGE_KEYS]

    award_only = pd.merge(
        award_keys,
        notice_keys,
        on=LINKAGE_KEYS,
        how="left",
        indicator=True
    )

    award_only = award_only[
        award_only["_merge"] == "left_only"
    ][LINKAGE_KEYS]

    notice_unique_count = len(notice_keys)
    award_unique_count = len(award_keys)
    common_count = len(common_keys)

    notice_linkage_rate = (
        common_count / notice_unique_count * 100
        if notice_unique_count
        else 0
    )

    award_linkage_rate = (
        common_count / award_unique_count * 100
        if award_unique_count
        else 0
    )

    audit = pd.DataFrame(
        [
            {
                "metric": "Procurement-notice records",
                "value": len(procurement_notices),
                "unit": "records"
            },
            {
                "metric": "Contract-award records",
                "value": len(contract_awards),
                "unit": "records"
            },
            {
                "metric": "Unique procurement-notice keys",
                "value": notice_unique_count,
                "unit": "keys"
            },
            {
                "metric": "Unique contract-award keys",
                "value": award_unique_count,
                "unit": "keys"
            },
            {
                "metric": "Keys present in both sources",
                "value": common_count,
                "unit": "keys"
            },
            {
                "metric": "Procurement-notice-only keys",
                "value": len(notice_only),
                "unit": "keys"
            },
            {
                "metric": "Contract-award-only keys",
                "value": len(award_only),
                "unit": "keys"
            },
            {
                "metric": "Procurement-notice linkage rate",
                "value": notice_linkage_rate,
                "unit": "percent"
            },
            {
                "metric": "Contract-award linkage rate",
                "value": award_linkage_rate,
                "unit": "percent"
            },
            {
                "metric": (
                    "Procurement-notice rows belonging "
                    "to duplicated keys"
                ),
                "value": count_key_duplicates(
                    procurement_notices
                ),
                "unit": "records"
            },
            {
                "metric": (
                    "Contract-award rows belonging "
                    "to duplicated keys"
                ),
                "value": count_key_duplicates(
                    contract_awards
                ),
                "unit": "records"
            }
        ]
    )

    return audit, common_keys, notice_only, award_only


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    log("=" * 72)
    log("SAMPLE SELECTION - ROAD INFRASTRUCTURE TENDERS")
    log("=" * 72)
    log("Source: OECE-SEACE Open Data Portal")
    log("Study period: 2020-2025")
    log()

    # --------------------------------------------------------
    # 1. SOURCE DATA
    # --------------------------------------------------------

    log("[1] Reading OECE-SEACE source datasets...")
    log()

    procurement_frames = []
    award_frames = []

    source_summary = []

    for year in YEARS:
        notice_file = find_source_file(
            "CONOSCE_CONVOCATORIAS",
            year
        )

        award_file = find_source_file(
            "CONOSCE_ADJUDICACIONES",
            year
        )

        notice = pd.read_excel(notice_file)
        award = pd.read_excel(award_file)

        notice["_source_year"] = year
        award["_source_year"] = year

        procurement_frames.append(notice)
        award_frames.append(award)

        source_summary.append(
            {
                "year": year,
                "procurement_notice_file": notice_file.name,
                "procurement_notice_records": len(notice),
                "contract_award_file": award_file.name,
                "contract_award_records": len(award)
            }
        )

        log(
            f"  {year}: "
            f"procurement notices={len(notice):,} | "
            f"contract awards={len(award):,}"
        )

    procurement_notices = pd.concat(
        procurement_frames,
        ignore_index=True
    )

    contract_awards = pd.concat(
        award_frames,
        ignore_index=True
    )

    source_summary_df = pd.DataFrame(source_summary)

    log()
    log(
        "  Procurement-notice records, 2020-2025: "
        f"{len(procurement_notices):,}"
    )
    log(
        "  Contract-award records, 2020-2025: "
        f"{len(contract_awards):,}"
    )

    # --------------------------------------------------------
    # 2. REQUIRED COLUMNS
    # --------------------------------------------------------

    require_columns(
        procurement_notices,
        [
            "codigoconvocatoria",
            "n_item",
            "objetocontractual",
            "descripcion_proceso",
            "tipoprocesoseleccion",
            "monto_referencial_item",
            "fecha_convocatoria"
        ],
        "Procurement-notice dataset"
    )

    require_columns(
        contract_awards,
        [
            "codigoconvocatoria",
            "n_item",
            "fechaintegracionbases",
            "fecha_buenapro"
        ],
        "Contract-award dataset"
    )

    # --------------------------------------------------------
    # 3. RECORD-LINKAGE AUDIT
    # --------------------------------------------------------

    log()
    log("[2] Auditing record linkage...")
    log(
        "  Linkage key: codigoconvocatoria + n_item"
    )

    (
        linkage_audit,
        common_keys,
        notice_only_keys,
        award_only_keys
    ) = build_linkage_audit(
        procurement_notices,
        contract_awards
    )

    audit_lookup = dict(
        zip(
            linkage_audit["metric"],
            linkage_audit["value"]
        )
    )

    log()
    log(
        "  Unique procurement-notice keys: "
        f"{int(audit_lookup['Unique procurement-notice keys']):,}"
    )

    log(
        "  Unique contract-award keys: "
        f"{int(audit_lookup['Unique contract-award keys']):,}"
    )

    log(
        "  Keys present in both sources: "
        f"{int(audit_lookup['Keys present in both sources']):,}"
    )

    log(
        "  Procurement-notice-only keys: "
        f"{int(audit_lookup['Procurement-notice-only keys']):,}"
    )

    log(
        "  Contract-award-only keys: "
        f"{int(audit_lookup['Contract-award-only keys']):,}"
    )

    log(
        "  Procurement-notice linkage rate: "
        f"{audit_lookup['Procurement-notice linkage rate']:.2f}%"
    )

    log(
        "  Contract-award linkage rate: "
        f"{audit_lookup['Contract-award linkage rate']:.2f}%"
    )

    # --------------------------------------------------------
    # 4. RECORD LINKAGE
    # --------------------------------------------------------

    log()
    log("[3] Linking procurement notices and contract awards...")

    merged = pd.merge(
        procurement_notices,
        contract_awards,
        on=LINKAGE_KEYS,
        how="inner",
        suffixes=("_conv", "_adj")
    )

    merged_records = len(merged)

    log(
        f"  Matched records after inner merge: "
        f"{merged_records:,}"
    )

    # --------------------------------------------------------
    # 5. SAMPLE-SELECTION FLOW
    # --------------------------------------------------------

    selection_flow = []

    def add_stage(stage, criterion, count):
        selection_flow.append(
            {
                "stage": stage,
                "criterion": criterion,
                "count": int(count)
            }
        )

        log(
            f"  {stage}: {criterion}: "
            f"{int(count):,}"
        )

    log()
    log("[4] Applying sample-selection criteria...")
    log()

    # Filter 1
    works_filter = merged[
        merged["objetocontractual_conv"]
        .astype(str)
        .str.upper()
        .str.contains(
            "OBRA",
            na=False
        )
    ].copy()

    add_stage(
        "Filter 1",
        "Contractual object = 'Obra'",
        len(works_filter)
    )

    # Filter 2
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

    add_stage(
        "Filter 2",
        "Road-infrastructure keywords",
        len(road_filter)
    )

    # Filter 3
    road_filter["monto_referencial_item"] = (
        pd.to_numeric(
            road_filter["monto_referencial_item"],
            errors="coerce"
        )
    )

    amount_filter = road_filter[
        road_filter["monto_referencial_item"]
        > MIN_REFERENCE_AMOUNT
    ].copy()

    add_stage(
        "Filter 3",
        "Reference amount > PEN 25,000,000",
        len(amount_filter)
    )

    # Filter 4
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

    add_stage(
        "Filter 4",
        "Selection procedure = 'Licitación Pública'",
        len(public_tender_filter)
    )

    # Filter 5
    exclusion_filter = public_tender_filter[
        ~public_tender_filter[
            "descripcion_proceso_conv"
        ]
        .astype(str)
        .str.contains(
            EXCLUSION_KEYWORDS,
            case=False,
            na=False,
            regex=True
        )
    ].copy()

    add_stage(
        "Filter 5",
        "Exclusion criteria",
        len(exclusion_filter)
    )

    # Filter 6
    filtered = exclusion_filter.drop_duplicates(
        subset=["codigoconvocatoria"],
        keep="first"
    ).copy()

    add_stage(
        "Filter 6",
        "Unique procurement procedures",
        len(filtered)
    )

    # --------------------------------------------------------
    # 6. AWARD-TIME VARIABLES
    # --------------------------------------------------------

    log()
    log("[5] Calculating award-time variables...")

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
    # 7. FINAL DATASET
    # --------------------------------------------------------

    log()
    log("[6] Preparing output dataset...")

    preferred_columns = [
        "codigoconvocatoria",
        "descripcion_proceso_conv",
        "montoreferencial",
        "monto_adjudicado_item_soles",
        "fecha_convocatoria_conv",
        "fechaintegracionbases",
        "fecha_buenapro",
        "duracion_etapa_consultas_dias",
        "duracion_etapa_evaluacion_dias",
        "plazo_total_adjudicacion_dias"
    ]

    missing_output_columns = [
        column
        for column in preferred_columns
        if column not in filtered.columns
    ]

    if missing_output_columns:
        raise KeyError(
            "Required output columns are missing after linkage: "
            + ", ".join(missing_output_columns)
        )

    final_dataset = filtered[
        preferred_columns
    ].copy()

    final_dataset.rename(
        columns={
            "descripcion_proceso_conv":
                "descripcion_proceso",
            "fecha_convocatoria_conv":
                "fecha_convocatoria"
        },
        inplace=True
    )

    final_dataset[
        "cant_consultas_observaciones"
    ] = pd.NA

    # --------------------------------------------------------
    # 8. SAVE REPRODUCIBLE OUTPUTS
    # --------------------------------------------------------

    log()
    log("[7] Saving reproducible outputs...")

    final_dataset.to_excel(
        SAMPLE_FILE,
        index=False
    )

    selection_flow_df = pd.DataFrame(
        selection_flow
    )

    linkage_summary_row = pd.DataFrame(
        [
            {
                "stage": "Record linkage",
                "criterion": (
                    "Keys present in both sources "
                    "(codigoconvocatoria + n_item)"
                ),
                "count": len(common_keys)
            }
        ]
    )

    methodological_flow = pd.concat(
        [
            pd.DataFrame(
                [
                    {
                        "stage": "Source A",
                        "criterion": (
                            "Procurement-notice records, "
                            "2020-2025"
                        ),
                        "count": len(
                            procurement_notices
                        )
                    },
                    {
                        "stage": "Source B",
                        "criterion": (
                            "Contract-award records, "
                            "2020-2025"
                        ),
                        "count": len(
                            contract_awards
                        )
                    }
                ]
            ),
            linkage_summary_row,
            selection_flow_df
        ],
        ignore_index=True
    )

    with pd.ExcelWriter(
        FLOW_FILE,
        engine="openpyxl"
    ) as writer:

        methodological_flow.to_excel(
            writer,
            sheet_name="selection_flow",
            index=False
        )

        linkage_audit.to_excel(
            writer,
            sheet_name="linkage_audit",
            index=False
        )

        source_summary_df.to_excel(
            writer,
            sheet_name="source_files",
            index=False
        )

        notice_only_keys.to_excel(
            writer,
            sheet_name="notice_only_keys",
            index=False
        )

        award_only_keys.to_excel(
            writer,
            sheet_name="award_only_keys",
            index=False
        )

    log(
        f"  Dataset: {SAMPLE_FILE.name}"
    )

    log(
        f"  Selection flow: {FLOW_FILE.name}"
    )

    # --------------------------------------------------------
    # 9. FINAL SUMMARY
    # --------------------------------------------------------

    log()
    log("=" * 72)
    log("RECORD LINKAGE")
    log("=" * 72)

    log(
        "Procurement-notice records: "
        f"{len(procurement_notices):,}"
    )

    log(
        "Contract-award records: "
        f"{len(contract_awards):,}"
    )

    log(
        "Unique procurement-notice keys: "
        f"{len(unique_keys(procurement_notices)):,}"
    )

    log(
        "Unique contract-award keys: "
        f"{len(unique_keys(contract_awards)):,}"
    )

    log(
        "Keys present in both sources: "
        f"{len(common_keys):,}"
    )

    log(
        "Procurement-notice-only keys: "
        f"{len(notice_only_keys):,}"
    )

    log(
        "Contract-award-only keys: "
        f"{len(award_only_keys):,}"
    )

    log(
        "Matched records after inner merge: "
        f"{merged_records:,}"
    )

    log()
    log("=" * 72)
    log("SAMPLE-SELECTION FLOW")
    log("=" * 72)

    for stage in selection_flow:
        log(
            f"{stage['stage']}: "
            f"{stage['criterion']}: "
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
        log(
            f"{type(error).__name__}: {error}"
        )

        save_log()
        sys.exit(1)
