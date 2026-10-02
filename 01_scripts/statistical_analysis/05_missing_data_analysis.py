from pathlib import Path
import sys
import logging

import numpy as np
import pandas as pd
from scipy import stats


# =============================================================================
# CONFIGURATION
# =============================================================================

EXPECTED_SAMPLE_SIZE = 137

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]

INPUT_FILE = PROJECT_ROOT / "02_results" / "03_1_integrated_dataset.xlsx"

RESULTS_DIR = PROJECT_ROOT / "02_results" / "statistical_analysis"
LOGS_DIR = PROJECT_ROOT / "03_logs" / "statistical_analysis"

OUTPUT_FILE = RESULTS_DIR / "05_1_missing_data_analysis.xlsx"
LOG_FILE = LOGS_DIR / "05_missing_data_analysis.log"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("missing_data_analysis")
logger.setLevel(logging.INFO)
logger.handlers.clear()

formatter = logging.Formatter("%(message)s")

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(
    LOG_FILE,
    mode="w",
    encoding="utf-8"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def log(message=""):
    logger.info(message)


# =============================================================================
# AUXILIARY FUNCTIONS
# =============================================================================

def separator():
    log("=" * 78)


def normalize_code(series):
    return pd.to_numeric(series, errors="raise").astype("int64")


def safe_mannwhitney(group_complete, group_missing):
    """
    Non-parametric comparison between procedures with available information
    and procedures with missing information.
    """
    x = pd.to_numeric(group_complete, errors="coerce").dropna()
    y = pd.to_numeric(group_missing, errors="coerce").dropna()

    if len(x) == 0 or len(y) == 0:
        return np.nan, np.nan

    result = stats.mannwhitneyu(
        x,
        y,
        alternative="two-sided"
    )

    return float(result.statistic), float(result.pvalue)


def rank_biserial_effect(group_complete, group_missing):
    """
    Rank-biserial correlation derived from the Mann-Whitney U statistic.

    Sign convention:
        positive -> values tend to be larger in the complete-data group
        negative -> values tend to be larger in the missing-data group
    """
    x = pd.to_numeric(group_complete, errors="coerce").dropna()
    y = pd.to_numeric(group_missing, errors="coerce").dropna()

    if len(x) == 0 or len(y) == 0:
        return np.nan

    u = stats.mannwhitneyu(
        x,
        y,
        alternative="two-sided"
    ).statistic

    return float((2 * u) / (len(x) * len(y)) - 1)


def compare_numeric_variable(df, variable, missing_indicator):
    complete = df.loc[~df[missing_indicator], variable]
    missing = df.loc[df[missing_indicator], variable]

    complete_clean = pd.to_numeric(
        complete,
        errors="coerce"
    ).dropna()

    missing_clean = pd.to_numeric(
        missing,
        errors="coerce"
    ).dropna()

    u_stat, p_value = safe_mannwhitney(
        complete_clean,
        missing_clean
    )

    effect = rank_biserial_effect(
        complete_clean,
        missing_clean
    )

    return {
        "missingness_definition": missing_indicator,
        "variable": variable,

        "complete_n": len(complete_clean),
        "missing_group_n": len(missing_clean),

        "complete_mean": (
            complete_clean.mean()
            if len(complete_clean) else np.nan
        ),
        "missing_group_mean": (
            missing_clean.mean()
            if len(missing_clean) else np.nan
        ),

        "complete_median": (
            complete_clean.median()
            if len(complete_clean) else np.nan
        ),
        "missing_group_median": (
            missing_clean.median()
            if len(missing_clean) else np.nan
        ),

        "complete_std": (
            complete_clean.std(ddof=1)
            if len(complete_clean) > 1 else np.nan
        ),
        "missing_group_std": (
            missing_clean.std(ddof=1)
            if len(missing_clean) > 1 else np.nan
        ),

        "mann_whitney_u": u_stat,
        "p_value": p_value,
        "rank_biserial_effect": effect,
    }


# =============================================================================
# MAIN
# =============================================================================

def main():

    separator()
    log("MISSING-DATA ANALYSIS - ROAD INFRASTRUCTURE TENDERS")
    separator()
    log("Input: Script 03 integrated analytical dataset")
    log(
        "Purpose: Diagnose whether temporal-data availability is "
        "systematically associated with observed procedure characteristics"
    )
    log()

    # -------------------------------------------------------------------------
    # 1. Validate input
    # -------------------------------------------------------------------------

    log("[1] Validating Script 03 input...")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    log(f"  Input file: {INPUT_FILE.name}")
    log("  Input file found.")
    log()

    # -------------------------------------------------------------------------
    # 2. Read dataset
    # -------------------------------------------------------------------------

    log("[2] Reading analytical dataset...")

    df = pd.read_excel(INPUT_FILE)

    log(f"  Rows: {len(df)}")
    log(f"  Columns: {len(df.columns)}")
    log()

    # -------------------------------------------------------------------------
    # 3. Validate analytical contract
    # -------------------------------------------------------------------------

    log("[3] Validating analytical contract...")

    required_columns = [
        "procedure_code",
        "reference_amount",
        "awarded_amount_pen",
        "notice_date",
        "integrated_terms_date",
        "award_date",
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
        "total_award_time_days",
        "queries_observations_count",
        "pages",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise KeyError(
            "Input dataset is missing required columns: "
            + ", ".join(missing_columns)
        )

    if len(df) != EXPECTED_SAMPLE_SIZE:
        raise ValueError(
            f"Expected {EXPECTED_SAMPLE_SIZE} procedures, "
            f"found {len(df)}."
        )

    df["procedure_code"] = normalize_code(
        df["procedure_code"]
    )

    if df["procedure_code"].duplicated().any():
        raise ValueError(
            "Duplicate procedure_code values detected."
        )

    log(
        f"  Expected analytical sample verified: "
        f"{EXPECTED_SAMPLE_SIZE}"
    )
    log("  Required columns verified.")
    log("  procedure_code uniqueness verified.")
    log()

    # -------------------------------------------------------------------------
    # 4. Create missingness indicators
    # -------------------------------------------------------------------------

    log("[4] Creating missingness indicators...")

    df["missing_integrated_terms_date"] = (
        df["integrated_terms_date"].isna()
    )

    df["missing_award_date"] = (
        df["award_date"].isna()
    )

    df["missing_stage_decomposition"] = (
        df[
            [
                "query_stage_duration_days",
                "evaluation_stage_duration_days",
            ]
        ]
        .isna()
        .any(axis=1)
    )

    df["missing_total_award_time"] = (
        df["total_award_time_days"].isna()
    )

    missing_integration = int(
        df["missing_integrated_terms_date"].sum()
    )

    missing_award = int(
        df["missing_award_date"].sum()
    )

    missing_decomposition = int(
        df["missing_stage_decomposition"].sum()
    )

    missing_total = int(
        df["missing_total_award_time"].sum()
    )

    log(
        f"  Missing integrated-terms dates: "
        f"{missing_integration}"
    )
    log(
        f"  Missing award dates: "
        f"{missing_award}"
    )
    log(
        f"  Missing stage decompositions: "
        f"{missing_decomposition}"
    )
    log(
        f"  Missing total award times: "
        f"{missing_total}"
    )
    log()

    # -------------------------------------------------------------------------
    # 5. Extract year
    # -------------------------------------------------------------------------

    log("[5] Deriving procurement-notice year...")

    df["notice_date"] = pd.to_datetime(
        df["notice_date"],
        errors="coerce"
    )

    df["notice_year"] = df["notice_date"].dt.year

    if df["notice_year"].isna().any():
        raise ValueError(
            "notice_year could not be derived for all procedures."
        )

    df["notice_year"] = df["notice_year"].astype(int)

    year_counts = (
        df.groupby(
            [
                "notice_year",
                "missing_integrated_terms_date"
            ]
        )
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    if False not in year_counts.columns:
        year_counts[False] = 0

    if True not in year_counts.columns:
        year_counts[True] = 0

    year_counts = year_counts.rename(
        columns={
            False: "integration_available",
            True: "integration_missing",
        }
    )

    year_counts["total"] = (
        year_counts["integration_available"]
        + year_counts["integration_missing"]
    )

    year_counts["missing_percent"] = (
        100
        * year_counts["integration_missing"]
        / year_counts["total"]
    )

    year_counts = year_counts[
        [
            "notice_year",
            "integration_available",
            "integration_missing",
            "total",
            "missing_percent",
        ]
    ]

    log("  Missing integrated-terms dates by notice year:")

    for _, row in year_counts.iterrows():
        log(
            f"    {int(row['notice_year'])}: "
            f"{int(row['integration_missing'])}/"
            f"{int(row['total'])} missing "
            f"({row['missing_percent']:.2f}%)"
        )

    log()

    # -------------------------------------------------------------------------
    # 6. Compare observed characteristics
    # -------------------------------------------------------------------------

    log(
        "[6] Comparing procedures with and without "
        "integrated-terms dates..."
    )

    variables_to_compare = [
        "queries_observations_count",
        "reference_amount",
        "awarded_amount_pen",
        "total_award_time_days",
        "pages",
    ]

    comparison_rows = []

    for variable in variables_to_compare:

        result = compare_numeric_variable(
            df=df,
            variable=variable,
            missing_indicator="missing_integrated_terms_date",
        )

        comparison_rows.append(result)

        log(
            f"  {variable}: "
            f"median available="
            f"{result['complete_median']:.3f}; "
            f"median missing="
            f"{result['missing_group_median']:.3f}; "
            f"U={result['mann_whitney_u']:.3f}; "
            f"p={result['p_value']:.6g}; "
            f"rank-biserial="
            f"{result['rank_biserial_effect']:.4f}"
        )

    comparisons = pd.DataFrame(comparison_rows)

    log()
    log(
        "  NOTE: Group comparisons are diagnostic. "
        "They do not establish the mechanism causing missing data."
    )
    log()

    # -------------------------------------------------------------------------
    # 7. Year association test
    # -------------------------------------------------------------------------

    log(
        "[7] Testing association between notice year and "
        "integration-date availability..."
    )

    contingency = pd.crosstab(
        df["notice_year"],
        df["missing_integrated_terms_date"]
    )

    if contingency.shape[0] >= 2 and contingency.shape[1] == 2:

        chi2, chi_p, chi_dof, expected = stats.chi2_contingency(
            contingency
        )

        expected_below_5 = int((expected < 5).sum())
        total_expected_cells = int(expected.size)
        percent_expected_below_5 = (
            100 * expected_below_5 / total_expected_cells
        )
        chi_square_assumption_ok = (
            np.min(expected) >= 1
            and percent_expected_below_5 <= 20
        )

        year_test = pd.DataFrame(
            [
                {
                    "test": "Chi-square test of independence",
                    "variables":
                        "notice_year vs missing_integrated_terms_date",
                    "statistic": chi2,
                    "degrees_of_freedom": chi_dof,
                    "p_value": chi_p,
                    "minimum_expected_frequency":
                        float(np.min(expected)),
                    "expected_cells_below_5":
                        expected_below_5,
                    "total_expected_cells":
                        total_expected_cells,
                    "percent_expected_cells_below_5":
                        percent_expected_below_5,
                    "chi_square_assumption_ok":
                        chi_square_assumption_ok,
                }
            ]
        )

        log(f"  Chi-square: {chi2:.4f}")
        log(f"  Degrees of freedom: {chi_dof}")
        log(f"  p-value: {chi_p:.6g}")
        log(
            f"  Minimum expected frequency: "
            f"{np.min(expected):.3f}"
        )
        log(
            f"  Expected cells < 5: "
            f"{expected_below_5}/{total_expected_cells} "
            f"({percent_expected_below_5:.2f}%)"
        )

        if chi_square_assumption_ok:
            log("  Assumption audit: PASS")
        else:
            log("  Assumption audit: CAUTION")
            log(
                "  WARNING: The chi-square approximation should be "
                "interpreted cautiously because expected-frequency "
                "criteria are not fully satisfied."
            )

    else:

        year_test = pd.DataFrame(
            [
                {
                    "test": "Chi-square test of independence",
                    "variables":
                        "notice_year vs missing_integrated_terms_date",
                    "statistic": np.nan,
                    "degrees_of_freedom": np.nan,
                    "p_value": np.nan,
                    "minimum_expected_frequency": np.nan,
                    "expected_cells_below_5": np.nan,
                    "total_expected_cells": np.nan,
                    "percent_expected_cells_below_5": np.nan,
                    "chi_square_assumption_ok": False,
                }
            ]
        )

        log(
            "  Test not estimable because the contingency "
            "table lacks sufficient categories."
        )

    log()
    log(
        "  NOTE: Statistical association with missingness "
        "does not by itself identify MCAR, MAR, or MNAR."
    )
    log()

    # -------------------------------------------------------------------------
    # 8. Audit missing cases
    # -------------------------------------------------------------------------

    log("[8] Preparing missing-case audit...")

    missing_cases = df.loc[
        (
            df["missing_integrated_terms_date"]
            | df["missing_award_date"]
        ),
        [
            "procedure_code",
            "notice_year",
            "notice_date",
            "integrated_terms_date",
            "award_date",
            "queries_observations_count",
            "reference_amount",
            "awarded_amount_pen",
            "total_award_time_days",
            "pages",
            "missing_integrated_terms_date",
            "missing_award_date",
            "missing_stage_decomposition",
            "missing_total_award_time",
        ],
    ].copy()

    log(
        f"  Procedures with at least one missing "
        f"key temporal date: {len(missing_cases)}"
    )
    log()

    # -------------------------------------------------------------------------
    # 9. Build coverage summary
    # -------------------------------------------------------------------------

    log("[9] Building analytical coverage summary...")

    coverage = pd.DataFrame(
        [
            {
                "analysis": "Query/observation count",
                "available_n":
                    int(
                        df[
                            "queries_observations_count"
                        ].notna().sum()
                    ),
                "total_n": len(df),
            },
            {
                "analysis": "Total award time",
                "available_n":
                    int(
                        df[
                            "total_award_time_days"
                        ].notna().sum()
                    ),
                "total_n": len(df),
            },
            {
                "analysis": "Temporal stage decomposition",
                "available_n":
                    int(
                        (
                            df[
                                [
                                    "query_stage_duration_days",
                                    "evaluation_stage_duration_days",
                                ]
                            ]
                            .notna()
                            .all(axis=1)
                        ).sum()
                    ),
                "total_n": len(df),
            },
        ]
    )

    coverage["missing_n"] = (
        coverage["total_n"]
        - coverage["available_n"]
    )

    coverage["coverage_percent"] = (
        100
        * coverage["available_n"]
        / coverage["total_n"]
    )

    for _, row in coverage.iterrows():
        log(
            f"  {row['analysis']:<35} "
            f"{int(row['available_n'])}/"
            f"{int(row['total_n'])} "
            f"({row['coverage_percent']:.2f}%)"
        )

    log()

    # -------------------------------------------------------------------------
    # 10. Save reproducible outputs
    # -------------------------------------------------------------------------

    log("[10] Saving reproducible missing-data outputs...")

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl"
    ) as writer:

        coverage.to_excel(
            writer,
            sheet_name="analytical_coverage",
            index=False
        )

        year_counts.to_excel(
            writer,
            sheet_name="missingness_by_year",
            index=False
        )

        comparisons.to_excel(
            writer,
            sheet_name="group_comparisons",
            index=False
        )

        year_test.to_excel(
            writer,
            sheet_name="year_association_test",
            index=False
        )

        missing_cases.to_excel(
            writer,
            sheet_name="missing_cases",
            index=False
        )

    log(f"  Output workbook: {OUTPUT_FILE.name}")
    log(f"  Log file: {LOG_FILE.name}")
    log()

    # -------------------------------------------------------------------------
    # FINAL AUDIT
    # -------------------------------------------------------------------------

    separator()
    log("MISSING-DATA ANALYSIS AUDIT")
    separator()

    log(
        f"Analytical procedures:                  "
        f"{len(df)}"
    )
    log(
        f"Missing integrated-terms dates:         "
        f"{missing_integration}"
    )
    log(
        f"Missing award dates:                    "
        f"{missing_award}"
    )
    log(
        f"Available total award times:            "
        f"{df['total_award_time_days'].notna().sum()}"
    )

    available_temporal_decompositions = int(
        df[
            [
                "query_stage_duration_days",
                "evaluation_stage_duration_days",
            ]
        ]
        .notna()
        .all(axis=1)
        .sum()
    )

    log(
        f"Available temporal decompositions:      "
        f"{available_temporal_decompositions}"
    )

    log()
    log("SCIENTIFIC SCOPE")
    log(
        "- Missing observations were diagnosed, "
        "not deleted."
    )
    log(
        "- Missing temporal dates were not imputed."
    )
    log(
        "- Group comparisons are descriptive/diagnostic "
        "and do not establish causality."
    )
    log(
        "- No MCAR, MAR, or MNAR mechanism is asserted "
        "from these tests alone."
    )
    log(
        "- The chi-square test is accompanied by an explicit "
        "expected-frequency assumption audit."
    )
    log(
        "- The master analytical sample remains unchanged "
        f"at n={EXPECTED_SAMPLE_SIZE}."
    )

    log()
    separator()
    log("PIPELINE STATUS: COMPLETE")
    separator()


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        log()
        separator()
        log("PIPELINE FAILED")
        separator()
        log(f"{type(exc).__name__}: {exc}")
        raise
