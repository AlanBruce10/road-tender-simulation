from pathlib import Path
import sys
import platform
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats


# =============================================================================
# 14_monte_carlo_simulation.py
# =============================================================================
# FINAL MONTE CARLO SIMULATION
# Road infrastructure tenders
#
# PURPOSE
# -------
# Perform the substantive scenario-based stochastic simulation only after:
#
# 1. The analytical population has been established.
# 2. The Low / Medium / High scenario structure has been justified.
# 3. Scenario-specific probability representations have been assessed.
# 4. Numerical Monte Carlo convergence has been demonstrated.
#
# PRIMARY MODEL ARCHITECTURE
# --------------------------
# Low:
#     Empirical / nonparametric representation.
#     Exact empirical functionals are retained as deterministic benchmarks.
#
# Medium:
#     Lognormal stochastic representation.
#
# High:
#     Lognormal stochastic representation.
#
# LOW PARAMETRIC SENSITIVITY
# --------------------------
# Low Lognormal is retained ONLY as a sensitivity representation.
# It is not promoted to the primary Low data-generating model.
#
# IMPORTANT
# ---------
# - This script DOES perform the final substantive Monte Carlo simulation.
# - It DOES NOT re-select distributions.
# - It DOES NOT redefine scenario thresholds.
# - It DOES NOT change the convergence tolerances.
# - It DOES NOT re-determine the number of iterations.
# - It DOES NOT delete observations.
# - It DOES NOT impute missing award times.
# - It DOES NOT perform discrete-event simulation.
# - It DOES NOT establish causality.
#
# INPUTS
# ------
# 02_results/03_1_integrated_dataset.xlsx
# 02_results/statistical_analysis/07_1_scenario_definition.xlsx
# 02_results/statistical_analysis/09_1_distribution_fitting.xlsx
# 02_results/stochastic_modeling/12_1_model_specification.xlsx
# 02_results/stochastic_modeling/13_1_monte_carlo_convergence.xlsx
#
# OUTPUTS
# -------
# 02_results/stochastic_modeling/14_1_monte_carlo_simulation.xlsx
# 03_logs/stochastic_modeling/14_monte_carlo_simulation.log
# =============================================================================


# =============================================================================
# CONFIGURATION
# =============================================================================

MASTER_EXPECTED_N = 137

# The final N is NOT hard-coded as a scientific decision.
# It is read from Script 13.
EXPECTED_CURRENT_OPERATIONAL_N = 50_000

# Deterministic final-simulation seeds.
# Different seeds are used for each stochastic representation.
FINAL_SEEDS = {
    ("Low", "Empirical"): 14012026,
    ("Low", "Lognormal"): 14022026,
    ("Medium", "Lognormal"): 14032026,
    ("High", "Lognormal"): 14042026,
}

SCENARIO_ORDER = [
    "Low",
    "Medium",
    "High",
]

PRIMARY_REPRESENTATIONS = {
    "Low": "Empirical",
    "Medium": "Lognormal",
    "High": "Lognormal",
}

SCIENTIFIC_ROLES = {
    ("Low", "Empirical"): "PRIMARY_ROBUST_REPRESENTATION",
    ("Low", "Lognormal"): "PARAMETRIC_SENSITIVITY_ONLY",
    ("Medium", "Lognormal"): "PRIMARY_PARAMETRIC_REPRESENTATION",
    ("High", "Lognormal"): "PRIMARY_PARAMETRIC_REPRESENTATION",
}


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(__file__).resolve().parents[2]

MASTER_FILE = (
    ROOT
    / "02_results"
    / "03_1_integrated_dataset.xlsx"
)

STAT_DIR = (
    ROOT
    / "02_results"
    / "statistical_analysis"
)

STOCH_DIR = (
    ROOT
    / "02_results"
    / "stochastic_modeling"
)

LOG_DIR = (
    ROOT
    / "03_logs"
    / "stochastic_modeling"
)

INPUT_07 = (
    STAT_DIR
    / "07_1_scenario_definition.xlsx"
)

INPUT_09 = (
    STAT_DIR
    / "09_1_distribution_fitting.xlsx"
)

INPUT_12 = (
    STOCH_DIR
    / "12_1_model_specification.xlsx"
)

INPUT_13 = (
    STOCH_DIR
    / "13_1_monte_carlo_convergence.xlsx"
)

OUTPUT_FILE = (
    STOCH_DIR
    / "14_1_monte_carlo_simulation.xlsx"
)

LOG_FILE = (
    LOG_DIR
    / "14_monte_carlo_simulation.log"
)

STOCH_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# =============================================================================
# LOGGING
# =============================================================================

LOG_LINES = []


def log(message=""):
    print(message)
    LOG_LINES.append(str(message))


def separator(char="=", n=78):
    log(char * n)


def save_log():
    LOG_FILE.write_text(
        "\n".join(LOG_LINES),
        encoding="utf-8",
    )


def fail(message):
    log("")
    log("ERROR: " + str(message))
    save_log()
    raise RuntimeError(message)


# =============================================================================
# BASIC VALIDATION FUNCTIONS
# =============================================================================

def require_file(path):

    if not path.exists():

        fail(
            f"Required input not found: {path}"
        )


def require_columns(
    df,
    columns,
    dataset_name,
):

    missing = [
        column
        for column in columns
        if column not in df.columns
    ]

    if missing:

        fail(
            f"{dataset_name} is missing required columns: "
            f"{missing}"
        )


def read_required_sheet(
    path,
    sheet_name,
):

    xls = pd.ExcelFile(path)

    if sheet_name not in xls.sheet_names:

        fail(
            f"Required sheet '{sheet_name}' not found in "
            f"{path.name}. Available sheets: "
            f"{xls.sheet_names}"
        )

    return pd.read_excel(
        path,
        sheet_name=sheet_name,
    )


# =============================================================================
# STATISTICAL FUNCTIONS
# =============================================================================

def summarize_distribution(
    x,
    exceedance_threshold,
):

    x = np.asarray(
        x,
        dtype=float,
    )

    if len(x) < 2:

        raise ValueError(
            "At least two observations are required."
        )

    return {
        "n": int(len(x)),
        "mean": float(
            np.mean(x)
        ),
        "median": float(
            np.median(x)
        ),
        "std": float(
            np.std(
                x,
                ddof=1,
            )
        ),
        "variance": float(
            np.var(
                x,
                ddof=1,
            )
        ),
        "coefficient_of_variation": float(
            np.std(
                x,
                ddof=1,
            )
            / np.mean(x)
        )
        if np.mean(x) != 0
        else np.nan,
        "minimum": float(
            np.min(x)
        ),
        "p05": float(
            np.quantile(
                x,
                0.05,
            )
        ),
        "p10": float(
            np.quantile(
                x,
                0.10,
            )
        ),
        "p25": float(
            np.quantile(
                x,
                0.25,
            )
        ),
        "p50": float(
            np.quantile(
                x,
                0.50,
            )
        ),
        "p75": float(
            np.quantile(
                x,
                0.75,
            )
        ),
        "p90": float(
            np.quantile(
                x,
                0.90,
            )
        ),
        "p95": float(
            np.quantile(
                x,
                0.95,
            )
        ),
        "p99": float(
            np.quantile(
                x,
                0.99,
            )
        ),
        "maximum": float(
            np.max(x)
        ),
        "exceedance_threshold_days": float(
            exceedance_threshold
        ),
        "exceedance_probability": float(
            np.mean(
                x > exceedance_threshold
            )
        ),
    }


def simulate_empirical(
    observed,
    n,
    rng,
):

    observed = np.asarray(
        observed,
        dtype=float,
    )

    return rng.choice(
        observed,
        size=n,
        replace=True,
    )


