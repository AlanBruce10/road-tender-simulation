"""
11_methodological_assessment.py

Methodological readiness assessment for the road-infrastructure tender study.

PURPOSE
-------
This script closes the statistical-analysis phase before stochastic modeling.

It does NOT:
- perform the final Monte Carlo simulation;
- perform discrete-event simulation;
- select a final probability distribution automatically;
- alter the master analytical sample;
- delete influential observations or outliers;
- impute missing temporal dates;
- establish causality.

It DOES:
1. Audit the analytical contract.
2. Summarize completion/readiness of Objectives 1 and 2.
3. Quantify precision using bootstrap confidence intervals.
4. Evaluate sample-size stability using repeated subsampling.
5. Evaluate stability of the main query-count / award-time relationship.
6. Evaluate stability of Low / Medium / High scenario patterns.
7. Consolidate distributional evidence from Scripts 09 and 10.
8. Assess whether stochastic modeling has an empirical rationale.
9. Assess what Monte Carlo could add beyond observed-sample statistics.
10. Assess feasibility and limitations of discrete-event simulation (DES).
11. Assess temporal-validation feasibility.
12. Produce component-specific methodological readiness flags.

The script is intentionally conservative. A component may be classified as:
READY
CAUTION
LIMITED
INSUFFICIENT_FOR_COMPONENT
NOT_YET_ASSESSED

These flags are methodological audit labels, not hypothesis-test results.
"""

from __future__ import annotations

import logging
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


# =============================================================================
# CONFIGURATION
# =============================================================================

EXPECTED_MASTER_N = 137
RANDOM_SEED = 2026

BOOTSTRAP_ITERATIONS = 10_000
SUBSAMPLE_ITERATIONS = 1_000

SUBSAMPLE_SIZES = [40, 60, 80, 100, 120]

CI_LEVEL = 0.95
ALPHA = 0.05

# Practical stability criteria.
# These are transparent audit thresholds, not universal statistical laws.
CORRELATION_ABS_TOLERANCE = 0.10
SCENARIO_ORDER_STABILITY_TARGET = 0.90
SIGN_STABILITY_TARGET = 0.90

MIN_DISTRIBUTION_N_READY = 30
MIN_DES_COMPLETE_COVERAGE_READY = 0.80
MIN_TEMPORAL_YEAR_N_DESCRIPTIVE = 10

PRIMARY_SCENARIO_METHOD = "Terciles"

ROOT = Path(__file__).resolve().parents[2]

INPUT_MASTER = ROOT / "02_results" / "03_1_integrated_dataset.xlsx"

STAT_RESULTS = ROOT / "02_results" / "statistical_analysis"
LOG_DIR = ROOT / "03_logs" / "statistical_analysis"

INPUT_07 = STAT_RESULTS / "07_1_scenario_definition.xlsx"
INPUT_08 = STAT_RESULTS / "08_1_scenario_robustness.xlsx"
INPUT_09 = STAT_RESULTS / "09_1_distribution_fitting.xlsx"
INPUT_10 = STAT_RESULTS / "10_1_distribution_diagnostics.xlsx"

OUTPUT_FILE = STAT_RESULTS / "11_1_methodological_assessment.xlsx"
LOG_FILE = LOG_DIR / "11_methodological_assessment.log"

STAT_RESULTS.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(RANDOM_SEED)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("methodological_assessment")
logger.setLevel(logging.INFO)
logger.handlers.clear()

formatter = logging.Formatter("%(message)s")

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def log(message: str = "") -> None:
    logger.info(message)


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")


