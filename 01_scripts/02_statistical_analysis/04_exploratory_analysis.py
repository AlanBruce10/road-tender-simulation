"""
04_exploratory_analysis.py
==========================

Exploratory statistical analysis of the integrated analytical dataset.

Purpose
-------
This script performs the first statistical characterization of the
analytical dataset produced by Script 03. It is intentionally diagnostic:
it does not define information-asymmetry scenarios, remove outliers,
select probability distributions, or perform stochastic simulation.

Input
-----
02_results/03_1_integrated_dataset.xlsx

Outputs
-------
02_results/statistical_analysis/
    04_1_descriptive_statistics.xlsx
    04_2_data_quality_diagnostics.xlsx
    04_3_association_analysis.xlsx

03_logs/statistical_analysis/
    04_exploratory_analysis.log

Author: Alan Bruce Hurtado Zavaleta
Research pipeline: Road Tender Simulation
"""

from pathlib import Path
from datetime import datetime
import sys
import warnings

import numpy as np
import pandas as pd

try:
    from scipy import stats
except ImportError as exc:
    raise ImportError(
        "SciPy is required for Script 04. Install it with: pip install scipy"
    ) from exc


# =============================================================================
# 1. PROJECT PATHS
# =============================================================================

SCRIPT_PATH = Path(__file__).resolve()

# Script 04 is located at:
# project_root/01_scripts/statistical_analysis/04_exploratory_analysis.py
PROJECT_ROOT = SCRIPT_PATH.parents[2]

INPUT_FILE = PROJECT_ROOT / "02_results" / "03_1_integrated_dataset.xlsx"

RESULTS_DIR = PROJECT_ROOT / "02_results" / "statistical_analysis"
LOGS_DIR = PROJECT_ROOT / "03_logs" / "statistical_analysis"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DESCRIPTIVE_FILE = RESULTS_DIR / "04_1_descriptive_statistics.xlsx"
QUALITY_FILE = RESULTS_DIR / "04_2_data_quality_diagnostics.xlsx"
ASSOCIATION_FILE = RESULTS_DIR / "04_3_association_analysis.xlsx"

LOG_FILE = LOGS_DIR / "04_exploratory_analysis.log"


# =============================================================================
# 2. ANALYTICAL CONTRACT
# =============================================================================

EXPECTED_ROWS = 137

REQUIRED_COLUMNS = [
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
    "file_name",
    "document_type",
    "queries_observations_count",
    "processing_method",
    "confidence",
    "count_status",
    "pages",
    "notes",
]

CORE_ANALYTICAL_VARIABLES = [
    "queries_observations_count",
    "query_stage_duration_days",
    "evaluation_stage_duration_days",
    "total_award_time_days",
]

ADDITIONAL_NUMERIC_VARIABLES = [
    "reference_amount",
    "awarded_amount_pen",
    "pages",
]

TIME_VARIABLES = [
    "query_stage_duration_days",
    "evaluation_stage_duration_days",
    "total_award_time_days",
]


# =============================================================================
# 3. LOGGING
# =============================================================================

LOG_LINES = []


def log(message=""):
    """Print and store a message in the reproducibility log."""
    text = str(message)
    print(text)
    LOG_LINES.append(text)


def save_log():
    """Persist log messages."""
    header = [
        "SCRIPT 04 - EXPLORATORY STATISTICAL ANALYSIS",
        f"Execution timestamp: {datetime.now().isoformat(timespec='seconds')}",
        f"Python version: {sys.version.split()[0]}",
        f"Pandas version: {pd.__version__}",
        f"NumPy version: {np.__version__}",
        f"SciPy version: {getattr(sys.modules.get('scipy'), '__version__', 'unknown')}",
        "",
    ]

    LOG_FILE.write_text(
        "\n".join(header + LOG_LINES),
        encoding="utf-8"
    )


# =============================================================================
# 4. HELPER FUNCTIONS
# =============================================================================

def safe_cv(series):
    """
    Coefficient of variation = standard deviation / mean.

    Returns NaN when the mean is zero or undefined.
    """
    x = pd.to_numeric(series, errors="coerce").dropna()

    if len(x) < 2:
        return np.nan

    mean = x.mean()

    if np.isclose(mean, 0):
        return np.nan

    return x.std(ddof=1) / mean


