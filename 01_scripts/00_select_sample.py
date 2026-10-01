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

SAMPLE_FILE = RESULTS_DIR / "00_1_sample_selection.xlsx"
FLOW_FILE = RESULTS_DIR / "00_2_sample_selection_flow.xlsx"
LOG_FILE = LOGS_DIR / "00_sample_selection.log"


# ============================================================
# STUDY PARAMETERS
# ============================================================

YEARS = range(2020, 2026)

MIN_REFERENCE_AMOUNT = 25_000_000

LINKAGE_KEYS = [
    "codigoconvocatoria",
    "n_item",
]

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
        encoding="utf-8",
    )


# ============================================================
# SOURCE FILE DISCOVERY
# ============================================================

def find_source_file(prefix, year):
    pattern = f"{prefix}{year}_*.xlsx"
    matches = sorted(DATA_DIR.glob(pattern))

    if len(matches) == 0:
        raise FileNotFoundError(
            f"No source file found for pattern: {pattern}"
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
            + ", ".join(missing)
        )


# ============================================================
# COUNTING FUNCTIONS
# ============================================================

def count_records(dataframe):
    return len(dataframe)


def count_procedure_item_keys(dataframe):
    return len(
        dataframe[
            ["codigoconvocatoria", "n_item"]
        ]
        .dropna()
        .drop_duplicates()
    )


def count_unique_procedures(dataframe):
    return (
        dataframe["codigoconvocatoria"]
        .dropna()
        .nunique()
    )


def stage_counts(dataframe):
    return {
        "records": count_records(dataframe),
        "procedure_item_keys":
            count_procedure_item_keys(dataframe),
        "unique_procedures":
            count_unique_procedures(dataframe),
    }


def duplicated_key_rows(dataframe):
    valid = dataframe.dropna(
        subset=LINKAGE_KEYS
    )

    return int(
        valid.duplicated(
            subset=LINKAGE_KEYS,
            keep=False,
        ).sum()
    )


# ============================================================
# RECORD LINKAGE AUDIT
# ============================================================

