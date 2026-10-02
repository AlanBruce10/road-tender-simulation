from pathlib import Path
import sys
import logging
import warnings
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats


# =============================================================================
# CONFIGURATION
# =============================================================================

EXPECTED_MASTER_SAMPLE_SIZE = 137

RANDOM_SEED = 2026
BOOTSTRAP_ITERATIONS = 10000
ALPHA = 0.05

SCENARIO_ORDER = ["Low", "Medium", "High"]

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]

INPUT_FILE = (
    PROJECT_ROOT
    / "02_results"
    / "statistical_analysis"
    / "07_1_scenario_definition.xlsx"
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
    / "08_1_scenario_robustness.xlsx"
)

LOG_FILE = (
    LOGS_DIR
    / "08_scenario_robustness.log"
)

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("scenario_robustness")
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
# STATISTICAL HELPERS
# =============================================================================

def holm_adjust(p_values):
    """
    Holm step-down adjustment for multiple comparisons.
    Returns adjusted p-values in original order.
    """

    p_values = np.asarray(p_values, dtype=float)
    m = len(p_values)

    order = np.argsort(p_values)
    sorted_p = p_values[order]

    adjusted_sorted = np.empty(m, dtype=float)

    running_max = 0.0

    for i, p in enumerate(sorted_p):
        adjusted = (m - i) * p
        running_max = max(running_max, adjusted)
        adjusted_sorted[i] = min(running_max, 1.0)

    adjusted = np.empty(m, dtype=float)
    adjusted[order] = adjusted_sorted

    return adjusted


def rank_biserial_mannwhitney(x, y):
    """
    Rank-biserial correlation based on Mann-Whitney U.

    Positive value means the first group tends to have larger values
    than the second group.

    r_rb = 2U/(n1*n2) - 1
    """

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    result = stats.mannwhitneyu(
        x,
        y,
        alternative="two-sided",
        method="auto",
    )

    u = float(result.statistic)

    effect = (
        2.0 * u / (len(x) * len(y))
        - 1.0
    )

    return (
        u,
        float(result.pvalue),
        float(effect),
    )


def bootstrap_statistic(
    values,
    statistic_function,
    iterations=BOOTSTRAP_ITERATIONS,
    seed=RANDOM_SEED,
):
    """
    Percentile bootstrap confidence interval.
    """

    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    if len(values) == 0:
        return np.nan, np.nan, np.nan

    rng = np.random.default_rng(seed)

    observed = float(
        statistic_function(values)
    )

    boot = np.empty(
        iterations,
        dtype=float,
    )

    n = len(values)

    for i in range(iterations):
        sample = rng.choice(
            values,
            size=n,
            replace=True,
        )

        boot[i] = statistic_function(
            sample
        )

    lower = float(
        np.percentile(
            boot,
            100 * ALPHA / 2,
        )
    )

    upper = float(
        np.percentile(
            boot,
            100 * (1 - ALPHA / 2),
        )
    )

    return observed, lower, upper


def iqr_statistic(values):
    values = np.asarray(values, dtype=float)

    return float(
        np.percentile(values, 75)
        - np.percentile(values, 25)
    )


def coefficient_of_variation(values):
    values = np.asarray(values, dtype=float)

    mean = np.mean(values)
    std = np.std(values, ddof=1)

    if mean == 0:
        return np.nan

    return float(std / mean)


def epsilon_squared_kruskal(
    h_statistic,
    n,
    k,
):
    if n <= k:
        return np.nan

    epsilon = (
        h_statistic - k + 1
    ) / (
        n - k
    )

    return float(
        max(0.0, epsilon)
    )