def descriptive_statistics(df, variables):
    """
    Calculate descriptive statistics without modifying observations.
    """
    rows = []

    for variable in variables:
        x = pd.to_numeric(df[variable], errors="coerce").dropna()

        n = len(x)
        missing = df[variable].isna().sum()

        if n == 0:
            rows.append({
                "variable": variable,
                "n": 0,
                "missing": missing,
            })
            continue

        q1 = x.quantile(0.25)
        median = x.quantile(0.50)
        q3 = x.quantile(0.75)
        iqr = q3 - q1

        rows.append({
            "variable": variable,
            "n": n,
            "missing": int(missing),
            "mean": x.mean(),
            "median": median,
            "std_dev": x.std(ddof=1) if n > 1 else np.nan,
            "variance": x.var(ddof=1) if n > 1 else np.nan,
            "coefficient_of_variation": safe_cv(x),
            "minimum": x.min(),
            "p25": q1,
            "p50": median,
            "p75": q3,
            "maximum": x.max(),
            "iqr": iqr,
            "skewness": stats.skew(
                x,
                bias=False,
                nan_policy="omit"
            ) if n >= 3 else np.nan,
            "excess_kurtosis": stats.kurtosis(
                x,
                fisher=True,
                bias=False,
                nan_policy="omit"
            ) if n >= 4 else np.nan,
        })

    return pd.DataFrame(rows)


def iqr_outlier_diagnostics(df, variables):
    """
    Flag observations outside the conventional 1.5*IQR limits.

    Important:
    This is a diagnostic only. No observation is removed.
    """
    summary_rows = []
    detail_rows = []

    for variable in variables:
        x = pd.to_numeric(df[variable], errors="coerce")

        valid = x.dropna()

        if valid.empty:
            continue

        q1 = valid.quantile(0.25)
        q3 = valid.quantile(0.75)
        iqr = q3 - q1

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        mask = (x < lower_bound) | (x > upper_bound)
        outlier_count = int(mask.fillna(False).sum())

        summary_rows.append({
            "variable": variable,
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "outlier_count": outlier_count,
            "outlier_percent": (
                100 * outlier_count / len(valid)
                if len(valid) > 0
                else np.nan
            ),
        })

        selected_columns = [
            "procedure_code",
            "procedure_description",
            variable,
        ]

        flagged = df.loc[
            mask.fillna(False),
            selected_columns
        ].copy()

        if not flagged.empty:
            flagged.insert(2, "variable", variable)
            flagged = flagged.rename(columns={variable: "observed_value"})
            flagged["lower_bound"] = lower_bound
            flagged["upper_bound"] = upper_bound

            detail_rows.append(flagged)

    summary = pd.DataFrame(summary_rows)

    if detail_rows:
        details = pd.concat(detail_rows, ignore_index=True)
    else:
        details = pd.DataFrame(
            columns=[
                "procedure_code",
                "procedure_description",
                "variable",
                "observed_value",
                "lower_bound",
                "upper_bound",
            ]
        )

    return summary, details


def normality_diagnostics(df, variables):
    """
    Perform normality diagnostics.

    Shapiro-Wilk is reported because n=137 is within a practical range
    for the test. Results are treated as diagnostics, not as automatic
    distribution-selection rules.
    """
    rows = []

    for variable in variables:
        x = pd.to_numeric(df[variable], errors="coerce").dropna()

        n = len(x)

        if n < 3:
            rows.append({
                "variable": variable,
                "n": n,
                "shapiro_w": np.nan,
                "shapiro_p_value": np.nan,
                "interpretation_alpha_0_05": "INSUFFICIENT_DATA",
            })
            continue

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            w_stat, p_value = stats.shapiro(x)

        interpretation = (
            "REJECT_NORMALITY"
            if p_value < 0.05
            else "DO_NOT_REJECT_NORMALITY"
        )

        rows.append({
            "variable": variable,
            "n": n,
            "shapiro_w": w_stat,
            "shapiro_p_value": p_value,
            "interpretation_alpha_0_05": interpretation,
        })

    return pd.DataFrame(rows)


