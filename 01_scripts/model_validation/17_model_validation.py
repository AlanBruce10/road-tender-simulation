# =============================================================================
# 17_model_validation.py
# =============================================================================
# MODEL VALIDATION - ROAD INFRASTRUCTURE TENDERS
#
# Purpose
# -------
# Validate the stochastic modeling architecture developed in Scripts 12-16.
#
# Validation layers:
#   1. Internal descriptive fidelity audit
#   2. Temporal out-of-sample validation (2020-2023 -> 2024-2025)
#   3. Direct stochastic model validation
#   4. Two-stage DES validation where temporal decomposition is available
#   5. Stability / interpretation audit
#
# IMPORTANT
# ---------
# - No previously selected threshold is changed retrospectively.
# - No previously selected probability model is changed to improve validation.
# - No observations are deleted from the master analytical population.
# - No missing temporal values are imputed.
# - Temporal holdout thresholds are estimated ONLY from the training period
#   when evaluating genuinely prospective scenario assignment.
# - The temporal validation is a validation experiment and does not replace
#   the primary full-sample tercile definition used in Scripts 07-16.
# - Monte Carlo remains the primary stochastic reference.
# - DES remains the secondary process-decomposition model.
# - No causal interpretation is imposed.
# =============================================================================

from pathlib import Path
import sys
import logging
import warnings

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

# =============================================================================
# CONFIGURATION
# =============================================================================

MASTER_N = 137

TRAIN_YEARS = [2020, 2021, 2022, 2023]
TEST_YEARS = [2024, 2025]

TEMPORAL_MC_N = 50_000
BASE_SEED = 2026

# Minimum counts are feasibility diagnostics, not universal statistical laws.
MIN_TOTAL_SCENARIO_TRAIN_N = 10
MIN_TOTAL_SCENARIO_TEST_N = 5
MIN_STAGE_SCENARIO_TRAIN_N = 8
MIN_STAGE_SCENARIO_TEST_N = 5

SCENARIO_ORDER = ["Low", "Medium", "High"]

# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(__file__).resolve().parents[2]

INPUT_MASTER = ROOT / "02_results" / "03_1_integrated_dataset.xlsx"
INPUT_SCENARIOS = ROOT / "02_results" / "statistical_analysis" / "07_1_scenario_definition.xlsx"
INPUT_MC = ROOT / "02_results" / "stochastic_modeling" / "14_1_monte_carlo_simulation.xlsx"
INPUT_DES = ROOT / "02_results" / "stochastic_modeling" / "16_1_discrete_event_simulation.xlsx"

OUTPUT_DIR = ROOT / "02_results" / "model_validation"
LOG_DIR = ROOT / "03_logs" / "model_validation"

OUTPUT_FILE = OUTPUT_DIR / "17_1_model_validation.xlsx"
LOG_FILE = LOG_DIR / "17_model_validation.log"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("model_validation")
logger.setLevel(logging.INFO)
logger.handlers.clear()

formatter = logging.Formatter("%(message)s")

file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def log(message=""):
    logger.info(message)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def normalize_code(series):
    return (
        series.astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )


def numeric(series):
    return pd.to_numeric(series, errors="coerce")


def safe_rel_error(estimate, reference):
    if pd.isna(estimate) or pd.isna(reference):
        return np.nan
    if reference == 0:
        return np.nan
    return (estimate - reference) / reference


def safe_abs_rel_error(estimate, reference):
    value = safe_rel_error(estimate, reference)
    return abs(value) if pd.notna(value) else np.nan


def empirical_exceedance(values, threshold):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.nan
    return float(np.mean(values > threshold))


def descriptive(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    if len(values) == 0:
        return {
            "n": 0,
            "mean": np.nan,
            "median": np.nan,
            "std_dev": np.nan,
            "p25": np.nan,
            "p75": np.nan,
            "p90": np.nan,
            "p95": np.nan,
            "minimum": np.nan,
            "maximum": np.nan,
        }

    return {
        "n": len(values),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "std_dev": float(np.std(values, ddof=1)) if len(values) > 1 else np.nan,
        "p25": float(np.quantile(values, 0.25)),
        "p75": float(np.quantile(values, 0.75)),
        "p90": float(np.quantile(values, 0.90)),
        "p95": float(np.quantile(values, 0.95)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
    }


def ks_two_sample(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)

    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]

    if len(a) == 0 or len(b) == 0:
        return np.nan, np.nan

    result = stats.ks_2samp(a, b, alternative="two-sided", method="auto")
    return float(result.statistic), float(result.pvalue)


def wasserstein(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)

    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]

    if len(a) == 0 or len(b) == 0:
        return np.nan

    return float(stats.wasserstein_distance(a, b))


def scenario_from_thresholds(x, q1, q2):
    if pd.isna(x):
        return np.nan
    if x <= q1:
        return "Low"
    elif x <= q2:
        return "Medium"
    else:
        return "High"


def fit_lognormal(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    values = values[values > 0]

    if len(values) < 2:
        return None

    shape, loc, scale = stats.lognorm.fit(values, floc=0)

    return {
        "shape": float(shape),
        "loc": float(loc),
        "scale": float(scale),
    }


def simulate_lognormal(params, n, seed):
    rng = np.random.default_rng(seed)

    return stats.lognorm.rvs(
        params["shape"],
        loc=params["loc"],
        scale=params["scale"],
        size=n,
        random_state=rng,
    )


def simulate_empirical(values, n, seed):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    rng = np.random.default_rng(seed)
    return rng.choice(values, size=n, replace=True)


def simulate_joint_pairs(query_values, evaluation_values, n, seed):
    q = np.asarray(query_values, dtype=float)
    e = np.asarray(evaluation_values, dtype=float)

    mask = np.isfinite(q) & np.isfinite(e)

    q = q[mask]
    e = e[mask]

    if len(q) == 0:
        return np.array([]), np.array([]), np.array([])

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(q), size=n)

    q_sim = q[idx]
    e_sim = e[idx]
    total_sim = q_sim + e_sim

    return q_sim, e_sim, total_sim


