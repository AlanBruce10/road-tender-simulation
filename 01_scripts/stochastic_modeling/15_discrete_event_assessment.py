"""
15_discrete_event_assessment.py

DISCRETE-EVENT SIMULATION ASSESSMENT
Road Infrastructure Tenders

Purpose
-------
Evaluate whether an explicit stage-level stochastic representation of the
procurement process is statistically feasible and scientifically additive
relative to the direct total-duration Monte Carlo model.

IMPORTANT
---------
This script DOES NOT perform the final discrete-event simulation.

It evaluates:
1. Stage-level data coverage.
2. Exact reconstruction of total award time.
3. Distributional behavior of stage durations.
4. Dependence between stages.
5. Dependence conditional on Low/Medium/High scenarios.
6. Scenario-stage relationships.
7. Whether an independence assumption would be defensible.
8. Whether stage decomposition contains information beyond total-duration
   simulation.
9. Whether DES should proceed to implementation.

No missing values are imputed.
No observations are deleted from the master analytical population.
No causal interpretation is imposed.
"""

from pathlib import Path
import warnings
import numpy as np
import pandas as pd

from scipy import stats

warnings.filterwarnings("ignore")

# =============================================================================
# CONFIGURATION
# =============================================================================

MASTER_EXPECTED_N = 137

ROOT = Path(__file__).resolve().parents[2]

INPUT_MASTER = ROOT / "02_results" / "03_1_integrated_dataset.xlsx"

INPUT_SCENARIOS = (
    ROOT
    / "02_results"
    / "statistical_analysis"
    / "07_1_scenario_definition.xlsx"
)

INPUT_MC = (
    ROOT
    / "02_results"
    / "stochastic_modeling"
    / "14_1_monte_carlo_simulation.xlsx"
)

OUTPUT_DIR = ROOT / "02_results" / "stochastic_modeling"
LOG_DIR = ROOT / "03_logs" / "stochastic_modeling"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "15_1_discrete_event_assessment.xlsx"
LOG_FILE = LOG_DIR / "15_discrete_event_assessment.log"

# Reproducible bootstrap settings
BOOTSTRAP_ITERATIONS = 10000
RANDOM_SEED = 2026

# Numerical tolerance for arithmetic reconstruction
ARITHMETIC_TOLERANCE = 1e-9


# =============================================================================
# LOGGING
# =============================================================================

LOG_LINES = []


def log(message=""):
    text = str(message)
    print(text)
    LOG_LINES.append(text)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def safe_spearman(x, y):
    data = pd.DataFrame({"x": x, "y": y}).dropna()

    if len(data) < 3:
        return np.nan, np.nan

    if data["x"].nunique() < 2 or data["y"].nunique() < 2:
        return np.nan, np.nan

    result = stats.spearmanr(data["x"], data["y"])

    return float(result.statistic), float(result.pvalue)


def safe_pearson(x, y):
    data = pd.DataFrame({"x": x, "y": y}).dropna()

    if len(data) < 3:
        return np.nan, np.nan

    if data["x"].nunique() < 2 or data["y"].nunique() < 2:
        return np.nan, np.nan

    result = stats.pearsonr(data["x"], data["y"])

    return float(result.statistic), float(result.pvalue)


def safe_kendall(x, y):
    data = pd.DataFrame({"x": x, "y": y}).dropna()

    if len(data) < 3:
        return np.nan, np.nan

    if data["x"].nunique() < 2 or data["y"].nunique() < 2:
        return np.nan, np.nan

    result = stats.kendalltau(data["x"], data["y"])

    return float(result.statistic), float(result.pvalue)


def descriptive_stats(series):
    x = pd.Series(series).dropna().astype(float)

    if len(x) == 0:
        return {
            "n": 0,
            "mean": np.nan,
            "median": np.nan,
            "std_dev": np.nan,
            "minimum": np.nan,
            "p25": np.nan,
            "p75": np.nan,
            "p90": np.nan,
            "p95": np.nan,
            "maximum": np.nan,
            "iqr": np.nan,
            "skewness": np.nan,
            "excess_kurtosis": np.nan,
        }

    return {
        "n": len(x),
        "mean": x.mean(),
        "median": x.median(),
        "std_dev": x.std(ddof=1),
        "minimum": x.min(),
        "p25": x.quantile(0.25),
        "p75": x.quantile(0.75),
        "p90": x.quantile(0.90),
        "p95": x.quantile(0.95),
        "maximum": x.max(),
        "iqr": x.quantile(0.75) - x.quantile(0.25),
        "skewness": stats.skew(x, bias=False) if len(x) >= 3 else np.nan,
        "excess_kurtosis": (
            stats.kurtosis(x, fisher=True, bias=False)
            if len(x) >= 4
            else np.nan
        ),
    }


def bootstrap_spearman_ci(x, y, iterations=10000, seed=2026):
    data = pd.DataFrame({"x": x, "y": y}).dropna()

    n = len(data)

    if n < 4:
        return np.nan, np.nan, np.nan, 0

    x_arr = data["x"].to_numpy(dtype=float)
    y_arr = data["y"].to_numpy(dtype=float)

    observed, _ = safe_spearman(x_arr, y_arr)

    rng = np.random.default_rng(seed)

    values = []

    for _ in range(iterations):
        idx = rng.integers(0, n, size=n)

        xb = x_arr[idx]
        yb = y_arr[idx]

        if len(np.unique(xb)) < 2 or len(np.unique(yb)) < 2:
            continue

        rho = stats.spearmanr(xb, yb).statistic

        if np.isfinite(rho):
            values.append(float(rho))

    if len(values) == 0:
        return observed, np.nan, np.nan, 0

    values = np.asarray(values)

    lower = np.quantile(values, 0.025)
    upper = np.quantile(values, 0.975)

    return observed, lower, upper, len(values)