def association_analysis(df):
    """
    Evaluate bivariate association between query/observation counts
    and each duration variable using Pearson and Spearman correlations.

    Pearson:
        linear association.

    Spearman:
        monotonic rank-based association, less dependent on normality.

    No causal interpretation is made here.
    """
    predictor = "queries_observations_count"
    rows = []

    for outcome in TIME_VARIABLES:
        pair = df[[predictor, outcome]].dropna()

        x = pair[predictor].astype(float)
        y = pair[outcome].astype(float)

        n = len(pair)

        if n < 3 or x.nunique() < 2 or y.nunique() < 2:
            rows.append({
                "predictor": predictor,
                "outcome": outcome,
                "n": n,
                "pearson_r": np.nan,
                "pearson_p_value": np.nan,
                "spearman_rho": np.nan,
                "spearman_p_value": np.nan,
            })
            continue

        pearson_r, pearson_p = stats.pearsonr(x, y)
        spearman_rho, spearman_p = stats.spearmanr(x, y)

        rows.append({
            "predictor": predictor,
            "outcome": outcome,
            "n": n,
            "pearson_r": pearson_r,
            "pearson_p_value": pearson_p,
            "spearman_rho": spearman_rho,
            "spearman_p_value": spearman_p,
        })

    return pd.DataFrame(rows)


def data_quality_summary(df):
    """Create dataset-level quality diagnostics."""
    rows = []

    rows.append({
        "check": "total_rows",
        "value": len(df),
        "status": "PASS" if len(df) == EXPECTED_ROWS else "REVIEW",
    })

    rows.append({
        "check": "unique_procedure_codes",
        "value": df["procedure_code"].nunique(),
        "status": (
            "PASS"
            if df["procedure_code"].nunique() == len(df)
            else "FAIL"
        ),
    })

    rows.append({
        "check": "duplicate_procedure_codes",
        "value": int(df["procedure_code"].duplicated().sum()),
        "status": (
            "PASS"
            if df["procedure_code"].duplicated().sum() == 0
            else "FAIL"
        ),
    })

    rows.append({
        "check": "missing_query_counts",
        "value": int(df["queries_observations_count"].isna().sum()),
        "status": (
            "PASS"
            if df["queries_observations_count"].isna().sum() == 0
            else "FAIL"
        ),
    })

    rows.append({
        "check": "negative_query_counts",
        "value": int((df["queries_observations_count"] < 0).sum()),
        "status": (
            "PASS"
            if (df["queries_observations_count"] < 0).sum() == 0
            else "FAIL"
        ),
    })

    for variable in TIME_VARIABLES:
        negative_count = int((df[variable] < 0).fillna(False).sum())

        rows.append({
            "check": f"negative_{variable}",
            "value": negative_count,
            "status": "PASS" if negative_count == 0 else "FAIL",
        })

    date_order_issue = (
        (df["integrated_terms_date"] < df["notice_date"]) |
        (df["award_date"] < df["integrated_terms_date"]) |
        (df["award_date"] < df["notice_date"])
    ).fillna(False)

    rows.append({
        "check": "chronological_order_violations",
        "value": int(date_order_issue.sum()),
        "status": "PASS" if date_order_issue.sum() == 0 else "FAIL",
    })

    invalid_status = (
        df["count_status"]
        .astype(str)
        .str.strip()
        .str.upper()
        .ne("OK")
    )

    rows.append({
        "check": "non_OK_count_status",
        "value": int(invalid_status.sum()),
        "status": "PASS" if invalid_status.sum() == 0 else "FAIL",
    })

    return pd.DataFrame(rows), date_order_issue


def missingness_table(df):
    """Summarize missingness for all variables."""
    rows = []

    for column in df.columns:
        missing = int(df[column].isna().sum())

        rows.append({
            "variable": column,
            "missing_count": missing,
            "missing_percent": 100 * missing / len(df),
        })

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# NEW: Temporal coverage audit
# -----------------------------------------------------------------------------