def compare_observed_simulated(
    scenario,
    model,
    observed,
    simulated,
    validation_type,
):
    obs = descriptive(observed)
    sim = descriptive(simulated)

    ks_stat, ks_p = ks_two_sample(observed, simulated)
    wd = wasserstein(observed, simulated)

    return {
        "validation_type": validation_type,
        "scenario": scenario,
        "model": model,
        "observed_n": obs["n"],
        "simulated_n": sim["n"],
        "observed_mean": obs["mean"],
        "simulated_mean": sim["mean"],
        "mean_relative_error": safe_rel_error(sim["mean"], obs["mean"]),
        "observed_median": obs["median"],
        "simulated_median": sim["median"],
        "median_relative_error": safe_rel_error(sim["median"], obs["median"]),
        "observed_std": obs["std_dev"],
        "simulated_std": sim["std_dev"],
        "std_relative_error": safe_rel_error(sim["std_dev"], obs["std_dev"]),
        "observed_p90": obs["p90"],
        "simulated_p90": sim["p90"],
        "p90_relative_error": safe_rel_error(sim["p90"], obs["p90"]),
        "observed_p95": obs["p95"],
        "simulated_p95": sim["p95"],
        "p95_relative_error": safe_rel_error(sim["p95"], obs["p95"]),
        "ks_statistic": ks_stat,
        "ks_pvalue": ks_p,
        "wasserstein_days": wd,
    }


# =============================================================================
# START
# =============================================================================

log("=" * 78)
log("MODEL VALIDATION - ROAD INFRASTRUCTURE TENDERS")
log("=" * 78)
log("Purpose: Validate the stochastic architecture developed in Scripts 12-16.")
log("")
log("IMPORTANT:")
log("- Internal fidelity and temporal out-of-sample validation are distinguished.")
log("- No previous modeling decision is changed to improve validation.")
log("- Temporal validation uses 2020-2023 for training and 2024-2025 for testing.")
log("")

# =============================================================================
# 1. VALIDATE INPUTS
# =============================================================================

log("[1] Validating analytical inputs...")

inputs = [
    INPUT_MASTER,
    INPUT_SCENARIOS,
    INPUT_MC,
    INPUT_DES,
]

for path in inputs:
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    log(f"  Found: {path.name}")

# =============================================================================
# 2. READ DATA
# =============================================================================

log("")
log("[2] Reading analytical datasets...")

master = pd.read_excel(INPUT_MASTER)

scenario_audit = pd.read_excel(
    INPUT_SCENARIOS,
    sheet_name="procedure_audit"
)

mc_primary = pd.read_excel(
    INPUT_MC,
    sheet_name="primary_results"
)

des_primary = pd.read_excel(
    INPUT_DES,
    sheet_name="des_summary"
)

log(f"  Master rows: {len(master)}")
log(f"  Scenario-audit rows: {len(scenario_audit)}")
log(f"  Monte Carlo primary-result rows: {len(mc_primary)}")
log(f"  DES primary-result rows: {len(des_primary)}")

# =============================================================================
# 3. VALIDATE CONTRACT
# =============================================================================

log("")
log("[3] Validating analytical contract...")

required_master = [
    "procedure_code",
    "queries_observations_count",
    "notice_date",
    "total_award_time_days",
    "query_stage_duration_days",
    "evaluation_stage_duration_days",
]

missing_master = [c for c in required_master if c not in master.columns]

if missing_master:
    raise ValueError(
        f"Master dataset missing required columns: {missing_master}"
    )

if len(master) != MASTER_N:
    raise ValueError(
        f"Expected master analytical sample n={MASTER_N}, found {len(master)}"
    )

master["procedure_code"] = normalize_code(master["procedure_code"])
scenario_audit["procedure_code"] = normalize_code(
    scenario_audit["procedure_code"]
)

if master["procedure_code"].duplicated().any():
    raise ValueError("Duplicate procedure_code found in master dataset.")

master["queries_observations_count"] = numeric(
    master["queries_observations_count"]
)
master["total_award_time_days"] = numeric(
    master["total_award_time_days"]
)
master["query_stage_duration_days"] = numeric(
    master["query_stage_duration_days"]
)
master["evaluation_stage_duration_days"] = numeric(
    master["evaluation_stage_duration_days"]
)
master["notice_date"] = pd.to_datetime(
    master["notice_date"],
    errors="coerce"
)

master["notice_year"] = master["notice_date"].dt.year

log(f"  Master analytical sample verified: {len(master)}")
log(
    f"  Available total award times: "
    f"{master['total_award_time_days'].notna().sum()}/{len(master)}"
)
log(
    f"  Complete stage decompositions: "
    f"{master[['query_stage_duration_days', 'evaluation_stage_duration_days']].notna().all(axis=1).sum()}/{len(master)}"
)
log("  procedure_code uniqueness verified.")

# =============================================================================
# 4. MERGE PRIMARY FULL-SAMPLE SCENARIOS
# =============================================================================

log("")
log("[4] Recovering locked full-sample scenario assignments...")

required_scenario_cols = [
    "procedure_code",
    "scenario_terciles",
]

missing_scenario_cols = [
    c for c in required_scenario_cols
    if c not in scenario_audit.columns
]

if missing_scenario_cols:
    raise ValueError(
        f"Scenario audit missing columns: {missing_scenario_cols}"
    )

data = master.merge(
    scenario_audit[
        ["procedure_code", "scenario_terciles"]
    ],
    on="procedure_code",
    how="left",
    validate="one_to_one",
)

if data["scenario_terciles"].isna().any():
    raise ValueError(
        "Some procedures lack full-sample tercile assignments."
    )

log("  Full-sample tercile assignments recovered.")
log("  These remain the locked primary scenarios from Script 07.")

# =============================================================================
# 5. INTERNAL FIDELITY AUDIT
# =============================================================================

log("")
log("[5] Building internal full-sample fidelity audit...")

internal_rows = []