def format_number(value, digits=4):
    if pd.isna(value):
        return "NA"

    return f"{value:.{digits}f}"


# =============================================================================
# START
# =============================================================================

log("=" * 78)
log("DISCRETE-EVENT SIMULATION ASSESSMENT - ROAD INFRASTRUCTURE TENDERS")
log("=" * 78)
log(
    "Purpose: Evaluate whether stage-level process simulation is feasible and "
    "scientifically additive."
)
log("")
log("IMPORTANT: This script does NOT perform the final discrete-event simulation.")
log("")


# =============================================================================
# 1. VALIDATE INPUT FILES
# =============================================================================

log("[1] Validating analytical inputs...")

required_files = [
    INPUT_MASTER,
    INPUT_SCENARIOS,
    INPUT_MC,
]

for file in required_files:
    if not file.exists():
        raise FileNotFoundError(f"Required input file not found: {file}")

    log(f"  Found: {file.name}")

log("")


# =============================================================================
# 2. READ INPUT DATA
# =============================================================================

log("[2] Reading source datasets...")

master = pd.read_excel(INPUT_MASTER)

scenario_audit = pd.read_excel(
    INPUT_SCENARIOS,
    sheet_name="procedure_audit"
)

log(f"  Master rows: {len(master)}")
log(f"  Scenario-audit rows: {len(scenario_audit)}")
log("")


# =============================================================================
# 3. VALIDATE ANALYTICAL CONTRACT
# =============================================================================

log("[3] Validating analytical contract...")

required_master_columns = [
    "procedure_code",
    "queries_observations_count",
    "notice_date",
    "integrated_terms_date",
    "award_date",
    "query_stage_duration_days",
    "evaluation_stage_duration_days",
    "total_award_time_days",
]

missing_master_columns = [
    col for col in required_master_columns
    if col not in master.columns
]

if missing_master_columns:
    raise ValueError(
        "Missing required master columns: "
        + ", ".join(missing_master_columns)
    )

if len(master) != MASTER_EXPECTED_N:
    raise ValueError(
        f"Expected master analytical population n={MASTER_EXPECTED_N}, "
        f"found n={len(master)}."
    )

if master["procedure_code"].duplicated().any():
    raise ValueError("procedure_code is not unique in master dataset.")

required_scenario_columns = [
    "procedure_code",
    "scenario_terciles",
]

missing_scenario_columns = [
    col for col in required_scenario_columns
    if col not in scenario_audit.columns
]

if missing_scenario_columns:
    raise ValueError(
        "Missing required Script 07 columns: "
        + ", ".join(missing_scenario_columns)
    )

log(f"  Master analytical sample verified: {len(master)}")
log("  procedure_code uniqueness verified.")
log("  Primary tercile scenario assignments found.")
log("")


# =============================================================================
# 4. MERGE PRIMARY SCENARIO ASSIGNMENTS
# =============================================================================

log("[4] Merging primary tercile scenario assignments...")

df = master.merge(
    scenario_audit[
        [
            "procedure_code",
            "scenario_terciles",
        ]
    ],
    on="procedure_code",
    how="left",
    validate="one_to_one",
)

if df["scenario_terciles"].isna().any():
    raise ValueError(
        "At least one master procedure lacks a tercile scenario assignment."
    )

log(f"  Merged analytical rows: {len(df)}")
log("  All procedures have primary scenario assignments.")
log("")


# =============================================================================
# 5. ASSESS STAGE-LEVEL COVERAGE
# =============================================================================

log("[5] Assessing stage-level temporal coverage...")

query_available = df["query_stage_duration_days"].notna()
evaluation_available = df["evaluation_stage_duration_days"].notna()
total_available = df["total_award_time_days"].notna()

complete_stage = query_available & evaluation_available

n_query = int(query_available.sum())
n_eval = int(evaluation_available.sum())
n_complete = int(complete_stage.sum())
n_total = int(total_available.sum())

coverage_query = n_query / len(df)
coverage_eval = n_eval / len(df)
coverage_complete = n_complete / len(df)
coverage_total = n_total / len(df)

log(
    f"  Query-stage duration:       "
    f"{n_query}/{len(df)} ({coverage_query:.2%})"
)

log(
    f"  Evaluation-stage duration:  "
    f"{n_eval}/{len(df)} ({coverage_eval:.2%})"
)

log(
    f"  Complete stage decomposition: "
    f"{n_complete}/{len(df)} ({coverage_complete:.2%})"
)

log(
    f"  Total award time:           "
    f"{n_total}/{len(df)} ({coverage_total:.2%})"
)

log("")


# =============================================================================
# 6. VERIFY EXACT TEMPORAL RECONSTRUCTION
# =============================================================================

log("[6] Verifying temporal reconstruction...")

stage_df = df.loc[complete_stage].copy()

stage_df["reconstructed_total_days"] = (
    stage_df["query_stage_duration_days"]
    + stage_df["evaluation_stage_duration_days"]
)