def jonckheere_terpstra(
    groups,
    alternative="increasing",
):
    """
    Jonckheere-Terpstra test for ordered alternatives.

    groups must be supplied in hypothesized order:
    Low, Medium, High.

    Uses asymptotic normal approximation with tie correction.
    """

    clean_groups = [
        np.asarray(group, dtype=float)
        for group in groups
    ]

    clean_groups = [
        group[np.isfinite(group)]
        for group in clean_groups
    ]

    k = len(clean_groups)

    if any(len(group) == 0 for group in clean_groups):
        return {
            "J": np.nan,
            "mean_J": np.nan,
            "variance_J": np.nan,
            "z": np.nan,
            "p_value": np.nan,
        }

    j_stat = 0.0

    for i in range(k - 1):
        for j in range(i + 1, k):

            x = clean_groups[i]
            y = clean_groups[j]

            for value_x in x:
                j_stat += np.sum(
                    value_x < y
                )

                j_stat += 0.5 * np.sum(
                    value_x == y
                )

    sizes = np.array(
        [len(group) for group in clean_groups],
        dtype=float,
    )

    n = int(np.sum(sizes))

    mean_j = (
        n ** 2
        - np.sum(sizes ** 2)
    ) / 4.0

    all_values = np.concatenate(
        clean_groups
    )

    _, tie_counts = np.unique(
        all_values,
        return_counts=True,
    )

    tie_term = np.sum(
        tie_counts
        * (tie_counts - 1)
        * (2 * tie_counts + 5)
    )

    group_term = np.sum(
        sizes
        * (sizes - 1)
        * (2 * sizes + 5)
    )

    variance_j = (
        (
            n
            * (n - 1)
            * (2 * n + 5)
            - group_term
            - tie_term
        )
        / 72.0
    )

    if variance_j <= 0:
        return {
            "J": float(j_stat),
            "mean_J": float(mean_j),
            "variance_J": float(variance_j),
            "z": np.nan,
            "p_value": np.nan,
        }

    z = (
        j_stat - mean_j
    ) / np.sqrt(variance_j)

    if alternative == "increasing":
        p_value = stats.norm.sf(z)

    elif alternative == "decreasing":
        p_value = stats.norm.cdf(z)

    else:
        p_value = (
            2
            * stats.norm.sf(abs(z))
        )

    return {
        "J": float(j_stat),
        "mean_J": float(mean_j),
        "variance_J": float(variance_j),
        "z": float(z),
        "p_value": float(p_value),
    }


# =============================================================================
# ANALYSIS HELPERS
# =============================================================================

def get_group_data(
    df,
    scenario_column,
):
    result = {}

    for scenario in SCENARIO_ORDER:

        values = df.loc[
            (
                df[scenario_column].astype(str)
                == scenario
            )
            & df[
                "total_award_time_days"
            ].notna(),
            "total_award_time_days",
        ].astype(float)

        result[scenario] = values.values

    return result


def descriptive_scenario_statistics(
    df,
    method,
    scenario_column,
):
    rows = []

    for scenario in SCENARIO_ORDER:

        subset = df.loc[
            df[scenario_column].astype(str)
            == scenario
        ].copy()

        y = subset[
            "total_award_time_days"
        ].dropna().astype(float)

        rows.append(
            {
                "method": method,
                "scenario": scenario,
                "n_master": len(subset),
                "n_award_time": len(y),
                "missing_award_time":
                    int(
                        subset[
                            "total_award_time_days"
                        ].isna().sum()
                    ),
                "mean":
                    float(y.mean())
                    if len(y) else np.nan,
                "median":
                    float(y.median())
                    if len(y) else np.nan,
                "std_dev":
                    float(y.std(ddof=1))
                    if len(y) > 1 else np.nan,
                "variance":
                    float(y.var(ddof=1))
                    if len(y) > 1 else np.nan,
                "minimum":
                    float(y.min())
                    if len(y) else np.nan,
                "p25":
                    float(y.quantile(0.25))
                    if len(y) else np.nan,
                "p75":
                    float(y.quantile(0.75))
                    if len(y) else np.nan,
                "maximum":
                    float(y.max())
                    if len(y) else np.nan,
                "iqr":
                    float(
                        y.quantile(0.75)
                        - y.quantile(0.25)
                    )
                    if len(y) else np.nan,
                "coefficient_of_variation":
                    coefficient_of_variation(y.values)
                    if len(y) > 1
                    else np.nan,
            }
        )

    return rows


