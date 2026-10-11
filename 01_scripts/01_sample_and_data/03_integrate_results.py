import sys
from pathlib import Path

import pandas as pd


# =============================================================================
# PROJECT PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RESULTS_DIR = PROJECT_ROOT / "02_results"
LOGS_DIR = PROJECT_ROOT / "03_logs"

SAMPLE_FILE = RESULTS_DIR / "00_1_sample_selection.xlsx"
COUNTS_FILE = RESULTS_DIR / "02_1_query_counts.xlsx"

OUTPUT_FILE = RESULTS_DIR / "03_1_integrated_dataset.xlsx"
LOG_FILE = LOGS_DIR / "03_integrate_results.log"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


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
# VALIDATION HELPERS
# =============================================================================

def require_file(path, label):
    if not path.exists():
        raise FileNotFoundError(
            f"{label} not found: {path}"
        )


def require_columns(dataframe, required_columns, label):
    missing_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise KeyError(
            f"{label} is missing required columns: "
            + ", ".join(missing_columns)
        )


def normalize_procedure_code(series):
    numeric = pd.to_numeric(
        series,
        errors="coerce"
    )

    if numeric.isna().any():
        invalid_count = int(
            numeric.isna().sum()
        )

        raise ValueError(
            "procedure_code contains "
            f"{invalid_count} invalid or missing value(s)."
        )

    return numeric.astype("int64")