stage_df["reconstruction_difference"] = (
    stage_df["reconstructed_total_days"]
    - stage_df["total_award_time_days"]
)

stage_df["exact_reconstruction"] = (
    stage_df["reconstruction_difference"].abs()
    <= ARITHMETIC_TOLERANCE
)

reconstruction_n = stage_df["total_award_time_days"].notna().sum()

if reconstruction_n > 0:
    exact_n = int(
        stage_df.loc[
            stage_df["total_award_time_days"].notna(),
            "exact_reconstruction"
        ].sum()
    )

    exact_rate = exact_n / reconstruction_n
else:
    exact_n = 0
    exact_rate = np.nan

max_abs_difference = (
    stage_df["reconstruction_difference"].abs().max()
    if reconstruction_n > 0
    else np.nan
)

log(
    f"  Stage-decomposed procedures with total time: "
    f"{reconstruction_n}"
)

log(
    f"  Exact arithmetic reconstructions: "
    f"{exact_n}/{reconstruction_n} ({exact_rate:.2%})"
)

log(
    f"  Maximum absolute reconstruction difference: "
    f"{format_number(max_abs_difference, 6)} days"
)

log("")


# =============================================================================
# 7. DESCRIBE STAGE DURATIONS
# =============================================================================

log("[7] Diagnosing stage-duration distributions...")

stage_variables = [
    "query_stage_duration_days",
    "evaluation_stage_duration_days",
]

stage_descriptive_rows = []

for variable in stage_variables:

    desc = descriptive_stats(stage_df[variable])

    row = {
        "variable": variable,
        **desc,
    }

    stage_descriptive_rows.append(row)

    log(
        f"  {variable}: "
        f"n={desc['n']}; "
        f"mean={desc['mean']:.2f}; "
        f"median={desc['median']:.2f}; "
        f"SD={desc['std_dev']:.2f}; "
        f"skewness={desc['skewness']:.3f}; "
        f"P95={desc['p95']:.2f}"
    )

stage_descriptive = pd.DataFrame(stage_descriptive_rows)

log("")


# =============================================================================
# 8. TEST STAGE DEPENDENCE
# =============================================================================

log("[8] Evaluating dependence between temporal stages...")

x = stage_df["query_stage_duration_days"]
y = stage_df["evaluation_stage_duration_days"]

pearson_r, pearson_p = safe_pearson(x, y)
spearman_rho, spearman_p = safe_spearman(x, y)
kendall_tau, kendall_p = safe_kendall(x, y)

(
    bootstrap_rho,
    bootstrap_lower,
    bootstrap_upper,
    bootstrap_valid,
) = bootstrap_spearman_ci(
    x,
    y,
    iterations=BOOTSTRAP_ITERATIONS,
    seed=RANDOM_SEED,
)

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

log(
    f"  Bootstrap Spearman 95% CI: "
    f"[{bootstrap_lower:.4f}, {bootstrap_upper:.4f}]"
)

log(
    f"  Valid bootstrap iterations: "
    f"{bootstrap_valid:,}/{BOOTSTRAP_ITERATIONS:,}"
)

log("")
log(
    "  NOTE: Statistical dependence between stages is evaluated explicitly; "
    "independence is not assumed automatically."
)
log("")


stage_dependence = pd.DataFrame(
    [
        {
            "analysis": "query_stage_vs_evaluation_stage",
            "n": len(stage_df),
            "pearson_r": pearson_r,
            "pearson_p": pearson_p,
            "spearman_rho": spearman_rho,
            "spearman_p": spearman_p,
            "kendall_tau": kendall_tau,
            "kendall_p": kendall_p,
            "bootstrap_spearman": bootstrap_rho,
            "bootstrap_ci_lower": bootstrap_lower,
            "bootstrap_ci_upper": bootstrap_upper,
            "bootstrap_valid_iterations": bootstrap_valid,
        }
    ]
)


# =============================================================================
# 9. ASSESS DEPENDENCE WITHIN SCENARIOS
# =============================================================================

log("[9] Evaluating stage dependence within Low/Medium/High scenarios...")

scenario_dependence_rows = []

scenario_order = ["Low", "Medium", "High"]

for scenario in scenario_order:

    subset = stage_df[
        stage_df["scenario_terciles"] == scenario
    ].copy()

    pr, pp = safe_pearson(
        subset["query_stage_duration_days"],
        subset["evaluation_stage_duration_days"],
    )

    sr, sp = safe_spearman(
        subset["query_stage_duration_days"],
        subset["evaluation_stage_duration_days"],
    )

    kt, kp = safe_kendall(
        subset["query_stage_duration_days"],
        subset["evaluation_stage_duration_days"],
    )

    scenario_dependence_rows.append(
        {
            "scenario": scenario,
            "n": len(subset),
            "pearson_r": pr,
            "pearson_p": pp,
            "spearman_rho": sr,
            "spearman_p": sp,
            "kendall_tau": kt,
            "kendall_p": kp,
        }
    )

    log(
        f"  {scenario}: n={len(subset)}; "
        f"Pearson={format_number(pr)}; "
        f"Spearman={format_number(sr)}; "
        f"Kendall={format_number(kt)}"
    )

scenario_dependence = pd.DataFrame(scenario_dependence_rows)

log("")


# =============================================================================
# 10. DESCRIBE STAGES BY PRIMARY SCENARIO
# =============================================================================