def omnibus_analysis(
    df,
    method,
    scenario_column,
):
    group_dict = get_group_data(
        df,
        scenario_column,
    )

    groups = [
        group_dict[scenario]
        for scenario in SCENARIO_ORDER
    ]

    n = sum(
        len(group)
        for group in groups
    )

    kw = stats.kruskal(
        *groups
    )

    epsilon = epsilon_squared_kruskal(
        float(kw.statistic),
        n,
        len(groups),
    )

    jt = jonckheere_terpstra(
        groups,
        alternative="increasing",
    )

    medians = [
        float(np.median(group))
        for group in groups
    ]

    monotonic_medians = (
        medians[0]
        <= medians[1]
        <= medians[2]
    )

    strict_monotonic_medians = (
        medians[0]
        < medians[1]
        < medians[2]
    )

    return {
        "method": method,
        "n": n,
        "low_n": len(groups[0]),
        "medium_n": len(groups[1]),
        "high_n": len(groups[2]),
        "low_median": medians[0],
        "medium_median": medians[1],
        "high_median": medians[2],
        "median_order_non_decreasing":
            monotonic_medians,
        "median_order_strictly_increasing":
            strict_monotonic_medians,
        "kruskal_h":
            float(kw.statistic),
        "kruskal_p":
            float(kw.pvalue),
        "epsilon_squared":
            epsilon,
        "jt_J":
            jt["J"],
        "jt_z":
            jt["z"],
        "jt_p_increasing":
            jt["p_value"],
    }


def pairwise_analysis(
    df,
    method,
    scenario_column,
):
    group_dict = get_group_data(
        df,
        scenario_column,
    )

    rows = []

    pairs = list(
        combinations(
            SCENARIO_ORDER,
            2,
        )
    )

    raw_p_values = []

    temp = []

    for group_a, group_b in pairs:

        x = group_dict[group_a]
        y = group_dict[group_b]

        u, p, r_rb = (
            rank_biserial_mannwhitney(
                x,
                y,
            )
        )

        record = {
            "method": method,
            "group_a": group_a,
            "group_b": group_b,
            "n_a": len(x),
            "n_b": len(y),
            "median_a":
                float(np.median(x)),
            "median_b":
                float(np.median(y)),
            "median_difference_a_minus_b":
                float(
                    np.median(x)
                    - np.median(y)
                ),
            "mann_whitney_u": u,
            "raw_p_value": p,
            "rank_biserial_a_vs_b":
                r_rb,
        }

        temp.append(record)
        raw_p_values.append(p)

    adjusted = holm_adjust(
        raw_p_values
    )

    for record, adjusted_p in zip(
        temp,
        adjusted,
    ):
        record[
            "holm_adjusted_p"
        ] = float(adjusted_p)

        record[
            "significant_after_holm"
        ] = bool(
            adjusted_p < ALPHA
        )

        rows.append(record)

    return rows


def bootstrap_scenario_statistics(
    df,
    method,
    scenario_column,
):
    rows = []

    for scenario_index, scenario in enumerate(
        SCENARIO_ORDER
    ):

        values = df.loc[
            (
                df[scenario_column].astype(str)
                == scenario
            )
            & df[
                "total_award_time_days"
            ].notna(),
            "total_award_time_days",
        ].astype(float).values

        seed_base = (
            RANDOM_SEED
            + scenario_index * 1000
            + sum(ord(c) for c in method)
        )

        median_est, median_low, median_high = (
            bootstrap_statistic(
                values,
                np.median,
                seed=seed_base,
            )
        )

        mean_est, mean_low, mean_high = (
            bootstrap_statistic(
                values,
                np.mean,
                seed=seed_base + 1,
            )
        )

        iqr_est, iqr_low, iqr_high = (
            bootstrap_statistic(
                values,
                iqr_statistic,
                seed=seed_base + 2,
            )
        )

        std_est, std_low, std_high = (
            bootstrap_statistic(
                values,
                lambda x: np.std(
                    x,
                    ddof=1,
                ),
                seed=seed_base + 3,
            )
        )

        rows.append(
            {
                "method": method,
                "scenario": scenario,
                "n": len(values),
                "bootstrap_iterations":
                    BOOTSTRAP_ITERATIONS,
                "median":
                    median_est,
                "median_ci95_lower":
                    median_low,
                "median_ci95_upper":
                    median_high,
                "mean":
                    mean_est,
                "mean_ci95_lower":
                    mean_low,
                "mean_ci95_upper":
                    mean_high,
                "iqr":
                    iqr_est,
                "iqr_ci95_lower":
                    iqr_low,
                "iqr_ci95_upper":
                    iqr_high,
                "std_dev":
                    std_est,
                "std_ci95_lower":
                    std_low,
                "std_ci95_upper":
                    std_high,
            }
        )

    return rows