for scenario in SCENARIO_ORDER:
    observed = data.loc[
        data["scenario_terciles"] == scenario,
        "total_award_time_days"
    ].dropna().to_numpy()

    obs = descriptive(observed)

    internal_rows.append({
        "scenario": scenario,
        "observed_n": obs["n"],
        "observed_mean": obs["mean"],
        "observed_median": obs["median"],
        "observed_std": obs["std_dev"],
        "observed_p90": obs["p90"],
        "observed_p95": obs["p95"],
        "interpretation": (
            "Descriptive benchmark only; this is not independent validation."
        ),
    })

    log(
        f"  {scenario}: n={obs['n']}; "
        f"median={obs['median']:.2f}; "
        f"P95={obs['p95']:.2f}"
    )

internal_fidelity = pd.DataFrame(internal_rows)

log("")
log("  NOTE: Reproduction of the full sample is not treated as out-of-sample validation.")

# =============================================================================
# 6. DEFINE TEMPORAL HOLDOUT
# =============================================================================

log("")
log("[6] Defining temporal validation experiment...")

train = data[data["notice_year"].isin(TRAIN_YEARS)].copy()
test = data[data["notice_year"].isin(TEST_YEARS)].copy()

other_years = data[
    ~data["notice_year"].isin(TRAIN_YEARS + TEST_YEARS)
]

if len(other_years) > 0:
    raise ValueError(
        "Unexpected notice years found outside 2020-2025."
    )

log(
    f"  Training period: {min(TRAIN_YEARS)}-{max(TRAIN_YEARS)} "
    f"(n={len(train)})"
)
log(
    f"  Validation period: {min(TEST_YEARS)}-{max(TEST_YEARS)} "
    f"(n={len(test)})"
)

if len(train) == 0 or len(test) == 0:
    raise ValueError("Temporal split produced an empty partition.")

# =============================================================================
# 7. DERIVE TRAINING-ONLY SCENARIO THRESHOLDS
# =============================================================================

log("")
log("[7] Deriving training-only tercile thresholds...")

train_queries = train["queries_observations_count"].dropna()

q1_train = float(train_queries.quantile(1 / 3))
q2_train = float(train_queries.quantile(2 / 3))

log(f"  Training-only lower tercile threshold: {q1_train:.3f}")
log(f"  Training-only upper tercile threshold: {q2_train:.3f}")

train["temporal_scenario"] = train[
    "queries_observations_count"
].apply(
    lambda x: scenario_from_thresholds(x, q1_train, q2_train)
)

test["temporal_scenario"] = test[
    "queries_observations_count"
].apply(
    lambda x: scenario_from_thresholds(x, q1_train, q2_train)
)

log("")
log("  IMPORTANT:")
log("  Temporal thresholds are estimated from 2020-2023 only.")
log("  2024-2025 outcomes do not influence scenario thresholds.")
log("  This validation classification does not replace Script 07's primary scenarios.")

# =============================================================================
# 8. TEMPORAL SPLIT FEASIBILITY
# =============================================================================

log("")
log("[8] Auditing temporal validation feasibility...")

feasibility_rows = []

total_temporal_ready = True
stage_temporal_ready = True

for scenario in SCENARIO_ORDER:

    train_total_n = train.loc[
        (train["temporal_scenario"] == scenario)
        & train["total_award_time_days"].notna()
    ].shape[0]

    test_total_n = test.loc[
        (test["temporal_scenario"] == scenario)
        & test["total_award_time_days"].notna()
    ].shape[0]

    train_stage_n = train.loc[
        (train["temporal_scenario"] == scenario)
        & train["query_stage_duration_days"].notna()
        & train["evaluation_stage_duration_days"].notna()
    ].shape[0]

    test_stage_n = test.loc[
        (test["temporal_scenario"] == scenario)
        & test["query_stage_duration_days"].notna()
        & test["evaluation_stage_duration_days"].notna()
    ].shape[0]

    total_status = (
        "PASS"
        if (
            train_total_n >= MIN_TOTAL_SCENARIO_TRAIN_N
            and test_total_n >= MIN_TOTAL_SCENARIO_TEST_N
        )
        else "CAUTION"
    )

    stage_status = (
        "PASS"
        if (
            train_stage_n >= MIN_STAGE_SCENARIO_TRAIN_N
            and test_stage_n >= MIN_STAGE_SCENARIO_TEST_N
        )
        else "CAUTION"
    )

    if total_status != "PASS":
        total_temporal_ready = False

    if stage_status != "PASS":
        stage_temporal_ready = False

    feasibility_rows.append({
        "scenario": scenario,
        "train_total_n": train_total_n,
        "test_total_n": test_total_n,
        "total_validation_status": total_status,
        "train_stage_n": train_stage_n,
        "test_stage_n": test_stage_n,
        "des_validation_status": stage_status,
    })

    log(
        f"  {scenario}: total train/test={train_total_n}/{test_total_n} "
        f"[{total_status}] | "
        f"stage train/test={train_stage_n}/{test_stage_n} "
        f"[{stage_status}]"
    )

temporal_feasibility = pd.DataFrame(feasibility_rows)

# =============================================================================
# 9. AUDIT TEMPORAL DISTRIBUTION SHIFT
# =============================================================================

log("")
log("[9] Auditing temporal distribution shift...")

shift_rows = []

variables_for_shift = [
    "queries_observations_count",
    "total_award_time_days",
]

for variable in variables_for_shift:

    a = train[variable].dropna().to_numpy()
    b = test[variable].dropna().to_numpy()

    ks_stat, ks_p = ks_two_sample(a, b)
    wd = wasserstein(a, b)

    shift_rows.append({
        "variable": variable,
        "train_n": len(a),
        "test_n": len(b),
        "train_median": np.median(a) if len(a) else np.nan,
        "test_median": np.median(b) if len(b) else np.nan,
        "ks_statistic": ks_stat,
        "ks_pvalue": ks_p,
        "wasserstein_distance": wd,
        "interpretation": (
            "Temporal difference diagnostic; not a causal test."
        ),
    })

    log(
        f"  {variable}: "
        f"train median={np.median(a):.2f}; "
        f"test median={np.median(b):.2f}; "
        f"KS={ks_stat:.4f}; p={ks_p:.6g}"
    )

temporal_shift = pd.DataFrame(shift_rows)

# =============================================================================
# 10. FIT TRAINING-ONLY STOCHASTIC REPRESENTATIONS
# =============================================================================

log("")
log("[10] Fitting training-only stochastic representations...")