def audit_unique_codes(dataframe, label):
    duplicated = dataframe[
        dataframe["procedure_code"].duplicated(
            keep=False
        )
    ].copy()

    if not duplicated.empty:
        duplicate_codes = sorted(
            duplicated[
                "procedure_code"
            ]
            .unique()
            .tolist()
        )

        preview = ", ".join(
            str(code)
            for code in duplicate_codes[:20]
        )

        raise ValueError(
            f"{label} contains duplicate procedure_code values: "
            f"{preview}"
        )


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def main():
    log("=" * 78)
    log(
        "RESULT INTEGRATION - ROAD INFRASTRUCTURE TENDERS"
    )
    log("=" * 78)
    log(
        "Input 1: Script 00 analytical sample"
    )
    log(
        "Input 2: Script 02 query/observation counts"
    )
    log()

    # -------------------------------------------------------------------------
    # 1. Validate input files
    # -------------------------------------------------------------------------

    log("[1] Validating input files...")

    require_file(
        SAMPLE_FILE,
        "Script 00 output"
    )

    require_file(
        COUNTS_FILE,
        "Script 02 output"
    )

    log(
        f"  Script 00 input: {SAMPLE_FILE.name}"
    )

    log(
        f"  Script 02 input: {COUNTS_FILE.name}"
    )

    # -------------------------------------------------------------------------
    # 2. Read source datasets
    # -------------------------------------------------------------------------

    log()
    log("[2] Reading source datasets...")

    sample = pd.read_excel(
        SAMPLE_FILE
    )

    counts = pd.read_excel(
        COUNTS_FILE
    )

    log(
        f"  Script 00 rows: {len(sample):,}"
    )

    log(
        f"  Script 02 rows: {len(counts):,}"
    )

    # -------------------------------------------------------------------------
    # 3. Validate required columns
    # -------------------------------------------------------------------------

    log()
    log("[3] Validating required columns...")

    sample_required_columns = [
        "procedure_code",
        "procedure_description",
        "reference_amount",
        "awarded_amount_pen",
        "notice_date",
        "integrated_terms_date",
        "award_date",
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
        "total_award_time_days",
        "queries_observations_count",
    ]

    counts_required_columns = [
        "procedure_code",
        "file_name",
        "document_type",
        "queries_observations_count",
        "processing_method",
        "confidence",
        "count_status",
        "pages",
        "notes",
    ]

    require_columns(
        sample,
        sample_required_columns,
        "Script 00 output"
    )

    require_columns(
        counts,
        counts_required_columns,
        "Script 02 output"
    )

    log("  Required columns verified.")

    # -------------------------------------------------------------------------
    # 4. Normalize procedure codes
    # -------------------------------------------------------------------------

    log()
    log("[4] Normalizing procedure codes...")

    sample["procedure_code"] = (
        normalize_procedure_code(
            sample["procedure_code"]
        )
    )

    counts["procedure_code"] = (
        normalize_procedure_code(
            counts["procedure_code"]
        )
    )

    log("  procedure_code normalized to integer.")

    # -------------------------------------------------------------------------
    # 5. Audit uniqueness
    # -------------------------------------------------------------------------

    log()
    log("[5] Auditing procedure-code uniqueness...")

    audit_unique_codes(
        sample,
        "Script 00 output"
    )

    audit_unique_codes(
        counts,
        "Script 02 output"
    )

    log(
        f"  Script 00 unique procedures: "
        f"{sample['procedure_code'].nunique():,}"
    )

    log(
        f"  Script 02 unique procedures: "
        f"{counts['procedure_code'].nunique():,}"
    )

    # -------------------------------------------------------------------------
    # 6. Audit Script 02 processing status
    # -------------------------------------------------------------------------

    log()
    log("[6] Auditing Script 02 processing status...")

    status_counts = (
        counts["count_status"]
        .fillna("MISSING")
        .astype(str)
        .value_counts()
    )

    for status, count in status_counts.items():
        log(
            f"  {status}: {count:,}"
        )

    unresolved = counts[
        counts["count_status"] != "OK"
    ].copy()

    if not unresolved.empty:
        unresolved_codes = (
            unresolved["procedure_code"]
            .astype(str)
            .tolist()
        )

        raise RuntimeError(
            "Script 02 contains unresolved procedures: "
            + ", ".join(unresolved_codes[:20])
        )

    missing_counts = counts[
        counts[
            "queries_observations_count"
        ].isna()
    ].copy()

    if not missing_counts.empty:
        missing_codes = (
            missing_counts["procedure_code"]
            .astype(str)
            .tolist()
        )

        raise RuntimeError(
            "Script 02 contains missing query/observation counts: "
            + ", ".join(missing_codes[:20])
        )

    log(
        "  All Script 02 procedures have status OK "
        "and a valid count."
    )

    # -------------------------------------------------------------------------
    # 7. Audit correspondence between Script 00 and Script 02
    # -------------------------------------------------------------------------

    log()
    log("[7] Auditing procedure correspondence...")

    sample_codes = set(
        sample["procedure_code"]
    )

    count_codes = set(
        counts["procedure_code"]
    )

    matched_codes = (
        sample_codes
        & count_codes
    )

    sample_only_codes = sorted(
        sample_codes
        - count_codes
    )

    counts_only_codes = sorted(
        count_codes
        - sample_codes
    )

    log(
        f"  Procedures in Script 00: "
        f"{len(sample_codes):,}"
    )

    log(
        f"  Procedures in Script 02: "
        f"{len(count_codes):,}"
    )

    log(
        f"  Procedures present in both: "
        f"{len(matched_codes):,}"
    )

    log(
        f"  Script 00 only: "
        f"{len(sample_only_codes):,}"
    )

    log(
        f"  Script 02 only: "
        f"{len(counts_only_codes):,}"
    )

    if sample_only_codes:
        log(
            "  Script 00-only codes: "
            + ", ".join(
                map(
                    str,
                    sample_only_codes[:20]
                )
            )
        )

    if counts_only_codes:
        log(
            "  Script 02-only codes: "
            + ", ".join(
                map(
                    str,
                    counts_only_codes[:20]
                )
            )
        )

    if (
        sample_only_codes
        or counts_only_codes
    ):
        raise RuntimeError(
            "Script 00 and Script 02 do not contain "
            "the same set of procedures."
        )

    # -------------------------------------------------------------------------
    # 8. Prepare Script 02 variables for integration
    # -------------------------------------------------------------------------

    log()
    log("[8] Preparing query/observation variables...")

    counts_subset = counts[
        [
            "procedure_code",
            "file_name",
            "document_type",
            "queries_observations_count",
            "processing_method",
            "confidence",
            "count_status",
            "pages",
            "notes",
        ]
    ].copy()

    # Script 00 contains an intentionally empty placeholder column.
    # It is removed before integration so that the validated Script 02
    # measurement becomes the definitive variable.
    sample_for_merge = sample.drop(
        columns=[
            "queries_observations_count"
        ]
    ).copy()

    log(
        "  Empty Script 00 placeholder removed."
    )

    log(
        "  Script 02 count retained as the definitive "
        "queries_observations_count variable."
    )

    # -------------------------------------------------------------------------
    # 9. Integrate datasets
    # -------------------------------------------------------------------------

    log()
    log("[9] Integrating Script 00 and Script 02 outputs...")

    integrated = sample_for_merge.merge(
        counts_subset,
        on="procedure_code",
        how="left",
        validate="one_to_one",
        indicator=True
    )

    merge_status = (
        integrated["_merge"]
        .value_counts()
    )

    matched_after_merge = int(
        merge_status.get(
            "both",
            0
        )
    )

    left_only_after_merge = int(
        merge_status.get(
            "left_only",
            0
        )
    )

    right_only_after_merge = int(
        merge_status.get(
            "right_only",
            0
        )
    )

    log(
        f"  Rows after integration: "
        f"{len(integrated):,}"
    )

    log(
        f"  Matched rows: "
        f"{matched_after_merge:,}"
    )

    log(
        f"  Left-only rows: "
        f"{left_only_after_merge:,}"
    )

    log(
        f"  Right-only rows: "
        f"{right_only_after_merge:,}"
    )

    if (
        len(integrated) != len(sample)
        or matched_after_merge != len(sample)
        or left_only_after_merge != 0
        or right_only_after_merge != 0
    ):
        raise RuntimeError(
            "Integration audit failed. "
            "The final dataset is not a complete "
            "one-to-one match."
        )

    integrated.drop(
        columns=["_merge"],
        inplace=True
    )

    # -------------------------------------------------------------------------
    # 10. Validate integrated dataset
    # -------------------------------------------------------------------------

    log()
    log("[10] Validating integrated dataset...")

    if (
        integrated["procedure_code"]
        .duplicated()
        .any()
    ):
        raise RuntimeError(
            "Integrated dataset contains duplicate "
            "procedure codes."
        )

    if (
        integrated[
            "queries_observations_count"
        ]
        .isna()
        .any()
    ):
        raise RuntimeError(
            "Integrated dataset contains missing "
            "query/observation counts."
        )

    invalid_status = integrated[
        integrated["count_status"] != "OK"
    ]

    if not invalid_status.empty:
        raise RuntimeError(
            "Integrated dataset contains procedures "
            "without count_status = OK."
        )

    negative_counts = integrated[
        integrated[
            "queries_observations_count"
        ] < 0
    ]

    if not negative_counts.empty:
        raise RuntimeError(
            "Integrated dataset contains negative "
            "query/observation counts."
        )

    log(
        f"  Unique procedures: "
        f"{integrated['procedure_code'].nunique():,}"
    )

    log(
        "  Missing query/observation counts: 0"
    )

    log(
        "  Duplicate procedure codes: 0"
    )

    log(
        "  Invalid processing statuses: 0"
    )

    # -------------------------------------------------------------------------
    # 11. Save integrated dataset
    # -------------------------------------------------------------------------

    log()
    log("[11] Saving integrated dataset...")

    integrated.to_excel(
        OUTPUT_FILE,
        index=False
    )

    log(
        f"  Dataset: {OUTPUT_FILE.name}"
    )

    # -------------------------------------------------------------------------
    # 12. Final audit
    # -------------------------------------------------------------------------

    zero_counts = int(
        (
            integrated[
                "queries_observations_count"
            ] == 0
        ).sum()
    )

    positive_counts = int(
        (
            integrated[
                "queries_observations_count"
            ] > 0
        ).sum()
    )

    pliegos = int(
        (
            integrated[
                "document_type"
            ] == "PLIEGO"
        ).sum()
    )

    no_formulation_acts = int(
        (
            integrated[
                "document_type"
            ] == "ACTA_NO_FORMULACION"
        ).sum()
    )

    log()
    log("=" * 78)
    log("RESULT INTEGRATION AUDIT")
    log("=" * 78)

    log(
        f"Script 00 procedures:             "
        f"{len(sample):,}"
    )

    log(
        f"Script 02 procedures:             "
        f"{len(counts):,}"
    )

    log(
        f"Matched procedures:               "
        f"{matched_after_merge:,}"
    )

    log(
        f"Final integrated procedures:      "
        f"{len(integrated):,}"
    )

    log(
        f"Pliegos:                          "
        f"{pliegos:,}"
    )

    log(
        f"No-formulation acts:              "
        f"{no_formulation_acts:,}"
    )

    log(
        f"Positive counts:                  "
        f"{positive_counts:,}"
    )

    log(
        f"Verified zero counts:             "
        f"{zero_counts:,}"
    )

    log(
        f"Missing counts:                   "
        f"{integrated['queries_observations_count'].isna().sum():,}"
    )

    log(
        f"Duplicate procedure codes:        "
        f"{integrated['procedure_code'].duplicated().sum():,}"
    )

    log()
    log("=" * 78)
    log("PIPELINE STATUS: COMPLETE")
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
        log("PIPELINE FAILED")
        log("=" * 78)

        log(
            f"{type(error).__name__}: "
            f"{error}"
        )

        save_log()

        sys.exit(1)