def modeling_readiness(
    df,
    method,
    scenario_column,
):
    rows = []

    for scenario in SCENARIO_ORDER:

        values = df.loc[
            (
                df[scenario_column].astype(str)
                == scenario
            )
            & df[
                "total_award_time_days"
            ].notna(),
            "total_award_time_days",
        ].astype(float)

        n = len(values)

        if n >= 30:
            size_flag = "ADEQUATE_FOR_CANDIDATE_FITTING"
        elif n >= 15:
            size_flag = "LIMITED_BUT_ANALYZABLE"
        else:
            size_flag = "SMALL_SAMPLE_CAUTION"

        rows.append(
            {
                "method": method,
                "scenario": scenario,
                "n_available":
                    n,
                "unique_award_times":
                    int(values.nunique()),
                "minimum":
                    float(values.min())
                    if n else np.nan,
                "maximum":
                    float(values.max())
                    if n else np.nan,
                "sample_size_diagnostic":
                    size_flag,
                "note":
                    (
                        "Sample-size labels are diagnostic only; "
                        "they are not formal universal thresholds "
                        "for distribution fitting."
                    ),
            }
        )

    return rows


# =============================================================================
# MAIN
# =============================================================================

def main():

    separator()
    log(
        "SCENARIO ROBUSTNESS ANALYSIS - "
        "ROAD INFRASTRUCTURE TENDERS"
    )
    separator()

    log(
        "Input: Script 07 scenario-definition diagnostics"
    )

    log(
        "Purpose: Evaluate whether low/medium/high award-time "
        "patterns are robust across candidate scenario definitions "
        "before probability-distribution fitting"
    )

    log()

    # =========================================================================
    # 1. VALIDATE INPUT
    # =========================================================================

    log("[1] Validating Script 07 input...")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    log(
        f"  Input file: {INPUT_FILE.name}"
    )

    log(
        "  Input file found."
    )

    log()

    # =========================================================================
    # 2. READ PROCEDURE AUDIT
    # =========================================================================

    log(
        "[2] Reading procedure-level scenario assignments..."
    )

    df = pd.read_excel(
        INPUT_FILE,
        sheet_name="procedure_audit",
    )

    log(
        f"  Rows: {len(df)}"
    )

    log(
        f"  Columns: {len(df.columns)}"
    )

    log()

    # =========================================================================
    # 3. VALIDATE CONTRACT
    # =========================================================================

    log(
        "[3] Validating analytical contract..."
    )

    required_columns = [
        "procedure_code",
        "queries_observations_count",
        "total_award_time_days",
        "scenario_terciles",
        "scenario_p25_p75",
        "scenario_data_driven",
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

    if df[
        "procedure_code"
    ].duplicated().any():
        raise ValueError(
            "Duplicate procedure_code values detected."
        )

    log(
        f"  Master analytical sample verified: "
        f"{len(df)}"
    )

    log(
        "  Unique procedure codes verified."
    )

    log(
        "  Scenario assignments verified."
    )

    log()

    # =========================================================================
    # 4. DEFINE METHODS
    # =========================================================================

    methods = [
        (
            "Terciles",
            "scenario_terciles",
            "PRIMARY_CANDIDATE",
        ),
        (
            "P25_P75",
            "scenario_p25_p75",
            "ROBUSTNESS_CANDIDATE",
        ),
        (
            "Data_driven_1D",
            "scenario_data_driven",
            "SENSITIVITY_CANDIDATE",
        ),
    ]

    log(
        "[4] Registering candidate scenario definitions..."
    )

    for method, _, role in methods:
        log(
            f"  {method}: {role}"
        )

    log(
        "  NOTE: These labels organize the robustness analysis; "
        "they do not constitute final scientific model selection."
    )

    log()

    # =========================================================================
    # 5. DESCRIPTIVE ROBUSTNESS
    # =========================================================================

    log(
        "[5] Evaluating descriptive robustness..."
    )

    descriptive_rows = []

    for method, column, _ in methods:

        rows = (
            descriptive_scenario_statistics(
                df,
                method,
                column,
            )
        )

        descriptive_rows.extend(
            rows
        )

        log(
            f"  {method}:"
        )

        for row in rows:
            log(
                f"    {row['scenario']}: "
                f"n={row['n_award_time']}; "
                f"median={row['median']:.2f}; "
                f"mean={row['mean']:.2f}; "
                f"SD={row['std_dev']:.2f}; "
                f"IQR={row['iqr']:.2f}"
            )

    descriptive_df = pd.DataFrame(
        descriptive_rows
    )

    log()

    # =========================================================================
    # 6. OMNIBUS AND ORDERED TREND
    # =========================================================================

    log(
        "[6] Evaluating omnibus differences and ordered trend..."
    )

    omnibus_rows = []

    for method, column, _ in methods:

        result = omnibus_analysis(
            df,
            method,
            column,
        )

        omnibus_rows.append(
            result
        )

        log(
            f"  {method}: "
            f"Kruskal-Wallis H="
            f"{result['kruskal_h']:.4f}; "
            f"p={result['kruskal_p']:.6g}; "
            f"epsilon²="
            f"{result['epsilon_squared']:.4f}"
        )

        log(
            f"    Jonckheere-Terpstra "
            f"z={result['jt_z']:.4f}; "
            f"one-sided p="
            f"{result['jt_p_increasing']:.6g}"
        )

        log(
            f"    Median order: "
            f"{result['low_median']:.2f} < "
            f"{result['medium_median']:.2f} < "
            f"{result['high_median']:.2f} "
            f"= "
            f"{result['median_order_strictly_increasing']}"
        )

    omnibus_df = pd.DataFrame(
        omnibus_rows
    )

    log()

    log(
        "  NOTE: The ordered-trend test evaluates whether "
        "award times tend to increase across Low -> Medium -> High."
    )

    log(
        "  It does not establish that query counts causally "
        "produce longer award times."
    )

    log()

    # =========================================================================
    # 7. PAIRWISE COMPARISONS
    # =========================================================================

    log(
        "[7] Running pairwise nonparametric comparisons..."
    )

    pairwise_rows = []

    for method, column, _ in methods:

        rows = pairwise_analysis(
            df,
            method,
            column,
        )

        pairwise_rows.extend(
            rows
        )

        log(
            f"  {method}:"
        )

        for row in rows:

            log(
                f"    {row['group_a']} vs "
                f"{row['group_b']}: "
                f"U={row['mann_whitney_u']:.3f}; "
                f"raw p={row['raw_p_value']:.6g}; "
                f"Holm p="
                f"{row['holm_adjusted_p']:.6g}; "
                f"rank-biserial="
                f"{row['rank_biserial_a_vs_b']:.4f}"
            )

    pairwise_df = pd.DataFrame(
        pairwise_rows
    )

    log()

    log(
        "  NOTE: Holm correction controls family-wise error "
        "within each three-comparison scenario-definition family."
    )

    log()

    # =========================================================================
    # 8. BOOTSTRAP UNCERTAINTY
    # =========================================================================

    log(
        "[8] Estimating bootstrap uncertainty..."
    )

    log(
        f"  Bootstrap iterations per statistic: "
        f"{BOOTSTRAP_ITERATIONS:,}"
    )

    log(
        f"  Reproducibility seed: {RANDOM_SEED}"
    )

    bootstrap_rows = []

    for method, column, _ in methods:

        rows = (
            bootstrap_scenario_statistics(
                df,
                method,
                column,
            )
        )

        bootstrap_rows.extend(
            rows
        )

        log(
            f"  {method}:"
        )

        for row in rows:

            log(
                f"    {row['scenario']}: "
                f"median={row['median']:.2f} "
                f"[{row['median_ci95_lower']:.2f}, "
                f"{row['median_ci95_upper']:.2f}]; "
                f"IQR={row['iqr']:.2f} "
                f"[{row['iqr_ci95_lower']:.2f}, "
                f"{row['iqr_ci95_upper']:.2f}]"
            )

    bootstrap_df = pd.DataFrame(
        bootstrap_rows
    )

    log()

    log(
        "  NOTE: Bootstrap is used here only to quantify "
        "sampling uncertainty in descriptive statistics."
    )

    log(
        "  This is not the stochastic Monte Carlo model "
        "specified for later simulation."
    )

    log()

    # =========================================================================
    # 9. MODELING READINESS
    # =========================================================================

    log(
        "[9] Auditing scenario-specific sample sizes "
        "for later distribution fitting..."
    )

    readiness_rows = []

    for method, column, _ in methods:

        rows = modeling_readiness(
            df,
            method,
            column,
        )

        readiness_rows.extend(
            rows
        )

        log(
            f"  {method}:"
        )

        for row in rows:

            log(
                f"    {row['scenario']}: "
                f"n={row['n_available']}; "
                f"unique times="
                f"{row['unique_award_times']}; "
                f"{row['sample_size_diagnostic']}"
            )

    readiness_df = pd.DataFrame(
        readiness_rows
    )

    log()

    # =========================================================================
    # 10. CROSS-METHOD ROBUSTNESS SUMMARY
    # =========================================================================

    log(
        "[10] Building cross-method robustness summary..."
    )

    robustness_rows = []

    for method, _, role in methods:

        omnibus_row = omnibus_df.loc[
            omnibus_df["method"]
            == method
        ].iloc[0]

        pairwise_method = (
            pairwise_df.loc[
                pairwise_df["method"]
                == method
            ]
        )

        all_pairwise_holm = bool(
            pairwise_method[
                "significant_after_holm"
            ].all()
        )

        readiness_method = (
            readiness_df.loc[
                readiness_df["method"]
                == method
            ]
        )

        minimum_n = int(
            readiness_method[
                "n_available"
            ].min()
        )

        robustness_rows.append(
            {
                "method": method,
                "analysis_role": role,
                "strictly_increasing_medians":
                    bool(
                        omnibus_row[
                            "median_order_strictly_increasing"
                        ]
                    ),
                "kruskal_p":
                    float(
                        omnibus_row[
                            "kruskal_p"
                        ]
                    ),
                "epsilon_squared":
                    float(
                        omnibus_row[
                            "epsilon_squared"
                        ]
                    ),
                "ordered_trend_p":
                    float(
                        omnibus_row[
                            "jt_p_increasing"
                        ]
                    ),
                "all_three_pairwise_holm_significant":
                    all_pairwise_holm,
                "minimum_scenario_n":
                    minimum_n,
                "small_sample_flag":
                    bool(
                        minimum_n < 15
                    ),
            }
        )

    robustness_df = pd.DataFrame(
        robustness_rows
    )

    for _, row in robustness_df.iterrows():

        log(
            f"  {row['method']}: "
            f"increasing medians="
            f"{row['strictly_increasing_medians']}; "
            f"all pairwise Holm significant="
            f"{row['all_three_pairwise_holm_significant']}; "
            f"minimum scenario n="
            f"{row['minimum_scenario_n']}; "
            f"small-sample flag="
            f"{row['small_sample_flag']}"
        )

    log()

    # =========================================================================
    # 11. SCIENTIFIC INTERPRETATION FLAGS
    # =========================================================================

    log(
        "[11] Building scientific interpretation audit..."
    )

    interpretation_rows = []

    for _, row in robustness_df.iterrows():

        method = row["method"]

        interpretation_rows.append(
            {
                "method": method,
                "ordered_pattern_supported":
                    bool(
                        row[
                            "strictly_increasing_medians"
                        ]
                        and
                        row[
                            "ordered_trend_p"
                        ] < ALPHA
                    ),
                "global_group_difference_detected":
                    bool(
                        row[
                            "kruskal_p"
                        ] < ALPHA
                    ),
                "all_pairwise_differences_detected_after_holm":
                    bool(
                        row[
                            "all_three_pairwise_holm_significant"
                        ]
                    ),
                "sample_size_limitation":
                    bool(
                        row[
                            "small_sample_flag"
                        ]
                    ),
                "interpretive_scope":
                    (
                        "Diagnostic evidence of scenario separation "
                        "and/or ordered association only; no causal "
                        "interpretation and no final stochastic-model "
                        "selection."
                    ),
            }
        )

    interpretation_df = pd.DataFrame(
        interpretation_rows
    )

    log(
        "  Interpretation audit created."
    )

    log()

    # =========================================================================
    # 12. SAVE
    # =========================================================================

    log(
        "[12] Saving reproducible robustness outputs..."
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        descriptive_df.to_excel(
            writer,
            sheet_name="descriptive_by_scenario",
            index=False,
        )

        omnibus_df.to_excel(
            writer,
            sheet_name="omnibus_ordered_tests",
            index=False,
        )

        pairwise_df.to_excel(
            writer,
            sheet_name="pairwise_tests",
            index=False,
        )

        bootstrap_df.to_excel(
            writer,
            sheet_name="bootstrap_uncertainty",
            index=False,
        )

        readiness_df.to_excel(
            writer,
            sheet_name="modeling_readiness",
            index=False,
        )

        robustness_df.to_excel(
            writer,
            sheet_name="robustness_summary",
            index=False,
        )

        interpretation_df.to_excel(
            writer,
            sheet_name="interpretation_audit",
            index=False,
        )

    log(
        f"  Output workbook: "
        f"{OUTPUT_FILE.name}"
    )

    log(
        f"  Log file: "
        f"{LOG_FILE.name}"
    )

    log()

    # =========================================================================
    # FINAL AUDIT
    # =========================================================================

    separator()
    log(
        "SCENARIO ROBUSTNESS AUDIT"
    )
    separator()

    log(
        f"Master analytical procedures:          "
        f"{len(df)}"
    )

    log(
        f"Available total award times:           "
        f"{df['total_award_time_days'].notna().sum()}"
    )

    log(
        f"Bootstrap iterations:                  "
        f"{BOOTSTRAP_ITERATIONS:,}"
    )

    log()

    for _, row in robustness_df.iterrows():

        log(
            f"{row['method']:<22} | "
            f"ordered={str(row['strictly_increasing_medians']):<5} | "
            f"KW p={row['kruskal_p']:.3g} | "
            f"JT p={row['ordered_trend_p']:.3g} | "
            f"all pairs={str(row['all_three_pairwise_holm_significant']):<5} | "
            f"min n={row['minimum_scenario_n']}"
        )

    log()
    log("SCIENTIFIC SCOPE")

    log(
        "- Scenario thresholds are inherited from Script 07; "
        "no new thresholds are optimized here."
    )

    log(
        "- Terciles and P25/P75 are evaluated as principal "
        "quantile-based candidates."
    )

    log(
        "- The data-driven partition is retained as a "
        "sensitivity analysis."
    )

    log(
        "- Kruskal-Wallis evaluates global distributional differences."
    )

    log(
        "- Pairwise Mann-Whitney tests use Holm multiplicity correction."
    )

    log(
        "- Jonckheere-Terpstra evaluates the prespecified "
        "Low -> Medium -> High ordering."
    )

    log(
        "- Bootstrap intervals quantify sampling uncertainty "
        "and do not constitute the later Monte Carlo simulation."
    )

    log(
        "- No observations are deleted."
    )

    log(
        "- No probability distribution is selected."
    )

    log(
        "- No Monte Carlo stochastic model is performed."
    )

    log(
        "- No discrete-event simulation is performed."
    )

    log(
        "- No causal interpretation is imposed."
    )

    log()
    separator()
    log(
        "PIPELINE STATUS: COMPLETE"
    )
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
        log(
            "PIPELINE FAILED"
        )
        separator()

        log(
            f"{type(exc).__name__}: {exc}"
        )

        raise