def simulate_lognormal(
    shape,
    loc,
    scale,
    n,
    rng,
):

    return stats.lognorm.rvs(
        s=shape,
        loc=loc,
        scale=scale,
        size=n,
        random_state=rng,
    )


def lognormal_theoretical_summary(
    shape,
    loc,
    scale,
):

    distribution = stats.lognorm(
        s=shape,
        loc=loc,
        scale=scale,
    )

    mean, variance = distribution.stats(
        moments="mv"
    )

    std = np.sqrt(
        variance
    )

    return {
        "theoretical_mean": float(
            mean
        ),
        "theoretical_median": float(
            distribution.median()
        ),
        "theoretical_std": float(
            std
        ),
        "theoretical_p90": float(
            distribution.ppf(
                0.90
            )
        ),
        "theoretical_p95": float(
            distribution.ppf(
                0.95
            )
        ),
        "theoretical_p99": float(
            distribution.ppf(
                0.99
            )
        ),
    }


def safe_relative_difference(
    value,
    reference,
):

    if (
        pd.isna(value)
        or
        pd.isna(reference)
    ):

        return np.nan

    if abs(reference) < 1e-12:

        return abs(
            value - reference
        )

    return (
        value - reference
    ) / abs(reference)


# =============================================================================
# MAIN
# =============================================================================