def build_linkage_audit(
    procurement_notices,
    contract_awards,
):
    notice_keys = (
        procurement_notices[LINKAGE_KEYS]
        .dropna()
        .drop_duplicates()
        .copy()
    )

    award_keys = (
        contract_awards[LINKAGE_KEYS]
        .dropna()
        .drop_duplicates()
        .copy()
    )

    common_keys = pd.merge(
        notice_keys,
        award_keys,
        on=LINKAGE_KEYS,
        how="inner",
    )

    notice_comparison = pd.merge(
        notice_keys,
        award_keys,
        on=LINKAGE_KEYS,
        how="left",
        indicator=True,
    )

    notice_only_keys = notice_comparison.loc[
        notice_comparison["_merge"] == "left_only",
        LINKAGE_KEYS,
    ].copy()

    award_comparison = pd.merge(
        award_keys,
        notice_keys,
        on=LINKAGE_KEYS,
        how="left",
        indicator=True,
    )

    award_only_keys = award_comparison.loc[
        award_comparison["_merge"] == "left_only",
        LINKAGE_KEYS,
    ].copy()

    notice_unique_count = len(notice_keys)
    award_unique_count = len(award_keys)
    common_count = len(common_keys)

    notice_linkage_rate = (
        common_count / notice_unique_count * 100
        if notice_unique_count
        else 0.0
    )

    award_linkage_rate = (
        common_count / award_unique_count * 100
        if award_unique_count
        else 0.0
    )

    linkage_audit = pd.DataFrame(
        [
            {
                "metric":
                    "Procurement-notice records",
                "value":
                    len(procurement_notices),
                "unit":
                    "records",
            },
            {
                "metric":
                    "Contract-award records",
                "value":
                    len(contract_awards),
                "unit":
                    "records",
            },
            {
                "metric":
                    "Unique procurement-notice procedure-item keys",
                "value":
                    notice_unique_count,
                "unit":
                    "procedure-item keys",
            },
            {
                "metric":
                    "Unique contract-award procedure-item keys",
                "value":
                    award_unique_count,
                "unit":
                    "procedure-item keys",
            },
            {
                "metric":
                    "Procedure-item keys present in both sources",
                "value":
                    common_count,
                "unit":
                    "procedure-item keys",
            },
            {
                "metric":
                    "Procurement-notice-only keys",
                "value":
                    len(notice_only_keys),
                "unit":
                    "procedure-item keys",
            },
            {
                "metric":
                    "Contract-award-only keys",
                "value":
                    len(award_only_keys),
                "unit":
                    "procedure-item keys",
            },
            {
                "metric":
                    "Procurement-notice linkage rate",
                "value":
                    notice_linkage_rate,
                "unit":
                    "percent",
            },
            {
                "metric":
                    "Contract-award linkage rate",
                "value":
                    award_linkage_rate,
                "unit":
                    "percent",
            },
            {
                "metric":
                    (
                        "Procurement-notice rows belonging "
                        "to duplicated procedure-item keys"
                    ),
                "value":
                    duplicated_key_rows(
                        procurement_notices
                    ),
                "unit":
                    "records",
            },
            {
                "metric":
                    (
                        "Contract-award rows belonging "
                        "to duplicated procedure-item keys"
                    ),
                "value":
                    duplicated_key_rows(
                        contract_awards
                    ),
                "unit":
                    "records",
            },
        ]
    )

    return (
        linkage_audit,
        common_keys,
        notice_only_keys,
        award_only_keys,
    )


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    log("=" * 78)
    log(
        "SAMPLE SELECTION - "
        "ROAD INFRASTRUCTURE TENDERS"
    )
    log("=" * 78)
    log("Source: OECE-SEACE Open Data Portal")
    log("Study period: 2020-2025")
    log()

    # --------------------------------------------------------
    # 1. READ SOURCE DATA
    # --------------------------------------------------------

    log(
        "[1] Reading OECE-SEACE "
        "source datasets..."
    )
    log()

    procurement_frames = []
    award_frames = []
    source_summary = []

    for year in YEARS:
        notice_file = find_source_file(
            "CONOSCE_CONVOCATORIAS",
            year,
        )

        award_file = find_source_file(
            "CONOSCE_ADJUDICACIONES",
            year,
        )

        notice = pd.read_excel(notice_file)
        award = pd.read_excel(award_file)

        procurement_frames.append(notice)
        award_frames.append(award)

        source_summary.append(
            {
                "year":
                    year,
                "procurement_notice_file":
                    notice_file.name,
                "procurement_notice_records":
                    len(notice),
                "contract_award_file":
                    award_file.name,
                "contract_award_records":
                    len(award),
            }
        )

        log(
            f"  {year}: "
            f"procurement notices={len(notice):,} | "
            f"contract awards={len(award):,}"
        )

    procurement_notices = pd.concat(
        procurement_frames,
        ignore_index=True,
    )

    contract_awards = pd.concat(
        award_frames,
        ignore_index=True,
    )

    source_summary_df = pd.DataFrame(
        source_summary
    )

    log()
    log(
        "  Procurement-notice records, "
        "2020-2025: "
        f"{len(procurement_notices):,}"
    )

    log(
        "  Contract-award records, "
        "2020-2025: "
        f"{len(contract_awards):,}"
    )

    # --------------------------------------------------------
    # 2. VALIDATE SOURCE STRUCTURE
    # --------------------------------------------------------

    log()
    log(
        "[2] Validating required "
        "source columns..."
    )

    require_columns(
        procurement_notices,
        [
            "codigoconvocatoria",
            "n_item",
            "descripcion_proceso",
            "objetocontractual",
            "tipoprocesoseleccion",
            "montoreferencial",
            "monto_referencial_item",
            "fecha_convocatoria",
            "fechaintegracionbases",
        ],
        "Procurement-notice dataset",
    )

    require_columns(
        contract_awards,
        [
            "codigoconvocatoria",
            "n_item",
            "monto_adjudicado_item_soles",
            "fecha_buenapro",
        ],
        "Contract-award dataset",
    )

    log("  Required columns verified.")

    # --------------------------------------------------------
    # 3. SOURCE AUDIT
    # --------------------------------------------------------

    log()
    log("[3] Auditing source datasets...")

    notice_counts = stage_counts(
        procurement_notices
    )

    award_counts = stage_counts(
        contract_awards
    )

    log()
    log("  PROCUREMENT NOTICES")
    log(
        f"    Records: "
        f"{notice_counts['records']:,}"
    )
    log(
        f"    Procedure-item keys: "
        f"{notice_counts['procedure_item_keys']:,}"
    )
    log(
        f"    Unique procedures: "
        f"{notice_counts['unique_procedures']:,}"
    )

    log()
    log("  CONTRACT AWARDS")
    log(
        f"    Records: "
        f"{award_counts['records']:,}"
    )
    log(
        f"    Procedure-item keys: "
        f"{award_counts['procedure_item_keys']:,}"
    )
    log(
        f"    Unique procedures: "
        f"{award_counts['unique_procedures']:,}"
    )

    # --------------------------------------------------------
    # 4. RECORD LINKAGE AUDIT
    # --------------------------------------------------------

    log()
    log("[4] Auditing record linkage...")
    log(
        "  Linkage key: "
        "codigoconvocatoria + n_item"
    )

    (
        linkage_audit,
        common_keys,
        notice_only_keys,
        award_only_keys,
    ) = build_linkage_audit(
        procurement_notices,
        contract_awards,
    )

    notice_linkage_rate = (
        len(common_keys)
        / notice_counts["procedure_item_keys"]
        * 100
    )

    award_linkage_rate = (
        len(common_keys)
        / award_counts["procedure_item_keys"]
        * 100
    )

    log()
    log(
        "  Procedure-item keys present "
        "in both sources: "
        f"{len(common_keys):,}"
    )

    log(
        "  Procurement-notice-only keys: "
        f"{len(notice_only_keys):,}"
    )

    log(
        "  Contract-award-only keys: "
        f"{len(award_only_keys):,}"
    )

    log(
        "  Procurement-notice linkage rate: "
        f"{notice_linkage_rate:.2f}%"
    )

    log(
        "  Contract-award linkage rate: "
        f"{award_linkage_rate:.2f}%"
    )

    # --------------------------------------------------------
    # 5. LINK SOURCE DATASETS
    # --------------------------------------------------------

    log()
    log(
        "[5] Linking procurement notices "
        "and contract awards..."
    )

    merged = pd.merge(
        procurement_notices,
        contract_awards,
        on=LINKAGE_KEYS,
        how="inner",
        suffixes=("_conv", "_adj"),
    )

    merged_counts = stage_counts(merged)

    log()
    log("  LINKED DATASET")
    log(
        f"    Records: "
        f"{merged_counts['records']:,}"
    )
    log(
        f"    Procedure-item keys: "
        f"{merged_counts['procedure_item_keys']:,}"
    )
    log(
        f"    Unique procedures: "
        f"{merged_counts['unique_procedures']:,}"
    )

    # --------------------------------------------------------
    # 6. SAMPLE-SELECTION CRITERIA
    # --------------------------------------------------------

    log()
    log(
        "[6] Applying sample-selection "
        "criteria..."
    )
    log()

    selection_flow = []

    def add_stage(
        stage,
        criterion,
        dataframe,
    ):
        counts = stage_counts(dataframe)

        selection_flow.append(
            {
                "stage":
                    stage,
                "criterion":
                    criterion,
                "records":
                    counts["records"],
                "procedure_item_keys":
                    counts["procedure_item_keys"],
                "unique_procedures":
                    counts["unique_procedures"],
            }
        )

        log(
            f"  {stage}: {criterion}"
        )
        log(
            f"    Records: "
            f"{counts['records']:,}"
        )
        log(
            f"    Procedure-item keys: "
            f"{counts['procedure_item_keys']:,}"
        )
        log(
            f"    Unique procedures: "
            f"{counts['unique_procedures']:,}"
        )
        log()

    # Filter 1
    works_filter = merged[
        merged["objetocontractual_conv"]
        .astype(str)
        .str.upper()
        .str.contains(
            "OBRA",
            na=False,
        )
    ].copy()

    add_stage(
        "Filter 1",
        "Contractual object = 'Obra'",
        works_filter,
    )

    # Filter 2
    road_filter = works_filter[
        works_filter[
            "descripcion_proceso_conv"
        ]
        .astype(str)
        .str.contains(
            ROAD_KEYWORDS,
            case=False,
            na=False,
            regex=True,
        )
    ].copy()

    add_stage(
        "Filter 2",
        "Road-infrastructure keywords",
        road_filter,
    )

    # Filter 3
    road_filter[
        "monto_referencial_item"
    ] = pd.to_numeric(
        road_filter[
            "monto_referencial_item"
        ],
        errors="coerce",
    )

    amount_filter = road_filter[
        road_filter[
            "monto_referencial_item"
        ] > MIN_REFERENCE_AMOUNT
    ].copy()

    add_stage(
        "Filter 3",
        "Reference amount > PEN 25,000,000",
        amount_filter,
    )

    # Filter 4
    public_tender_filter = amount_filter[
        amount_filter[
            "tipoprocesoseleccion_conv"
        ]
        .astype(str)
        .str.contains(
            "LICITACIÓN PÚBLICA",
            case=False,
            na=False,
            regex=False,
        )
    ].copy()

    add_stage(
        "Filter 4",
        (
            "Selection procedure = "
            "'Licitación Pública'"
        ),
        public_tender_filter,
    )

    # Filter 5
    exclusion_filter = (
        public_tender_filter[
            ~public_tender_filter[
                "descripcion_proceso_conv"
            ]
            .astype(str)
            .str.contains(
                EXCLUSION_KEYWORDS,
                case=False,
                na=False,
                regex=True,
            )
        ]
        .copy()
    )

    add_stage(
        "Filter 5",
        "Exclusion criteria",
        exclusion_filter,
    )

    # Filter 6
    filtered = (
        exclusion_filter
        .drop_duplicates(
            subset=[
                "codigoconvocatoria"
            ],
            keep="first",
        )
        .copy()
    )

    add_stage(
        "Filter 6",
        "Unique procurement procedures",
        filtered,
    )

    # --------------------------------------------------------
    # 7. CALCULATE TIME VARIABLES
    # --------------------------------------------------------

    log(
        "[7] Calculating award-time "
        "variables..."
    )

    filtered[
        "fecha_convocatoria_conv"
    ] = pd.to_datetime(
        filtered[
            "fecha_convocatoria_conv"
        ],
        errors="coerce",
        dayfirst=True,
    )

    filtered[
        "fechaintegracionbases"
    ] = pd.to_datetime(
        filtered[
            "fechaintegracionbases"
        ],
        errors="coerce",
        dayfirst=True,
    )

    filtered[
        "fecha_buenapro"
    ] = pd.to_datetime(
        filtered[
            "fecha_buenapro"
        ],
        errors="coerce",
        dayfirst=True,
    )

    filtered[
        "duracion_etapa_consultas_dias"
    ] = (
        filtered["fechaintegracionbases"]
        - filtered[
            "fecha_convocatoria_conv"
        ]
    ).dt.days

    filtered[
        "duracion_etapa_evaluacion_dias"
    ] = (
        filtered["fecha_buenapro"]
        - filtered["fechaintegracionbases"]
    ).dt.days

    filtered[
        "plazo_total_adjudicacion_dias"
    ] = (
        filtered["fecha_buenapro"]
        - filtered[
            "fecha_convocatoria_conv"
        ]
    ).dt.days

    log(
        "  Award-time variables calculated."
    )

    # --------------------------------------------------------
    # 8. PREPARE FINAL DATASET
    # --------------------------------------------------------

    log()
    log("[8] Preparing final dataset...")

    final_columns = [
        "codigoconvocatoria",
        "descripcion_proceso_conv",
        "montoreferencial",
        "monto_adjudicado_item_soles",
        "fecha_convocatoria_conv",
        "fechaintegracionbases",
        "fecha_buenapro",
        "duracion_etapa_consultas_dias",
        "duracion_etapa_evaluacion_dias",
        "plazo_total_adjudicacion_dias",
    ]

    require_columns(
        filtered,
        final_columns,
        "Linked and filtered dataset",
    )

    final_dataset = filtered[
        final_columns
    ].copy()

    final_dataset.rename(
        columns={
            "codigoconvocatoria":
                "procedure_code",
            "descripcion_proceso_conv":
                "procedure_description",
            "montoreferencial":
                "reference_amount",
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
        inplace=True,
    )

    final_dataset[
        "queries_observations_count"
    ] = pd.NA

    final_dataset.sort_values(
        by="procedure_code",
        inplace=True,
    )

    final_dataset.reset_index(
        drop=True,
        inplace=True,
    )

    # --------------------------------------------------------
    # 9. BUILD AUDIT TABLES
    # --------------------------------------------------------

    source_audit = pd.DataFrame(
        [
            {
                "dataset":
                    "Procurement notices",
                "records":
                    notice_counts["records"],
                "procedure_item_keys":
                    notice_counts[
                        "procedure_item_keys"
                    ],
                "unique_procedures":
                    notice_counts[
                        "unique_procedures"
                    ],
            },
            {
                "dataset":
                    "Contract awards",
                "records":
                    award_counts["records"],
                "procedure_item_keys":
                    award_counts[
                        "procedure_item_keys"
                    ],
                "unique_procedures":
                    award_counts[
                        "unique_procedures"
                    ],
            },
            {
                "dataset":
                    "Linked dataset",
                "records":
                    merged_counts["records"],
                "procedure_item_keys":
                    merged_counts[
                        "procedure_item_keys"
                    ],
                "unique_procedures":
                    merged_counts[
                        "unique_procedures"
                    ],
            },
        ]
    )

    selection_flow_df = pd.DataFrame(
        selection_flow
    )

    # --------------------------------------------------------
    # 10. BUILD METHODOLOGICAL FUNNEL
    # --------------------------------------------------------

    methodological_funnel = pd.DataFrame(
        [
            {
                "stage":
                    "Analytical population",
                "selection_criterion":
                    (
                        "Linked procurement procedures, "
                        "2020-2025"
                    ),
                "unique_procedures":
                    merged_counts[
                        "unique_procedures"
                    ],
            },
            {
                "stage":
                    "Filter 1",
                "selection_criterion":
                    "Contractual object = Works",
                "unique_procedures":
                    count_unique_procedures(
                        works_filter
                    ),
            },
            {
                "stage":
                    "Filter 2",
                "selection_criterion":
                    (
                        "Road-infrastructure "
                        "keywords"
                    ),
                "unique_procedures":
                    count_unique_procedures(
                        road_filter
                    ),
            },
            {
                "stage":
                    "Filter 3",
                "selection_criterion":
                    (
                        "Reference amount "
                        "> PEN 25,000,000"
                    ),
                "unique_procedures":
                    count_unique_procedures(
                        amount_filter
                    ),
            },
            {
                "stage":
                    "Filter 4",
                "selection_criterion":
                    (
                        "Selection procedure = "
                        "Public Tender"
                    ),
                "unique_procedures":
                    count_unique_procedures(
                        public_tender_filter
                    ),
            },
            {
                "stage":
                    "Filter 5",
                "selection_criterion":
                    "Exclusion criteria",
                "unique_procedures":
                    count_unique_procedures(
                        exclusion_filter
                    ),
            },
            {
                "stage":
                    "Final sample",
                "selection_criterion":
                    (
                        "Unique procurement "
                        "procedures"
                    ),
                "unique_procedures":
                    count_unique_procedures(
                        filtered
                    ),
            },
        ]
    )

    # --------------------------------------------------------
    # 11. SAVE OUTPUTS
    # --------------------------------------------------------

    log()
    log(
        "[9] Saving reproducible outputs..."
    )

    final_dataset.to_excel(
        SAMPLE_FILE,
        index=False,
    )

    with pd.ExcelWriter(
        FLOW_FILE,
        engine="openpyxl",
    ) as writer:

        methodological_funnel.to_excel(
            writer,
            sheet_name="methodological_funnel",
            index=False,
        )

        selection_flow_df.to_excel(
            writer,
            sheet_name="selection_flow",
            index=False,
        )

        source_audit.to_excel(
            writer,
            sheet_name="source_audit",
            index=False,
        )

        linkage_audit.to_excel(
            writer,
            sheet_name="linkage_audit",
            index=False,
        )

        source_summary_df.to_excel(
            writer,
            sheet_name="source_files",
            index=False,
        )

        notice_only_keys.to_excel(
            writer,
            sheet_name="notice_only_keys",
            index=False,
        )

        award_only_keys.to_excel(
            writer,
            sheet_name="award_only_keys",
            index=False,
        )

    log(
        f"  Dataset: {SAMPLE_FILE.name}"
    )

    log(
        f"  Audit workbook: "
        f"{FLOW_FILE.name}"
    )

    # --------------------------------------------------------
    # 12. FINAL SUMMARY
    # --------------------------------------------------------

    log()
    log("=" * 78)
    log("SOURCE AND LINKAGE AUDIT")
    log("=" * 78)

    log(
        f"{'Dataset':<28}"
        f"{'Records':>14}"
        f"{'Proc-item keys':>18}"
        f"{'Procedures':>16}"
    )

    log("-" * 78)

    for _, row in source_audit.iterrows():
        log(
            f"{row['dataset']:<28}"
            f"{int(row['records']):>14,}"
            f"{int(row['procedure_item_keys']):>18,}"
            f"{int(row['unique_procedures']):>16,}"
        )

    log()
    log(
        "Matched procedure-item keys: "
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

    log()
    log("=" * 78)
    log("METHODOLOGICAL FUNNEL")
    log("=" * 78)

    log(
        f"{'Stage':<24}"
        f"{'Unique procedures':>20}"
    )

    log("-" * 44)

    for _, row in (
        methodological_funnel.iterrows()
    ):
        log(
            f"{row['stage']:<24}"
            f"{int(row['unique_procedures']):>20,}"
        )

    log()
    log("=" * 78)
    log("SAMPLE-SELECTION AUDIT")
    log("=" * 78)

    log(
        f"{'Stage':<12}"
        f"{'Records':>14}"
        f"{'Proc-item keys':>18}"
        f"{'Procedures':>16}"
    )

    log("-" * 78)

    for stage in selection_flow:
        log(
            f"{stage['stage']:<12}"
            f"{stage['records']:>14,}"
            f"{stage['procedure_item_keys']:>18,}"
            f"{stage['unique_procedures']:>16,}"
        )

    log()
    log("=" * 78)

    log(
        f"FINAL SAMPLE: "
        f"{len(final_dataset):,} "
        "unique procedures"
    )

    log("=" * 78)

    save_log()


# ============================================================
# EXECUTION
# ============================================================

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