log("[10] Describing temporal stages by primary scenario...")

scenario_stage_rows = []

for scenario in scenario_order:

    subset = stage_df[
        stage_df["scenario_terciles"] == scenario
    ]

    for variable in stage_variables:

        desc = descriptive_stats(subset[variable])

        scenario_stage_rows.append(
            {
                "scenario": scenario,
                "variable": variable,
                **desc,
            }
        )

        log(
            f"  {scenario} | {variable}: "
            f"n={desc['n']}; "
            f"median={desc['median']:.2f}; "
            f"mean={desc['mean']:.2f}; "
            f"SD={desc['std_dev']:.2f}"
        )

scenario_stage_summary = pd.DataFrame(scenario_stage_rows)

log("")


# =============================================================================
# 11. TEST SCENARIO DIFFERENCES FOR EACH STAGE
# =============================================================================

log("[11] Evaluating scenario differences in each temporal stage...")

stage_scenario_test_rows = []

for variable in stage_variables:

    groups = []

    group_sizes = []

    for scenario in scenario_order:

        values = (
            stage_df.loc[
                stage_df["scenario_terciles"] == scenario,
                variable,
            ]
            .dropna()
            .astype(float)
            .to_numpy()
        )

        groups.append(values)
        group_sizes.append(len(values))

    if all(len(group) > 0 for group in groups):
        kw = stats.kruskal(*groups)

        h_stat = float(kw.statistic)
        p_value = float(kw.pvalue)

        n_total_stage = sum(group_sizes)
        k = len(groups)

        if n_total_stage > k:
            epsilon_squared = max(
                0.0,
                (h_stat - k + 1)
                / (n_total_stage - k)
            )
        else:
            epsilon_squared = np.nan

    else:
        h_stat = np.nan
        p_value = np.nan
        epsilon_squared = np.nan

    medians = [
        np.median(group) if len(group) else np.nan
        for group in groups
    ]

    ordered_medians = (
        medians[0] < medians[1] < medians[2]
        if all(np.isfinite(medians))
        else False
    )

    stage_scenario_test_rows.append(
        {
            "variable": variable,
            "low_n": group_sizes[0],
            "medium_n": group_sizes[1],
            "high_n": group_sizes[2],
            "low_median": medians[0],
            "medium_median": medians[1],
            "high_median": medians[2],
            "strictly_increasing_medians": ordered_medians,
            "kruskal_h": h_stat,
            "kruskal_p": p_value,
            "epsilon_squared": epsilon_squared,
        }
    )

    log(
        f"  {variable}: "
        f"H={h_stat:.4f}; "
        f"p={p_value:.6g}; "
        f"epsilon²={epsilon_squared:.4f}; "
        f"ordered medians={ordered_medians}"
    )

stage_scenario_tests = pd.DataFrame(stage_scenario_test_rows)

log("")


# =============================================================================
# 12. QUANTIFY EACH STAGE'S CONTRIBUTION TO TOTAL DURATION
# =============================================================================

log("[12] Quantifying stage contributions to total award time...")

valid_total_stage = stage_df[
    stage_df["total_award_time_days"].notna()
    & (stage_df["total_award_time_days"] > 0)
].copy()

valid_total_stage["query_stage_share"] = (
    valid_total_stage["query_stage_duration_days"]
    / valid_total_stage["total_award_time_days"]
)

valid_total_stage["evaluation_stage_share"] = (
    valid_total_stage["evaluation_stage_duration_days"]
    / valid_total_stage["total_award_time_days"]
)

stage_share_rows = []

for variable in [
    "query_stage_share",
    "evaluation_stage_share",
]:

    desc = descriptive_stats(valid_total_stage[variable])

    stage_share_rows.append(
        {
            "variable": variable,
            **desc,
        }
    )

    log(
        f"  {variable}: "
        f"median={desc['median']:.3f}; "
        f"mean={desc['mean']:.3f}; "
        f"IQR={desc['iqr']:.3f}"
    )

stage_shares = pd.DataFrame(stage_share_rows)

log("")


# =============================================================================
# 13. TEST WHETHER QUERY COUNTS RELATE TO EACH STAGE
# =============================================================================

log("[13] Evaluating query-count relationships with individual stages...")

query_stage_relationship_rows = []

for variable in stage_variables:

    subset = stage_df[
        [
            "queries_observations_count",
            variable,
        ]
    ].dropna()

    pr, pp = safe_pearson(
        subset["queries_observations_count"],
        subset[variable],
    )

    sr, sp = safe_spearman(
        subset["queries_observations_count"],
        subset[variable],
    )

    kt, kp = safe_kendall(
        subset["queries_observations_count"],
        subset[variable],
    )

    query_stage_relationship_rows.append(
        {
            "outcome": variable,
            "n": len(subset),
            "pearson_r": pr,
            "pearson_p": pp,
            "spearman_rho": sr,
            "spearman_p": sp,
            "kendall_tau": kt,
            "kendall_p": kp,
        }
    )

    log(
        f"  queries_observations_count vs {variable}: "
        f"n={len(subset)}; "
        f"Pearson={pr:.4f}; "
        f"Spearman={sr:.4f}; "
        f"Kendall={kt:.4f}"
    )

query_stage_relationships = pd.DataFrame(
    query_stage_relationship_rows
)

log("")


# =============================================================================
# 14. ASSESS WHETHER INDEPENDENT STAGE SAMPLING WOULD BE DEFENSIBLE
# =============================================================================