def require_columns(df: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def safe_float(value):
    try:
        if pd.isna(value):
            return np.nan
        return float(value)
    except Exception:
        return np.nan


def finite_array(values) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    return x[np.isfinite(x)]


def percentile_ci(values, ci_level=CI_LEVEL):
    x = finite_array(values)
    if len(x) == 0:
        return np.nan, np.nan

    alpha = 1.0 - ci_level
    lower = np.quantile(x, alpha / 2.0)
    upper = np.quantile(x, 1.0 - alpha / 2.0)
    return float(lower), float(upper)


def coefficient_of_variation(values):
    x = finite_array(values)
    if len(x) < 2:
        return np.nan
    mean = np.mean(x)
    if np.isclose(mean, 0):
        return np.nan
    return float(np.std(x, ddof=1) / mean)


def robust_spearman(x, y):
    x = np.asarray(x)
    y = np.asarray(y)

    mask = pd.notna(x) & pd.notna(y)
    x = x[mask].astype(float)
    y = y[mask].astype(float)

    if len(x) < 3:
        return np.nan, np.nan

    if np.unique(x).size < 2 or np.unique(y).size < 2:
        return np.nan, np.nan

    result = stats.spearmanr(x, y)
    return float(result.statistic), float(result.pvalue)


def robust_pearson(x, y):
    x = np.asarray(x)
    y = np.asarray(y)

    mask = pd.notna(x) & pd.notna(y)
    x = x[mask].astype(float)
    y = y[mask].astype(float)

    if len(x) < 3:
        return np.nan, np.nan

    if np.unique(x).size < 2 or np.unique(y).size < 2:
        return np.nan, np.nan

    result = stats.pearsonr(x, y)
    return float(result.statistic), float(result.pvalue)


def robust_kendall(x, y):
    x = np.asarray(x)
    y = np.asarray(y)

    mask = pd.notna(x) & pd.notna(y)
    x = x[mask].astype(float)
    y = y[mask].astype(float)

    if len(x) < 3:
        return np.nan, np.nan

    if np.unique(x).size < 2 or np.unique(y).size < 2:
        return np.nan, np.nan

    result = stats.kendalltau(x, y)
    return float(result.statistic), float(result.pvalue)


def classify_component(status: str) -> str:
    allowed = {
        "READY",
        "CAUTION",
        "LIMITED",
        "INSUFFICIENT_FOR_COMPONENT",
        "NOT_YET_ASSESSED",
    }
    if status not in allowed:
        raise ValueError(f"Invalid readiness status: {status}")
    return status


# =============================================================================
# BOOTSTRAP HELPERS
# =============================================================================

def bootstrap_univariate(values, statistic_func, iterations=BOOTSTRAP_ITERATIONS):
    x = finite_array(values)

    if len(x) < 2:
        return np.array([])

    results = np.empty(iterations, dtype=float)

    for i in range(iterations):
        sample = rng.choice(x, size=len(x), replace=True)
        try:
            results[i] = statistic_func(sample)
        except Exception:
            results[i] = np.nan

    return results[np.isfinite(results)]


def bootstrap_correlation(
    df,
    x_col,
    y_col,
    method="spearman",
    iterations=BOOTSTRAP_ITERATIONS,
):
    work = df[[x_col, y_col]].dropna().copy()

    if len(work) < 3:
        return np.array([])

    x = work[x_col].to_numpy(dtype=float)
    y = work[y_col].to_numpy(dtype=float)

    results = np.empty(iterations, dtype=float)

    for i in range(iterations):
        idx = rng.integers(0, len(work), size=len(work))
        xb = x[idx]
        yb = y[idx]

        try:
            if method == "spearman":
                value = stats.spearmanr(xb, yb).statistic
            elif method == "pearson":
                if np.unique(xb).size < 2 or np.unique(yb).size < 2:
                    value = np.nan
                else:
                    value = stats.pearsonr(xb, yb).statistic
            elif method == "kendall":
                value = stats.kendalltau(xb, yb).statistic
            else:
                raise ValueError(f"Unknown correlation method: {method}")

            results[i] = value
        except Exception:
            results[i] = np.nan

    return results[np.isfinite(results)]


# =============================================================================
# SUBSAMPLING HELPERS
# =============================================================================

def subsample_relationship_stability(
    df,
    x_col,
    y_col,
    sample_sizes,
    iterations=SUBSAMPLE_ITERATIONS,
):
    work = df[[x_col, y_col]].dropna().copy().reset_index(drop=True)

    full_rho, _ = robust_spearman(work[x_col], work[y_col])

    records = []

    for n in sample_sizes:
        if n > len(work):
            continue

        estimates = []

        for _ in range(iterations):
            idx = rng.choice(len(work), size=n, replace=False)
            sample = work.iloc[idx]

            rho, _ = robust_spearman(sample[x_col], sample[y_col])

            if np.isfinite(rho):
                estimates.append(rho)

        estimates = np.asarray(estimates, dtype=float)

        if len(estimates) == 0:
            continue

        q025, q975 = np.quantile(estimates, [0.025, 0.975])

        abs_diff = np.abs(estimates - full_rho)

        records.append(
            {
                "subsample_n": n,
                "valid_iterations": len(estimates),
                "full_sample_spearman": full_rho,
                "median_subsample_spearman": np.median(estimates),
                "mean_subsample_spearman": np.mean(estimates),
                "sd_subsample_spearman": np.std(estimates, ddof=1),
                "p025": q025,
                "p975": q975,
                "positive_sign_frequency": np.mean(estimates > 0),
                "within_abs_0_10_of_full_frequency": np.mean(
                    abs_diff <= CORRELATION_ABS_TOLERANCE
                ),
                "median_absolute_difference_from_full": np.median(abs_diff),
            }
        )

    return pd.DataFrame(records)


def subsample_scenario_stability(
    df,
    scenario_col,
    outcome_col,
    sample_sizes,
    iterations=SUBSAMPLE_ITERATIONS,
):
    work = df[[scenario_col, outcome_col]].dropna().copy().reset_index(drop=True)

    records = []

    for n in sample_sizes:
        if n > len(work):
            continue

        ordered_count = 0
        valid_count = 0
        kw_significant_count = 0

        low_medians = []
        medium_medians = []
        high_medians = []

        for _ in range(iterations):
            idx = rng.choice(len(work), size=n, replace=False)
            sample = work.iloc[idx]

            groups = {}

            valid = True
            for scenario in ["Low", "Medium", "High"]:
                vals = sample.loc[
                    sample[scenario_col] == scenario, outcome_col
                ].dropna().to_numpy(dtype=float)

                if len(vals) < 2:
                    valid = False
                    break

                groups[scenario] = vals

            if not valid:
                continue

            valid_count += 1

            med_low = np.median(groups["Low"])
            med_medium = np.median(groups["Medium"])
            med_high = np.median(groups["High"])

            low_medians.append(med_low)
            medium_medians.append(med_medium)
            high_medians.append(med_high)

            if med_low < med_medium < med_high:
                ordered_count += 1

            try:
                kw = stats.kruskal(
                    groups["Low"],
                    groups["Medium"],
                    groups["High"],
                )
                if kw.pvalue < ALPHA:
                    kw_significant_count += 1
            except Exception:
                pass

        if valid_count == 0:
            continue

        records.append(
            {
                "subsample_n": n,
                "valid_iterations": valid_count,
                "strict_median_order_frequency": ordered_count / valid_count,
                "kruskal_p_lt_0_05_frequency": (
                    kw_significant_count / valid_count
                ),
                "median_low": np.median(low_medians),
                "median_medium": np.median(medium_medians),
                "median_high": np.median(high_medians),
            }
        )

    return pd.DataFrame(records)


# =============================================================================
# MAIN
# =============================================================================

def main():

    log("=" * 78)
    log("METHODOLOGICAL ASSESSMENT - ROAD INFRASTRUCTURE TENDERS")
    log("=" * 78)
    log("Purpose: Close the statistical-analysis phase before stochastic modeling")
    log("")

    # =========================================================================
    # [1] INPUT VALIDATION
    # =========================================================================

    log("[1] Validating analytical inputs...")

    required_files = [
        INPUT_MASTER,
        INPUT_07,
        INPUT_08,
        INPUT_09,
        INPUT_10,
    ]

    for path in required_files:
        require_file(path)
        log(f"  Found: {path.name}")

    log("")

    # =========================================================================
    # [2] READ DATA
    # =========================================================================

    log("[2] Reading source datasets...")

    master = pd.read_excel(INPUT_MASTER)

    scenario_audit = pd.read_excel(INPUT_07, sheet_name="procedure_audit")
    decision_framework = pd.read_excel(
        INPUT_07,
        sheet_name="decision_framework",
    )

    robustness_summary = pd.read_excel(
        INPUT_08,
        sheet_name="robustness_summary",
    )
    modeling_readiness_08 = pd.read_excel(
        INPUT_08,
        sheet_name="modeling_readiness",
    )

    distribution_fits = pd.read_excel(
        INPUT_09,
        sheet_name="distribution_fits",
    )
    bootstrap_gof = pd.read_excel(
        INPUT_09,
        sheet_name="bootstrap_gof",
    )
    selection_stability = pd.read_excel(
        INPUT_09,
        sheet_name="selection_stability",
    )
    selection_audit = pd.read_excel(
        INPUT_09,
        sheet_name="selection_audit",
    )

    shape_diagnostics = pd.read_excel(
        INPUT_10,
        sheet_name="shape_diagnostics",
    )
    tail_sensitivity = pd.read_excel(
        INPUT_10,
        sheet_name="tail_sensitivity",
    )
    diagnostic_framework = pd.read_excel(
        INPUT_10,
        sheet_name="diagnostic_framework",
    )

    log(f"  Master rows: {len(master)}")
    log(f"  Scenario-audit rows: {len(scenario_audit)}")
    log(f"  Distribution-fit rows: {len(distribution_fits)}")
    log("")

    # =========================================================================
    # [3] ANALYTICAL CONTRACT
    # =========================================================================

    log("[3] Auditing analytical contract...")

    required_master_columns = [
        "procedure_code",
        "notice_date",
        "integrated_terms_date",
        "award_date",
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
        "total_award_time_days",
        "queries_observations_count",
    ]

    require_columns(master, required_master_columns, "Master dataset")

    require_columns(
        scenario_audit,
        [
            "procedure_code",
            "queries_observations_count",
            "total_award_time_days",
            "scenario_terciles",
            "scenario_p25_p75",
            "scenario_data_driven",
        ],
        "Script 07 procedure_audit",
    )

    if len(master) != EXPECTED_MASTER_N:
        raise ValueError(
            f"Expected master sample n={EXPECTED_MASTER_N}, "
            f"found n={len(master)}."
        )

    if master["procedure_code"].duplicated().any():
        raise ValueError("Duplicate procedure_code values in master dataset.")

    if scenario_audit["procedure_code"].duplicated().any():
        raise ValueError("Duplicate procedure_code values in Script 07 audit.")

    master_codes = set(master["procedure_code"])
    scenario_codes = set(scenario_audit["procedure_code"])

    if master_codes != scenario_codes:
        raise ValueError(
            "Procedure-code mismatch between master dataset and Script 07."
        )

    master_n = len(master)
    query_n = master["queries_observations_count"].notna().sum()
    total_time_n = master["total_award_time_days"].notna().sum()

    stage_complete_mask = (
        master["query_stage_duration_days"].notna()
        & master["evaluation_stage_duration_days"].notna()
    )
    stage_complete_n = int(stage_complete_mask.sum())

    analytical_contract = pd.DataFrame(
        [
            {
                "component": "master_analytical_sample",
                "available_n": master_n,
                "expected_n": EXPECTED_MASTER_N,
                "coverage_percent": 100 * master_n / EXPECTED_MASTER_N,
                "status": "PASS",
            },
            {
                "component": "queries_observations_count",
                "available_n": query_n,
                "expected_n": master_n,
                "coverage_percent": 100 * query_n / master_n,
                "status": (
                    "PASS" if query_n == master_n else "CAUTION"
                ),
            },
            {
                "component": "total_award_time_days",
                "available_n": total_time_n,
                "expected_n": master_n,
                "coverage_percent": 100 * total_time_n / master_n,
                "status": (
                    "PASS"
                    if total_time_n / master_n >= 0.95
                    else "CAUTION"
                ),
            },
            {
                "component": "complete_temporal_stage_decomposition",
                "available_n": stage_complete_n,
                "expected_n": master_n,
                "coverage_percent": 100 * stage_complete_n / master_n,
                "status": (
                    "PASS"
                    if stage_complete_n / master_n
                    >= MIN_DES_COMPLETE_COVERAGE_READY
                    else "CAUTION"
                ),
            },
        ]
    )

    log(f"  Master analytical sample: {master_n}")
    log(f"  Query-count coverage: {query_n}/{master_n}")
    log(f"  Total-award-time coverage: {total_time_n}/{master_n}")
    log(f"  Complete temporal decompositions: {stage_complete_n}/{master_n}")
    log("")

    # =========================================================================
    # [4] OBJECTIVE STATUS
    # =========================================================================

    log("[4] Auditing readiness of Objectives 1 and 2...")

    tercile_counts = (
        scenario_audit["scenario_terciles"]
        .value_counts(dropna=False)
        .to_dict()
    )

    p25_counts = (
        scenario_audit["scenario_p25_p75"]
        .value_counts(dropna=False)
        .to_dict()
    )

    objective_status = pd.DataFrame(
        [
            {
                "objective": "Objective_1_sample_identification",
                "evidence": (
                    f"Master analytical population contains {master_n} "
                    "unique eligible procedures and preserves all selected "
                    "procedures."
                ),
                "status": "READY",
                "interpretation": (
                    "The identification/data-acquisition stage is complete "
                    "for the prespecified analytical population."
                ),
            },
            {
                "objective": "Objective_2_scenario_operationalization",
                "evidence": (
                    "Three reproducible candidate scenario definitions were "
                    "evaluated in Scripts 07-08; quantile-based definitions "
                    "show ordered award-time patterns."
                ),
                "status": "CAUTION",
                "interpretation": (
                    "Scenario evidence is mature, but the final analytical "
                    "role of terciles versus P25/P75 must be explicitly "
                    "prespecified before stochastic modeling."
                ),
            },
            {
                "objective": "Objective_3_stochastic_modeling",
                "evidence": (
                    "Distribution fitting and diagnostics are available, "
                    "but no final stochastic simulation has yet been run."
                ),
                "status": "NOT_YET_ASSESSED",
                "interpretation": (
                    "This objective begins only after methodological "
                    "readiness is established."
                ),
            },
            {
                "objective": "Objective_4_model_validation",
                "evidence": (
                    "Validation architecture is being assessed before model "
                    "construction."
                ),
                "status": "NOT_YET_ASSESSED",
                "interpretation": (
                    "Final validation must follow model specification and "
                    "simulation."
                ),
            },
        ]
    )

    log(
        "  Objective 1: READY "
        f"(master analytical population n={master_n})"
    )
    log(
        "  Objective 2: CAUTION "
        "(evidence strong; final analytical role still to be prespecified)"
    )
    log("")

    # =========================================================================
    # [5] FULL-SAMPLE RELATIONSHIP REFERENCE
    # =========================================================================

    log("[5] Establishing full-sample relationship reference...")

    primary = master[
        ["queries_observations_count", "total_award_time_days"]
    ].dropna()

    pearson_r, pearson_p = robust_pearson(
        primary["queries_observations_count"],
        primary["total_award_time_days"],
    )

    spearman_rho, spearman_p = robust_spearman(
        primary["queries_observations_count"],
        primary["total_award_time_days"],
    )

    kendall_tau, kendall_p = robust_kendall(
        primary["queries_observations_count"],
        primary["total_award_time_days"],
    )

    log(f"  Primary complete cases: {len(primary)}")
    log(
        f"  Pearson r={pearson_r:.4f} "
        f"(p={pearson_p:.6g})"
    )
    log(
        f"  Spearman rho={spearman_rho:.4f} "
        f"(p={spearman_p:.6g})"
    )
    log(
        f"  Kendall tau={kendall_tau:.4f} "
        f"(p={kendall_p:.6g})"
    )
    log("")

    # =========================================================================
    # [6] BOOTSTRAP PRECISION
    # =========================================================================

    log("[6] Quantifying bootstrap precision...")

    bootstrap_records = []

    # Correlations
    for method, point in [
        ("Pearson", pearson_r),
        ("Spearman", spearman_rho),
        ("Kendall", kendall_tau),
    ]:
        boot = bootstrap_correlation(
            master,
            "queries_observations_count",
            "total_award_time_days",
            method=method.lower(),
        )

        lo, hi = percentile_ci(boot)

        bootstrap_records.append(
            {
                "analysis": "relationship",
                "statistic": method,
                "scenario": "All",
                "n": len(primary),
                "point_estimate": point,
                "bootstrap_iterations": len(boot),
                "ci_level": CI_LEVEL,
                "ci_lower": lo,
                "ci_upper": hi,
                "bootstrap_sd": (
                    np.std(boot, ddof=1) if len(boot) > 1 else np.nan
                ),
                "sign_consistency_frequency": (
                    np.mean(boot > 0) if len(boot) else np.nan
                ),
            }
        )

        log(
            f"  {method}: {point:.4f} "
            f"[{lo:.4f}, {hi:.4f}]"
        )

    # Scenario-specific award-time statistics
    scenario_work = scenario_audit.copy()

    for scenario in ["Low", "Medium", "High"]:
        values = scenario_work.loc[
            scenario_work["scenario_terciles"] == scenario,
            "total_award_time_days",
        ].dropna().to_numpy(dtype=float)

        statistic_specs = [
            ("median", np.median),
            (
                "std_dev",
                lambda x: np.std(x, ddof=1),
            ),
            (
                "p90",
                lambda x: np.quantile(x, 0.90),
            ),
        ]

        for stat_name, func in statistic_specs:
            point = float(func(values))
            boot = bootstrap_univariate(values, func)
            lo, hi = percentile_ci(boot)

            bootstrap_records.append(
                {
                    "analysis": "scenario_award_time",
                    "statistic": stat_name,
                    "scenario": scenario,
                    "n": len(values),
                    "point_estimate": point,
                    "bootstrap_iterations": len(boot),
                    "ci_level": CI_LEVEL,
                    "ci_lower": lo,
                    "ci_upper": hi,
                    "bootstrap_sd": (
                        np.std(boot, ddof=1)
                        if len(boot) > 1
                        else np.nan
                    ),
                    "sign_consistency_frequency": np.nan,
                }
            )

        log(
            f"  {scenario}: n={len(values)}; "
            f"median={np.median(values):.2f}; "
            f"SD={np.std(values, ddof=1):.2f}; "
            f"P90={np.quantile(values, 0.90):.2f}"
        )

    bootstrap_precision = pd.DataFrame(bootstrap_records)
    log("")

    # =========================================================================
    # [7] SUBSAMPLE RELATIONSHIP STABILITY
    # =========================================================================

    log("[7] Evaluating relationship stability under subsampling...")

    valid_subsample_sizes = [
        n for n in SUBSAMPLE_SIZES if n <= len(primary)
    ]

    relationship_stability = subsample_relationship_stability(
        master,
        "queries_observations_count",
        "total_award_time_days",
        valid_subsample_sizes,
    )

    for _, row in relationship_stability.iterrows():
        log(
            f"  n={int(row['subsample_n'])}: "
            f"median rho={row['median_subsample_spearman']:.4f}; "
            f"positive={row['positive_sign_frequency']:.2%}; "
            f"within ±{CORRELATION_ABS_TOLERANCE:.2f} of full="
            f"{row['within_abs_0_10_of_full_frequency']:.2%}"
        )

    log("")

    # =========================================================================
    # [8] SCENARIO STABILITY
    # =========================================================================

    log("[8] Evaluating Low-Medium-High scenario stability...")

    scenario_stability = subsample_scenario_stability(
        scenario_audit,
        "scenario_terciles",
        "total_award_time_days",
        valid_subsample_sizes,
    )

    for _, row in scenario_stability.iterrows():
        log(
            f"  n={int(row['subsample_n'])}: "
            f"strict Low<Medium<High median order="
            f"{row['strict_median_order_frequency']:.2%}; "
            f"Kruskal p<0.05="
            f"{row['kruskal_p_lt_0_05_frequency']:.2%}"
        )

    log("")

    # =========================================================================
    # [9] DISTRIBUTION EVIDENCE CONSOLIDATION
    # =========================================================================

    log("[9] Consolidating distributional evidence...")

    require_columns(
        selection_audit,
        [
            "method",
            "scenario",
            "n",
            "aic_preferred_distribution",
            "bootstrap_ks_p",
            "bootstrap_aic_selection_frequency",
            "decision_flag",
        ],
        "Script 09 selection_audit",
    )

    primary_selection = selection_audit[
        selection_audit["method"].astype(str).str.lower()
        == PRIMARY_SCENARIO_METHOD.lower()
    ].copy()

    if primary_selection.empty:
        # Defensive fallback in case the stored method label differs in case.
        primary_selection = selection_audit.copy()

    distribution_records = []

    for _, row in primary_selection.iterrows():
        scenario = str(row["scenario"])
        n = int(row["n"])
        preferred = str(row["aic_preferred_distribution"])
        ks_p = safe_float(row["bootstrap_ks_p"])
        selection_freq = safe_float(
            row["bootstrap_aic_selection_frequency"]
        )
        decision_flag = str(row["decision_flag"])

        if n < MIN_DISTRIBUTION_N_READY:
            readiness = "LIMITED"
        elif np.isfinite(ks_p) and ks_p < ALPHA:
            readiness = "CAUTION"
        else:
            readiness = "READY"

        distribution_records.append(
            {
                "scenario": scenario,
                "n": n,
                "aic_preferred_distribution": preferred,
                "bootstrap_ks_p": ks_p,
                "bootstrap_aic_selection_frequency": selection_freq,
                "script09_decision_flag": decision_flag,
                "methodological_readiness": readiness,
                "interpretation": (
                    "Candidate distribution has adequate diagnostic support."
                    if readiness == "READY"
                    else (
                        "Distributional representation requires explicit "
                        "sensitivity treatment before final simulation."
                    )
                ),
            }
        )

        log(
            f"  {scenario}: {preferred}; n={n}; "
            f"bootstrap KS p={ks_p:.4f}; "
            f"readiness={readiness}"
        )

    distribution_stability = pd.DataFrame(distribution_records)

    log("")

    # =========================================================================
    # [10] STOCHASTIC-MODELING NEED ASSESSMENT
    # =========================================================================

    log("[10] Assessing empirical rationale for stochastic modeling...")

    scenario_dispersion = []

    for scenario in ["Low", "Medium", "High"]:
        vals = scenario_audit.loc[
            scenario_audit["scenario_terciles"] == scenario,
            "total_award_time_days",
        ].dropna().to_numpy(dtype=float)

        if len(vals) == 0:
            continue

        scenario_dispersion.append(
            {
                "scenario": scenario,
                "n": len(vals),
                "mean": np.mean(vals),
                "median": np.median(vals),
                "std_dev": np.std(vals, ddof=1),
                "coefficient_of_variation": coefficient_of_variation(vals),
                "p10": np.quantile(vals, 0.10),
                "p90": np.quantile(vals, 0.90),
                "p90_minus_p10": (
                    np.quantile(vals, 0.90)
                    - np.quantile(vals, 0.10)
                ),
                "unique_values": np.unique(vals).size,
            }
        )

    stochastic_dispersion = pd.DataFrame(scenario_dispersion)

    all_have_variability = bool(
        (stochastic_dispersion["std_dev"] > 0).all()
    )

    all_have_multiple_unique = bool(
        (stochastic_dispersion["unique_values"] > 1).all()
    )

    stochastic_need_status = (
        "READY"
        if all_have_variability and all_have_multiple_unique
        else "INSUFFICIENT_FOR_COMPONENT"
    )

    log(
        "  Non-degenerate within-scenario variability: "
        f"{all_have_variability}"
    )
    log(
        "  Multiple observed award times in every scenario: "
        f"{all_have_multiple_unique}"
    )
    log(
        "  Stochastic representation rationale: "
        f"{stochastic_need_status}"
    )
    log("")

    # =========================================================================
    # [11] MONTE CARLO ASSESSMENT
    # =========================================================================

    log("[11] Assessing Monte Carlo methodological role...")

    monte_carlo_rows = [
        {
            "criterion": "empirical_uncertainty_exists",
            "observed_evidence": (
                "Award time exhibits substantial within-scenario dispersion "
                "in Low, Medium, and High groups."
            ),
            "implication": (
                "A deterministic single-value representation would discard "
                "observed uncertainty."
            ),
            "status": stochastic_need_status,
        },
        {
            "criterion": "probability_model_available",
            "observed_evidence": (
                "Script 09 fitted candidate probability distributions and "
                "Script 10 diagnosed their adequacy."
            ),
            "implication": (
                "Probability models can potentially generate stochastic "
                "award-time realizations, subject to scenario-specific "
                "goodness-of-fit limitations."
            ),
            "status": (
                "CAUTION"
                if (distribution_stability["methodological_readiness"]
                    == "CAUTION").any()
                else "READY"
            ),
        },
        {
            "criterion": "monte_carlo_additional_value",
            "observed_evidence": (
                "The research objective concerns variability and "
                "distributional outcomes rather than only a point estimate."
            ),
            "implication": (
                "Monte Carlo may be useful for propagating an explicitly "
                "specified stochastic model and estimating simulation-based "
                "quantities such as tail probabilities and scenario "
                "distributions."
            ),
            "status": "CAUTION",
        },
        {
            "criterion": "iteration_count_justification",
            "observed_evidence": (
                "The approved protocol mentions 10,000 iterations, but "
                "simulation convergence has not yet been empirically audited."
            ),
            "implication": (
                "10,000 iterations must not be treated as a universal rule. "
                "A later convergence experiment must evaluate Monte Carlo "
                "error and stability across increasing iteration counts."
            ),
            "status": "NOT_YET_ASSESSED",
        },
        {
            "criterion": "final_monte_carlo_authorization",
            "observed_evidence": (
                "Statistical evidence supports stochastic representation, "
                "but final probability-model specification and convergence "
                "testing remain pending."
            ),
            "implication": (
                "Monte Carlo is a plausible candidate method, not yet a "
                "scientifically finalized procedure."
            ),
            "status": "CAUTION",
        },
    ]

    monte_carlo_assessment = pd.DataFrame(monte_carlo_rows)

    for _, row in monte_carlo_assessment.iterrows():
        log(
            f"  {row['criterion']}: {row['status']}"
        )

    log("")

    # =========================================================================
    # [12] DES FEASIBILITY
    # =========================================================================

    log("[12] Assessing discrete-event simulation feasibility...")

    des_work = master[
        [
            "query_stage_duration_days",
            "evaluation_stage_duration_days",
            "total_award_time_days",
        ]
    ].dropna()

    des_n = len(des_work)
    des_coverage = des_n / master_n

    if des_n >= 3:
        stage_spearman, stage_spearman_p = robust_spearman(
            des_work["query_stage_duration_days"],
            des_work["evaluation_stage_duration_days"],
        )
    else:
        stage_spearman = np.nan
        stage_spearman_p = np.nan

    if des_n > 0:
        arithmetic_error = (
            des_work["query_stage_duration_days"]
            + des_work["evaluation_stage_duration_days"]
            - des_work["total_award_time_days"]
        )

        arithmetic_exact_share = float(
            np.mean(np.isclose(arithmetic_error, 0.0, atol=1e-9))
        )
        arithmetic_max_abs_error = float(
            np.max(np.abs(arithmetic_error))
        )
    else:
        arithmetic_exact_share = np.nan
        arithmetic_max_abs_error = np.nan

    if des_coverage >= MIN_DES_COMPLETE_COVERAGE_READY:
        des_data_status = "READY"
    elif des_coverage >= 0.60:
        des_data_status = "CAUTION"
    else:
        des_data_status = "LIMITED"

    des_assessment = pd.DataFrame(
        [
            {
                "criterion": "complete_stage_decomposition",
                "observed_value": des_n,
                "coverage_percent": 100 * des_coverage,
                "status": des_data_status,
                "interpretation": (
                    "DES can only use procedures with complete stage "
                    "durations unless a justified missing-data strategy is "
                    "introduced."
                ),
            },
            {
                "criterion": "temporal_arithmetic_consistency",
                "observed_value": arithmetic_exact_share,
                "coverage_percent": 100 * arithmetic_exact_share
                if np.isfinite(arithmetic_exact_share)
                else np.nan,
                "status": (
                    "READY"
                    if np.isfinite(arithmetic_exact_share)
                    and arithmetic_exact_share >= 0.99
                    else "CAUTION"
                ),
                "interpretation": (
                    "Checks whether modeled stages reconstruct observed "
                    "total award time."
                ),
            },
            {
                "criterion": "stage_dependence",
                "observed_value": stage_spearman,
                "coverage_percent": np.nan,
                "status": "CAUTION",
                "interpretation": (
                    "Stage dependence must be considered before any DES "
                    "assumes independent stage durations. Spearman rho="
                    f"{stage_spearman:.4f}, p={stage_spearman_p:.6g}."
                    if np.isfinite(stage_spearman)
                    else "Stage dependence could not be estimated."
                ),
            },
            {
                "criterion": "des_incremental_value",
                "observed_value": np.nan,
                "coverage_percent": np.nan,
                "status": "NOT_YET_ASSESSED",
                "interpretation": (
                    "DES should be retained only if stage-level simulation "
                    "adds interpretable information beyond direct modeling "
                    "of total award time."
                ),
            },
        ]
    )

    log(
        f"  Complete stage decompositions: "
        f"{des_n}/{master_n} ({des_coverage:.2%})"
    )
    log(
        f"  Exact stage-sum reconstruction: "
        f"{arithmetic_exact_share:.2%}"
    )
    log(
        f"  Stage-duration Spearman rho: "
        f"{stage_spearman:.4f} "
        f"(p={stage_spearman_p:.6g})"
    )
    log(
        f"  DES data-readiness status: {des_data_status}"
    )
    log("")

    # =========================================================================
    # [13] TEMPORAL VALIDATION FEASIBILITY
    # =========================================================================

    log("[13] Assessing temporal-validation feasibility...")

    temp = master.copy()
    temp["notice_date"] = pd.to_datetime(
        temp["notice_date"],
        errors="coerce",
    )
    temp["notice_year"] = temp["notice_date"].dt.year

    year_rows = []

    for year, group in temp.groupby("notice_year", dropna=False):
        if pd.isna(year):
            year_label = "Missing"
        else:
            year_label = str(int(year))

        n_year = len(group)
        total_available = group["total_award_time_days"].notna().sum()
        stage_available = (
            group["query_stage_duration_days"].notna()
            & group["evaluation_stage_duration_days"].notna()
        ).sum()

        year_rows.append(
            {
                "notice_year": year_label,
                "n": n_year,
                "total_award_time_available": total_available,
                "total_award_time_coverage_percent": (
                    100 * total_available / n_year
                ),
                "stage_decomposition_available": stage_available,
                "stage_decomposition_coverage_percent": (
                    100 * stage_available / n_year
                ),
                "descriptive_year_size_flag": (
                    "ADEQUATE_FOR_DESCRIPTIVE_AUDIT"
                    if n_year >= MIN_TEMPORAL_YEAR_N_DESCRIPTIVE
                    else "SMALL_YEAR_SAMPLE"
                ),
            }
        )

    temporal_validation = pd.DataFrame(year_rows)

    valid_years = temporal_validation[
        temporal_validation["notice_year"] != "Missing"
    ]

    temporal_year_count = len(valid_years)

    recent_year_stage_problem = bool(
        (
            valid_years[
                "stage_decomposition_coverage_percent"
            ] < 80
        ).any()
    )

    if temporal_year_count >= 4:
        temporal_status = "CAUTION"
    else:
        temporal_status = "LIMITED"

    validation_assessment = pd.DataFrame(
        [
            {
                "validation_dimension": "historical_internal_validation",
                "status": "READY",
                "scientific_role": (
                    "Bootstrap, sensitivity analyses, and empirical-vs-model "
                    "comparisons can be performed using the development data."
                ),
            },
            {
                "validation_dimension": "temporal_validation",
                "status": temporal_status,
                "scientific_role": (
                    "Multiple notice years exist, so temporal validation can "
                    "be investigated. However, year-specific sample size and "
                    "temporal missingness must be respected."
                ),
            },
            {
                "validation_dimension": "stage_level_temporal_validation",
                "status": (
                    "CAUTION"
                    if recent_year_stage_problem
                    else "READY"
                ),
                "scientific_role": (
                    "Stage-level validation is constrained by incomplete "
                    "integration-date coverage in some years."
                ),
            },
            {
                "validation_dimension": "future_external_validation",
                "status": "NOT_YET_ASSESSED",
                "scientific_role": (
                    "A later independent cohort would provide stronger "
                    "evidence of temporal transportability but is not "
                    "required to alter the current prespecified population."
                ),
            },
        ]
    )

    for _, row in temporal_validation.iterrows():
        log(
            f"  {row['notice_year']}: n={int(row['n'])}; "
            f"total-time coverage="
            f"{row['total_award_time_coverage_percent']:.2f}%; "
            f"stage coverage="
            f"{row['stage_decomposition_coverage_percent']:.2f}%"
        )

    log("")

    # =========================================================================
    # [14] SAMPLE-SIZE / PRECISION READINESS
    # =========================================================================

    log("[14] Building sample-size and precision readiness audit...")

    # Full Spearman bootstrap sign stability
    spearman_boot_row = bootstrap_precision[
        (bootstrap_precision["analysis"] == "relationship")
        & (bootstrap_precision["statistic"] == "Spearman")
    ].iloc[0]

    spearman_sign_stability = safe_float(
        spearman_boot_row["sign_consistency_frequency"]
    )

    # Largest evaluated subsample
    if not relationship_stability.empty:
        rel_last = relationship_stability.sort_values(
            "subsample_n"
        ).iloc[-1]

        rel_within_tolerance = safe_float(
            rel_last["within_abs_0_10_of_full_frequency"]
        )
    else:
        rel_within_tolerance = np.nan

    if not scenario_stability.empty:
        scen_last = scenario_stability.sort_values(
            "subsample_n"
        ).iloc[-1]

        scenario_order_stability = safe_float(
            scen_last["strict_median_order_frequency"]
        )
    else:
        scenario_order_stability = np.nan

    if (
        np.isfinite(spearman_sign_stability)
        and spearman_sign_stability >= SIGN_STABILITY_TARGET
        and np.isfinite(rel_within_tolerance)
        and rel_within_tolerance >= 0.75
    ):
        relationship_sample_status = "READY"
    else:
        relationship_sample_status = "CAUTION"

    if (
        np.isfinite(scenario_order_stability)
        and scenario_order_stability
        >= SCENARIO_ORDER_STABILITY_TARGET
    ):
        scenario_sample_status = "READY"
    else:
        scenario_sample_status = "CAUTION"

    sample_size_assessment = pd.DataFrame(
        [
            {
                "component": "primary_relationship",
                "observed_n": len(primary),
                "evidence_metric": (
                    "Bootstrap sign stability and repeated-subsample "
                    "agreement with full-sample Spearman estimate"
                ),
                "metric_value_1": spearman_sign_stability,
                "metric_value_2": rel_within_tolerance,
                "status": relationship_sample_status,
                "interpretation": (
                    "Readiness is based on empirical precision/stability, "
                    "not on a universal minimum-n rule."
                ),
            },
            {
                "component": "scenario_ordering",
                "observed_n": total_time_n,
                "evidence_metric": (
                    "Frequency of strict Low < Medium < High median ordering "
                    "in repeated subsamples"
                ),
                "metric_value_1": scenario_order_stability,
                "metric_value_2": np.nan,
                "status": scenario_sample_status,
                "interpretation": (
                    "Scenario readiness is evaluated by stability of the "
                    "empirical ordering under data reduction."
                ),
            },
            {
                "component": "probability_distribution_fitting",
                "observed_n": np.nan,
                "evidence_metric": (
                    "Scenario-specific sample size plus bootstrap GOF and "
                    "selection stability from Script 09"
                ),
                "metric_value_1": np.nan,
                "metric_value_2": np.nan,
                "status": (
                    "CAUTION"
                    if (distribution_stability[
                        "methodological_readiness"
                    ] == "CAUTION").any()
                    else "READY"
                ),
                "interpretation": (
                    "Adequacy is scenario-specific. Larger n would improve "
                    "tail and distribution estimation, but lack of perfect "
                    "fit is not solved by an arbitrary minimum sample rule."
                ),
            },
            {
                "component": "discrete_event_stage_modeling",
                "observed_n": des_n,
                "evidence_metric": (
                    "Complete stage-decomposition coverage"
                ),
                "metric_value_1": des_coverage,
                "metric_value_2": stage_spearman,
                "status": des_data_status,
                "interpretation": (
                    "Stage-level modeling has less information than "
                    "total-award-time modeling and requires explicit "
                    "missingness/dependence treatment."
                ),
            },
        ]
    )

    for _, row in sample_size_assessment.iterrows():
        log(
            f"  {row['component']}: {row['status']}"
        )

    log("")

    # =========================================================================
    # [15] METHODOLOGICAL READINESS MATRIX
    # =========================================================================

    log("[15] Building final component-specific methodological readiness...")

    low_row = distribution_stability[
        distribution_stability["scenario"].astype(str).str.lower()
        == "low"
    ]

    medium_row = distribution_stability[
        distribution_stability["scenario"].astype(str).str.lower()
        == "medium"
    ]

    high_row = distribution_stability[
        distribution_stability["scenario"].astype(str).str.lower()
        == "high"
    ]

    low_status = (
        low_row.iloc[0]["methodological_readiness"]
        if not low_row.empty
        else "NOT_YET_ASSESSED"
    )

    medium_status = (
        medium_row.iloc[0]["methodological_readiness"]
        if not medium_row.empty
        else "NOT_YET_ASSESSED"
    )

    high_status = (
        high_row.iloc[0]["methodological_readiness"]
        if not high_row.empty
        else "NOT_YET_ASSESSED"
    )

    readiness_rows = [
        {
            "component": "Master analytical population",
            "status": classify_component("READY"),
            "basis": (
                f"{master_n} unique procedures; analytical contract verified."
            ),
            "next_action": (
                "Preserve n=137 as the master analytical population."
            ),
        },
        {
            "component": "Primary relationship analysis",
            "status": classify_component(
                relationship_sample_status
            ),
            "basis": (
                "Relationship precision and stability evaluated through "
                "bootstrap and repeated subsampling."
            ),
            "next_action": (
                "Retain continuous query/observation count as the reference "
                "analytical representation."
            ),
        },
        {
            "component": "Low-Medium-High scenario structure",
            "status": classify_component(
                scenario_sample_status
            ),
            "basis": (
                "Scenario ordering evaluated under repeated subsampling and "
                "previous robustness analyses."
            ),
            "next_action": (
                "Prespecify the distinct roles of terciles and P25/P75 "
                "before simulation."
            ),
        },
        {
            "component": "Low probability representation",
            "status": classify_component(low_status),
            "basis": (
                "Script 09 goodness-of-fit plus Script 10 mismatch "
                "diagnostics."
            ),
            "next_action": (
                "Do not force a parametric model solely because it has the "
                "lowest AIC. Carry explicit sensitivity alternatives into "
                "model specification."
            ),
        },
        {
            "component": "Medium probability representation",
            "status": classify_component(medium_status),
            "basis": (
                "Scenario-specific distribution fitting and bootstrap GOF."
            ),
            "next_action": (
                "Carry supported candidates into formal model specification."
            ),
        },
        {
            "component": "High probability representation",
            "status": classify_component(high_status),
            "basis": (
                "Scenario-specific distribution fitting and bootstrap GOF."
            ),
            "next_action": (
                "Carry supported candidates into formal model specification."
            ),
        },
        {
            "component": "Stochastic modeling rationale",
            "status": classify_component(stochastic_need_status),
            "basis": (
                "Observed award-time variability remains substantial within "
                "each scenario."
            ),
            "next_action": (
                "Model uncertainty explicitly rather than replacing each "
                "scenario with a single deterministic duration."
            ),
        },
        {
            "component": "Monte Carlo simulation",
            "status": classify_component("CAUTION"),
            "basis": (
                "Monte Carlo has a plausible role for uncertainty "
                "propagation, but final model specification and convergence "
                "testing remain pending."
            ),
            "next_action": (
                "Specify the stochastic model first, then run an explicit "
                "Monte Carlo convergence experiment before fixing the "
                "iteration count."
            ),
        },
        {
            "component": "Discrete-event simulation",
            "status": classify_component(des_data_status),
            "basis": (
                f"{des_n}/{master_n} procedures have complete temporal stage "
                "decomposition; stage dependence was explicitly audited."
            ),
            "next_action": (
                "Demonstrate incremental scientific value over direct "
                "total-time modeling before retaining DES in the final "
                "architecture."
            ),
        },
        {
            "component": "Temporal validation",
            "status": classify_component(temporal_status),
            "basis": (
                "Multiple years are available, but annual sample sizes and "
                "stage-level missingness constrain a simple holdout design."
            ),
            "next_action": (
                "Evaluate candidate temporal validation designs before "
                "splitting the development data."
            ),
        },
        {
            "component": "Final stochastic model",
            "status": classify_component("NOT_YET_ASSESSED"),
            "basis": (
                "No final stochastic architecture has been selected."
            ),
            "next_action": (
                "Proceed to formal model specification only after this "
                "assessment is reviewed."
            ),
        },
    ]

    methodological_readiness = pd.DataFrame(readiness_rows)

    for _, row in methodological_readiness.iterrows():
        log(
            f"  {row['component']:<38} | {row['status']}"
        )

    log("")

    # =========================================================================
    # [16] PRESPECIFIED NEXT-PHASE PROTOCOL
    # =========================================================================

    log("[16] Creating prespecified next-phase protocol...")

    next_phase_protocol = pd.DataFrame(
        [
            {
                "sequence": 1,
                "future_step": "Model specification",
                "rule": (
                    "Define the stochastic representation before performing "
                    "the final simulation. Do not select models based only "
                    "on visually attractive results."
                ),
            },
            {
                "sequence": 2,
                "future_step": "Scenario-role specification",
                "rule": (
                    "Maintain the continuous query count as the reference "
                    "variable. Explicitly define the role of terciles for "
                    "scenario simulation and P25/P75 for extreme-group "
                    "hypothesis contrasts if scientifically retained."
                ),
            },
            {
                "sequence": 3,
                "future_step": "Distribution specification",
                "rule": (
                    "Use Script 09-10 evidence. Do not force a common "
                    "parametric distribution where goodness-of-fit evidence "
                    "indicates meaningful mismatch."
                ),
            },
            {
                "sequence": 4,
                "future_step": "Monte Carlo convergence",
                "rule": (
                    "Evaluate increasing iteration counts such as 100, 500, "
                    "1,000, 2,500, 5,000, and 10,000 using fixed reproducible "
                    "seeds and Monte Carlo error/stability metrics."
                ),
            },
            {
                "sequence": 5,
                "future_step": "Monte Carlo simulation",
                "rule": (
                    "Run the final simulation only after convergence and "
                    "probability-model specification are documented."
                ),
            },
            {
                "sequence": 6,
                "future_step": "DES decision",
                "rule": (
                    "Retain discrete-event simulation only if stage-level "
                    "representation adds scientific information beyond "
                    "direct total-award-time modeling."
                ),
            },
            {
                "sequence": 7,
                "future_step": "Validation",
                "rule": (
                    "Preserve preapproved KS and t-test analyses where "
                    "applicable, but supplement them with distributional, "
                    "quantile, uncertainty, sensitivity, and predictive "
                    "validation metrics."
                ),
            },
            {
                "sequence": 8,
                "future_step": "Causal interpretation",
                "rule": (
                    "Do not infer causal effects from the observational "
                    "historical design. Report associations, conditional "
                    "distributions, scenario differences, and predictive "
                    "behavior unless a separate causal design is justified."
                ),
            },
        ]
    )

    log("  Next-phase protocol created.")
    log("")

    # =========================================================================
    # [17] SAVE OUTPUTS
    # =========================================================================

    log("[17] Saving reproducible methodological-assessment outputs...")

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        analytical_contract.to_excel(
            writer,
            sheet_name="analytical_contract",
            index=False,
        )

        objective_status.to_excel(
            writer,
            sheet_name="objective_status",
            index=False,
        )

        bootstrap_precision.to_excel(
            writer,
            sheet_name="bootstrap_precision",
            index=False,
        )

        relationship_stability.to_excel(
            writer,
            sheet_name="relationship_stability",
            index=False,
        )

        scenario_stability.to_excel(
            writer,
            sheet_name="scenario_stability",
            index=False,
        )

        sample_size_assessment.to_excel(
            writer,
            sheet_name="sample_size_assessment",
            index=False,
        )

        distribution_stability.to_excel(
            writer,
            sheet_name="distribution_stability",
            index=False,
        )

        stochastic_dispersion.to_excel(
            writer,
            sheet_name="stochastic_dispersion",
            index=False,
        )

        monte_carlo_assessment.to_excel(
            writer,
            sheet_name="monte_carlo_assessment",
            index=False,
        )

        des_assessment.to_excel(
            writer,
            sheet_name="des_assessment",
            index=False,
        )

        temporal_validation.to_excel(
            writer,
            sheet_name="temporal_validation",
            index=False,
        )

        validation_assessment.to_excel(
            writer,
            sheet_name="validation_assessment",
            index=False,
        )

        methodological_readiness.to_excel(
            writer,
            sheet_name="methodological_readiness",
            index=False,
        )

        next_phase_protocol.to_excel(
            writer,
            sheet_name="next_phase_protocol",
            index=False,
        )

    log(f"  Output workbook: {OUTPUT_FILE.name}")
    log(f"  Log file: {LOG_FILE.name}")
    log("")

    # =========================================================================
    # FINAL AUDIT
    # =========================================================================

    log("=" * 78)
    log("METHODOLOGICAL ASSESSMENT AUDIT")
    log("=" * 78)

    log(f"Master analytical procedures:          {master_n}")
    log(f"Primary relationship sample:           {len(primary)}")
    log(
        f"Complete temporal decompositions:      "
        f"{des_n} ({des_coverage:.2%})"
    )
    log(f"Bootstrap iterations:                  {BOOTSTRAP_ITERATIONS:,}")
    log(f"Subsample iterations per size:         {SUBSAMPLE_ITERATIONS:,}")
    log("")

    log("PRIMARY RELATIONSHIP")
    log("-" * 78)
    log(
        f"Pearson r:                            "
        f"{pearson_r:.4f}"
    )
    log(
        f"Spearman rho:                         "
        f"{spearman_rho:.4f}"
    )
    log(
        f"Kendall tau:                          "
        f"{kendall_tau:.4f}"
    )
    log("")

    log("COMPONENT READINESS")
    log("-" * 78)

    for _, row in methodological_readiness.iterrows():
        log(
            f"{row['component']:<40} {row['status']}"
        )

    log("")
    log("SCIENTIFIC INTERPRETATION")
    log("-" * 78)
    log(
        "- n=137 is treated as the prespecified master analytical "
        "population, not as an arbitrary minimum sample size."
    )
    log(
        "- Sample adequacy is evaluated component by component using "
        "precision and empirical stability rather than a universal n rule."
    )
    log(
        "- Bootstrap procedures quantify sampling uncertainty; they are "
        "not the final Monte Carlo award-time simulation."
    )
    log(
        "- Subsampling evaluates robustness to reduced information; it "
        "does not create new independent observations."
    )
    log(
        "- Evidence of stochastic variability does not automatically "
        "justify a particular probability distribution."
    )
    log(
        "- Monte Carlo remains a candidate uncertainty-propagation method "
        "pending formal model specification and convergence analysis."
    )
    log(
        "- The originally proposed 10,000 iterations are not accepted as "
        "self-justifying; convergence must be demonstrated."
    )
    log(
        "- DES remains conditional on stage-level data sufficiency, "
        "dependence structure, and incremental scientific value."
    )
    log(
        "- No causal interpretation is authorized by this assessment."
    )
    log(
        "- No observations were deleted, no missing values were imputed, "
        "and the master analytical sample remains n=137."
    )
    log("")

    # Overall pipeline status deliberately avoids pretending that all
    # future methodological choices are finalized.
    blocking = methodological_readiness[
        "status"
    ].eq("INSUFFICIENT_FOR_COMPONENT").any()

    if blocking:
        overall_status = "REVIEW_REQUIRED_BEFORE_STOCHASTIC_MODELING"
    else:
        overall_status = "READY_FOR_MODEL_SPECIFICATION_WITH_RECORDED_CAUTIONS"

    log("=" * 78)
    log(f"PIPELINE STATUS: {overall_status}")
    log("=" * 78)


if __name__ == "__main__":
    main()
