from pathlib import Path
import sys
import logging
import warnings

import numpy as np
import pandas as pd
from scipy import stats


# =============================================================================
# CONFIGURATION
# =============================================================================

EXPECTED_MASTER_SAMPLE_SIZE = 137

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]

INPUT_FILE = (
    PROJECT_ROOT
    / "02_results"
    / "03_1_integrated_dataset.xlsx"
)

RESULTS_DIR = (
    PROJECT_ROOT
    / "02_results"
    / "statistical_analysis"
)

LOGS_DIR = (
    PROJECT_ROOT
    / "03_logs"
    / "statistical_analysis"
)

OUTPUT_FILE = (
    RESULTS_DIR
    / "07_1_scenario_definition.xlsx"
)

LOG_FILE = (
    LOGS_DIR
    / "07_scenario_definition.log"
)

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("scenario_definition")
logger.setLevel(logging.INFO)
logger.handlers.clear()

formatter = logging.Formatter("%(message)s")

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(
    LOG_FILE,
    mode="w",
    encoding="utf-8",
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def log(message=""):
    logger.info(message)


def separator():
    log("=" * 78)


# =============================================================================
# HELPERS
# =============================================================================

def epsilon_squared_kruskal(h_statistic, n, k):
    """
    Epsilon-squared effect size for Kruskal-Wallis.

    epsilon^2 = (H - k + 1) / (n - k)

    Negative values caused by sampling variability are truncated at zero.
    """
    if n <= k:
        return np.nan

    value = (h_statistic - k + 1) / (n - k)

    return float(max(0.0, value))


def scenario_summary(df, method, scenario_column):
    rows = []

    for scenario in ["Low", "Medium", "High"]:

        subset = df.loc[
            df[scenario_column] == scenario
        ].copy()

        x = subset["queries_observations_count"]
        y = subset["total_award_time_days"].dropna()

        rows.append(
            {
                "method": method,
                "scenario": scenario,
                "n_master": len(subset),
                "n_with_total_award_time": len(y),
                "queries_min": (
                    float(x.min()) if len(x) else np.nan
                ),
                "queries_max": (
                    float(x.max()) if len(x) else np.nan
                ),
                "queries_mean": (
                    float(x.mean()) if len(x) else np.nan
                ),
                "queries_median": (
                    float(x.median()) if len(x) else np.nan
                ),
                "award_time_mean": (
                    float(y.mean()) if len(y) else np.nan
                ),
                "award_time_median": (
                    float(y.median()) if len(y) else np.nan
                ),
                "award_time_std": (
                    float(y.std(ddof=1))
                    if len(y) > 1 else np.nan
                ),
                "award_time_iqr": (
                    float(
                        y.quantile(0.75)
                        - y.quantile(0.25)
                    )
                    if len(y) else np.nan
                ),
            }
        )

    return rows


def evaluate_method(df, method, scenario_column):
    """
    Diagnostic comparison of total award time across three scenarios.
    No causal interpretation and no automatic method selection.
    """

    valid = df.loc[
        df["total_award_time_days"].notna()
        & df[scenario_column].notna()
    ].copy()

    groups = []

    for scenario in ["Low", "Medium", "High"]:
        values = valid.loc[
            valid[scenario_column] == scenario,
            "total_award_time_days",
        ].dropna()

        groups.append(values)

    if any(len(group) == 0 for group in groups):
        return {
            "method": method,
            "n": len(valid),
            "k": 3,
            "kruskal_h": np.nan,
            "kruskal_p": np.nan,
            "epsilon_squared": np.nan,
            "low_n": len(groups[0]),
            "medium_n": len(groups[1]),
            "high_n": len(groups[2]),
            "smallest_group_n": min(
                len(group) for group in groups
            ),
            "largest_group_n": max(
                len(group) for group in groups
            ),
            "group_size_ratio": np.nan,
        }

    result = stats.kruskal(*groups)

    h_stat = float(result.statistic)
    p_value = float(result.pvalue)

    n = sum(len(group) for group in groups)
    k = 3

    epsilon = epsilon_squared_kruskal(
        h_stat,
        n,
        k,
    )

    sizes = [len(group) for group in groups]

    ratio = (
        max(sizes) / min(sizes)
        if min(sizes) > 0
        else np.nan
    )

    return {
        "method": method,
        "n": n,
        "k": k,
        "kruskal_h": h_stat,
        "kruskal_p": p_value,
        "epsilon_squared": epsilon,
        "low_n": sizes[0],
        "medium_n": sizes[1],
        "high_n": sizes[2],
        "smallest_group_n": min(sizes),
        "largest_group_n": max(sizes),
        "group_size_ratio": ratio,
    }


def optimal_1d_three_cluster_partition(values):
    """
    Exact 1D partition into three contiguous clusters.

    The sorted query-count values are partitioned into three non-empty
    contiguous groups minimizing total within-cluster sum of squares.

    This avoids requiring scikit-learn and makes the clustering
    deterministic and fully reproducible.

    IMPORTANT:
    This is a diagnostic data-driven partition, not automatically
    the scientifically preferred scenario definition.
    """

    values = np.asarray(values, dtype=float)

    unique_values = np.unique(values)

    if len(unique_values) < 3:
        raise ValueError(
            "At least three distinct query-count values are required "
            "for three-cluster partitioning."
        )

    unique_values.sort()

    n = len(unique_values)

    prefix_sum = np.zeros(n + 1)
    prefix_sq = np.zeros(n + 1)

    prefix_sum[1:] = np.cumsum(unique_values)
    prefix_sq[1:] = np.cumsum(unique_values ** 2)

    def segment_sse(start, end):
        count = end - start

        if count <= 0:
            return np.inf

        total = prefix_sum[end] - prefix_sum[start]
        total_sq = prefix_sq[end] - prefix_sq[start]

        return total_sq - (total ** 2) / count

    best = None

    for i in range(1, n - 1):
        for j in range(i + 1, n):

            sse = (
                segment_sse(0, i)
                + segment_sse(i, j)
                + segment_sse(j, n)
            )

            if best is None or sse < best["sse"]:
                best = {
                    "i": i,
                    "j": j,
                    "sse": float(sse),
                }

    i = best["i"]
    j = best["j"]

    low_max = unique_values[i - 1]
    medium_min = unique_values[i]

    medium_max = unique_values[j - 1]
    high_min = unique_values[j]

    cut_1 = (low_max + medium_min) / 2
    cut_2 = (medium_max + high_min) / 2

    return {
        "cut_1": float(cut_1),
        "cut_2": float(cut_2),
        "low_max_observed": float(low_max),
        "medium_min_observed": float(medium_min),
        "medium_max_observed": float(medium_max),
        "high_min_observed": float(high_min),
        "within_cluster_sse": best["sse"],
    }


def assign_by_two_cuts(series, cut_1, cut_2):
    return pd.cut(
        series,
        bins=[
            -np.inf,
            cut_1,
            cut_2,
            np.inf,
        ],
        labels=[
            "Low",
            "Medium",
            "High",
        ],
        include_lowest=True,
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    separator()
    log(
        "SCENARIO-DEFINITION DIAGNOSTICS - "
        "ROAD INFRASTRUCTURE TENDERS"
    )
    separator()

    log(
        "Input: Script 03 integrated analytical dataset"
    )

    log(
        "Purpose: Compare reproducible alternatives for defining "
        "low, medium, and high query/observation scenarios before "
        "stochastic modeling"
    )

    log()

    # =========================================================================
    # 1. INPUT
    # =========================================================================

    log("[1] Validating Script 03 input...")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    log(f"  Input file: {INPUT_FILE.name}")
    log("  Input file found.")
    log()

    # =========================================================================
    # 2. READ
    # =========================================================================

    log("[2] Reading analytical dataset...")

    df = pd.read_excel(INPUT_FILE)

    log(f"  Rows: {len(df)}")
    log(f"  Columns: {len(df.columns)}")
    log()

    # =========================================================================
    # 3. CONTRACT
    # =========================================================================

    log("[3] Validating analytical contract...")

    required_columns = [
        "procedure_code",
        "queries_observations_count",
        "total_award_time_days",
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

    if len(df) != EXPECTED_MASTER_SAMPLE_SIZE:
        raise ValueError(
            f"Expected {EXPECTED_MASTER_SAMPLE_SIZE} procedures, "
            f"found {len(df)}."
        )

    if df["procedure_code"].duplicated().any():
        raise ValueError(
            "Duplicate procedure_code values detected."
        )

    df["queries_observations_count"] = pd.to_numeric(
        df["queries_observations_count"],
        errors="coerce",
    )

    df["total_award_time_days"] = pd.to_numeric(
        df["total_award_time_days"],
        errors="coerce",
    )

    if df["queries_observations_count"].isna().any():
        raise ValueError(
            "Missing query/observation counts detected."
        )

    if (
        df["queries_observations_count"] < 0
    ).any():
        raise ValueError(
            "Negative query/observation counts detected."
        )

    log(
        f"  Master analytical sample verified: "
        f"{len(df)}"
    )
    log(
        "  queries_observations_count coverage: "
        f"{df['queries_observations_count'].notna().sum()}/{len(df)}"
    )
    log(
        "  total_award_time_days coverage: "
        f"{df['total_award_time_days'].notna().sum()}/{len(df)}"
    )
    log()

    # =========================================================================
    # 4. CONTINUOUS REFERENCE
    # =========================================================================

    log(
        "[4] Establishing continuous-variable reference..."
    )

    q = df["queries_observations_count"]

    continuous_reference = pd.DataFrame(
        [
            {
                "n": len(q),
                "minimum": float(q.min()),
                "p25": float(q.quantile(0.25)),
                "median": float(q.median()),
                "p75": float(q.quantile(0.75)),
                "maximum": float(q.max()),
                "mean": float(q.mean()),
                "std_dev": float(q.std(ddof=1)),
                "unique_values": int(q.nunique()),
            }
        ]
    )

    log(f"  n: {len(q)}")
    log(f"  Minimum: {q.min():.0f}")
    log(f"  P25: {q.quantile(0.25):.3f}")
    log(f"  Median: {q.median():.3f}")
    log(f"  P75: {q.quantile(0.75):.3f}")
    log(f"  Maximum: {q.max():.0f}")
    log(
        "  NOTE: The continuous variable remains the reference "
        "representation; categorization is evaluated diagnostically."
    )
    log()

    # =========================================================================
    # 5. METHOD A - TERCILES
    # =========================================================================

    log("[5] Defining tercile-based scenarios...")

    tercile_q1 = float(q.quantile(1 / 3))
    tercile_q2 = float(q.quantile(2 / 3))

    df["scenario_terciles"] = assign_by_two_cuts(
        q,
        tercile_q1,
        tercile_q2,
    )

    log(
        f"  Raw tercile quantiles: "
        f"{tercile_q1:.3f}, {tercile_q2:.3f}"
    )

    tercile_counts = (
        df["scenario_terciles"]
        .value_counts()
        .reindex(
            ["Low", "Medium", "High"],
            fill_value=0,
        )
    )

    for scenario, count in tercile_counts.items():
        log(
            f"  {scenario}: {int(count)} procedures"
        )

    log()

    # =========================================================================
    # 6. METHOD B - P25/P75
    # =========================================================================

    log("[6] Defining P25/P75 scenarios...")

    p25 = float(q.quantile(0.25))
    p75 = float(q.quantile(0.75))

    df["scenario_p25_p75"] = assign_by_two_cuts(
        q,
        p25,
        p75,
    )

    log(f"  P25 threshold: {p25:.3f}")
    log(f"  P75 threshold: {p75:.3f}")

    p_counts = (
        df["scenario_p25_p75"]
        .value_counts()
        .reindex(
            ["Low", "Medium", "High"],
            fill_value=0,
        )
    )

    for scenario, count in p_counts.items():
        log(
            f"  {scenario}: {int(count)} procedures"
        )

    log()

    # =========================================================================
    # 7. METHOD C - DATA-DRIVEN 1D PARTITION
    # =========================================================================

    log(
        "[7] Defining data-driven three-cluster partition..."
    )

    cluster_info = optimal_1d_three_cluster_partition(
        q.values
    )

    cluster_cut_1 = cluster_info["cut_1"]
    cluster_cut_2 = cluster_info["cut_2"]

    df["scenario_data_driven"] = assign_by_two_cuts(
        q,
        cluster_cut_1,
        cluster_cut_2,
    )

    log(
        f"  Cut 1: {cluster_cut_1:.3f}"
    )
    log(
        f"  Cut 2: {cluster_cut_2:.3f}"
    )

    log(
        "  Observed boundary 1: "
        f"{cluster_info['low_max_observed']:.0f} / "
        f"{cluster_info['medium_min_observed']:.0f}"
    )

    log(
        "  Observed boundary 2: "
        f"{cluster_info['medium_max_observed']:.0f} / "
        f"{cluster_info['high_min_observed']:.0f}"
    )

    cluster_counts = (
        df["scenario_data_driven"]
        .value_counts()
        .reindex(
            ["Low", "Medium", "High"],
            fill_value=0,
        )
    )

    for scenario, count in cluster_counts.items():
        log(
            f"  {scenario}: {int(count)} procedures"
        )

    log(
        "  NOTE: The data-driven partition minimizes within-cluster "
        "dispersion in query counts; it does not use award time and "
        "does not automatically define the preferred scientific scenarios."
    )
    log()

    # =========================================================================
    # 8. SCENARIO SUMMARIES
    # =========================================================================

    log(
        "[8] Summarizing scenario characteristics..."
    )

    summary_rows = []

    methods = [
        (
            "Terciles",
            "scenario_terciles",
        ),
        (
            "P25_P75",
            "scenario_p25_p75",
        ),
        (
            "Data_driven_1D",
            "scenario_data_driven",
        ),
    ]

    for method, column in methods:

        rows = scenario_summary(
            df,
            method,
            column,
        )

        summary_rows.extend(rows)

        log(f"  {method}:")

        for row in rows:
            log(
                f"    {row['scenario']}: "
                f"n={row['n_master']}; "
                f"queries={row['queries_min']:.0f}-"
                f"{row['queries_max']:.0f}; "
                f"award-time median="
                f"{row['award_time_median']:.2f}"
            )

    scenario_summaries = pd.DataFrame(
        summary_rows
    )

    log()

    # =========================================================================
    # 9. NONPARAMETRIC SEPARATION
    # =========================================================================

    log(
        "[9] Evaluating award-time separation across scenario definitions..."
    )

    evaluation_rows = []

    for method, column in methods:

        result = evaluate_method(
            df,
            method,
            column,
        )

        evaluation_rows.append(result)

        log(
            f"  {method}: "
            f"H={result['kruskal_h']:.4f}; "
            f"p={result['kruskal_p']:.6g}; "
            f"epsilon²={result['epsilon_squared']:.4f}; "
            f"group sizes="
            f"{result['low_n']}/"
            f"{result['medium_n']}/"
            f"{result['high_n']}"
        )

    method_evaluation = pd.DataFrame(
        evaluation_rows
    )

    log()
    log(
        "  NOTE: Kruskal-Wallis evaluates whether award-time "
        "distributions differ across groups. It does not establish "
        "causality and is not used here to automatically select a method."
    )
    log()

    # =========================================================================
    # 10. THRESHOLD AUDIT
    # =========================================================================

    log("[10] Building threshold audit...")

    threshold_audit = pd.DataFrame(
        [
            {
                "method": "Terciles",
                "lower_cut": tercile_q1,
                "upper_cut": tercile_q2,
                "basis":
                    "Empirical 33.3rd and 66.7th percentiles",
                "uses_outcome_to_define_groups": False,
            },
            {
                "method": "P25_P75",
                "lower_cut": p25,
                "upper_cut": p75,
                "basis":
                    "Empirical 25th and 75th percentiles",
                "uses_outcome_to_define_groups": False,
            },
            {
                "method": "Data_driven_1D",
                "lower_cut": cluster_cut_1,
                "upper_cut": cluster_cut_2,
                "basis":
                    "Exact 1D three-cluster partition minimizing "
                    "within-cluster query-count SSE",
                "uses_outcome_to_define_groups": False,
            },
        ]
    )

    log(
        "  All candidate scenario definitions use only "
        "queries_observations_count."
    )
    log(
        "  total_award_time_days is not used to determine thresholds."
    )
    log()

    # =========================================================================
    # 11. ASSIGNMENT AGREEMENT
    # =========================================================================

    log(
        "[11] Auditing agreement between scenario definitions..."
    )

    pairings = [
        (
            "Terciles",
            "scenario_terciles",
            "P25_P75",
            "scenario_p25_p75",
        ),
        (
            "Terciles",
            "scenario_terciles",
            "Data_driven_1D",
            "scenario_data_driven",
        ),
        (
            "P25_P75",
            "scenario_p25_p75",
            "Data_driven_1D",
            "scenario_data_driven",
        ),
    ]

    agreement_rows = []

    for (
        method_a,
        col_a,
        method_b,
        col_b,
    ) in pairings:

        agreement = float(
            (
                df[col_a].astype(str)
                == df[col_b].astype(str)
            ).mean()
        )

        agreement_rows.append(
            {
                "method_a": method_a,
                "method_b": method_b,
                "same_assignment_n": int(
                    (
                        df[col_a].astype(str)
                        == df[col_b].astype(str)
                    ).sum()
                ),
                "total_n": len(df),
                "agreement_percent":
                    100 * agreement,
            }
        )

        log(
            f"  {method_a} vs {method_b}: "
            f"{100*agreement:.2f}% same assignments"
        )

    assignment_agreement = pd.DataFrame(
        agreement_rows
    )

    log()

    # =========================================================================
    # 12. PROCEDURE-LEVEL AUDIT
    # =========================================================================

    log(
        "[12] Preparing procedure-level scenario audit..."
    )

    procedure_audit = df[
        [
            "procedure_code",
            "queries_observations_count",
            "total_award_time_days",
            "scenario_terciles",
            "scenario_p25_p75",
            "scenario_data_driven",
        ]
    ].copy()

    procedure_audit[
        "all_methods_agree"
    ] = (
        (
            procedure_audit["scenario_terciles"].astype(str)
            == procedure_audit["scenario_p25_p75"].astype(str)
        )
        &
        (
            procedure_audit["scenario_terciles"].astype(str)
            == procedure_audit["scenario_data_driven"].astype(str)
        )
    )

    all_agree_n = int(
        procedure_audit[
            "all_methods_agree"
        ].sum()
    )

    log(
        f"  Procedures assigned identically by all methods: "
        f"{all_agree_n}/{len(procedure_audit)} "
        f"({100*all_agree_n/len(procedure_audit):.2f}%)"
    )
    log()

    # =========================================================================
    # 13. DECISION FRAMEWORK
    # =========================================================================

    log(
        "[13] Building methodological decision framework..."
    )

    decision_framework = pd.DataFrame(
        [
            {
                "criterion":
                    "Preserve continuous information",
                "continuous_variable":
                    "Strong",
                "terciles":
                    "Reduced",
                "p25_p75":
                    "Reduced",
                "data_driven_1d":
                    "Reduced",
                "interpretation":
                    "Any categorization loses information relative "
                    "to the original continuous count.",
            },
            {
                "criterion":
                    "Balanced group sizes",
                "continuous_variable":
                    "Not applicable",
                "terciles":
                    "Designed for approximate balance",
                "p25_p75":
                    "Middle group intentionally larger",
                "data_driven_1d":
                    "Not guaranteed",
                "interpretation":
                    "Group balance affects precision in later "
                    "scenario-specific analyses.",
            },
            {
                "criterion":
                    "Simple reproducible thresholds",
                "continuous_variable":
                    "Not applicable",
                "terciles":
                    "Yes",
                "p25_p75":
                    "Yes",
                "data_driven_1d":
                    "Yes, but sample-dependent",
                "interpretation":
                    "Quantile thresholds are especially easy to "
                    "reproduce and communicate.",
            },
            {
                "criterion":
                    "Outcome-independent construction",
                "continuous_variable":
                    "Yes",
                "terciles":
                    "Yes",
                "p25_p75":
                    "Yes",
                "data_driven_1d":
                    "Yes",
                "interpretation":
                    "No candidate threshold is optimized using "
                    "award-time outcomes.",
            },
            {
                "criterion":
                    "Direct compatibility with low/medium/high scenarios",
                "continuous_variable":
                    "No categorization",
                "terciles":
                    "Yes",
                "p25_p75":
                    "Yes",
                "data_driven_1d":
                    "Yes",
                "interpretation":
                    "Scenario modeling may require categories, but "
                    "continuous analyses should remain available "
                    "for sensitivity checks.",
            },
        ]
    )

    log(
        "  Decision framework created."
    )
    log(
        "  NOTE: No automatic ranking or final scenario definition "
        "is imposed in this script."
    )
    log()

    # =========================================================================
    # 14. SAVE
    # =========================================================================

    log(
        "[14] Saving reproducible scenario-definition diagnostics..."
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        continuous_reference.to_excel(
            writer,
            sheet_name="continuous_reference",
            index=False,
        )

        threshold_audit.to_excel(
            writer,
            sheet_name="threshold_audit",
            index=False,
        )

        scenario_summaries.to_excel(
            writer,
            sheet_name="scenario_summaries",
            index=False,
        )

        method_evaluation.to_excel(
            writer,
            sheet_name="method_evaluation",
            index=False,
        )

        assignment_agreement.to_excel(
            writer,
            sheet_name="assignment_agreement",
            index=False,
        )

        procedure_audit.to_excel(
            writer,
            sheet_name="procedure_audit",
            index=False,
        )

        decision_framework.to_excel(
            writer,
            sheet_name="decision_framework",
            index=False,
        )

    log(
        f"  Output workbook: {OUTPUT_FILE.name}"
    )

    log(
        f"  Log file: {LOG_FILE.name}"
    )

    log()

    # =========================================================================
    # FINAL AUDIT
    # =========================================================================

    separator()
    log("SCENARIO-DEFINITION DIAGNOSTICS AUDIT")
    separator()

    log(
        f"Master analytical procedures:          "
        f"{len(df)}"
    )

    log(
        f"Query-count coverage:                  "
        f"{df['queries_observations_count'].notna().sum()}"
    )

    log(
        f"Total-award-time coverage:             "
        f"{df['total_award_time_days'].notna().sum()}"
    )

    log(
        f"P25/P75 thresholds:                    "
        f"{p25:.3f} / {p75:.3f}"
    )

    log(
        f"Tercile thresholds:                    "
        f"{tercile_q1:.3f} / {tercile_q2:.3f}"
    )

    log(
        f"Data-driven thresholds:                "
        f"{cluster_cut_1:.3f} / {cluster_cut_2:.3f}"
    )

    log()
    log("SCIENTIFIC SCOPE")

    log(
        "- The continuous query/observation count remains "
        "the reference representation."
    )

    log(
        "- Three candidate scenario definitions are compared."
    )

    log(
        "- Scenario thresholds are defined without using "
        "the award-time outcome."
    )

    log(
        "- Kruskal-Wallis comparisons are diagnostic and "
        "do not establish causality."
    )

    log(
        "- No scenario-definition method is automatically selected."
    )

    log(
        "- No observations are deleted."
    )

    log(
        "- No probability distribution is selected."
    )

    log(
        "- No stochastic simulation is performed."
    )

    log(
        "- No Monte Carlo procedure is performed."
    )

    log(
        "- No discrete-event simulation is performed."
    )

    log()
    separator()
    log("PIPELINE STATUS: COMPLETE")
    separator()


if __name__ == "__main__":

    warnings.filterwarnings(
        "ignore",
        category=RuntimeWarning,
    )

    try:
        main()

    except Exception as exc:
        log()
        separator()
        log("PIPELINE FAILED")
        separator()
        log(
            f"{type(exc).__name__}: {exc}"
        )
        raise
