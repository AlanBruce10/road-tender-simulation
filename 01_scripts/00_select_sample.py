import pandas as pd
import numpy as np
from pathlib import Path

# ============================================================
# PROJECT PATHS
# ============================================================
# The script automatically locates the repository root.
# Expected repository structure:
#
# road-tender-simulation/
# ├── 00_data/
# ├── 01_scripts/
# ├── 02_results/
# ├── 03_logs/
# └── 04_screenshots/
#
# Raw OECE-SEACE Excel files must be manually downloaded and
# placed in 00_data/. See 00_data/README.md for instructions.

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DATA = PROJECT_ROOT / "00_data"
RESULTS = PROJECT_ROOT / "02_results"

RESULTS.mkdir(parents=True, exist_ok=True)

EXCEL_BASE = RESULTS / "BASE_FINAL_137_PROCESOS.xlsx"
EXCEL_EMBUDO = RESULTS / "flujo_seleccion_muestra.xlsx"


def log(message):
    print(message)


selection_flow = []


def add_stage(name, count):
    selection_flow.append({"stage": name, "count": int(count)})
    log(f"  -> {name}: {count:,}")


def main():
    log("=" * 70)
    log(" SAMPLE GENERATION - ROAD INFRASTRUCTURE TENDERS")
    log("=" * 70)

    log("\n[1] Reading OECE-SEACE files for 2020-2025...")

    procurement_notices = pd.DataFrame()
    contract_awards = pd.DataFrame()

    for year in range(2020, 2026):
        try:
            notice = pd.read_excel(
                RAW_DATA / f"convocatoria_{year}.xlsx"
            )
            award = pd.read_excel(
                RAW_DATA / f"adjudicacion_{year}.xlsx"
            )

            procurement_notices = pd.concat(
                [procurement_notices, notice],
                ignore_index=True
            )

            contract_awards = pd.concat(
                [contract_awards, award],
                ignore_index=True
            )

            log(
                f"  {year}: "
                f"procurement notices={len(notice):,}, "
                f"contract awards={len(award):,}"
            )

        except Exception as e:
            log(f"  {year}: ERROR - {e}")

    log(
        f"\n  TOTAL PROCUREMENT NOTICES: "
        f"{len(procurement_notices):,}"
    )

    log(
        f"  TOTAL CONTRACT AWARDS: "
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

    log(
        "\n[2] Merging datasets by "
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

    log("\n[3] Filtering contractual object = 'Obra'...")

    if "objetocontractual_conv" in merged.columns:
        works_filter = merged[
            merged["objetocontractual_conv"]
            .str.upper()
            .str.contains("OBRA", na=False)
        ].copy()
    else:
        works_filter = merged.copy()

    log(f"  Result: {len(works_filter):,}")

    add_stage(
        "Filter 1: Contractual object = 'Obra'",
        len(works_filter)
    )

    log(
        "\n[4] Filtering road infrastructure "
        "(keywords)..."
    )

    road_keywords = (
        "VIAL|CARRETERA|PUENTE|CAMINO|PAVIMENT|"
        "ASFALTO|TRÁNSITO|TRANSITO|AUTOPISTA"
    )

    road_filter = works_filter[
        works_filter["descripcion_proceso_conv"]
        .str.contains(
            road_keywords,
            case=False,
            na=False
        )
    ].copy()

    log(f"  Result: {len(road_filter):,}")

    add_stage(
        "Filter 2: Description contains road-infrastructure keywords",
        len(road_filter)
    )

    log(
        "\n[5] Filtering reference amount "
        "> PEN 25 million..."
    )

    amount_filter = road_filter[
        road_filter["monto_referencial_item"] > 25000000
    ].copy()

    log(f"  Result: {len(amount_filter):,}")

    add_stage(
        "Filter 3: Reference amount > PEN 25,000,000",
        len(amount_filter)
    )

    log(
        "\n[6] Filtering selection procedure = "
        "Licitacion Publica..."
    )

    public_tender_filter = amount_filter[
        amount_filter["tipoprocesoseleccion_conv"]
        .str.contains(
            "LICITACIÓN PÚBLICA",
            case=False,
            na=False
        )
    ].copy()

    log(f"  Result: {len(public_tender_filter):,}")

    add_stage(
        "Filter 4: Selection procedure = 'Licitacion Publica'",
        len(public_tender_filter)
    )

    log("\n[7] Applying exclusion criteria...")

    exclusion_keywords = (
        "AGUA POTABLE|ALCANTARILLADO|SALUD|HOSPITAL|"
        "ESTABLECIMIENTO DE SALUD|REDES COMPLEMENTARIAS|"
        "MURO DE PROTECCIÓN|DRENAJE|FLUVIAL|"
        "ADQUISICION|ADQUISICIÓN|PRESA|IRRIGACIÓN|"
        "PUENTE PEATONAL"
    )

    exclusion_filter = public_tender_filter[
        ~public_tender_filter[
            "descripcion_proceso_conv"
        ].str.contains(
            exclusion_keywords,
            case=False,
            na=False
        )
    ].copy()

    log(f"  Result: {len(exclusion_filter):,}")

    add_stage(
        "Filter 5: Exclusion criteria",
        len(exclusion_filter)
    )

    log(
        "\n[8] Removing duplicates by "
        "procurement procedure code..."
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

    log("\n[9] Calculating award-time variables...")

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

    log("\n[10] Preparing final columns...")

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

    final_dataset = filtered[final_columns].copy()

    final_dataset.rename(
        columns={
            "descripcion_proceso_conv":
                "descripcion_proceso",
            "fecha_convocatoria_conv":
                "fecha_convocatoria"
        },
        inplace=True
    )

    final_dataset["cant_consultas_observaciones"] = None

    log(
        f"\n[11] Saving base dataset: "
        f"{EXCEL_BASE.name}"
    )

    final_dataset.to_excel(
        EXCEL_BASE,
        index=False
    )

    log(f"  Saved: {EXCEL_BASE}")

    log("\n[12] Saving sample-selection flow...")

    flow_dataframe = pd.DataFrame(selection_flow)

    flow_dataframe.to_excel(
        EXCEL_EMBUDO,
        index=False
    )

    log(f"  Saved: {EXCEL_EMBUDO}")

    log("\n[13] Running 2020 pilot verification...")

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

    present = final_dataset[
        final_dataset[
            "codigoconvocatoria"
        ].isin(pilot_codes)
    ]

    log(
        f"  Pilot codes found: "
        f"{len(present)} of 14"
    )

    log("\n" + "=" * 70)
    log(" SAMPLE-SELECTION FLOW")
    log("=" * 70)

    for stage in selection_flow:
        log(
            f"  {stage['stage']}: "
            f"{stage['count']:,}"
        )

    log("\n" + "=" * 70)

    log(
        f" FINAL SAMPLE: "
        f"{len(final_dataset)} procedures"
    )

    log("=" * 70)


if __name__ == "__main__":
    main()