log("[14] Assessing independence assumption for stage simulation...")

dependence_detected = (
    np.isfinite(spearman_p)
    and spearman_p < 0.05
)

dependence_magnitude = abs(spearman_rho)

if not dependence_detected:
    independence_status = "NOT_REJECTED_BUT_NOT_PROVEN"
    independence_note = (
        "No statistically detectable monotonic dependence was identified, "
        "but independence cannot be established solely from a non-significant test."
    )

elif dependence_magnitude < 0.20:
    independence_status = "WEAK_DEPENDENCE_CAUTION"
    independence_note = (
        "Dependence is statistically detectable but weak. "
        "Independent stage sampling would require sensitivity analysis."
    )

else:
    independence_status = "INDEPENDENCE_NOT_SUPPORTED"
    independence_note = (
        "Stage dependence is statistically detectable and non-trivial. "
        "A DES implementation should preserve dependence rather than sample "
        "the two stages independently."
    )

log(f"  Independence assessment: {independence_status}")
log(f"  Interpretation: {independence_note}")
log("")


independence_audit = pd.DataFrame(
    [
        {
            "criterion": "stage_dependence",
            "spearman_rho": spearman_rho,
            "spearman_p": spearman_p,
            "bootstrap_ci_lower": bootstrap_lower,
            "bootstrap_ci_upper": bootstrap_upper,
            "status": independence_status,
            "interpretation": independence_note,
        }
    ]
)


# =============================================================================
# 15. ASSESS SCIENTIFIC ADDITIVE VALUE OF STAGE DECOMPOSITION
# =============================================================================

log("[15] Assessing incremental scientific value of stage decomposition...")

stage_query_rhos = dict(
    zip(
        query_stage_relationships["outcome"],
        query_stage_relationships["spearman_rho"],
    )
)

query_stage_rho = stage_query_rhos.get(
    "query_stage_duration_days",
    np.nan,
)

evaluation_stage_rho = stage_query_rhos.get(
    "evaluation_stage_duration_days",
    np.nan,
)

stage_relationships_differ = (
    np.isfinite(query_stage_rho)
    and np.isfinite(evaluation_stage_rho)
    and abs(query_stage_rho - evaluation_stage_rho) >= 0.10
)

both_stages_variable = (
    stage_descriptive.loc[
        stage_descriptive["variable"]
        == "query_stage_duration_days",
        "std_dev"
    ].iloc[0] > 0
    and
    stage_descriptive.loc[
        stage_descriptive["variable"]
        == "evaluation_stage_duration_days",
        "std_dev"
    ].iloc[0] > 0
)

coverage_sufficient_for_assessment = (
    coverage_complete >= 0.70
)

exact_process_identity = (
    np.isfinite(exact_rate)
    and exact_rate >= 0.99
)

additive_rows = [
    {
        "criterion": "stage_coverage",
        "observed_value": coverage_complete,
        "rule": ">= 0.70 for feasibility assessment",
        "status": (
            "PASS"
            if coverage_sufficient_for_assessment
            else "CAUTION"
        ),
        "scientific_meaning": (
            "Stage-level data exist for a substantial majority of the master population."
        ),
    },
    {
        "criterion": "exact_temporal_reconstruction",
        "observed_value": exact_rate,
        "rule": ">= 0.99",
        "status": (
            "PASS"
            if exact_process_identity
            else "FAIL"
        ),
        "scientific_meaning": (
            "The two observed stages reconstruct the total award-time outcome."
        ),
    },
    {
        "criterion": "nondegenerate_stage_variability",
        "observed_value": bool(both_stages_variable),
        "rule": "Both stages must contain empirical variability",
        "status": (
            "PASS"
            if both_stages_variable
            else "FAIL"
        ),
        "scientific_meaning": (
            "Stage decomposition represents stochastic quantities rather than constants."
        ),
    },
    {
        "criterion": "stage_specific_information",
        "observed_value": bool(stage_relationships_differ),
        "rule": (
            "Absolute difference between stage-specific Spearman coefficients >= 0.10"
        ),
        "status": (
            "PASS"
            if stage_relationships_differ
            else "CAUTION"
        ),
        "scientific_meaning": (
            "The information-asymmetry proxy has meaningfully different associations "
            "with the two temporal stages."
        ),
    },
    {
        "criterion": "dependence_requires_process_structure",
        "observed_value": spearman_rho,
        "rule": (
            "Dependence must be explicitly considered rather than assumed absent"
        ),
        "status": (
            "PASS"
            if independence_status == "INDEPENDENCE_NOT_SUPPORTED"
            else "CAUTION"
        ),
        "scientific_meaning": (
            "Joint stage modeling may contain information that is hidden by direct "
            "simulation of total duration."
        ),
    },
]

additive_value_audit = pd.DataFrame(additive_rows)

for _, row in additive_value_audit.iterrows():
    log(
        f"  {row['criterion']}: "
        f"{row['status']}"
    )

log("")


# =============================================================================
# 16. ASSESS LIMITATIONS OF A STAGE-LEVEL DES
# =============================================================================

log("[16] Auditing limitations of a possible discrete-event model...")

missing_stage_n = len(df) - n_complete
missing_stage_rate = missing_stage_n / len(df)