training_models = {}
training_model_rows = []

for scenario in SCENARIO_ORDER:

    values = train.loc[
        train["temporal_scenario"] == scenario,
        "total_award_time_days"
    ].dropna().to_numpy(dtype=float)

    if scenario == "Low":
        training_models[scenario] = {
            "representation": "Empirical",
            "values": values,
        }

        training_model_rows.append({
            "scenario": scenario,
            "representation": "Empirical",
            "train_n": len(values),
            "shape": np.nan,
            "loc": np.nan,
            "scale": np.nan,
            "scientific_role": (
                "Training-only empirical representation following "
                "the previously specified Low protocol."
            ),
        })

        log(
            f"  Low: empirical training representation "
            f"(n={len(values)})"
        )

    else:
        params = fit_lognormal(values)

        if params is None:
            raise ValueError(
                f"Unable to fit training-only Lognormal for {scenario}."
            )

        training_models[scenario] = {
            "representation": "Lognormal",
            "params": params,
            "values": values,
        }

        training_model_rows.append({
            "scenario": scenario,
            "representation": "Lognormal",
            "train_n": len(values),
            "shape": params["shape"],
            "loc": params["loc"],
            "scale": params["scale"],
            "scientific_role": (
                "Training-only refit of the probability family "
                "authorized before validation."
            ),
        })

        log(
            f"  {scenario}: Lognormal training fit "
            f"(n={len(values)}; "
            f"sigma={params['shape']:.6f}; "
            f"scale={params['scale']:.6f})"
        )

training_models_df = pd.DataFrame(training_model_rows)

log("")
log("  NOTE: Probability families are not re-selected using validation outcomes.")

# =============================================================================
# 11. TEMPORAL OUT-OF-SAMPLE MONTE CARLO VALIDATION
# =============================================================================

log("")
log("[11] Running temporal out-of-sample stochastic validation...")

temporal_mc_rows = []
temporal_simulations = {}

for i, scenario in enumerate(SCENARIO_ORDER):

    observed_test = test.loc[
        test["temporal_scenario"] == scenario,
        "total_award_time_days"
    ].dropna().to_numpy(dtype=float)

    model = training_models[scenario]

    seed = BASE_SEED + 100 + i

    if model["representation"] == "Empirical":
        simulated = simulate_empirical(
            model["values"],
            TEMPORAL_MC_N,
            seed,
        )
    else:
        simulated = simulate_lognormal(
            model["params"],
            TEMPORAL_MC_N,
            seed,
        )

    temporal_simulations[scenario] = simulated

    row = compare_observed_simulated(
        scenario=scenario,
        model=model["representation"],
        observed=observed_test,
        simulated=simulated,
        validation_type="TEMPORAL_OUT_OF_SAMPLE",
    )

    temporal_mc_rows.append(row)

    log(
        f"  {scenario}: test n={len(observed_test)}; "
        f"observed median={row['observed_median']:.2f}; "
        f"predicted median={row['simulated_median']:.2f}; "
        f"KS={row['ks_statistic']:.4f}; "
        f"p={row['ks_pvalue']:.6g}; "
        f"Wasserstein={row['wasserstein_days']:.2f} days"
    )

temporal_mc_validation = pd.DataFrame(temporal_mc_rows)

# =============================================================================
# 12. TEMPORAL PREDICTIVE INTERVAL COVERAGE
# =============================================================================

log("")
log("[12] Evaluating temporal predictive coverage...")

coverage_rows = []

for scenario in SCENARIO_ORDER:

    sim = temporal_simulations[scenario]

    lower90 = float(np.quantile(sim, 0.05))
    upper90 = float(np.quantile(sim, 0.95))

    lower95 = float(np.quantile(sim, 0.025))
    upper95 = float(np.quantile(sim, 0.975))

    observed = test.loc[
        test["temporal_scenario"] == scenario,
        "total_award_time_days"
    ].dropna().to_numpy(dtype=float)

    if len(observed) > 0:
        coverage90 = float(
            np.mean((observed >= lower90) & (observed <= upper90))
        )
        coverage95 = float(
            np.mean((observed >= lower95) & (observed <= upper95))
        )
    else:
        coverage90 = np.nan
        coverage95 = np.nan

    coverage_rows.append({
        "scenario": scenario,
        "test_n": len(observed),
        "predicted_90_lower": lower90,
        "predicted_90_upper": upper90,
        "observed_90_coverage": coverage90,
        "nominal_90_coverage": 0.90,
        "coverage90_error": (
            coverage90 - 0.90
            if pd.notna(coverage90)
            else np.nan
        ),
        "predicted_95_lower": lower95,
        "predicted_95_upper": upper95,
        "observed_95_coverage": coverage95,
        "nominal_95_coverage": 0.95,
        "coverage95_error": (
            coverage95 - 0.95
            if pd.notna(coverage95)
            else np.nan
        ),
    })

    log(
        f"  {scenario}: "
        f"90% interval coverage={coverage90:.3f}; "
        f"95% interval coverage={coverage95:.3f}"
    )

predictive_coverage = pd.DataFrame(coverage_rows)

# =============================================================================
# 13. VALIDATE ORDERED SCENARIO STRUCTURE IN HOLDOUT
# =============================================================================

log("")
log("[13] Testing scenario ordering in the temporal holdout...")

test_groups = []

scenario_test_medians = {}

for scenario in SCENARIO_ORDER:

    values = test.loc[
        test["temporal_scenario"] == scenario,
        "total_award_time_days"
    ].dropna().to_numpy(dtype=float)

    test_groups.append(values)

    scenario_test_medians[scenario] = (
        float(np.median(values))
        if len(values)
        else np.nan
    )

if all(len(g) > 0 for g in test_groups):
    kw = stats.kruskal(*test_groups)
    kw_h = float(kw.statistic)
    kw_p = float(kw.pvalue)
else:
    kw_h = np.nan
    kw_p = np.nan

ordered_holdout = (
    scenario_test_medians["Low"]
    < scenario_test_medians["Medium"]
    < scenario_test_medians["High"]
    if all(
        pd.notna(scenario_test_medians[s])
        for s in SCENARIO_ORDER
    )
    else False
)