def temporal_coverage_audit(df):
    """
    Audit availability of dates and derived temporal variables.

    The audit is descriptive only. Missing dates are neither imputed
    nor used to remove procedures from the analytical dataset.
    """
    variables = [
        ("notice_date", "Notice date"),
        ("integrated_terms_date", "Integrated-terms date"),
        ("award_date", "Award date"),
        ("query_stage_duration_days", "Query-stage duration"),
        ("evaluation_stage_duration_days", "Evaluation-stage duration"),
        ("total_award_time_days", "Total award time"),
    ]

    coverage_rows = []

    for variable, label in variables:
        available = int(df[variable].notna().sum())
        missing = int(df[variable].isna().sum())
        total = len(df)

        coverage_rows.append({
            "variable": variable,
            "label": label,
            "available": available,
            "missing": missing,
            "total": total,
            "coverage_percent": 100 * available / total,
        })

    coverage = pd.DataFrame(coverage_rows)

    temporal_variables = [
        "integrated_terms_date",
        "notice_date",
        "award_date",
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
        "total_award_time_days",
    ]

    temporal_missing_mask = df[temporal_variables].isna().any(axis=1)

    temporal_missing_cases = df.loc[
        temporal_missing_mask,
        [
            "procedure_code",
            "procedure_description",
            "notice_date",
            "integrated_terms_date",
            "award_date",
            "query_stage_duration_days",
            "evaluation_stage_duration_days",
            "total_award_time_days",
        ],
    ].copy()

    return coverage, temporal_missing_cases


# -----------------------------------------------------------------------------
# NEW: Temporal arithmetic consistency audit
# -----------------------------------------------------------------------------

def temporal_consistency_audit(df):
    """
    Verify that derived temporal variables are arithmetically consistent
    with their source dates.

    Checks performed (only when the required fields are available):

        query_stage_duration_days      == integrated_terms_date - notice_date
        evaluation_stage_duration_days == award_date - integrated_terms_date
        total_award_time_days          == award_date - notice_date

    The audit is descriptive only. Inconsistencies are reported but
    nothing is imputed or removed.
    """
    required = [
        "procedure_code",
        "procedure_description",
        "notice_date",
        "integrated_terms_date",
        "award_date",
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
        "total_award_time_days",
    ]

    subset = df[required].copy()

    for column in ["notice_date", "integrated_terms_date", "award_date"]:
        subset[column] = pd.to_datetime(subset[column], errors="coerce")

    for column in [
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
        "total_award_time_days",
    ]:
        subset[column] = pd.to_numeric(subset[column], errors="coerce")

    expected_query = (
        subset["integrated_terms_date"] - subset["notice_date"]
    ).dt.days

    expected_evaluation = (
        subset["award_date"] - subset["integrated_terms_date"]
    ).dt.days

    expected_total = (
        subset["award_date"] - subset["notice_date"]
    ).dt.days

    query_check = (
        subset["query_stage_duration_days"].notna()
        & expected_query.notna()
    )
    evaluation_check = (
        subset["evaluation_stage_duration_days"].notna()
        & expected_evaluation.notna()
    )
    total_check = (
        subset["total_award_time_days"].notna()
        & expected_total.notna()
    )

    query_consistent = (
        query_check
        & np.isclose(
            subset["query_stage_duration_days"],
            expected_query,
            atol=0,
            equal_nan=False,
        )
    )

    evaluation_consistent = (
        evaluation_check
        & np.isclose(
            subset["evaluation_stage_duration_days"],
            expected_evaluation,
            atol=0,
            equal_nan=False,
        )
    )

    total_consistent = (
        total_check
        & np.isclose(
            subset["total_award_time_days"],
            expected_total,
            atol=0,
            equal_nan=False,
        )
    )

    complete_decomposition = (
        query_check
        & evaluation_check
        & total_check
    )

    temporal_consistency_details = subset.loc[
        complete_decomposition
    ].copy()

    def _summarize(check_mask, consistent_mask, label):
        checkable = int(check_mask.sum())
        consistent = int(consistent_mask.sum())
        inconsistent = checkable - consistent

        return {
            "check": label,
            "checkable": checkable,
            "consistent": consistent,
            "inconsistent": inconsistent,
            "status": "PASS" if inconsistent == 0 else "FAIL",
        }

    summary_rows = [
        _summarize(
            query_check,
            query_consistent,
            "query_stage_duration_days matches integrated_terms_date - notice_date",
        ),
        _summarize(
            evaluation_check,
            evaluation_consistent,
            "evaluation_stage_duration_days matches award_date - integrated_terms_date",
        ),
        _summarize(
            total_check,
            total_consistent,
            "total_award_time_days matches award_date - notice_date",
        ),
    ]

    temporal_consistency_summary = pd.DataFrame(summary_rows)

    inconsistency_mask = (
        (query_check & ~query_consistent)
        | (evaluation_check & ~evaluation_consistent)
        | (total_check & ~total_consistent)
    )

    temporal_inconsistencies = subset.loc[
        inconsistency_mask
    ].copy()

    if not temporal_inconsistencies.empty:
        temporal_inconsistencies["expected_query_stage_duration_days"] = (
            expected_query[inconsistency_mask].values
        )
        temporal_inconsistencies["expected_evaluation_stage_duration_days"] = (
            expected_evaluation[inconsistency_mask].values
        )
        temporal_inconsistencies["expected_total_award_time_days"] = (
            expected_total[inconsistency_mask].values
        )

    return (
        temporal_consistency_summary,
        temporal_consistency_details,
        temporal_inconsistencies,
    )