limitations = pd.DataFrame(
    [
        {
            "limitation": "Incomplete stage decomposition",
            "observed_result": (
                f"{missing_stage_n}/{len(df)} procedures "
                f"({missing_stage_rate:.2%}) lack complete stage durations"
            ),
            "implication": (
                "A stage-level DES would use fewer observed procedures than the "
                "direct total-duration Monte Carlo model."
            ),
        },
        {
            "limitation": "Non-random missingness concern",
            "observed_result": (
                "Script 05 identified systematic associations with availability "
                "of integrated-terms dates."
            ),
            "implication": (
                "The n=109 stage-level subset must not be treated as automatically "
                "representative of all n=137 procedures."
            ),
        },
        {
            "limitation": "Stage dependence",
            "observed_result": (
                f"Spearman rho={spearman_rho:.4f}"
            ),
            "implication": (
                "Independent random sampling of stage durations may distort the "
                "distribution of reconstructed total time."
            ),
        },
        {
            "limitation": "Observed process resolution",
            "observed_result": (
                "Only two empirical temporal stages are available in the analytical dataset."
            ),
            "implication": (
                "The model is a parsimonious stage-process representation rather than "
                "a detailed operational DES with queues, resources, or individual events."
            ),
        },
        {
            "limitation": "Causal interpretation",
            "observed_result": (
                "The analytical design is observational."
            ),
            "implication": (
                "DES may reproduce stochastic process behavior but cannot by itself "
                "establish causal effects of queries/observations."
            ),
        },
    ]
)

for _, row in limitations.iterrows():
    log(f"  - {row['limitation']}: {row['observed_result']}")

log("")


# =============================================================================
# 17. BUILD DES AUTHORIZATION GATES
# =============================================================================

log("[17] Evaluating discrete-event simulation authorization gates...")

des1_pass = coverage_complete >= 0.70
des2_pass = exact_process_identity
des3_pass = both_stages_variable

# Dependence is not a reason to reject DES.
# It means dependence must be modeled.
des4_pass = (
    np.isfinite(spearman_rho)
    and np.isfinite(spearman_p)
)

# Incremental scientific value:
# stage-specific relationships differ OR nontrivial stage dependence exists.
incremental_value = (
    stage_relationships_differ
    or (
        np.isfinite(spearman_rho)
        and abs(spearman_rho) >= 0.20
    )
)

des5_pass = incremental_value

authorization_gates = pd.DataFrame(
    [
        {
            "gate": "DES1",
            "criterion": "Stage-level coverage sufficient for modeling",
            "status": "PASS" if des1_pass else "CAUTION",
            "observed_result": f"{coverage_complete:.2%}",
        },
        {
            "gate": "DES2",
            "criterion": "Stages reconstruct total award time",
            "status": "PASS" if des2_pass else "FAIL",
            "observed_result": (
                f"{exact_rate:.2%}"
                if np.isfinite(exact_rate)
                else "NA"
            ),
        },
        {
            "gate": "DES3",
            "criterion": "Both stages contain stochastic variability",
            "status": "PASS" if des3_pass else "FAIL",
            "observed_result": str(both_stages_variable),
        },
        {
            "gate": "DES4",
            "criterion": "Stage dependence is empirically estimable",
            "status": "PASS" if des4_pass else "FAIL",
            "observed_result": (
                f"Spearman rho={format_number(spearman_rho)}"
            ),
        },
        {
            "gate": "DES5",
            "criterion": (
                "Stage decomposition provides incremental analytical value"
            ),
            "status": "PASS" if des5_pass else "CAUTION",
            "observed_result": str(incremental_value),
        },
    ]
)

for _, row in authorization_gates.iterrows():
    log(
        f"  {row['gate']} | "
        f"{row['status']:<7} | "
        f"{row['criterion']}"
    )

log("")


# =============================================================================
# 18. FINAL DES METHODOLOGICAL DECISION
# =============================================================================

log("[18] Determining methodological DES decision...")

hard_fail = (
    (not des2_pass)
    or (not des3_pass)
    or (not des4_pass)
)

if hard_fail:

    final_des_status = "DES_NOT_JUSTIFIED"

    final_des_note = (
        "The observed stage structure does not satisfy the minimum "
        "requirements for an explicit stage-level stochastic model."
    )

elif des1_pass and des5_pass:

    # Because Script 05 already identified systematic missingness,
    # authorization remains explicitly qualified.
    final_des_status = "DES_AUTHORIZED_WITH_CAUTION"

    final_des_note = (
        "A two-stage stochastic process representation is scientifically "
        "defensible and provides incremental analytical information, but "
        "implementation must preserve stage dependence and explicitly report "
        "the n=109 stage-coverage limitation and the missing-data findings "
        "from Script 05."
    )

else:

    final_des_status = "DES_AUTHORIZED_WITH_CAUTION"

    final_des_note = (
        "Stage-level simulation is technically feasible, but its incremental "
        "scientific value relative to direct total-duration Monte Carlo is "
        "limited or uncertain. Any implementation should therefore be treated "
        "as a secondary process-decomposition analysis rather than the primary "
        "stochastic model."
    )

log(f"  Final DES status: {final_des_status}")
log(f"  Interpretation: {final_des_note}")
log("")


final_decision = pd.DataFrame(
    [
        {
            "component": "Discrete-event simulation",
            "decision": final_des_status,
            "master_population_n": len(df),
            "stage_complete_n": n_complete,
            "stage_coverage": coverage_complete,
            "exact_reconstruction_rate": exact_rate,
            "stage_spearman_rho": spearman_rho,
            "stage_spearman_p": spearman_p,
            "stage_specific_information": stage_relationships_differ,
            "incremental_value": incremental_value,
            "scientific_note": final_des_note,
        }
    ]
)