holdout_ordering = pd.DataFrame([{
    "low_median": scenario_test_medians["Low"],
    "medium_median": scenario_test_medians["Medium"],
    "high_median": scenario_test_medians["High"],
    "strictly_increasing_medians": ordered_holdout,
    "kruskal_h": kw_h,
    "kruskal_p": kw_p,
    "interpretation": (
        "Independent temporal holdout test of whether the previously "
        "identified Low-Medium-High pattern persists."
    ),
}])

log(
    f"  Holdout medians: "
    f"{scenario_test_medians['Low']:.2f} < "
    f"{scenario_test_medians['Medium']:.2f} < "
    f"{scenario_test_medians['High']:.2f} "
    f"= {ordered_holdout}"
)

log(
    f"  Holdout Kruskal-Wallis: "
    f"H={kw_h:.4f}; p={kw_p:.6g}"
)

# =============================================================================
# 14. TEMPORAL RELATIONSHIP VALIDATION
# =============================================================================

log("")
log("[14] Evaluating continuous relationship in training and holdout periods...")

relationship_rows = []

for label, subset in [
    ("TRAIN_2020_2023", train),
    ("TEST_2024_2025", test),
]:

    complete = subset[
        ["queries_observations_count", "total_award_time_days"]
    ].dropna()

    x = complete["queries_observations_count"].to_numpy(dtype=float)
    y = complete["total_award_time_days"].to_numpy(dtype=float)

    pearson = stats.pearsonr(x, y)
    spearman = stats.spearmanr(x, y)
    kendall = stats.kendalltau(x, y)

    relationship_rows.append({
        "period": label,
        "n": len(complete),
        "pearson_r": float(pearson.statistic),
        "pearson_p": float(pearson.pvalue),
        "spearman_rho": float(spearman.statistic),
        "spearman_p": float(spearman.pvalue),
        "kendall_tau": float(kendall.statistic),
        "kendall_p": float(kendall.pvalue),
    })

    log(
        f"  {label}: n={len(complete)}; "
        f"Pearson={pearson.statistic:.4f}; "
        f"Spearman={spearman.statistic:.4f}; "
        f"Kendall={kendall.statistic:.4f}"
    )

temporal_relationship = pd.DataFrame(relationship_rows)

# =============================================================================
# 15. TEMPORAL DES VALIDATION
# =============================================================================

log("")
log("[15] Evaluating temporal validation of the two-stage DES...")

des_validation_rows = []

for i, scenario in enumerate(SCENARIO_ORDER):

    train_stage = train[
        (train["temporal_scenario"] == scenario)
        & train["query_stage_duration_days"].notna()
        & train["evaluation_stage_duration_days"].notna()
    ].copy()

    test_stage = test[
        (test["temporal_scenario"] == scenario)
        & test["query_stage_duration_days"].notna()
        & test["evaluation_stage_duration_days"].notna()
    ].copy()

    if len(train_stage) == 0 or len(test_stage) == 0:
        des_validation_rows.append({
            "scenario": scenario,
            "train_stage_n": len(train_stage),
            "test_stage_n": len(test_stage),
            "status": "INSUFFICIENT_DATA",
        })
        continue

    q_sim, e_sim, total_sim = simulate_joint_pairs(
        train_stage["query_stage_duration_days"].to_numpy(),
        train_stage["evaluation_stage_duration_days"].to_numpy(),
        TEMPORAL_MC_N,
        BASE_SEED + 500 + i,
    )

    observed_total = (
        test_stage["query_stage_duration_days"].to_numpy(dtype=float)
        + test_stage["evaluation_stage_duration_days"].to_numpy(dtype=float)
    )

    total_comparison = compare_observed_simulated(
        scenario=scenario,
        model="Joint_empirical_DES",
        observed=observed_total,
        simulated=total_sim,
        validation_type="TEMPORAL_OUT_OF_SAMPLE_DES",
    )

    observed_query = descriptive(
        test_stage["query_stage_duration_days"].to_numpy(dtype=float)
    )
    simulated_query = descriptive(q_sim)

    observed_eval = descriptive(
        test_stage["evaluation_stage_duration_days"].to_numpy(dtype=float)
    )
    simulated_eval = descriptive(e_sim)

    observed_rho = (
        stats.spearmanr(
            test_stage["query_stage_duration_days"],
            test_stage["evaluation_stage_duration_days"],
        ).statistic
        if len(test_stage) >= 3
        else np.nan
    )

    simulated_rho = stats.spearmanr(q_sim, e_sim).statistic

    des_validation_rows.append({
        "scenario": scenario,
        "train_stage_n": len(train_stage),
        "test_stage_n": len(test_stage),
        "status": (
            "EVALUATED"
            if (
                len(train_stage) >= MIN_STAGE_SCENARIO_TRAIN_N
                and len(test_stage) >= MIN_STAGE_SCENARIO_TEST_N
            )
            else "SMALL_SAMPLE_CAUTION"
        ),
        "observed_query_median": observed_query["median"],
        "simulated_query_median": simulated_query["median"],
        "query_median_relative_error": safe_rel_error(
            simulated_query["median"],
            observed_query["median"],
        ),
        "observed_evaluation_median": observed_eval["median"],
        "simulated_evaluation_median": simulated_eval["median"],
        "evaluation_median_relative_error": safe_rel_error(
            simulated_eval["median"],
            observed_eval["median"],
        ),
        "observed_total_median": total_comparison["observed_median"],
        "simulated_total_median": total_comparison["simulated_median"],
        "total_median_relative_error": total_comparison[
            "median_relative_error"
        ],
        "observed_total_p95": total_comparison["observed_p95"],
        "simulated_total_p95": total_comparison["simulated_p95"],
        "total_p95_relative_error": total_comparison[
            "p95_relative_error"
        ],
        "ks_statistic": total_comparison["ks_statistic"],
        "ks_pvalue": total_comparison["ks_pvalue"],
        "wasserstein_days": total_comparison["wasserstein_days"],
        "observed_stage_spearman": observed_rho,
        "simulated_training_stage_spearman": simulated_rho,
    })

    log(
        f"  {scenario}: train/test stage n="
        f"{len(train_stage)}/{len(test_stage)}; "
        f"observed total median={total_comparison['observed_median']:.2f}; "
        f"predicted={total_comparison['simulated_median']:.2f}; "
        f"KS={total_comparison['ks_statistic']:.4f}; "
        f"p={total_comparison['ks_pvalue']:.6g}"
    )