# =============================================================================
# 5. MAIN PIPELINE
# =============================================================================

def main():

    log("=" * 78)
    log("EXPLORATORY STATISTICAL ANALYSIS - ROAD INFRASTRUCTURE TENDERS")
    log("=" * 78)
    log("Input: Script 03 integrated analytical dataset")
    log("Purpose: Statistical diagnosis before scenario definition and simulation")
    log()

    # -------------------------------------------------------------------------
    # Step 1
    # -------------------------------------------------------------------------

    log("[1] Validating Script 03 input...")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Required input file not found: {INPUT_FILE}"
        )

    log(f"  Input file: {INPUT_FILE.name}")
    log("  Input file found.")
    log()

    # -------------------------------------------------------------------------
    # Step 2
    # -------------------------------------------------------------------------

    log("[2] Reading analytical dataset...")

    df = pd.read_excel(INPUT_FILE)

    log(f"  Rows: {len(df)}")
    log(f"  Columns: {len(df.columns)}")
    log()

    # -------------------------------------------------------------------------
    # Step 3
    # -------------------------------------------------------------------------

    log("[3] Validating analytical contract...")

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        raise KeyError(
            "Input dataset is missing required columns: "
            + ", ".join(missing_columns)
        )

    if len(df) != EXPECTED_ROWS:
        log(
            f"  WARNING: Expected {EXPECTED_ROWS} rows, "
            f"but found {len(df)}."
        )
    else:
        log(f"  Expected analytical sample verified: {EXPECTED_ROWS}")

    duplicate_codes = df["procedure_code"].duplicated().sum()

    if duplicate_codes > 0:
        raise ValueError(
            f"Duplicate procedure_code values detected: {duplicate_codes}"
        )

    log("  Required columns verified.")
    log("  procedure_code uniqueness verified.")
    log()

    # -------------------------------------------------------------------------
    # Step 4
    # -------------------------------------------------------------------------

    log("[4] Running data-quality diagnostics...")

    quality_summary, chronological_issue_mask = data_quality_summary(df)
    missingness = missingness_table(df)

    failed_checks = quality_summary[
        quality_summary["status"] == "FAIL"
    ]

    review_checks = quality_summary[
        quality_summary["status"] == "REVIEW"
    ]

    for _, row in quality_summary.iterrows():
        log(
            f"  {row['status']:<6} | "
            f"{row['check']:<45} | {row['value']}"
        )

    log()

    # -------------------------------------------------------------------------
    # Step 4A / 4B (NEW): Temporal coverage and arithmetic consistency
    # -------------------------------------------------------------------------

    log("[4A] Auditing temporal data coverage...")

    temporal_coverage, temporal_missing_cases = temporal_coverage_audit(df)

    for _, row in temporal_coverage.iterrows():
        log(
            f"  {row['label']:<35} "
            f"{int(row['available']):>3}/{int(row['total']):<3} "
            f"({row['coverage_percent']:.2f}%)"
        )

    log(
        f"  Procedures with incomplete temporal information: "
        f"{len(temporal_missing_cases)}"
    )
    log()

    log("[4B] Auditing temporal arithmetic consistency...")

    (
        temporal_consistency_summary,
        temporal_consistency_details,
        temporal_inconsistencies,
    ) = temporal_consistency_audit(df)

    for _, row in temporal_consistency_summary.iterrows():
        log(
            f"  {row['status']:<6} | "
            f"{row['check']:<50} | {row['value'] if 'value' in row else row['inconsistent']}"
        )

    log()

    # -------------------------------------------------------------------------
    # Step 5
    # -------------------------------------------------------------------------

    log("[5] Calculating descriptive statistics...")

    variables_for_description = (
        CORE_ANALYTICAL_VARIABLES
        + ADDITIONAL_NUMERIC_VARIABLES
    )

    descriptive = descriptive_statistics(
        df,
        variables_for_description
    )

    for _, row in descriptive.iterrows():
        log(
            f"  {row['variable']}: "
            f"n={int(row['n'])}, "
            f"mean={row.get('mean', np.nan):.3f}, "
            f"median={row.get('median', np.nan):.3f}"
        )

    log()

    # -------------------------------------------------------------------------
    # Step 6
    # -------------------------------------------------------------------------

    log("[6] Diagnosing potential outliers using the 1.5*IQR rule...")

    outlier_summary, outlier_details = iqr_outlier_diagnostics(
        df,
        CORE_ANALYTICAL_VARIABLES
    )

    for _, row in outlier_summary.iterrows():
        log(
            f"  {row['variable']}: "
            f"{int(row['outlier_count'])} flagged "
            f"({row['outlier_percent']:.2f}%)"
        )

    log("  NOTE: No observations were removed or modified.")
    log()

    # -------------------------------------------------------------------------
    # Step 7
    # -------------------------------------------------------------------------

    log("[7] Running normality diagnostics...")

    normality = normality_diagnostics(
        df,
        CORE_ANALYTICAL_VARIABLES
    )

    for _, row in normality.iterrows():
        log(
            f"  {row['variable']}: "
            f"W={row['shapiro_w']:.4f}, "
            f"p={row['shapiro_p_value']:.6g}, "
            f"{row['interpretation_alpha_0_05']}"
        )

    log(
        "  NOTE: Normality tests are diagnostic and do not select "
        "a probability distribution."
    )
    log()

    # -------------------------------------------------------------------------
    # Step 8
    # -------------------------------------------------------------------------

    log("[8] Evaluating bivariate associations...")

    associations = association_analysis(df)

    for _, row in associations.iterrows():
        log(
            f"  queries_observations_count vs {row['outcome']}: "
            f"Pearson r={row['pearson_r']:.4f} "
            f"(p={row['pearson_p_value']:.6g}); "
            f"Spearman rho={row['spearman_rho']:.4f} "
            f"(p={row['spearman_p_value']:.6g})"
        )

    log(
        "  NOTE: These coefficients describe association only; "
        "they do not establish causality."
    )
    log()

    # -------------------------------------------------------------------------
    # Step 9
    # -------------------------------------------------------------------------

    log("[9] Auditing document and processing metadata...")

    document_types = (
        df["document_type"]
        .fillna("MISSING")
        .astype(str)
        .value_counts(dropna=False)
        .rename_axis("document_type")
        .reset_index(name="procedures")
    )

    processing_methods = (
        df["processing_method"]
        .fillna("MISSING")
        .astype(str)
        .value_counts(dropna=False)
        .rename_axis("processing_method")
        .reset_index(name="procedures")
    )

    confidence_levels = (
        df["confidence"]
        .fillna("MISSING")
        .astype(str)
        .value_counts(dropna=False)
        .rename_axis("confidence")
        .reset_index(name="procedures")
    )

    count_statuses = (
        df["count_status"]
        .fillna("MISSING")
        .astype(str)
        .value_counts(dropna=False)
        .rename_axis("count_status")
        .reset_index(name="procedures")
    )

    log(f"  Document types: {len(document_types)} categories")
    log(f"  Processing methods: {len(processing_methods)} categories")
    log(f"  Confidence categories: {len(confidence_levels)} categories")
    log(f"  Count-status categories: {len(count_statuses)} categories")
    log()

    # -------------------------------------------------------------------------
    # Step 10
    # -------------------------------------------------------------------------

    log("[10] Saving reproducible statistical outputs...")

    # Descriptive workbook
    with pd.ExcelWriter(
        DESCRIPTIVE_FILE,
        engine="openpyxl"
    ) as writer:

        descriptive.to_excel(
            writer,
            sheet_name="descriptive_statistics",
            index=False
        )

        normality.to_excel(
            writer,
            sheet_name="normality_diagnostics",
            index=False
        )

        outlier_summary.to_excel(
            writer,
            sheet_name="outlier_summary",
            index=False
        )

        outlier_details.to_excel(
            writer,
            sheet_name="outlier_details",
            index=False
        )

    # Data-quality workbook
    with pd.ExcelWriter(
        QUALITY_FILE,
        engine="openpyxl"
    ) as writer:

        quality_summary.to_excel(
            writer,
            sheet_name="quality_checks",
            index=False
        )

        missingness.to_excel(
            writer,
            sheet_name="missingness",
            index=False
        )

        df.loc[
            chronological_issue_mask
        ].to_excel(
            writer,
            sheet_name="chronology_issues",
            index=False
        )

        document_types.to_excel(
            writer,
            sheet_name="document_types",
            index=False
        )

        processing_methods.to_excel(
            writer,
            sheet_name="processing_methods",
            index=False
        )

        confidence_levels.to_excel(
            writer,
            sheet_name="confidence_levels",
            index=False
        )

        count_statuses.to_excel(
            writer,
            sheet_name="count_status",
            index=False
        )

        temporal_coverage.to_excel(
            writer,
            sheet_name="temporal_coverage",
            index=False
        )

        temporal_missing_cases.to_excel(
            writer,
            sheet_name="temporal_missing_cases",
            index=False
        )

        temporal_consistency_summary.to_excel(
            writer,
            sheet_name="temporal_consistency",
            index=False
        )

        temporal_inconsistencies.to_excel(
            writer,
            sheet_name="temporal_inconsistencies",
            index=False
        )

    # Association workbook
    with pd.ExcelWriter(
        ASSOCIATION_FILE,
        engine="openpyxl"
    ) as writer:

        associations.to_excel(
            writer,
            sheet_name="correlations",
            index=False
        )

        df[
            [
                "procedure_code",
                "queries_observations_count",
                "query_stage_duration_days",
                "evaluation_stage_duration_days",
                "total_award_time_days",
            ]
        ].to_excel(
            writer,
            sheet_name="analysis_data",
            index=False
        )

    log(f"  Descriptive statistics: {DESCRIPTIVE_FILE.name}")
    log(f"  Data-quality diagnostics: {QUALITY_FILE.name}")
    log(f"  Association analysis: {ASSOCIATION_FILE.name}")
    log(f"  Log file: {LOG_FILE.name}")
    log()

    # -------------------------------------------------------------------------
    # Final audit
    # -------------------------------------------------------------------------

    log("=" * 78)
    log("EXPLORATORY ANALYSIS AUDIT")
    log("=" * 78)
    log(f"Analytical procedures:            {len(df)}")
    log(
        f"Unique procedure codes:           "
        f"{df['procedure_code'].nunique()}"
    )
    log(
        f"Missing query counts:             "
        f"{df['queries_observations_count'].isna().sum()}"
    )
    log(
        f"Verified zero query counts:       "
        f"{(df['queries_observations_count'] == 0).sum()}"
    )
    log(
        f"Positive query counts:            "
        f"{(df['queries_observations_count'] > 0).sum()}"
    )
    log(
        f"Failed data-quality checks:       "
        f"{len(failed_checks)}"
    )
    log(
        f"Checks requiring review:          "
        f"{len(review_checks)}"
    )
    log()

    log()
    log("TEMPORAL DATA COVERAGE")
    log("-" * 78)
    for _, row in temporal_coverage.iterrows():
        log(
            f"{row['label']:<35} "
            f"{int(row['available']):>3}/{int(row['total']):<3} "
            f"{row['coverage_percent']:>7.2f}%"
        )
    log()
    log(
        f"Complete temporal decompositions: "
        f"{len(temporal_consistency_details)}"
    )
    log(
        f"Temporal arithmetic inconsistencies: "
        f"{len(temporal_inconsistencies)}"
    )
    log()

    log("SCIENTIFIC SCOPE")
    log("- No observations removed.")
    log("- No outliers removed.")
    log("- No scenario thresholds defined.")
    log("- No probability distribution selected.")
    log("- No stochastic simulation performed.")
    log("- No causal interpretation imposed.")
    log()

    if (
        len(failed_checks) == 0
        and len(temporal_inconsistencies) == 0
    ):
        log("=" * 78)
        log("PIPELINE STATUS: COMPLETE")
        log("=" * 78)
    else:
        log("=" * 78)
        log("PIPELINE STATUS: COMPLETE WITH DATA-QUALITY FLAGS")
        log("=" * 78)

    save_log()


# =============================================================================
# 6. EXECUTION
# =============================================================================

if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        log()
        log("=" * 78)
        log("PIPELINE FAILED")
        log("=" * 78)
        log(f"{type(error).__name__}: {error}")

        try:
            save_log()
        except Exception:
            pass

        raise