# =============================================================================
# 19. DEFINE NEXT-PHASE PROTOCOL
# =============================================================================

log("[19] Building prespecified next-phase protocol...")

if final_des_status == "DES_NOT_JUSTIFIED":

    next_protocol_rows = [
        {
            "step": 1,
            "action": "Do not implement a substantive DES",
            "purpose": (
                "Avoid adding model complexity without sufficient empirical support."
            ),
        },
        {
            "step": 2,
            "action": "Proceed to model validation",
            "purpose": (
                "Validate the authorized Monte Carlo model against observed behavior."
            ),
        },
        {
            "step": 3,
            "action": "Retain stage analysis as diagnostic evidence",
            "purpose": (
                "Report why DES was evaluated and methodologically rejected."
            ),
        },
    ]

else:

    next_protocol_rows = [
        {
            "step": 1,
            "action": (
                "Construct a two-stage stochastic process model"
            ),
            "purpose": (
                "Represent query/integration and evaluation/award durations separately."
            ),
        },
        {
            "step": 2,
            "action": (
                "Preserve empirical dependence between stage durations"
            ),
            "purpose": (
                "Avoid the unsupported assumption that stage durations are independent."
            ),
        },
        {
            "step": 3,
            "action": (
                "Compare reconstructed DES total times with direct Monte Carlo totals"
            ),
            "purpose": (
                "Quantify whether process decomposition materially changes stochastic conclusions."
            ),
        },
        {
            "step": 4,
            "action": (
                "Treat DES as secondary if incremental predictive value is limited"
            ),
            "purpose": (
                "Prevent unnecessary model complexity from being presented as scientific improvement."
            ),
        },
        {
            "step": 5,
            "action": (
                "Carry stage-coverage limitation into validation"
            ),
            "purpose": (
                "Ensure n=109 is distinguished from the n=136 total-duration sample."
            ),
        },
    ]

next_protocol = pd.DataFrame(next_protocol_rows)

for _, row in next_protocol.iterrows():
    log(
        f"  {int(row['step'])}. "
        f"{row['action']}"
    )

log("")


# =============================================================================
# 20. BUILD COVERAGE AUDIT
# =============================================================================

coverage_audit = pd.DataFrame(
    [
        {
            "component": "Master analytical population",
            "available_n": len(df),
            "total_n": len(df),
            "coverage": 1.0,
        },
        {
            "component": "Query-stage duration",
            "available_n": n_query,
            "total_n": len(df),
            "coverage": coverage_query,
        },
        {
            "component": "Evaluation-stage duration",
            "available_n": n_eval,
            "total_n": len(df),
            "coverage": coverage_eval,
        },
        {
            "component": "Complete stage decomposition",
            "available_n": n_complete,
            "total_n": len(df),
            "coverage": coverage_complete,
        },
        {
            "component": "Total award time",
            "available_n": n_total,
            "total_n": len(df),
            "coverage": coverage_total,
        },
    ]
)


# =============================================================================
# 21. BUILD PROCEDURE-LEVEL STAGE AUDIT
# =============================================================================

procedure_columns = [
    "procedure_code",
    "queries_observations_count",
    "scenario_terciles",
    "query_stage_duration_days",
    "evaluation_stage_duration_days",
    "total_award_time_days",
]

procedure_stage_audit = df[procedure_columns].copy()

procedure_stage_audit["complete_stage_decomposition"] = (
    procedure_stage_audit[
        [
            "query_stage_duration_days",
            "evaluation_stage_duration_days",
        ]
    ]
    .notna()
    .all(axis=1)
)

procedure_stage_audit["reconstructed_total_days"] = (
    procedure_stage_audit["query_stage_duration_days"]
    + procedure_stage_audit["evaluation_stage_duration_days"]
)

procedure_stage_audit["reconstruction_difference"] = (
    procedure_stage_audit["reconstructed_total_days"]
    - procedure_stage_audit["total_award_time_days"]
)


# =============================================================================
# 22. BUILD SCIENTIFIC INTERPRETATION AUDIT
# =============================================================================

interpretation_audit = pd.DataFrame(
    [
        {
            "issue": "Role of Script 15",
            "authorized_interpretation": (
                "Methodological feasibility and incremental-value assessment."
            ),
            "not_authorized": (
                "Claiming that a DES has already been performed."
            ),
        },
        {
            "issue": "Stage dependence",
            "authorized_interpretation": (
                "Observed dependence must be considered in any stage-level simulation."
            ),
            "not_authorized": (
                "Assuming independent stage durations without sensitivity analysis."
            ),
        },
        {
            "issue": "Stage coverage",
            "authorized_interpretation": (
                "Stage analyses use the available n=109 decomposition subset."
            ),
            "not_authorized": (
                "Presenting n=109 as if it were the complete master population."
            ),
        },
        {
            "issue": "Missingness",
            "authorized_interpretation": (
                "Script 05 findings remain applicable to stage-level analyses."
            ),
            "not_authorized": (
                "Assuming stage missingness is random."
            ),
        },
        {
            "issue": "Monte Carlo comparison",
            "authorized_interpretation": (
                "DES must demonstrate incremental analytical value beyond direct total-time simulation."
            ),
            "not_authorized": (
                "Treating additional model complexity as evidence of superior validity."
            ),
        },
        {
            "issue": "Causality",
            "authorized_interpretation": (
                "Stage-level stochastic associations may be described."
            ),
            "not_authorized": (
                "Claiming that queries/observations causally generate stage delays."
            ),
        },
    ]
)