temporal_des_validation = pd.DataFrame(des_validation_rows)

# =============================================================================
# 16. COMPARE DIRECT STOCHASTIC MODEL AND DES IN HOLDOUT
# =============================================================================

log("")
log("[16] Comparing direct stochastic model and DES validation behavior...")

model_comparison_rows = []

for scenario in SCENARIO_ORDER:

    mc_row = temporal_mc_validation[
        temporal_mc_validation["scenario"] == scenario
    ]

    des_row = temporal_des_validation[
        temporal_des_validation["scenario"] == scenario
    ]

    if mc_row.empty:
        continue

    mc_row = mc_row.iloc[0]

    if des_row.empty:
        des_median_error = np.nan
        des_wasserstein = np.nan
        des_status = "NOT_AVAILABLE"
    else:
        des_row = des_row.iloc[0]
        des_median_error = des_row.get(
            "total_median_relative_error",
            np.nan
        )
        des_wasserstein = des_row.get(
            "wasserstein_days",
            np.nan
        )
        des_status = des_row.get(
            "status",
            "UNKNOWN"
        )

    model_comparison_rows.append({
        "scenario": scenario,
        "direct_model": mc_row["model"],
        "direct_model_test_n": mc_row["observed_n"],
        "direct_median_relative_error": mc_row[
            "median_relative_error"
        ],
        "direct_wasserstein_days": mc_row[
            "wasserstein_days"
        ],
        "des_status": des_status,
        "des_median_relative_error": des_median_error,
        "des_wasserstein_days": des_wasserstein,
        "interpretation": (
            "Comparison is descriptive. Lower error in one metric does "
            "not automatically establish global model superiority."
        ),
    })

model_comparison = pd.DataFrame(model_comparison_rows)

log("  Direct-model and DES validation metrics assembled.")
log("  No winner is automatically selected from a single validation metric.")

# =============================================================================
# 17. YEAR-BY-YEAR AUDIT
# =============================================================================

log("")
log("[17] Building year-by-year validation audit...")

year_rows = []

for year in sorted(data["notice_year"].dropna().unique()):

    year = int(year)

    subset = data[data["notice_year"] == year]

    complete_total = subset["total_award_time_days"].notna().sum()

    complete_stage = subset[
        [
            "query_stage_duration_days",
            "evaluation_stage_duration_days",
        ]
    ].notna().all(axis=1).sum()

    total_values = subset[
        "total_award_time_days"
    ].dropna().to_numpy()

    year_rows.append({
        "notice_year": year,
        "n_procedures": len(subset),
        "total_time_available_n": complete_total,
        "total_time_coverage": complete_total / len(subset),
        "stage_complete_n": complete_stage,
        "stage_coverage": complete_stage / len(subset),
        "median_total_award_time": (
            float(np.median(total_values))
            if len(total_values)
            else np.nan
        ),
        "median_queries_observations": float(
            subset["queries_observations_count"].median()
        ),
        "temporal_role": (
            "TRAIN"
            if year in TRAIN_YEARS
            else "TEST"
        ),
    })

year_audit = pd.DataFrame(year_rows)

for _, row in year_audit.iterrows():
    log(
        f"  {int(row['notice_year'])}: "
        f"n={int(row['n_procedures'])}; "
        f"total coverage={row['total_time_coverage']:.2%}; "
        f"stage coverage={row['stage_coverage']:.2%}; "
        f"role={row['temporal_role']}"
    )

# =============================================================================
# 18. VALIDATION LIMITATIONS
# =============================================================================

log("")
log("[18] Recording validation limitations...")

limitations = pd.DataFrame([
    {
        "limitation": "Observational design",
        "implication": (
            "Validation evaluates reproducibility and predictive/descriptive "
            "behavior, not causal effects."
        ),
    },
    {
        "limitation": "Temporal sample size",
        "implication": (
            "Scenario-specific holdout estimates may have substantial "
            "sampling uncertainty."
        ),
    },
    {
        "limitation": "Temporal distribution shift",
        "implication": (
            "2024-2025 may differ structurally from 2020-2023; "
            "validation therefore evaluates temporal transportability."
        ),
    },
    {
        "limitation": "Incomplete stage decomposition",
        "implication": (
            "DES validation is restricted to procedures with both "
            "stage durations available."
        ),
    },
    {
        "limitation": "Systematic stage-data availability",
        "implication": (
            "Script 05 identified associations between integrated-terms "
            "date availability and observed procedure characteristics."
        ),
    },
    {
        "limitation": "Empirical Low representation",
        "implication": (
            "Low-scenario temporal predictions are constrained by the "
            "finite support observed in the training sample."
        ),
    },
    {
        "limitation": "Two-stage process resolution",
        "implication": (
            "DES represents only the two temporal stages observed "
            "reliably in the analytical dataset."
        ),
    },
])

log(f"  Recorded limitations: {len(limitations)}")

# =============================================================================
# 19. BUILD VALIDATION DECISION FRAMEWORK
# =============================================================================

log("")
log("[19] Building validation decision framework...")

holdout_relationship = temporal_relationship[
    temporal_relationship["period"] == "TEST_2024_2025"
].iloc[0]

direct_finite = temporal_mc_validation[
    [
        "median_relative_error",
        "p95_relative_error",
        "wasserstein_days",
    ]
].replace([np.inf, -np.inf], np.nan)

direct_metrics_available = direct_finite.notna().any().all()

if len(temporal_des_validation) > 0:
    des_evaluated_count = int(
        temporal_des_validation["status"]
        .isin(["EVALUATED", "SMALL_SAMPLE_CAUTION"])
        .sum()
    )
else:
    des_evaluated_count = 0