def main():

    separator()

    log(
        "FINAL MONTE CARLO SIMULATION - ROAD INFRASTRUCTURE TENDERS"
    )

    separator()

    log(
        "Purpose: Perform the substantive stochastic simulation authorized "
        "by Scripts 12-13."
    )

    log(
        "IMPORTANT: No model selection or convergence criterion is changed here."
    )

    log("")


    # =========================================================================
    # 1. VALIDATE INPUT FILES
    # =========================================================================

    log(
        "[1] Validating analytical inputs..."
    )

    required_files = [
        MASTER_FILE,
        INPUT_07,
        INPUT_09,
        INPUT_12,
        INPUT_13,
    ]

    for path in required_files:

        require_file(
            path
        )

        log(
            f"  Found: {path.name}"
        )

    log("")


    # =========================================================================
    # 2. READ INPUTS
    # =========================================================================

    log(
        "[2] Reading source datasets..."
    )

    master = pd.read_excel(
        MASTER_FILE
    )

    scenario_audit = read_required_sheet(
        INPUT_07,
        "procedure_audit",
    )

    distribution_fits = read_required_sheet(
        INPUT_09,
        "distribution_fits",
    )

    probability_spec = read_required_sheet(
        INPUT_12,
        "probability_specification",
    )

    low_protocol = read_required_sheet(
        INPUT_12,
        "low_scenario_protocol",
    )

    simulation_targets = read_required_sheet(
        INPUT_12,
        "simulation_targets",
    )

    authorization_13 = read_required_sheet(
        INPUT_13,
        "authorization",
    )

    experiment_decisions_13 = read_required_sheet(
        INPUT_13,
        "experiment_decisions",
    )

    reference_summary_13 = read_required_sheet(
        INPUT_13,
        "reference_summary",
    )

    log(
        f"  Master rows: {len(master)}"
    )

    log(
        f"  Scenario-audit rows: {len(scenario_audit)}"
    )

    log(
        f"  Distribution-fit rows: {len(distribution_fits)}"
    )

    log("")


    # =========================================================================
    # 3. VALIDATE ANALYTICAL CONTRACT
    # =========================================================================

    log(
        "[3] Validating analytical contract..."
    )

    if len(master) != MASTER_EXPECTED_N:

        fail(
            "Expected master analytical sample "
            f"n={MASTER_EXPECTED_N}, "
            f"found n={len(master)}."
        )

    require_columns(
        master,
        [
            "procedure_code",
            "queries_observations_count",
            "total_award_time_days",
        ],
        "Master dataset",
    )

    require_columns(
        scenario_audit,
        [
            "procedure_code",
            "queries_observations_count",
            "total_award_time_days",
            "scenario_terciles",
        ],
        "Script 07 procedure audit",
    )

    if master[
        "procedure_code"
    ].duplicated().any():

        fail(
            "Duplicate procedure_code values "
            "detected in master dataset."
        )

    if scenario_audit[
        "procedure_code"
    ].duplicated().any():

        fail(
            "Duplicate procedure_code values "
            "detected in Script 07."
        )

    master_codes = set(
        master[
            "procedure_code"
        ].astype(int)
    )

    scenario_codes = set(
        scenario_audit[
            "procedure_code"
        ].astype(int)
    )

    if master_codes != scenario_codes:

        fail(
            "Procedure-code mismatch between "
            "master dataset and Script 07."
        )

    available_award_times = int(
        master[
            "total_award_time_days"
        ].notna().sum()
    )

    if available_award_times != 136:

        fail(
            "Expected 136 available total award times, "
            f"found {available_award_times}."
        )

    observed_scenarios = set(
        scenario_audit[
            "scenario_terciles"
        ]
        .dropna()
        .astype(str)
        .unique()
    )

    expected_scenarios = set(
        SCENARIO_ORDER
    )

    if observed_scenarios != expected_scenarios:

        fail(
            "Unexpected tercile scenario labels: "
            f"{sorted(observed_scenarios)}"
        )

    log(
        f"  Master analytical sample verified: {len(master)}"
    )

    log(
        "  Available total award times: "
        f"{available_award_times}/{len(master)}"
    )

    log(
        "  Primary scenario definition verified: Terciles"
    )

    log("")


    # =========================================================================
    # 4. VERIFY SCRIPT 13 AUTHORIZATION
    # =========================================================================

    log(
        "[4] Verifying Script 13 Monte Carlo authorization..."
    )

    require_columns(
        authorization_13,
        [
            "decision",
            "status",
            "value",
            "basis",
        ],
        "Script 13 authorization",
    )

    operational_rows = authorization_13[
        authorization_13[
            "decision"
        ]
        .astype(str)
        .str.strip()
        .eq(
            "Final operational iteration count"
        )
    ]

    if len(
        operational_rows
    ) != 1:

        fail(
            "Could not identify exactly one final "
            "operational iteration decision in Script 13."
        )

    operational_row = (
        operational_rows.iloc[0]
    )

    final_status = str(
        operational_row[
            "status"
        ]
    ).strip()

    if (
        final_status
        !=
        "AUTHORIZED_FOR_FINAL_SIMULATION"
    ):

        fail(
            "Script 13 has not authorized the final simulation. "
            f"Current status: {final_status}"
        )

    try:

        operational_n = int(
            float(
                operational_row[
                    "value"
                ]
            )
        )

    except Exception:

        fail(
            "Script 13 final operational iteration count "
            "could not be interpreted as an integer."
        )

    if operational_n <= 0:

        fail(
            "Invalid operational iteration count "
            f"from Script 13: {operational_n}"
        )

    log(
        "  Script 13 authorization: "
        f"{final_status}"
    )

    log(
        "  Operational Monte Carlo iterations: "
        f"{operational_n:,}"
    )

    if (
        operational_n
        != EXPECTED_CURRENT_OPERATIONAL_N
    ):

        log(
            "  WARNING: Operational N differs from the "
            f"currently expected {EXPECTED_CURRENT_OPERATIONAL_N:,}."
        )

        log(
            "  Script 14 will use the value actually authorized "
            "by Script 13 rather than overriding it."
        )

    else:

        log(
            "  Current expected operational N verified: "
            f"{EXPECTED_CURRENT_OPERATIONAL_N:,}"
        )

    log("")


    # =========================================================================
    # 5. VERIFY EXPERIMENT-SPECIFIC DECISIONS
    # =========================================================================

    log(
        "[5] Verifying representation-specific convergence decisions..."
    )

    require_columns(
        experiment_decisions_13,
        [
            "scenario",
            "representation",
            "scientific_role",
            "status",
        ],
        "Script 13 experiment decisions",
    )

    required_decisions = [
        (
            "Low",
            "Empirical",
            "PRIMARY_ROBUST_REPRESENTATION",
        ),
        (
            "Low",
            "Lognormal",
            "PARAMETRIC_SENSITIVITY_ONLY",
        ),
        (
            "Medium",
            "Lognormal",
            "PRIMARY_PARAMETRIC_CANDIDATE",
        ),
        (
            "High",
            "Lognormal",
            "PRIMARY_PARAMETRIC_CANDIDATE",
        ),
    ]

    decision_audit_rows = []

    for (
        scenario,
        representation,
        expected_role,
    ) in required_decisions:

        subset = experiment_decisions_13[
            (
                experiment_decisions_13[
                    "scenario"
                ]
                .astype(str)
                .eq(
                    scenario
                )
            )
            &
            (
                experiment_decisions_13[
                    "representation"
                ]
                .astype(str)
                .eq(
                    representation
                )
            )
        ]

        if len(subset) != 1:

            fail(
                "Expected exactly one Script 13 decision for "
                f"{scenario} | {representation}; "
                f"found {len(subset)}."
            )

        row = subset.iloc[0]

        observed_role = str(
            row[
                "scientific_role"
            ]
        ).strip()

        status = str(
            row[
                "status"
            ]
        ).strip()

        if observed_role != expected_role:

            fail(
                f"Scientific-role mismatch for "
                f"{scenario} | {representation}. "
                f"Expected {expected_role}; "
                f"found {observed_role}."
            )

        if (
            scenario in [
                "Medium",
                "High",
            ]
            and status != "CONVERGED"
        ):

            fail(
                f"{scenario} Lognormal was expected to be "
                f"CONVERGED, found {status}."
            )

        if (
            scenario == "Low"
            and representation == "Lognormal"
            and status != "CONVERGED"
        ):

            fail(
                "Low Lognormal sensitivity representation "
                f"was expected to be CONVERGED, found {status}."
            )

        if (
            scenario == "Low"
            and representation == "Empirical"
            and status
            not in [
                "STRUCTURAL_DISCRETE_SUPPORT",
                "CONVERGED",
            ]
        ):

            fail(
                "Unexpected Low empirical Script 13 status: "
                f"{status}"
            )

        decision_audit_rows.append(
            {
                "scenario": scenario,
                "representation": representation,
                "expected_scientific_role": expected_role,
                "observed_scientific_role": observed_role,
                "script13_status": status,
                "accepted_for_script14": True,
            }
        )

        log(
            f"  {scenario} | {representation}: "
            f"{status}"
        )

    decision_audit = pd.DataFrame(
        decision_audit_rows
    )

    log("")


    # =========================================================================
    # 6. PREPARE PRIMARY TERCILE SAMPLES
    # =========================================================================

    log(
        "[6] Preparing observed scenario samples..."
    )

    samples = {}

    sample_audit_rows = []

    for scenario in SCENARIO_ORDER:

        scenario_mask = (
            scenario_audit[
                "scenario_terciles"
            ]
            ==
            scenario
        )

        total_n = int(
            scenario_mask.sum()
        )

        x = (
            scenario_audit.loc[
                scenario_mask,
                "total_award_time_days",
            ]
            .dropna()
            .astype(float)
            .to_numpy()
        )

        if len(x) == 0:

            fail(
                f"No award-time observations "
                f"for scenario {scenario}."
            )

        samples[
            scenario
        ] = x

        sample_audit_rows.append(
            {
                "scenario": scenario,
                "n_scenario_total": total_n,
                "n_award_time_available": int(
                    len(x)
                ),
                "n_award_time_missing": int(
                    total_n - len(x)
                ),
                "minimum": float(
                    np.min(x)
                ),
                "median": float(
                    np.median(x)
                ),
                "mean": float(
                    np.mean(x)
                ),
                "std": float(
                    np.std(
                        x,
                        ddof=1,
                    )
                ),
                "maximum": float(
                    np.max(x)
                ),
            }
        )

        log(
            f"  {scenario}: "
            f"n={len(x)}; "
            f"range={np.min(x):.0f}-"
            f"{np.max(x):.0f} days"
        )

    sample_audit = pd.DataFrame(
        sample_audit_rows
    )

    log("")


    # =========================================================================
    # 7. VERIFY SCRIPT 12 PROBABILITY PROTOCOL
    # =========================================================================

    log(
        "[7] Verifying Script 12 probability-model protocol..."
    )

    require_columns(
        probability_spec,
        [
            "scenario",
            "aic_preferred_distribution",
            "simulation_authorization",
        ],
        "Script 12 probability specification",
    )

    probability_lookup = (
        probability_spec
        .set_index(
            "scenario"
        )
        .to_dict(
            "index"
        )
    )

    for scenario in SCENARIO_ORDER:

        if scenario not in probability_lookup:

            fail(
                f"Scenario {scenario} missing "
                "from Script 12 probability specification."
            )

        row = probability_lookup[
            scenario
        ]

        preferred = str(
            row[
                "aic_preferred_distribution"
            ]
        ).strip()

        authorization = str(
            row[
                "simulation_authorization"
            ]
        ).strip()

        log(
            f"  {scenario}: "
            f"{preferred} | "
            f"{authorization}"
        )

    low_protocol_text = " ".join(
        low_protocol.astype(str)
        .fillna("")
        .values
        .ravel()
        .tolist()
    ).lower()

    if "empirical" not in low_protocol_text:

        fail(
            "Script 12 Low-scenario protocol does not contain "
            "the expected empirical representation."
        )

    log(
        "  Low empirical/nonparametric primary protocol verified."
    )

    log("")


    # =========================================================================
    # 8. EXTRACT LOGNORMAL PARAMETERS
    # =========================================================================

    log(
        "[8] Extracting authorized Lognormal parameters..."
    )

    require_columns(
        distribution_fits,
        [
            "method",
            "scenario",
            "distribution",
            "shape_1",
            "loc",
            "scale",
        ],
        "Script 09 distribution fits",
    )

    lognormal_params = {}

    for scenario in SCENARIO_ORDER:

        fit = distribution_fits[
            (
                distribution_fits[
                    "method"
                ]
                .astype(str)
                .eq(
                    "Terciles"
                )
            )
            &
            (
                distribution_fits[
                    "scenario"
                ]
                .astype(str)
                .eq(
                    scenario
                )
            )
            &
            (
                distribution_fits[
                    "distribution"
                ]
                .astype(str)
                .eq(
                    "Lognormal"
                )
            )
        ]

        if len(fit) != 1:

            fail(
                "Expected exactly one Terciles/Lognormal "
                f"fit for {scenario}; found {len(fit)}."
            )

        fit = fit.iloc[0]

        shape = float(
            fit[
                "shape_1"
            ]
        )

        loc = float(
            fit[
                "loc"
            ]
        )

        scale = float(
            fit[
                "scale"
            ]
        )

        if (
            not np.isfinite(shape)
            or
            not np.isfinite(loc)
            or
            not np.isfinite(scale)
            or
            shape <= 0
            or
            scale <= 0
        ):

            fail(
                f"Invalid Lognormal parameters "
                f"for {scenario}."
            )

        lognormal_params[
            scenario
        ] = {
            "shape": shape,
            "loc": loc,
            "scale": scale,
        }

        log(
            f"  {scenario}: "
            f"sigma={shape:.6f}; "
            f"loc={loc:.6f}; "
            f"scale={scale:.6f}"
        )

    log("")


    # =========================================================================
    # 9. DEFINE EXCEEDANCE THRESHOLDS
    # =========================================================================

    log(
        "[9] Defining prespecified scenario-specific exceedance thresholds..."
    )

    exceedance_thresholds = {}

    threshold_rows = []

    for scenario in SCENARIO_ORDER:

        x = samples[
            scenario
        ]

        threshold = float(
            pd.Series(
                x
            ).quantile(
                0.90
            )
        )

        exceedance_thresholds[
            scenario
        ] = threshold

        threshold_rows.append(
            {
                "scenario": scenario,
                "threshold_definition": "Observed scenario P90",
                "threshold_days": threshold,
                "source": "Observed tercile scenario sample",
                "selected_before_final_simulation": True,
            }
        )

        log(
            f"  {scenario}: "
            f"observed P90 = {threshold:.2f} days"
        )

    threshold_audit = pd.DataFrame(
        threshold_rows
    )

    log(
        "  NOTE: These thresholds reproduce the "
        "prespecified convergence-stage definition."
    )

    log("")


    # =========================================================================
    # 10. COMPUTE EXACT OBSERVED EMPIRICAL BENCHMARKS
    # =========================================================================

    log(
        "[10] Computing exact observed scenario benchmarks..."
    )

    empirical_rows = []

    for scenario in SCENARIO_ORDER:

        summary = summarize_distribution(
            samples[
                scenario
            ],
            exceedance_thresholds[
                scenario
            ],
        )

        empirical_rows.append(
            {
                "scenario": scenario,
                "representation": "Observed empirical sample",
                **summary,
            }
        )

        log(
            f"  {scenario}: "
            f"mean={summary['mean']:.2f}; "
            f"median={summary['median']:.2f}; "
            f"SD={summary['std']:.2f}; "
            f"P90={summary['p90']:.2f}; "
            f"P95={summary['p95']:.2f}"
        )

    empirical_benchmarks = pd.DataFrame(
        empirical_rows
    )

    log("")


    # =========================================================================
    # 11. RUN FINAL STOCHASTIC SIMULATIONS
    # =========================================================================

    log(
        "[11] Running final authorized stochastic simulations..."
    )

    experiments = [
        {
            "scenario": "Low",
            "representation": "Empirical",
            "scientific_role":
                "PRIMARY_ROBUST_REPRESENTATION",
            "primary_or_sensitivity":
                "PRIMARY",
        },
        {
            "scenario": "Low",
            "representation": "Lognormal",
            "scientific_role":
                "PARAMETRIC_SENSITIVITY_ONLY",
            "primary_or_sensitivity":
                "SENSITIVITY",
        },
        {
            "scenario": "Medium",
            "representation": "Lognormal",
            "scientific_role":
                "PRIMARY_PARAMETRIC_REPRESENTATION",
            "primary_or_sensitivity":
                "PRIMARY",
        },
        {
            "scenario": "High",
            "representation": "Lognormal",
            "scientific_role":
                "PRIMARY_PARAMETRIC_REPRESENTATION",
            "primary_or_sensitivity":
                "PRIMARY",
        },
    ]

    simulation_arrays = {}

    simulation_summary_rows = []

    for experiment in experiments:

        scenario = experiment[
            "scenario"
        ]

        representation = experiment[
            "representation"
        ]

        role = experiment[
            "scientific_role"
        ]

        primary_or_sensitivity = experiment[
            "primary_or_sensitivity"
        ]

        seed = FINAL_SEEDS[
            (
                scenario,
                representation,
            )
        ]

        rng = np.random.default_rng(
            seed
        )

        if representation == "Empirical":

            simulated = simulate_empirical(
                samples[
                    scenario
                ],
                operational_n,
                rng,
            )

        elif representation == "Lognormal":

            params = lognormal_params[
                scenario
            ]

            simulated = simulate_lognormal(
                params[
                    "shape"
                ],
                params[
                    "loc"
                ],
                params[
                    "scale"
                ],
                operational_n,
                rng,
            )

        else:

            fail(
                "Unknown simulation representation: "
                f"{representation}"
            )

        simulation_arrays[
            (
                scenario,
                representation,
            )
        ] = simulated

        summary = summarize_distribution(
            simulated,
            exceedance_thresholds[
                scenario
            ],
        )

        simulation_summary_rows.append(
            {
                "scenario": scenario,
                "representation": representation,
                "scientific_role": role,
                "primary_or_sensitivity":
                    primary_or_sensitivity,
                "iterations": operational_n,
                "seed": seed,
                **summary,
            }
        )

        log(
            f"  {scenario} | {representation}: "
            f"N={operational_n:,}; "
            f"mean={summary['mean']:.2f}; "
            f"median={summary['median']:.2f}; "
            f"SD={summary['std']:.2f}; "
            f"P90={summary['p90']:.2f}; "
            f"P95={summary['p95']:.2f}"
        )

    simulation_summary = pd.DataFrame(
        simulation_summary_rows
    )

    log("")


    # =========================================================================
    # 12. COMPUTE LOGNORMAL THEORETICAL BENCHMARKS
    # =========================================================================

    log(
        "[12] Computing theoretical Lognormal benchmarks..."
    )

    theoretical_rows = []

    for scenario in SCENARIO_ORDER:

        params = lognormal_params[
            scenario
        ]

        theoretical = (
            lognormal_theoretical_summary(
                params[
                    "shape"
                ],
                params[
                    "loc"
                ],
                params[
                    "scale"
                ],
            )
        )

        theoretical_rows.append(
            {
                "scenario": scenario,
                "distribution": "Lognormal",
                "shape": params[
                    "shape"
                ],
                "loc": params[
                    "loc"
                ],
                "scale": params[
                    "scale"
                ],
                **theoretical,
            }
        )

        log(
            f"  {scenario}: "
            f"theoretical mean="
            f"{theoretical['theoretical_mean']:.2f}; "
            f"median="
            f"{theoretical['theoretical_median']:.2f}"
        )

    theoretical_benchmarks = pd.DataFrame(
        theoretical_rows
    )

    log("")


    # =========================================================================
    # 13. AUDIT MONTE CARLO NUMERICAL ACCURACY
    # =========================================================================

    log(
        "[13] Auditing final Monte Carlo numerical accuracy..."
    )

    numerical_accuracy_rows = []

    for _, row in simulation_summary.iterrows():

        scenario = row[
            "scenario"
        ]

        representation = row[
            "representation"
        ]

        if representation == "Empirical":

            reference = (
                empirical_benchmarks[
                    empirical_benchmarks[
                        "scenario"
                    ]
                    ==
                    scenario
                ]
                .iloc[0]
            )

            reference_type = (
                "Exact finite empirical distribution"
            )

            reference_values = {
                "mean": float(
                    reference[
                        "mean"
                    ]
                ),
                "median": float(
                    reference[
                        "median"
                    ]
                ),
                "std": float(
                    reference[
                        "std"
                    ]
                ),
                "p90": float(
                    reference[
                        "p90"
                    ]
                ),
                "p95": float(
                    reference[
                        "p95"
                    ]
                ),
            }

        else:

            reference = (
                theoretical_benchmarks[
                    theoretical_benchmarks[
                        "scenario"
                    ]
                    ==
                    scenario
                ]
                .iloc[0]
            )

            reference_type = (
                "Analytical Lognormal distribution"
            )

            reference_values = {
                "mean": float(
                    reference[
                        "theoretical_mean"
                    ]
                ),
                "median": float(
                    reference[
                        "theoretical_median"
                    ]
                ),
                "std": float(
                    reference[
                        "theoretical_std"
                    ]
                ),
                "p90": float(
                    reference[
                        "theoretical_p90"
                    ]
                ),
                "p95": float(
                    reference[
                        "theoretical_p95"
                    ]
                ),
            }

        numerical_accuracy_rows.append(
            {
                "scenario": scenario,
                "representation": representation,
                "reference_type": reference_type,

                "simulated_mean":
                    float(
                        row[
                            "mean"
                        ]
                    ),
                "reference_mean":
                    reference_values[
                        "mean"
                    ],
                "mean_relative_difference":
                    safe_relative_difference(
                        row[
                            "mean"
                        ],
                        reference_values[
                            "mean"
                        ],
                    ),

                "simulated_median":
                    float(
                        row[
                            "median"
                        ]
                    ),
                "reference_median":
                    reference_values[
                        "median"
                    ],
                "median_relative_difference":
                    safe_relative_difference(
                        row[
                            "median"
                        ],
                        reference_values[
                            "median"
                        ],
                    ),

                "simulated_std":
                    float(
                        row[
                            "std"
                        ]
                    ),
                "reference_std":
                    reference_values[
                        "std"
                    ],
                "std_relative_difference":
                    safe_relative_difference(
                        row[
                            "std"
                        ],
                        reference_values[
                            "std"
                        ],
                    ),

                "simulated_p90":
                    float(
                        row[
                            "p90"
                        ]
                    ),
                "reference_p90":
                    reference_values[
                        "p90"
                    ],
                "p90_relative_difference":
                    safe_relative_difference(
                        row[
                            "p90"
                        ],
                        reference_values[
                            "p90"
                        ],
                    ),

                "simulated_p95":
                    float(
                        row[
                            "p95"
                        ]
                    ),
                "reference_p95":
                    reference_values[
                        "p95"
                    ],
                "p95_relative_difference":
                    safe_relative_difference(
                        row[
                            "p95"
                        ],
                        reference_values[
                            "p95"
                        ],
                    ),
            }
        )

    numerical_accuracy = pd.DataFrame(
        numerical_accuracy_rows
    )

    for _, row in numerical_accuracy.iterrows():

        log(
            f"  {row['scenario']} | "
            f"{row['representation']}: "
            f"mean difference="
            f"{row['mean_relative_difference'] * 100:.3f}%"
        )

    log(
        "  NOTE: Low empirical quantiles retain finite-support "
        "behavior diagnosed in Script 13."
    )

    log("")


    # =========================================================================
    # 14. BUILD PRIMARY FINAL RESULTS
    # =========================================================================

    log(
        "[14] Building primary stochastic-results table..."
    )

    primary_rows = []

    for scenario in SCENARIO_ORDER:

        representation = (
            PRIMARY_REPRESENTATIONS[
                scenario
            ]
        )

        sim = (
            simulation_summary[
                (
                    simulation_summary[
                        "scenario"
                    ]
                    ==
                    scenario
                )
                &
                (
                    simulation_summary[
                        "representation"
                    ]
                    ==
                    representation
                )
            ]
            .iloc[0]
        )

        observed = (
            empirical_benchmarks[
                empirical_benchmarks[
                    "scenario"
                ]
                ==
                scenario
            ]
            .iloc[0]
        )

        primary_rows.append(
            {
                "scenario": scenario,
                "primary_representation":
                    representation,
                "iterations":
                    operational_n,

                "observed_n":
                    int(
                        observed[
                            "n"
                        ]
                    ),

                "observed_mean":
                    float(
                        observed[
                            "mean"
                        ]
                    ),
                "simulated_mean":
                    float(
                        sim[
                            "mean"
                        ]
                    ),

                "observed_median":
                    float(
                        observed[
                            "median"
                        ]
                    ),
                "simulated_median":
                    float(
                        sim[
                            "median"
                        ]
                    ),

                "observed_std":
                    float(
                        observed[
                            "std"
                        ]
                    ),
                "simulated_std":
                    float(
                        sim[
                            "std"
                        ]
                    ),

                "observed_p90":
                    float(
                        observed[
                            "p90"
                        ]
                    ),
                "simulated_p90":
                    float(
                        sim[
                            "p90"
                        ]
                    ),

                "observed_p95":
                    float(
                        observed[
                            "p95"
                        ]
                    ),
                "simulated_p95":
                    float(
                        sim[
                            "p95"
                        ]
                    ),

                "observed_exceedance_probability":
                    float(
                        observed[
                            "exceedance_probability"
                        ]
                    ),

                "simulated_exceedance_probability":
                    float(
                        sim[
                            "exceedance_probability"
                        ]
                    ),
            }
        )

    primary_results = pd.DataFrame(
        primary_rows
    )

    for _, row in primary_results.iterrows():

        log(
            f"  {row['scenario']}: "
            f"{row['primary_representation']} | "
            f"simulated median="
            f"{row['simulated_median']:.2f}; "
            f"simulated P95="
            f"{row['simulated_p95']:.2f}"
        )

    log("")


    # =========================================================================
    # 15. SCENARIO CONTRASTS
    # =========================================================================

    log(
        "[15] Quantifying primary scenario contrasts..."
    )

    primary_lookup = (
        primary_results
        .set_index(
            "scenario"
        )
    )

    contrast_pairs = [
        (
            "Medium",
            "Low",
        ),
        (
            "High",
            "Low",
        ),
        (
            "High",
            "Medium",
        ),
    ]

    contrast_rows = []

    for scenario_a, scenario_b in contrast_pairs:

        a = primary_lookup.loc[
            scenario_a
        ]

        b = primary_lookup.loc[
            scenario_b
        ]

        mean_difference = (
            a[
                "simulated_mean"
            ]
            -
            b[
                "simulated_mean"
            ]
        )

        median_difference = (
            a[
                "simulated_median"
            ]
            -
            b[
                "simulated_median"
            ]
        )

        std_difference = (
            a[
                "simulated_std"
            ]
            -
            b[
                "simulated_std"
            ]
        )

        p90_difference = (
            a[
                "simulated_p90"
            ]
            -
            b[
                "simulated_p90"
            ]
        )

        p95_difference = (
            a[
                "simulated_p95"
            ]
            -
            b[
                "simulated_p95"
            ]
        )

        mean_ratio = (
            a[
                "simulated_mean"
            ]
            /
            b[
                "simulated_mean"
            ]
            if
            b[
                "simulated_mean"
            ]
            != 0
            else
            np.nan
        )

        median_ratio = (
            a[
                "simulated_median"
            ]
            /
            b[
                "simulated_median"
            ]
            if
            b[
                "simulated_median"
            ]
            != 0
            else
            np.nan
        )

        p95_ratio = (
            a[
                "simulated_p95"
            ]
            /
            b[
                "simulated_p95"
            ]
            if
            b[
                "simulated_p95"
            ]
            != 0
            else
            np.nan
        )

        contrast_rows.append(
            {
                "scenario_a": scenario_a,
                "scenario_b": scenario_b,

                "mean_difference_days":
                    float(
                        mean_difference
                    ),
                "mean_ratio":
                    float(
                        mean_ratio
                    ),

                "median_difference_days":
                    float(
                        median_difference
                    ),
                "median_ratio":
                    float(
                        median_ratio
                    ),

                "std_difference_days":
                    float(
                        std_difference
                    ),

                "p90_difference_days":
                    float(
                        p90_difference
                    ),

                "p95_difference_days":
                    float(
                        p95_difference
                    ),
                "p95_ratio":
                    float(
                        p95_ratio
                    ),
            }
        )

        log(
            f"  {scenario_a} vs {scenario_b}: "
            f"median difference="
            f"{median_difference:.2f} days; "
            f"P95 difference="
            f"{p95_difference:.2f} days"
        )

    scenario_contrasts = pd.DataFrame(
        contrast_rows
    )

    log("")


    # =========================================================================
    # 16. PROBABILITY OF CROSS-SCENARIO ORDERING
    # =========================================================================

    log(
        "[16] Estimating stochastic cross-scenario ordering probabilities..."
    )

    low_primary = simulation_arrays[
        (
            "Low",
            "Empirical",
        )
    ]

    medium_primary = simulation_arrays[
        (
            "Medium",
            "Lognormal",
        )
    ]

    high_primary = simulation_arrays[
        (
            "High",
            "Lognormal",
        )
    ]

    # All arrays have the common operational N.
    # Pairing is used only as a reproducible Monte Carlo device
    # for estimating independent-draw comparison probabilities.

    probability_medium_gt_low = float(
        np.mean(
            medium_primary
            >
            low_primary
        )
    )

    probability_high_gt_low = float(
        np.mean(
            high_primary
            >
            low_primary
        )
    )

    probability_high_gt_medium = float(
        np.mean(
            high_primary
            >
            medium_primary
        )
    )

    probability_ordered_triplet = float(
        np.mean(
            (
                low_primary
                <
                medium_primary
            )
            &
            (
                medium_primary
                <
                high_primary
            )
        )
    )

    ordering_probabilities = pd.DataFrame(
        [
            {
                "comparison":
                    "P(T_Medium > T_Low)",
                "probability":
                    probability_medium_gt_low,
                "interpretation":
                    "Probability that an independent simulated Medium-scenario "
                    "duration exceeds an independent simulated Low-scenario duration.",
            },
            {
                "comparison":
                    "P(T_High > T_Low)",
                "probability":
                    probability_high_gt_low,
                "interpretation":
                    "Probability that an independent simulated High-scenario "
                    "duration exceeds an independent simulated Low-scenario duration.",
            },
            {
                "comparison":
                    "P(T_High > T_Medium)",
                "probability":
                    probability_high_gt_medium,
                "interpretation":
                    "Probability that an independent simulated High-scenario "
                    "duration exceeds an independent simulated Medium-scenario duration.",
            },
            {
                "comparison":
                    "P(T_Low < T_Medium < T_High)",
                "probability":
                    probability_ordered_triplet,
                "interpretation":
                    "Probability that three independently generated scenario "
                    "durations appear in the prespecified Low-Medium-High order.",
            },
        ]
    )

    for _, row in ordering_probabilities.iterrows():

        log(
            f"  {row['comparison']}: "
            f"{row['probability']:.4f}"
        )

    log(
        "  NOTE: These are stochastic comparison probabilities, "
        "not causal probabilities."
    )

    log("")


    # =========================================================================
    # 17. LOW PARAMETRIC SENSITIVITY
    # =========================================================================

    log(
        "[17] Evaluating Low empirical vs Low Lognormal sensitivity..."
    )

    low_empirical_summary = (
        simulation_summary[
            (
                simulation_summary[
                    "scenario"
                ]
                ==
                "Low"
            )
            &
            (
                simulation_summary[
                    "representation"
                ]
                ==
                "Empirical"
            )
        ]
        .iloc[0]
    )

    low_lognormal_summary = (
        simulation_summary[
            (
                simulation_summary[
                    "scenario"
                ]
                ==
                "Low"
            )
            &
            (
                simulation_summary[
                    "representation"
                ]
                ==
                "Lognormal"
            )
        ]
        .iloc[0]
    )

    low_sensitivity_rows = []

    for metric in [
        "mean",
        "median",
        "std",
        "p90",
        "p95",
        "p99",
        "exceedance_probability",
    ]:

        empirical_value = float(
            low_empirical_summary[
                metric
            ]
        )

        parametric_value = float(
            low_lognormal_summary[
                metric
            ]
        )

        difference = (
            parametric_value
            -
            empirical_value
        )

        relative_difference = (
            difference
            /
            abs(
                empirical_value
            )
            if
            abs(
                empirical_value
            )
            > 1e-12
            else
            np.nan
        )

        low_sensitivity_rows.append(
            {
                "metric": metric,
                "low_empirical_value":
                    empirical_value,
                "low_lognormal_value":
                    parametric_value,
                "absolute_difference":
                    difference,
                "relative_difference":
                    relative_difference,
                "scientific_role":
                    "Sensitivity only; empirical remains primary for Low.",
            }
        )

    low_sensitivity = pd.DataFrame(
        low_sensitivity_rows
    )

    log(
        "  Low empirical remains PRIMARY."
    )

    log(
        "  Low Lognormal remains PARAMETRIC SENSITIVITY ONLY."
    )

    log("")


    # =========================================================================
    # 18. BUILD DISTRIBUTION CURVES
    # =========================================================================

    log(
        "[18] Building reproducible stochastic distribution curves..."
    )

    curve_probabilities = np.concatenate(
        [
            np.arange(
                0.01,
                0.10,
                0.01,
            ),
            np.arange(
                0.10,
                0.91,
                0.05,
            ),
            np.arange(
                0.92,
                1.00,
                0.01,
            ),
        ]
    )

    curve_probabilities = np.unique(
        np.round(
            curve_probabilities,
            6,
        )
    )

    curve_rows = []

    for scenario in SCENARIO_ORDER:

        representation = (
            PRIMARY_REPRESENTATIONS[
                scenario
            ]
        )

        simulated = simulation_arrays[
            (
                scenario,
                representation,
            )
        ]

        for probability in curve_probabilities:

            curve_rows.append(
                {
                    "scenario": scenario,
                    "representation":
                        representation,
                    "cumulative_probability":
                        float(
                            probability
                        ),
                    "simulated_quantile_days":
                        float(
                            np.quantile(
                                simulated,
                                probability,
                            )
                        ),
                }
            )

    distribution_curves = pd.DataFrame(
        curve_rows
    )

    log(
        f"  Distribution-curve records: "
        f"{len(distribution_curves)}"
    )

    log("")


    # =========================================================================
    # 19. BUILD HISTOGRAM DATA
    # =========================================================================

    log(
        "[19] Building compact histogram data for reproducible figures..."
    )

    histogram_rows = []

    for scenario in SCENARIO_ORDER:

        representation = (
            PRIMARY_REPRESENTATIONS[
                scenario
            ]
        )

        simulated = simulation_arrays[
            (
                scenario,
                representation,
            )
        ]

        counts, edges = np.histogram(
            simulated,
            bins="fd",
            density=False,
        )

        probabilities = (
            counts
            /
            counts.sum()
        )

        for i in range(
            len(counts)
        ):

            histogram_rows.append(
                {
                    "scenario":
                        scenario,
                    "representation":
                        representation,
                    "bin_left":
                        float(
                            edges[
                                i
                            ]
                        ),
                    "bin_right":
                        float(
                            edges[
                                i + 1
                            ]
                        ),
                    "bin_midpoint":
                        float(
                            (
                                edges[
                                    i
                                ]
                                +
                                edges[
                                    i + 1
                                ]
                            )
                            / 2
                        ),
                    "count":
                        int(
                            counts[
                                i
                            ]
                        ),
                    "probability":
                        float(
                            probabilities[
                                i
                            ]
                        ),
                }
            )

    histogram_data = pd.DataFrame(
        histogram_rows
    )

    log(
        f"  Histogram records: "
        f"{len(histogram_data)}"
    )

    log("")


    # =========================================================================
    # 20. BUILD SIMULATION DRAW AUDIT SAMPLE
    # =========================================================================

    log(
        "[20] Building compact simulation-draw audit..."
    )

    # We deliberately do not write all 200,000 generated values to Excel.
    # The simulations are exactly reproducible from seeds and parameters.
    # A compact deterministic sample is retained for audit.

    audit_draw_rows = []

    AUDIT_DRAW_N = min(
        1_000,
        operational_n,
    )

    for (
        scenario,
        representation,
    ), simulated in simulation_arrays.items():

        for index in range(
            AUDIT_DRAW_N
        ):

            audit_draw_rows.append(
                {
                    "scenario":
                        scenario,
                    "representation":
                        representation,
                    "draw_index":
                        index + 1,
                    "simulated_award_time_days":
                        float(
                            simulated[
                                index
                            ]
                        ),
                }
            )

    simulation_draw_audit = pd.DataFrame(
        audit_draw_rows
    )

    log(
        f"  Stored audit draws: "
        f"{len(simulation_draw_audit):,}"
    )

    log(
        "  NOTE: Full simulations are reproducible from the "
        "recorded seeds, parameters, and operational N."
    )

    log("")


    # =========================================================================
    # 21. BUILD MODEL ARCHITECTURE AUDIT
    # =========================================================================

    log(
        "[21] Building final model-architecture audit..."
    )

    model_architecture = pd.DataFrame(
        [
            {
                "component":
                    "Exposure",
                "final_choice":
                    "queries_observations_count",
                "status":
                    "LOCKED_FROM_PRIOR_PHASE",
                "source":
                    "Scripts 03-12",
            },
            {
                "component":
                    "Primary outcome",
                "final_choice":
                    "total_award_time_days",
                "status":
                    "LOCKED_FROM_PRIOR_PHASE",
                "source":
                    "Scripts 03-12",
            },
            {
                "component":
                    "Primary scenario definition",
                "final_choice":
                    "Terciles",
                "status":
                    "LOCKED_FROM_SCRIPT_12",
                "source":
                    "Scripts 07-12",
            },
            {
                "component":
                    "Low primary representation",
                "final_choice":
                    "Empirical / nonparametric",
                "status":
                    "AUTHORIZED_PRIMARY",
                "source":
                    "Scripts 09-13",
            },
            {
                "component":
                    "Low sensitivity representation",
                "final_choice":
                    "Lognormal",
                "status":
                    "SENSITIVITY_ONLY",
                "source":
                    "Scripts 09-13",
            },
            {
                "component":
                    "Medium representation",
                "final_choice":
                    "Lognormal",
                "status":
                    "AUTHORIZED_PRIMARY",
                "source":
                    "Scripts 09-13",
            },
            {
                "component":
                    "High representation",
                "final_choice":
                    "Lognormal",
                "status":
                    "AUTHORIZED_PRIMARY",
                "source":
                    "Scripts 09-13",
            },
            {
                "component":
                    "Monte Carlo iterations",
                "final_choice":
                    operational_n,
                "status":
                    "AUTHORIZED_BY_CONVERGENCE",
                "source":
                    "Script 13",
            },
            {
                "component":
                    "Discrete-event simulation",
                "final_choice":
                    "Not performed in Script 14",
                "status":
                    "PENDING_SEPARATE_ASSESSMENT",
                "source":
                    "Script 12 protocol",
            },
            {
                "component":
                    "Causal interpretation",
                "final_choice":
                    "Not authorized",
                "status":
                    "EXCLUDED",
                "source":
                    "Entire analytical pipeline",
            },
        ]
    )

    log(
        "  Model architecture locked for this simulation."
    )

    log("")


    # =========================================================================
    # 22. BUILD INTERPRETATION AUDIT
    # =========================================================================

    log(
        "[22] Building scientific interpretation audit..."
    )

    interpretation_audit = pd.DataFrame(
        [
            {
                "issue":
                    "Meaning of Monte Carlo output",
                "interpretation":
                    "The simulated distributions propagate the stochastic "
                    "representations authorized by prior scripts. They do not "
                    "create new empirical observations.",
            },
            {
                "issue":
                    "Low empirical representation",
                "interpretation":
                    "Low is represented primarily by the observed empirical "
                    "distribution because the simple Lognormal model did not "
                    "receive sole-model authorization.",
            },
            {
                "issue":
                    "Low exact functionals",
                "interpretation":
                    "The exact empirical Low mean, median, dispersion and "
                    "quantiles remain the deterministic reference. Monte Carlo "
                    "resampling is used to propagate that empirical distribution.",
            },
            {
                "issue":
                    "Low Lognormal",
                "interpretation":
                    "The Low Lognormal model is reported only as a parametric "
                    "sensitivity analysis and must not replace the empirical "
                    "primary representation.",
            },
            {
                "issue":
                    "Medium and High",
                "interpretation":
                    "Medium and High use the Lognormal candidates authorized "
                    "for final stochastic simulation after distributional and "
                    "numerical-convergence assessment.",
            },
            {
                "issue":
                    "50,000 iterations",
                "interpretation":
                    "The operational iteration count is inherited from Script "
                    "13 and is not selected or modified in Script 14.",
            },
            {
                "issue":
                    "Scenario contrasts",
                "interpretation":
                    "Differences between simulated scenario distributions "
                    "describe conditional stochastic contrasts. They do not "
                    "identify a causal effect of queries or observations.",
            },
            {
                "issue":
                    "Ordering probabilities",
                "interpretation":
                    "Cross-scenario probabilities compare independent draws "
                    "from the specified scenario distributions. They are not "
                    "probabilities of causal treatment effects.",
            },
            {
                "issue":
                    "Observed sample size",
                "interpretation":
                    "Monte Carlo iterations increase numerical precision under "
                    "the fitted or empirical stochastic representation; they do "
                    "not increase the number of independent procurement cases.",
            },
            {
                "issue":
                    "Model validation",
                "interpretation":
                    "Numerical convergence and final simulation do not complete "
                    "scientific validation. External/temporal and empirical "
                    "validation remain subsequent pipeline tasks.",
            },
            {
                "issue":
                    "Discrete-event simulation",
                "interpretation":
                    "No DES result is generated here. Its feasibility and "
                    "incremental scientific value remain reserved for a "
                    "subsequent assessment.",
            },
        ]
    )

    log(
        "  Interpretation audit created."
    )

    log("")


    # =========================================================================
    # 23. REPRODUCIBILITY METADATA
    # =========================================================================

    log(
        "[23] Building reproducibility metadata..."
    )

    metadata = pd.DataFrame(
        [
            {
                "key":
                    "script",
                "value":
                    "14_monte_carlo_simulation.py",
            },
            {
                "key":
                    "execution_timestamp",
                "value":
                    datetime.now().isoformat(
                        timespec="seconds"
                    ),
            },
            {
                "key":
                    "python_version",
                "value":
                    sys.version.replace(
                        "\n",
                        " ",
                    ),
            },
            {
                "key":
                    "platform",
                "value":
                    platform.platform(),
            },
            {
                "key":
                    "numpy_version",
                "value":
                    np.__version__,
            },
            {
                "key":
                    "pandas_version",
                "value":
                    pd.__version__,
            },
            {
                "key":
                    "scipy_version",
                "value":
                    getattr(
                        stats,
                        "__version__",
                        "See scipy package metadata",
                    ),
            },
            {
                "key":
                    "master_expected_n",
                "value":
                    MASTER_EXPECTED_N,
            },
            {
                "key":
                    "available_total_award_times",
                "value":
                    available_award_times,
            },
            {
                "key":
                    "operational_monte_carlo_n",
                "value":
                    operational_n,
            },
            {
                "key":
                    "low_empirical_seed",
                "value":
                    FINAL_SEEDS[
                        (
                            "Low",
                            "Empirical",
                        )
                    ],
            },
            {
                "key":
                    "low_lognormal_seed",
                "value":
                    FINAL_SEEDS[
                        (
                            "Low",
                            "Lognormal",
                        )
                    ],
            },
            {
                "key":
                    "medium_lognormal_seed",
                "value":
                    FINAL_SEEDS[
                        (
                            "Medium",
                            "Lognormal",
                        )
                    ],
            },
            {
                "key":
                    "high_lognormal_seed",
                "value":
                    FINAL_SEEDS[
                        (
                            "High",
                            "Lognormal",
                        )
                    ],
            },
            {
                "key":
                    "primary_scenario_definition",
                "value":
                    "Terciles",
            },
            {
                "key":
                    "low_primary_representation",
                "value":
                    "Empirical",
            },
            {
                "key":
                    "medium_primary_representation",
                "value":
                    "Lognormal",
            },
            {
                "key":
                    "high_primary_representation",
                "value":
                    "Lognormal",
            },
        ]
    )

    log(
        "  Reproducibility metadata created."
    )

    log("")


    # =========================================================================
    # 24. SAVE OUTPUTS
    # =========================================================================

    log(
        "[24] Saving final Monte Carlo outputs..."
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        primary_results.to_excel(
            writer,
            sheet_name="primary_results",
            index=False,
        )

        simulation_summary.to_excel(
            writer,
            sheet_name="simulation_summary",
            index=False,
        )

        empirical_benchmarks.to_excel(
            writer,
            sheet_name="empirical_benchmarks",
            index=False,
        )

        theoretical_benchmarks.to_excel(
            writer,
            sheet_name="theoretical_benchmarks",
            index=False,
        )

        numerical_accuracy.to_excel(
            writer,
            sheet_name="numerical_accuracy",
            index=False,
        )

        scenario_contrasts.to_excel(
            writer,
            sheet_name="scenario_contrasts",
            index=False,
        )

        ordering_probabilities.to_excel(
            writer,
            sheet_name="ordering_probabilities",
            index=False,
        )

        low_sensitivity.to_excel(
            writer,
            sheet_name="low_sensitivity",
            index=False,
        )

        threshold_audit.to_excel(
            writer,
            sheet_name="threshold_audit",
            index=False,
        )

        sample_audit.to_excel(
            writer,
            sheet_name="sample_audit",
            index=False,
        )

        decision_audit.to_excel(
            writer,
            sheet_name="decision_audit",
            index=False,
        )

        model_architecture.to_excel(
            writer,
            sheet_name="model_architecture",
            index=False,
        )

        distribution_curves.to_excel(
            writer,
            sheet_name="distribution_curves",
            index=False,
        )

        histogram_data.to_excel(
            writer,
            sheet_name="histogram_data",
            index=False,
        )

        simulation_draw_audit.to_excel(
            writer,
            sheet_name="draw_audit",
            index=False,
        )

        interpretation_audit.to_excel(
            writer,
            sheet_name="interpretation_audit",
            index=False,
        )

        metadata.to_excel(
            writer,
            sheet_name="metadata",
            index=False,
        )

        simulation_targets.to_excel(
            writer,
            sheet_name="script12_targets",
            index=False,
        )

        authorization_13.to_excel(
            writer,
            sheet_name="script13_authorization",
            index=False,
        )

        experiment_decisions_13.to_excel(
            writer,
            sheet_name="script13_decisions",
            index=False,
        )

        reference_summary_13.to_excel(
            writer,
            sheet_name="script13_references",
            index=False,
        )

    log(
        f"  Output workbook: {OUTPUT_FILE.name}"
    )

    log(
        f"  Log file: {LOG_FILE.name}"
    )

    log("")


    # =========================================================================
    # FINAL AUDIT
    # =========================================================================

    separator()

    log(
        "FINAL MONTE CARLO SIMULATION AUDIT"
    )

    separator()

    log(
        f"Master analytical procedures:          {len(master)}"
    )

    log(
        f"Available total award times:           {available_award_times}"
    )

    log(
        f"Operational Monte Carlo iterations:    {operational_n:,}"
    )

    log("")

    log(
        "PRIMARY STOCHASTIC REPRESENTATIONS"
    )

    log("-" * 78)

    log(
        "Low        Empirical     PRIMARY ROBUST REPRESENTATION"
    )

    log(
        "Medium     Lognormal     PRIMARY PARAMETRIC REPRESENTATION"
    )

    log(
        "High       Lognormal     PRIMARY PARAMETRIC REPRESENTATION"
    )

    log(
        "Low        Lognormal     PARAMETRIC SENSITIVITY ONLY"
    )

    log("")

    log(
        "PRIMARY SIMULATION RESULTS"
    )

    log("-" * 78)

    for _, row in primary_results.iterrows():

        log(
            f"{row['scenario']:<10} "
            f"{row['primary_representation']:<12} | "
            f"mean={row['simulated_mean']:.2f} | "
            f"median={row['simulated_median']:.2f} | "
            f"SD={row['simulated_std']:.2f} | "
            f"P90={row['simulated_p90']:.2f} | "
            f"P95={row['simulated_p95']:.2f}"
        )

    log("")

    log(
        "STOCHASTIC ORDERING PROBABILITIES"
    )

    log("-" * 78)

    log(
        "P(T_Medium > T_Low):                  "
        f"{probability_medium_gt_low:.4f}"
    )

    log(
        "P(T_High > T_Low):                    "
        f"{probability_high_gt_low:.4f}"
    )

    log(
        "P(T_High > T_Medium):                 "
        f"{probability_high_gt_medium:.4f}"
    )

    log(
        "P(T_Low < T_Medium < T_High):         "
        f"{probability_ordered_triplet:.4f}"
    )

    log("")

    log(
        "SCIENTIFIC SCOPE"
    )

    log("-" * 78)

    log(
        "- Script 14 performs the final scenario-based Monte Carlo simulation."
    )

    log(
        "- The operational iteration count is inherited from Script 13."
    )

    log(
        "- The iteration count is not re-selected or optimized in this script."
    )

    log(
        "- Low uses empirical/nonparametric resampling as its primary representation."
    )

    log(
        "- Exact Low empirical functionals remain deterministic benchmarks."
    )

    log(
        "- Low Lognormal is retained only as parametric sensitivity."
    )

    log(
        "- Medium and High use the Lognormal representations authorized previously."
    )

    log(
        "- Monte Carlo iterations do not increase the number of independent tenders."
    )

    log(
        "- Scenario contrasts describe stochastic differences, not causal effects."
    )

    log(
        "- Numerical convergence does not prove the scientific truth of a distribution."
    )

    log(
        "- No observations are deleted."
    )

    log(
        "- No missing temporal values are imputed."
    )

    log(
        "- No scenario thresholds are redefined."
    )

    log(
        "- No probability distribution is re-selected."
    )

    log(
        "- No discrete-event simulation is performed."
    )

    log(
        "- Model validation remains a subsequent pipeline phase."
    )

    log("")

    separator()

    log(
        "PIPELINE STATUS: FINAL_MONTE_CARLO_SIMULATION_COMPLETE"
    )

    separator()

    save_log()


# =============================================================================
# EXECUTION
# =============================================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        if not LOG_LINES:

            print(
                f"ERROR: {exc}"
            )

        else:

            log("")
            log(
                "PIPELINE STATUS: FAILED"
            )
            save_log()

        raise
