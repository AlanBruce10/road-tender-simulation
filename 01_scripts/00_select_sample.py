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
selection_flow = []


def log(message=""):
    text = str(message)
    print(text)
    log_lines.append(text)


def save_log():
    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8"
    )


def add_stage(name, count):
    selection_flow.append(
        {
            "stage": name,
            "count": int(count)
        }
    )
    log(f"  -> {name}: {count:,}")


# ============================================================
# SOURCE FILE DISCOVERY
# ============================================================

def find_source_file(prefix, year):
    pattern = f"{prefix}{year}_*.xlsx"
    matches = sorted(DATA_DIR.glob(pattern))

    if not matches:
        raise FileNotFoundError(
            f"No source file found for pattern: {pattern}"
        )

    if len(matches) > 1:
        names = ", ".join(file.name for file in matches)
        raise RuntimeError(
            f"Multiple source files found for {year}: {names}"
        )

    return matches[0]


def load_source_data():
    procurement_notices = []
    contract_awards = []

    log("[1] Reading OECE-SEACE source datasets...")
    log()

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

        procurement_notices.append(notice)
        contract_awards.append(award)

        log(
            f"  {year}: "
            f"procurement notices={len(notice):,} | "
            f"contract awards={len(award):,}"
        )

    procurement_notices = pd.concat(
        procurement_notices,
        ignore_index=True
    )

    contract_awards = pd.concat(
        contract_awards,
        ignore_index=True
    )

    log()
    log(
        "  TOTAL PROCUREMENT NOTICES: "
        f"{len(procurement_notices):,}"
    )
    log(
        "  TOTAL CONTRACT AWARDS: "
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

    return procurement_notices, contract_awards


# ============================================================
# SAMPLE SELECTION
# ============================================================

def select_sample(procurement_notices, contract_awards):

    log()
    log(
        "[2] Merging datasets by "
        "codigoconvocatoria + n_item..."
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

    log()
    log("[3] Filtering contractual object = 'Obra'...")

    if "objetocontractual_conv" not in merged.columns:
        raise KeyError(
            "Required column not found: objetocontractual_conv"
        )

    works = merged[
        merged["objetocontractual_conv"]
        .astype("string")
        .str.contains(
            "OBRA",
            case=False,
            na=False
        )
    ].copy()

    log(f"  Result: {len(works):,}")

    add_stage(
        "Filter 1: Contractual object = 'Obra'",
        len(works)
    )

    log()
    log("[4] Filtering road-infrastructure keywords...")

    roads = works[
        works["descripcion_proceso_conv"]
        .astype("string")
        .str.contains(
            ROAD_KEYWORDS,
            case=False,
            na=False,
            regex=True
        )
    ].copy()

    log(f"  Result: {len(roads):,}")

    add_stage(
        "Filter 2: Road-infrastructure keywords",
        len(roads)
    )

    log()
    log(
        "[5] Filtering reference amount "
        "> PEN 25,000,000..."
    )

    roads["monto_referencial_item"] = pd.to_numeric(
        roads["monto_referencial_item"],
        errors="coerce"
    )

    amount = roads[
        roads["monto_referencial_item"]
        > MIN_REFERENCE_AMOUNT
    ].copy()

    log(f"  Result: {len(amount):,}")

    add_stage(
        "Filter 3: Reference amount > PEN 25,000,000",
        len(amount)
    )

    log()
    log(
        "[6] Filtering selection procedure = "
        "'Licitación Pública'..."
    )

    public_tenders = amount[
        amount["tipoprocesoseleccion_conv"]
        .astype("string")
        .str.contains(
            "LICITACIÓN PÚBLICA",
            case=False,
            na=False
        )
    ].copy()

    log(f"  Result: {len(public_tenders):,}")

    add_stage(
        "Filter 4: Selection procedure = 'Licitación Pública'",
        len(public_tenders)
    )

    log()
    log("[7] Applying exclusion criteria...")

    eligible = public_tenders[
        ~public_tenders["descripcion_proceso_conv"]
        .astype("string")
        .str.contains(
            EXCLUSION_KEYWORDS,
            case=False,
            na=False,
            regex=True
        )
    ].copy()

    log(f"  Result: {len(eligible):,}")

    add_stage(
        "Filter 5: Exclusion criteria",
        len(eligible)
    )

    log()
    log(
        "[8] Removing duplicate procurement procedures..."
    )

    sample = eligible.drop_duplicates(
        subset=["codigoconvocatoria"],
        keep="first"
    ).copy()

    log(f"  Result: {len(sample):,}")

    add_stage(
        "Filter 6: Unique procurement procedures",
        len(sample)
    )

    return sample


# ============================================================
# AWARD-TIME VARIABLES
# ============================================================

def calculate_award_times(sample):

    log()
    log("[9] Calculating award-time variables...")

    date_columns = [
        "fecha_convocatoria_conv",
        "fechaintegracionbases",
        "fecha_buenapro"
    ]

    for column in date_columns:
        sample[column] = pd.to_datetime(
            sample[column],
            errors="coerce",
            dayfirst=True
        )

    sample["duracion_etapa_consultas_dias"] = (
        sample["fechaintegracionbases"]
        - sample["fecha_convocatoria_conv"]
    ).dt.days

    sample["duracion_etapa_evaluacion_dias"] = (
        sample["fecha_buenapro"]
        - sample["fechaintegracionbases"]
    ).dt.days

    sample["plazo_total_adjudicacion_dias"] = (
        sample["fecha_buenapro"]
        - sample["fecha_convocatoria_conv"]
    ).dt.days

    log("  Award-time variables calculated.")

    return sample


# ============================================================
# OUTPUT DATASET
# ============================================================

def prepare_output(sample):

    log()
    log("[10] Preparing output dataset...")

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
        "plazo_total_adjudicacion_dias"
    ]

    missing = [
        column
        for column in final_columns
        if column not in sample.columns
    ]

    if missing:
        raise KeyError(
            "Required output columns not found: "
            + ", ".join(missing)
        )

    output = sample[final_columns].copy()

    output.rename(
        columns={
            "descripcion_proceso_conv":
                "descripcion_proceso",
            "fecha_convocatoria_conv":
                "fecha_convocatoria"
        },
        inplace=True
    )

    output["cant_consultas_observaciones"] = pd.NA

    return output


# ============================================================
# PILOT VERIFICATION
# ============================================================

def verify_pilot(final_dataset):

    log()
    log("[11] Running 2020 pilot verification...")

    pilot_codes = [
        664728,
        638506,
        676061,
        696209,
        654278,
        654914,
        653257,
        645854,
        693199,
        619504,
        678446,
        686773,
        644853,
        619659
    ]

    present_codes = set(
        final_dataset.loc[
            final_dataset["codigoconvocatoria"]
            .isin(pilot_codes),
            "codigoconvocatoria"
        ].tolist()
    )

    missing_codes = [
        code
        for code in pilot_codes
        if code not in present_codes
    ]

    log(
        f"  Pilot codes found: "
        f"{len(present_codes)} of {len(pilot_codes)}"
    )

    if missing_codes:
        log(
            "  Pilot codes not found: "
            + ", ".join(map(str, missing_codes))
        )


# ============================================================
# SAVE RESULTS
# ============================================================

def save_results(final_dataset):

    log()
    log("[12] Saving reproducible outputs...")

    final_dataset.to_excel(
        SAMPLE_FILE,
        index=False
    )

    flow_dataframe = pd.DataFrame(selection_flow)

    flow_dataframe.to_excel(
        FLOW_FILE,
        index=False
    )

    log(f"  Dataset: {SAMPLE_FILE.name}")
    log(f"  Selection flow: {FLOW_FILE.name}")


# ============================================================
# MAIN
# ============================================================

def main():

    log("=" * 70)
    log(" SAMPLE SELECTION - ROAD INFRASTRUCTURE TENDERS")
    log("=" * 70)
    log("Source: OECE-SEACE Open Data Portal")
    log("Study period: 2020-2025")
    log()

    procurement_notices, contract_awards = (
        load_source_data()
    )

    sample = select_sample(
        procurement_notices,
        contract_awards
    )

    sample = calculate_award_times(sample)

    final_dataset = prepare_output(sample)

    verify_pilot(final_dataset)

    save_results(final_dataset)

    log()
    log("=" * 70)
    log(" SAMPLE-SELECTION FLOW")
    log("=" * 70)

    for stage in selection_flow:
        log(
            f"  {stage['stage']}: "
            f"{stage['count']:,}"
        )

    log()
    log("=" * 70)
    log(
        f" FINAL SAMPLE: "
        f"{len(final_dataset):,} procedures"
    )
    log("=" * 70)

    save_log()


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        log()
        log("=" * 70)
        log("EXECUTION FAILED")
        log("=" * 70)
        log(
            f"{type(error).__name__}: {error}"
        )

        save_log()
        sys.exit(1)