validation_framework = pd.DataFrame([
    {
        "component": "Temporal split feasibility",
        "status": "PASS" if total_temporal_ready else "CAUTION",
        "evidence": (
            "Scenario-specific training and validation counts audited."
        ),
    },
    {
        "component": "Independent scenario ordering",
        "status": "PASS" if ordered_holdout else "CAUTION",
        "evidence": (
            f"Holdout Low/Medium/High medians: "
            f"{scenario_test_medians['Low']:.2f}, "
            f"{scenario_test_medians['Medium']:.2f}, "
            f"{scenario_test_medians['High']:.2f}; "
            f"Kruskal p={kw_p:.6g}"
        ),
    },
    {
        "component": "Continuous relationship transportability",
        "status": (
            "PASS"
            if (
                pd.notna(holdout_relationship["spearman_rho"])
                and holdout_relationship["spearman_rho"] > 0
            )
            else "CAUTION"
        ),
        "evidence": (
            f"Holdout Spearman rho="
            f"{holdout_relationship['spearman_rho']:.4f}; "
            f"p={holdout_relationship['spearman_p']:.6g}"
        ),
    },
    {
        "component": "Direct stochastic predictive validation",
        "status": (
            "EVALUATED"
            if direct_metrics_available
            else "CAUTION"
        ),
        "evidence": (
            "Training-only representations compared with 2024-2025 "
            "observed award-time distributions."
        ),
    },
    {
        "component": "DES temporal validation",
        "status": (
            "EVALUATED"
            if des_evaluated_count == 3
            else "CAUTION"
        ),
        "evidence": (
            f"{des_evaluated_count}/3 scenarios evaluated with "
            "available stage-level holdout data."
        ),
    },
    {
        "component": "Causal validation",
        "status": "NOT_AUTHORIZED",
        "evidence": (
            "Observational design does not identify causal effects."
        ),
    },
])

for _, row in validation_framework.iterrows():
    log(
        f"  {row['component']:<45} | {row['status']}"
    )

# =============================================================================
# 20. SCIENTIFIC INTERPRETATION AUDIT
# =============================================================================

log("")
log("[20] Building scientific interpretation audit...")

interpretation_audit = pd.DataFrame([
    {
        "issue": "Internal fit",
        "authorized_interpretation": (
            "Useful as descriptive fidelity / calibration evidence."
        ),
        "not_authorized": (
            "Claiming internal reproduction alone proves external validity."
        ),
    },
    {
        "issue": "Temporal validation",
        "authorized_interpretation": (
            "Assesses whether patterns calibrated on 2020-2023 "
            "transport to 2024-2025."
        ),
        "not_authorized": (
            "Claiming universal validity beyond the studied population "
            "and period."
        ),
    },
    {
        "issue": "K-S test",
        "authorized_interpretation": (
            "One distributional discrepancy diagnostic considered "
            "alongside effect/error metrics."
        ),
        "not_authorized": (
            "Treating p>0.05 as proof that two distributions are identical."
        ),
    },
    {
        "issue": "Monte Carlo",
        "authorized_interpretation": (
            "Primary uncertainty-propagation representation under "
            "previously specified scenario models."
        ),
        "not_authorized": (
            "Interpreting simulation iterations as new independent tenders."
        ),
    },
    {
        "issue": "DES",
        "authorized_interpretation": (
            "Secondary two-stage process representation preserving "
            "observed stage dependence."
        ),
        "not_authorized": (
            "Claiming DES is superior merely because it is more complex."
        ),
    },
    {
        "issue": "Scenario contrasts",
        "authorized_interpretation": (
            "Stochastic/descriptive differences associated with "
            "query/observation scenario."
        ),
        "not_authorized": (
            "Claiming queries/observations causally produce the observed "
            "delay differences."
        ),
    },
])

log("  Interpretation boundaries recorded.")

# =============================================================================
# 21. PROCEDURE-LEVEL TEMPORAL AUDIT
# =============================================================================

log("")
log("[21] Building procedure-level temporal validation audit...")

procedure_temporal_audit = data[
    [
        "procedure_code",
        "notice_year",
        "queries_observations_count",
        "scenario_terciles",
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
        "total_award_time_days",
    ]
].copy()

procedure_temporal_audit["temporal_role"] = np.where(
    procedure_temporal_audit["notice_year"].isin(TRAIN_YEARS),
    "TRAIN",
    "TEST",
)

procedure_temporal_audit["temporal_scenario"] = (
    procedure_temporal_audit["queries_observations_count"]
    .apply(
        lambda x: scenario_from_thresholds(
            x,
            q1_train,
            q2_train
        )
    )
)

procedure_temporal_audit[
    "scenario_assignment_agrees_with_full_sample"
] = (
    procedure_temporal_audit["scenario_terciles"]
    == procedure_temporal_audit["temporal_scenario"]
)

agreement_rate = (
    procedure_temporal_audit[
        "scenario_assignment_agrees_with_full_sample"
    ].mean()
)

log(
    f"  Training-threshold vs full-sample scenario agreement: "
    f"{agreement_rate:.2%}"
)

# =============================================================================
# 22. REPRODUCIBILITY METADATA
# =============================================================================

log("")
log("[22] Building reproducibility metadata...")

metadata = pd.DataFrame([
    {
        "parameter": "master_population_n",
        "value": MASTER_N,
    },
    {
        "parameter": "training_years",
        "value": "2020,2021,2022,2023",
    },
    {
        "parameter": "validation_years",
        "value": "2024,2025",
    },
    {
        "parameter": "training_lower_tercile",
        "value": q1_train,
    },
    {
        "parameter": "training_upper_tercile",
        "value": q2_train,
    },
    {
        "parameter": "temporal_simulation_n",
        "value": TEMPORAL_MC_N,
    },
    {
        "parameter": "base_seed",
        "value": BASE_SEED,
    },
    {
        "parameter": "primary_stochastic_reference",
        "value": "Direct total-duration stochastic model",
    },
    {
        "parameter": "secondary_process_model",
        "value": "Two-stage joint empirical DES",
    },
    {
        "parameter": "low_temporal_representation",
        "value": "Empirical resampling",
    },
    {
        "parameter": "medium_temporal_representation",
        "value": "Lognormal refit on training period only",
    },
    {
        "parameter": "high_temporal_representation",
        "value": "Lognormal refit on training period only",
    },
])