# =============================================================================
# 23. SAVE OUTPUT WORKBOOK
# =============================================================================

log("[20] Saving reproducible DES-assessment outputs...")

with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl"
) as writer:

    coverage_audit.to_excel(
        writer,
        sheet_name="coverage_audit",
        index=False,
    )

    stage_descriptive.to_excel(
        writer,
        sheet_name="stage_descriptive",
        index=False,
    )

    stage_dependence.to_excel(
        writer,
        sheet_name="stage_dependence",
        index=False,
    )

    scenario_dependence.to_excel(
        writer,
        sheet_name="scenario_dependence",
        index=False,
    )

    scenario_stage_summary.to_excel(
        writer,
        sheet_name="scenario_stage_summary",
        index=False,
    )

    stage_scenario_tests.to_excel(
        writer,
        sheet_name="stage_scenario_tests",
        index=False,
    )

    stage_shares.to_excel(
        writer,
        sheet_name="stage_shares",
        index=False,
    )

    query_stage_relationships.to_excel(
        writer,
        sheet_name="query_stage_relationships",
        index=False,
    )

    independence_audit.to_excel(
        writer,
        sheet_name="independence_audit",
        index=False,
    )

    additive_value_audit.to_excel(
        writer,
        sheet_name="additive_value_audit",
        index=False,
    )

    limitations.to_excel(
        writer,
        sheet_name="limitations",
        index=False,
    )

    authorization_gates.to_excel(
        writer,
        sheet_name="authorization_gates",
        index=False,
    )

    final_decision.to_excel(
        writer,
        sheet_name="final_decision",
        index=False,
    )

    next_protocol.to_excel(
        writer,
        sheet_name="next_protocol",
        index=False,
    )

    procedure_stage_audit.to_excel(
        writer,
        sheet_name="procedure_stage_audit",
        index=False,
    )

    interpretation_audit.to_excel(
        writer,
        sheet_name="interpretation_audit",
        index=False,
    )

log(f"  Output workbook: {OUTPUT_FILE.name}")
log(f"  Log file: {LOG_FILE.name}")
log("")


# =============================================================================
# FINAL AUDIT
# =============================================================================

log("=" * 78)
log("DISCRETE-EVENT SIMULATION ASSESSMENT AUDIT")
log("=" * 78)

log(
    f"Master analytical procedures:          "
    f"{len(df)}"
)

log(
    f"Available total award times:           "
    f"{n_total}"
)

log(
    f"Complete temporal decompositions:      "
    f"{n_complete} ({coverage_complete:.2%})"
)

log(
    f"Exact stage reconstructions:           "
    f"{exact_n}/{reconstruction_n} "
    f"({exact_rate:.2%})"
)

log(
    f"Stage-duration Spearman rho:           "
    f"{spearman_rho:.4f}"
)

log(
    f"Stage-duration Spearman p-value:       "
    f"{spearman_p:.6g}"
)

log("")

log("STAGE-SPECIFIC QUERY/OBSERVATION RELATIONSHIPS")
log("-" * 78)

for _, row in query_stage_relationships.iterrows():

    log(
        f"{row['outcome']:<38} "
        f"n={int(row['n']):3d} | "
        f"Spearman={row['spearman_rho']:.4f} | "
        f"p={row['spearman_p']:.6g}"
    )

log("")

log("DES AUTHORIZATION GATES")
log("-" * 78)

for _, row in authorization_gates.iterrows():

    log(
        f"{row['gate']:<6} "
        f"{row['status']:<8} "
        f"{row['criterion']}"
    )

log("")

log("FINAL METHODOLOGICAL DECISION")
log("-" * 78)

log(f"DES status: {final_des_status}")
log(final_des_note)

log("")

log("SCIENTIFIC SCOPE")
log("- No discrete-event simulation is performed in Script 15.")
log("- Stage-level feasibility is evaluated before implementation.")
log("- The master analytical population remains n=137.")
log("- Stage-level analyses use available complete decompositions only.")
log("- Missing temporal values are not imputed.")
log("- No observations are deleted from the master population.")
log("- Stage dependence is measured rather than assumed absent.")
log("- Independent stage sampling is not automatically authorized.")
log("- DES complexity is not treated as evidence of scientific superiority.")
log("- The direct total-duration Monte Carlo model remains the primary stochastic reference.")
log("- Any DES implementation must demonstrate incremental analytical value.")
log("- No causal interpretation is imposed.")

log("")

if final_des_status == "DES_NOT_JUSTIFIED":
    pipeline_status = "DES_NOT_AUTHORIZED_PROCEED_TO_MODEL_VALIDATION"
else:
    pipeline_status = "DES_ASSESSED_PROCEED_ACCORDING_TO_RECORDED_CAUTION"

log("=" * 78)
log(f"PIPELINE STATUS: {pipeline_status}")
log("=" * 78)


# =============================================================================
# WRITE LOG
# =============================================================================

LOG_FILE.write_text(
    "\n".join(LOG_LINES),
    encoding="utf-8",
)