# =============================================================================
# 23. SAVE OUTPUTS
# =============================================================================

log("")
log("[23] Saving reproducible validation outputs...")

with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl"
) as writer:

    internal_fidelity.to_excel(
        writer,
        sheet_name="internal_fidelity",
        index=False,
    )

    temporal_feasibility.to_excel(
        writer,
        sheet_name="temporal_feasibility",
        index=False,
    )

    temporal_shift.to_excel(
        writer,
        sheet_name="temporal_shift",
        index=False,
    )

    training_models_df.to_excel(
        writer,
        sheet_name="training_models",
        index=False,
    )

    temporal_mc_validation.to_excel(
        writer,
        sheet_name="temporal_mc_validation",
        index=False,
    )

    predictive_coverage.to_excel(
        writer,
        sheet_name="predictive_coverage",
        index=False,
    )

    holdout_ordering.to_excel(
        writer,
        sheet_name="holdout_ordering",
        index=False,
    )

    temporal_relationship.to_excel(
        writer,
        sheet_name="temporal_relationship",
        index=False,
    )

    temporal_des_validation.to_excel(
        writer,
        sheet_name="temporal_des_validation",
        index=False,
    )

    model_comparison.to_excel(
        writer,
        sheet_name="model_comparison",
        index=False,
    )

    year_audit.to_excel(
        writer,
        sheet_name="year_audit",
        index=False,
    )

    validation_framework.to_excel(
        writer,
        sheet_name="validation_framework",
        index=False,
    )

    limitations.to_excel(
        writer,
        sheet_name="limitations",
        index=False,
    )

    interpretation_audit.to_excel(
        writer,
        sheet_name="interpretation_audit",
        index=False,
    )

    procedure_temporal_audit.to_excel(
        writer,
        sheet_name="procedure_audit",
        index=False,
    )

    metadata.to_excel(
        writer,
        sheet_name="reproducibility",
        index=False,
    )

log(f"  Output workbook: {OUTPUT_FILE.name}")
log(f"  Log file: {LOG_FILE.name}")

# =============================================================================
# FINAL AUDIT
# =============================================================================

log("")
log("=" * 78)
log("MODEL VALIDATION AUDIT")
log("=" * 78)

log(f"Master analytical procedures:          {len(data)}")
log(
    f"Training period:                       "
    f"{min(TRAIN_YEARS)}-{max(TRAIN_YEARS)} "
    f"(n={len(train)})"
)
log(
    f"Temporal validation period:            "
    f"{min(TEST_YEARS)}-{max(TEST_YEARS)} "
    f"(n={len(test)})"
)
log(
    f"Training-only tercile thresholds:      "
    f"{q1_train:.3f} / {q2_train:.3f}"
)
log(
    f"Scenario assignment agreement:         "
    f"{agreement_rate:.2%}"
)

log("")
log("TEMPORAL HOLDOUT SCENARIO STRUCTURE")
log("-" * 78)

log(
    f"Low median:                            "
    f"{scenario_test_medians['Low']:.2f}"
)
log(
    f"Medium median:                         "
    f"{scenario_test_medians['Medium']:.2f}"
)
log(
    f"High median:                           "
    f"{scenario_test_medians['High']:.2f}"
)
log(
    f"Strict Low < Medium < High:             "
    f"{ordered_holdout}"
)
log(
    f"Holdout Kruskal-Wallis p:              "
    f"{kw_p:.6g}"
)

log("")
log("TEMPORAL HOLDOUT CONTINUOUS RELATIONSHIP")
log("-" * 78)

log(
    f"Spearman rho:                          "
    f"{holdout_relationship['spearman_rho']:.4f}"
)
log(
    f"Spearman p-value:                      "
    f"{holdout_relationship['spearman_p']:.6g}"
)

log("")
log("DIRECT STOCHASTIC MODEL VALIDATION")
log("-" * 78)

for _, row in temporal_mc_validation.iterrows():

    log(
        f"{row['scenario']:<10} "
        f"{row['model']:<12} | "
        f"test n={int(row['observed_n']):<3} | "
        f"obs median={row['observed_median']:.2f} | "
        f"pred median={row['simulated_median']:.2f} | "
        f"KS={row['ks_statistic']:.4f} | "
        f"W={row['wasserstein_days']:.2f}"
    )

log("")
log("DES TEMPORAL VALIDATION")
log("-" * 78)

for _, row in temporal_des_validation.iterrows():

    scenario = row["scenario"]
    status = row["status"]

    if status == "INSUFFICIENT_DATA":
        log(
            f"{scenario:<10} | "
            f"INSUFFICIENT_DATA"
        )
    else:
        log(
            f"{scenario:<10} | "
            f"train/test={int(row['train_stage_n'])}/"
            f"{int(row['test_stage_n'])} | "
            f"obs median={row['observed_total_median']:.2f} | "
            f"pred median={row['simulated_total_median']:.2f} | "
            f"KS={row['ks_statistic']:.4f} | "
            f"W={row['wasserstein_days']:.2f}"
        )

log("")
log("SCIENTIFIC INTERPRETATION")
log("-" * 78)

log("- Full-sample reproduction is treated as internal fidelity, not independent validation.")
log("- Temporal validation calibrates only on 2020-2023 and evaluates 2024-2025.")
log("- Validation-period outcomes do not determine temporal scenario thresholds.")
log("- Previously selected probability families are not changed after seeing validation results.")
log("- Low retains an empirical/nonparametric representation.")
log("- Medium and High retain the previously authorized Lognormal family.")
log("- DES validation uses only procedures with complete stage decomposition.")
log("- K-S p-values are not interpreted as proof of distributional identity.")
log("- Wasserstein distance and quantile errors complement hypothesis-test diagnostics.")
log("- Monte Carlo iterations do not create additional independent tenders.")
log("- DES simulated entities do not create additional independent tenders.")
log("- No missing temporal values are imputed.")
log("- No observations are removed from the master analytical population.")
log("- No causal interpretation is authorized.")

log("")
log("=" * 78)
log("PIPELINE STATUS: MODEL_VALIDATION_COMPLETE_REVIEW_RESULTS_BEFORE_ROBUSTNESS")
log("=" * 78)
