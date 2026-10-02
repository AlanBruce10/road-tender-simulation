from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from scipy import stats


# =============================================================================
# 13_monte_carlo_convergence.py
# =============================================================================
# MONTE CARLO CONVERGENCE ASSESSMENT
# Road infrastructure tenders
#
# PURPOSE
# -------
# Determine empirically the minimum numerically sufficient Monte Carlo
# iteration count before the substantive stochastic simulation.
#
# IMPORTANT
# ---------
# 1. This script DOES NOT perform the final substantive simulation.
# 2. Convergence tolerances are NOT relaxed after observing results.
# 3. The original Script 12 iteration grid is preserved.
# 4. If genuine numerical non-convergence remains, a prospective extension
#    grid is evaluated automatically.
# 5. The Low empirical representation is treated specially because its
#    distribution is finite and discrete. Exact empirical functionals can
#    therefore be calculated directly without Monte Carlo approximation.
# 6. Failure of a very narrow simulated-median tolerance for a finite
#    empirical distribution is diagnosed separately from genuine numerical
#    non-convergence.
# =============================================================================


# =============================================================================
# CONFIGURATION
# =============================================================================

MASTER_EXPECTED_N = 137

SEEDS = [
    2026,
    3107,
    4219,
    5333,
    6421,
    7547,
    8641,
    9767,
    10891,
    12007,
]

REFERENCE_N = 1_000_000

# Original prespecified grid from Script 12
BASE_GRID = [
    100,
    500,
    1_000,
    2_500,
    5_000,
    10_000,
    25_000,
    50_000,
    100_000,
]

# Prospective extension.
# This is NOT used automatically for every failure.
# It is used only if the failure is classified as genuine numerical
# non-convergence rather than finite-support structural behavior.
EXTENSION_GRID = [
    250_000,
    500_000,
    1_000_000,
]

# -------------------------------------------------------------------------
# Convergence tolerances
# IMPORTANT: unchanged from the previous Script 13.
# -------------------------------------------------------------------------

REL_TOL_MEAN = 0.01
REL_TOL_MEDIAN = 0.01
REL_TOL_STD = 0.02
REL_TOL_P90 = 0.02
REL_TOL_P95 = 0.025
ABS_TOL_EXCEEDANCE = 0.01

REQUIRE_PERSISTENCE = True


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(__file__).resolve().parents[2]

INPUT_MASTER = (
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

OUTPUT_FILE = (
    STOCH_DIR
    / "13_1_monte_carlo_convergence.xlsx"
)

LOG_DIR = (
    ROOT
    / "03_logs"
    / "stochastic_modeling"
)

LOG_FILE = (
    LOG_DIR
    / "13_monte_carlo_convergence.log"
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
# BASIC FUNCTIONS
# =============================================================================

def safe_relative_error(value, reference):

    if pd.isna(value) or pd.isna(reference):
        return np.nan

    if abs(reference) < 1e-12:
        return abs(value - reference)

    return abs(value - reference) / abs(reference)


def summarize_sample(x, exceedance_threshold):

    x = np.asarray(
        x,
        dtype=float,
    )

    return {
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
        "exceedance_probability": float(
            np.mean(
                x > exceedance_threshold
            )
        ),
    }


def summarize_empirical_exact(
    x,
    exceedance_threshold,
):

    """
    Exact descriptive functionals of the observed
    finite empirical distribution.

    These values are deterministic.

    They are NOT Monte Carlo estimates.
    """

    x = np.asarray(
        x,
        dtype=float,
    )

    return {
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
        "exceedance_probability": float(
            np.mean(
                x > exceedance_threshold
            )
        ),
    }


# =============================================================================
# RANDOM GENERATORS
# =============================================================================

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
    scale,
    loc,
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


# =============================================================================
# CONVERGENCE RULE
# =============================================================================

def convergence_flag(row):

    return bool(

        row["mean_relative_error"]
        <= REL_TOL_MEAN

        and

        row["median_relative_error"]
        <= REL_TOL_MEDIAN

        and

        row["std_relative_error"]
        <= REL_TOL_STD

        and

        row["p90_relative_error"]
        <= REL_TOL_P90

        and

        row["p95_relative_error"]
        <= REL_TOL_P95

        and

        row["exceedance_absolute_error"]
        <= ABS_TOL_EXCEEDANCE
    )


# =============================================================================
# EMPIRICAL FINITE-SUPPORT DIAGNOSTIC
# =============================================================================

def empirical_quantile_support_diagnostic(
    observed,
    reference,
    tolerance,
    quantity,
):

    """
    Diagnostic for finite empirical distributions.

    Determines whether at least one observed support value can
    fall within the prespecified relative-error interval around
    the exact empirical reference.

    IMPORTANT:
    This function does NOT change the tolerance.
    """

    observed = np.asarray(
        observed,
        dtype=float,
    )

    support = np.unique(observed)

    if abs(reference) < 1e-12:

        errors = np.abs(
            support - reference
        )

    else:

        errors = (
            np.abs(
                support - reference
            )
            / abs(reference)
        )

    minimum_error = float(
        np.min(errors)
    )

    nearest_value = float(
        support[
            np.argmin(errors)
        ]
    )

    return {
        "quantity": quantity,
        "reference_value": float(reference),
        "nearest_observed_support_value": nearest_value,
        "minimum_support_relative_error": minimum_error,
        "prespecified_tolerance": float(tolerance),
        "support_value_within_tolerance": bool(
            minimum_error <= tolerance
        ),
    }


# =============================================================================
# GRID SIMULATION
# =============================================================================

def run_grid(
    experiments,
    grid,
    samples,
    lognormal_params,
    exceedance_thresholds,
    reference_summary,
):

    records = []

    for experiment_index, experiment in enumerate(
        experiments
    ):

        scenario = experiment["scenario"]

        representation = (
            experiment["representation"]
        )

        scientific_role = (
            experiment["scientific_role"]
        )

        threshold = (
            exceedance_thresholds[
                scenario
            ]
        )

        reference_row = (
            reference_summary[
                (
                    reference_summary[
                        "scenario"
                    ]
                    == scenario
                )
                &
                (
                    reference_summary[
                        "representation"
                    ]
                    == representation
                )
            ]
            .iloc[0]
        )

        for n in grid:

            for seed in SEEDS:

                derived_seed = (
                    seed
                    + 100_000
                    * (
                        experiment_index
                        + 1
                    )
                    + int(n)
                )

                rng = (
                    np.random.default_rng(
                        derived_seed
                    )
                )

                if (
                    representation
                    == "Empirical"
                ):

                    simulated = (
                        simulate_empirical(
                            samples[
                                scenario
                            ],
                            n,
                            rng,
                        )
                    )

                elif (
                    representation
                    == "Lognormal"
                ):

                    params = (
                        lognormal_params[
                            scenario
                        ]
                    )

                    simulated = (
                        simulate_lognormal(
                            params["shape"],
                            params["scale"],
                            params["loc"],
                            n,
                            rng,
                        )
                    )

                else:

                    fail(
                        "Unknown representation: "
                        + representation
                    )

                summary = (
                    summarize_sample(
                        simulated,
                        threshold,
                    )
                )

                record = {
                    "scenario": scenario,
                    "representation": representation,
                    "scientific_role": scientific_role,
                    "iterations": int(n),
                    "seed": int(seed),
                    "derived_seed": int(
                        derived_seed
                    ),
                    "exceedance_threshold_days": (
                        threshold
                    ),
                    **summary,
                }

                record[
                    "mean_relative_error"
                ] = safe_relative_error(
                    summary["mean"],
                    reference_row[
                        "reference_mean"
                    ],
                )

                record[
                    "median_relative_error"
                ] = safe_relative_error(
                    summary["median"],
                    reference_row[
                        "reference_median"
                    ],
                )

                record[
                    "std_relative_error"
                ] = safe_relative_error(
                    summary["std"],
                    reference_row[
                        "reference_std"
                    ],
                )

                record[
                    "p90_relative_error"
                ] = safe_relative_error(
                    summary["p90"],
                    reference_row[
                        "reference_p90"
                    ],
                )

                record[
                    "p95_relative_error"
                ] = safe_relative_error(
                    summary["p95"],
                    reference_row[
                        "reference_p95"
                    ],
                )

                record[
                    "exceedance_absolute_error"
                ] = abs(
                    summary[
                        "exceedance_probability"
                    ]
                    -
                    reference_row[
                        "reference_exceedance_probability"
                    ]
                )

                record[
                    "within_tolerance"
                ] = convergence_flag(
                    record
                )

                records.append(
                    record
                )

    return pd.DataFrame(
        records
    )


# =============================================================================
# CONVERGENCE SUMMARY
# =============================================================================

def summarize_convergence(
    convergence_df
):

    rows = []

    group_columns = [
        "scenario",
        "representation",
        "scientific_role",
        "iterations",
    ]

    for keys, group in (
        convergence_df.groupby(
            group_columns
        )
    ):

        (
            scenario,
            representation,
            scientific_role,
            n,
        ) = keys

        rows.append(
            {
                "scenario": scenario,
                "representation": representation,
                "scientific_role": scientific_role,
                "iterations": int(n),

                "seed_runs": len(
                    group
                ),

                "proportion_seeds_within_tolerance": float(
                    group[
                        "within_tolerance"
                    ].mean()
                ),

                "all_seeds_within_tolerance": bool(
                    group[
                        "within_tolerance"
                    ].all()
                ),

                "max_mean_relative_error": float(
                    group[
                        "mean_relative_error"
                    ].max()
                ),

                "max_median_relative_error": float(
                    group[
                        "median_relative_error"
                    ].max()
                ),

                "max_std_relative_error": float(
                    group[
                        "std_relative_error"
                    ].max()
                ),

                "max_p90_relative_error": float(
                    group[
                        "p90_relative_error"
                    ].max()
                ),

                "max_p95_relative_error": float(
                    group[
                        "p95_relative_error"
                    ].max()
                ),

                "max_exceedance_absolute_error": float(
                    group[
                        "exceedance_absolute_error"
                    ].max()
                ),

                "between_seed_cv_mean": float(
                    group["mean"].std(
                        ddof=1
                    )
                    /
                    group["mean"].mean()
                ),

                "between_seed_cv_median": float(
                    group["median"].std(
                        ddof=1
                    )
                    /
                    group[
                        "median"
                    ].mean()
                ),

                "between_seed_cv_std": float(
                    group["std"].std(
                        ddof=1
                    )
                    /
                    group["std"].mean()
                ),

                "between_seed_cv_p90": float(
                    group["p90"].std(
                        ddof=1
                    )
                    /
                    group["p90"].mean()
                ),

                "between_seed_cv_p95": float(
                    group["p95"].std(
                        ddof=1
                    )
                    /
                    group["p95"].mean()
                ),

                "between_seed_sd_exceedance_probability": float(
                    group[
                        "exceedance_probability"
                    ].std(
                        ddof=1
                    )
                ),
            }
        )

    summary = pd.DataFrame(
        rows
    )

    summary[
        "persistent_from_here"
    ] = False

    group_keys = [
        "scenario",
        "representation",
        "scientific_role",
    ]

    for _, indexes in (
        summary.groupby(
            group_keys
        ).groups.items()
    ):

        subset = (
            summary
            .loc[indexes]
            .sort_values(
                "iterations"
            )
        )

        flags = (
            subset[
                "all_seeds_within_tolerance"
            ]
            .astype(bool)
            .to_numpy()
        )

        persistence = []

        for i in range(
            len(flags)
        ):

            persistence.append(
                bool(
                    flags[
                        i:
                    ].all()
                )
            )

        summary.loc[
            subset.index,
            "persistent_from_here",
        ] = persistence

    return summary


# =============================================================================
# MAIN
# =============================================================================

def main():

    warnings.filterwarnings(
        "ignore"
    )

    separator()

    log(
        "MONTE CARLO CONVERGENCE ASSESSMENT - ROAD INFRASTRUCTURE TENDERS"
    )

    separator()

    log(
        "Purpose: Empirically determine the minimum numerically sufficient"
    )

    log(
        "Monte Carlo iteration count before final stochastic simulation."
    )

    log("")

    log(
        "IMPORTANT: Convergence tolerances are preserved unchanged."
    )

    log(
        "Finite-support empirical behavior is diagnosed separately."
    )

    log(
        "This is a convergence experiment, not the final simulation."
    )


    # =========================================================================
    # 1. INPUT VALIDATION
    # =========================================================================

    log("")

    log(
        "[1] Validating analytical inputs..."
    )

    required_files = [
        INPUT_MASTER,
        INPUT_07,
        INPUT_09,
        INPUT_12,
    ]

    for file in required_files:

        if not file.exists():

            fail(
                f"Required input not found: {file}"
            )

        log(
            f"  Found: {file.name}"
        )


    # =========================================================================
    # 2. READ INPUTS
    # =========================================================================

    log("")

    log(
        "[2] Reading source datasets..."
    )

    master = pd.read_excel(
        INPUT_MASTER
    )

    scenario_audit = pd.read_excel(
        INPUT_07,
        sheet_name="procedure_audit",
    )

    distribution_fits = pd.read_excel(
        INPUT_09,
        sheet_name="distribution_fits",
    )

    probability_spec = pd.read_excel(
        INPUT_12,
        sheet_name="probability_specification",
    )

    convergence_grid_12 = pd.read_excel(
        INPUT_12,
        sheet_name="convergence_grid",
    )

    convergence_criteria_12 = pd.read_excel(
        INPUT_12,
        sheet_name="convergence_criteria",
    )

    low_protocol = pd.read_excel(
        INPUT_12,
        sheet_name="low_scenario_protocol",
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


    # =========================================================================
    # 3. ANALYTICAL CONTRACT
    # =========================================================================

    log("")

    log(
        "[3] Validating analytical contract..."
    )

    if (
        len(master)
        != MASTER_EXPECTED_N
    ):

        fail(
            "Expected master analytical sample "
            f"n={MASTER_EXPECTED_N}, "
            f"found n={len(master)}."
        )

    required_master_columns = [
        "procedure_code",
        "queries_observations_count",
        "total_award_time_days",
    ]

    missing_columns = [
        column
        for column
        in required_master_columns
        if column
        not in master.columns
    ]

    if missing_columns:

        fail(
            "Missing master columns: "
            f"{missing_columns}"
        )

    if (
        master[
            "procedure_code"
        ]
        .duplicated()
        .any()
    ):

        fail(
            "Duplicate procedure_code values detected."
        )

    required_scenario_columns = [
        "procedure_code",
        "queries_observations_count",
        "total_award_time_days",
        "scenario_terciles",
    ]

    missing_columns = [
        column
        for column
        in required_scenario_columns
        if column
        not in scenario_audit.columns
    ]

    if missing_columns:

        fail(
            "Missing Script 07 columns: "
            f"{missing_columns}"
        )

    expected_scenarios = {
        "Low",
        "Medium",
        "High",
    }

    observed_scenarios = set(
        scenario_audit[
            "scenario_terciles"
        ]
        .dropna()
        .astype(str)
        .unique()
    )

    if (
        observed_scenarios
        != expected_scenarios
    ):

        fail(
            "Unexpected tercile scenario labels: "
            f"{sorted(observed_scenarios)}"
        )

    log(
        f"  Master analytical sample verified: {len(master)}"
    )

    available_award_times = (
        master[
            "total_award_time_days"
        ]
        .notna()
        .sum()
    )

    log(
        "  Available total award times: "
        f"{available_award_times}/{len(master)}"
    )

    log(
        "  Primary scenario definition verified: Terciles"
    )


    # =========================================================================
    # 4. SCRIPT 12 GRID
    # =========================================================================

    log("")

    log(
        "[4] Verifying prespecified convergence grid from Script 12..."
    )

    script12_grid = (
        convergence_grid_12[
            "iterations"
        ]
        .dropna()
        .astype(int)
        .tolist()
    )

    if (
        script12_grid
        != BASE_GRID
    ):

        fail(
            "Script 12 convergence grid differs from the "
            "expected prespecified base grid."
        )

    log(
        "  Original Script 12 grid verified:"
    )

    log(
        "  "
        + ", ".join(
            f"{x:,}"
            for x in BASE_GRID
        )
    )

    log("")

    log(
        "  Prospective extension grid:"
    )

    log(
        "  "
        + ", ".join(
            f"{x:,}"
            for x in EXTENSION_GRID
        )
    )

    log("")

    log(
        f"  Independent deterministic seeds: {len(SEEDS)}"
    )

    log(
        f"  High-iteration parametric reference: {REFERENCE_N:,}"
    )


    # =========================================================================
    # 5. SCENARIO SAMPLES
    # =========================================================================

    log("")

    log(
        "[5] Preparing primary tercile scenario samples..."
    )

    samples = {}

    for scenario in [
        "Low",
        "Medium",
        "High",
    ]:

        x = (
            scenario_audit.loc[
                scenario_audit[
                    "scenario_terciles"
                ]
                == scenario,
                "total_award_time_days",
            ]
            .dropna()
            .astype(float)
            .to_numpy()
        )

        if len(x) == 0:

            fail(
                "No award-time observations "
                f"for scenario {scenario}."
            )

        samples[
            scenario
        ] = x

        log(
            f"  {scenario}: "
            f"n={len(x)}; "
            f"min={np.min(x):.2f}; "
            f"median={np.median(x):.2f}; "
            f"max={np.max(x):.2f}"
        )


    # =========================================================================
    # 6. PROBABILITY REPRESENTATIONS
    # =========================================================================

    log("")

    log(
        "[6] Verifying probability representations authorized by Script 12..."
    )

    required_probability_columns = [
        "scenario",
        "aic_preferred_distribution",
        "simulation_authorization",
    ]

    missing_columns = [
        column
        for column
        in required_probability_columns
        if column
        not in probability_spec.columns
    ]

    if missing_columns:

        fail(
            "Missing Script 12 probability-specification columns: "
            f"{missing_columns}"
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

    for scenario in [
        "Low",
        "Medium",
        "High",
    ]:

        if (
            scenario
            not in probability_lookup
        ):

            fail(
                f"Scenario {scenario} missing "
                "from Script 12 probability specification."
            )

        row = (
            probability_lookup[
                scenario
            ]
        )

        log(
            f"  {scenario}: "
            f"{row['aic_preferred_distribution']} | "
            f"{row['simulation_authorization']}"
        )


    # =========================================================================
    # 7. LOGNORMAL PARAMETERS
    # =========================================================================

    log("")

    log(
        "[7] Extracting Script 09 Lognormal parameters..."
    )

    lognormal_params = {}

    for scenario in [
        "Low",
        "Medium",
        "High",
    ]:

        fit = distribution_fits[
            (
                distribution_fits[
                    "method"
                ]
                == "Terciles"
            )
            &
            (
                distribution_fits[
                    "scenario"
                ]
                == scenario
            )
            &
            (
                distribution_fits[
                    "distribution"
                ]
                == "Lognormal"
            )
        ]

        if len(fit) != 1:

            fail(
                "Expected exactly one "
                "Terciles/Lognormal fit for "
                f"{scenario}; found {len(fit)}."
            )

        fit = fit.iloc[0]

        shape = float(
            fit["shape_1"]
        )

        loc = float(
            fit["loc"]
        )

        scale = float(
            fit["scale"]
        )

        if (
            not np.isfinite(shape)
            or
            not np.isfinite(scale)
        ):

            fail(
                "Invalid Lognormal parameters "
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


    # =========================================================================
    # 8. EXPERIMENTS
    # =========================================================================

    log("")

    log(
        "[8] Defining convergence experiments..."
    )

    experiments = [

        {
            "scenario": "Low",
            "representation": "Empirical",
            "scientific_role":
                "PRIMARY_ROBUST_REPRESENTATION",
        },

        {
            "scenario": "Low",
            "representation": "Lognormal",
            "scientific_role":
                "PARAMETRIC_SENSITIVITY_ONLY",
        },

        {
            "scenario": "Medium",
            "representation": "Lognormal",
            "scientific_role":
                "PRIMARY_PARAMETRIC_CANDIDATE",
        },

        {
            "scenario": "High",
            "representation": "Lognormal",
            "scientific_role":
                "PRIMARY_PARAMETRIC_CANDIDATE",
        },
    ]

    for experiment in experiments:

        log(
            f"  {experiment['scenario']} | "
            f"{experiment['representation']} | "
            f"{experiment['scientific_role']}"
        )


    # =========================================================================
    # 9. EXCEEDANCE THRESHOLDS
    # =========================================================================

    log("")

    log(
        "[9] Defining scenario-specific exceedance thresholds..."
    )

    exceedance_thresholds = {}

    for scenario in [
        "Low",
        "Medium",
        "High",
    ]:

        threshold = float(
            np.quantile(
                samples[
                    scenario
                ],
                0.90,
            )
        )

        exceedance_thresholds[
            scenario
        ] = threshold

        log(
            f"  {scenario}: "
            f"empirical observed P90 = "
            f"{threshold:.2f} days"
        )

    log("")

    log(
        "  NOTE: Thresholds are fixed before the convergence experiment."
    )


    # =========================================================================
    # 10. REPRESENTATION-SPECIFIC REFERENCES
    # =========================================================================

    log("")

    log(
        "[10] Building representation-specific numerical references..."
    )

    reference_records = []

    for experiment_index, experiment in enumerate(
        experiments
    ):

        scenario = (
            experiment[
                "scenario"
            ]
        )

        representation = (
            experiment[
                "representation"
            ]
        )

        scientific_role = (
            experiment[
                "scientific_role"
            ]
        )

        threshold = (
            exceedance_thresholds[
                scenario
            ]
        )

        # ---------------------------------------------------------------------
        # EMPIRICAL
        # ---------------------------------------------------------------------

        if (
            representation
            == "Empirical"
        ):

            exact_summary = (
                summarize_empirical_exact(
                    samples[
                        scenario
                    ],
                    threshold,
                )
            )

            for seed in SEEDS:

                reference_records.append(
                    {
                        "scenario":
                            scenario,

                        "representation":
                            representation,

                        "scientific_role":
                            scientific_role,

                        "seed":
                            seed,

                        "derived_seed":
                            np.nan,

                        "reference_n":
                            len(
                                samples[
                                    scenario
                                ]
                            ),

                        "reference_type":
                            "EXACT_EMPIRICAL_FUNCTIONAL",

                        "exceedance_threshold_days":
                            threshold,

                        **exact_summary,
                    }
                )

            log(
                f"  {scenario} | Empirical: "
                "exact empirical functionals "
                "used as deterministic reference"
            )

        # ---------------------------------------------------------------------
        # PARAMETRIC
        # ---------------------------------------------------------------------

        elif (
            representation
            == "Lognormal"
        ):

            for seed in SEEDS:

                derived_seed = (
                    seed
                    + 100_000
                    * (
                        experiment_index
                        + 1
                    )
                    + 10_000_000
                )

                rng = (
                    np.random.default_rng(
                        derived_seed
                    )
                )

                params = (
                    lognormal_params[
                        scenario
                    ]
                )

                simulated = (
                    simulate_lognormal(
                        params["shape"],
                        params["scale"],
                        params["loc"],
                        REFERENCE_N,
                        rng,
                    )
                )

                summary = (
                    summarize_sample(
                        simulated,
                        threshold,
                    )
                )

                reference_records.append(
                    {
                        "scenario":
                            scenario,

                        "representation":
                            representation,

                        "scientific_role":
                            scientific_role,

                        "seed":
                            seed,

                        "derived_seed":
                            derived_seed,

                        "reference_n":
                            REFERENCE_N,

                        "reference_type":
                            "HIGH_ITERATION_MONTE_CARLO",

                        "exceedance_threshold_days":
                            threshold,

                        **summary,
                    }
                )

            log(
                f"  {scenario} | {representation}: "
                f"{len(SEEDS)} independent "
                "high-iteration references completed"
            )


    reference_df = pd.DataFrame(
        reference_records
    )

    reference_summary = (
        reference_df
        .groupby(
            [
                "scenario",
                "representation",
                "scientific_role",
            ],
            as_index=False,
        )
        .agg(

            reference_mean=(
                "mean",
                "mean",
            ),

            reference_median=(
                "median",
                "mean",
            ),

            reference_std=(
                "std",
                "mean",
            ),

            reference_p90=(
                "p90",
                "mean",
            ),

            reference_p95=(
                "p95",
                "mean",
            ),

            reference_exceedance_probability=(
                "exceedance_probability",
                "mean",
            ),

            between_seed_sd_mean=(
                "mean",
                "std",
            ),

            between_seed_sd_median=(
                "median",
                "std",
            ),

            between_seed_sd_std=(
                "std",
                "std",
            ),

            between_seed_sd_p90=(
                "p90",
                "std",
            ),

            between_seed_sd_p95=(
                "p95",
                "std",
            ),

            between_seed_sd_exceedance_probability=(
                "exceedance_probability",
                "std",
            ),
        )
    )


    # =========================================================================
    # 11. LOW EMPIRICAL FINITE-SUPPORT DIAGNOSTIC
    # =========================================================================

    log("")

    log(
        "[11] Diagnosing finite-support structure of Low empirical model..."
    )

    low_reference = (
        reference_summary[
            (
                reference_summary[
                    "scenario"
                ]
                == "Low"
            )
            &
            (
                reference_summary[
                    "representation"
                ]
                == "Empirical"
            )
        ]
        .iloc[0]
    )

    structural_records = []

    structural_definitions = [

        (
            "Median",
            "reference_median",
            REL_TOL_MEDIAN,
        ),

        (
            "P90",
            "reference_p90",
            REL_TOL_P90,
        ),

        (
            "P95",
            "reference_p95",
            REL_TOL_P95,
        ),
    ]

    for (
        quantity,
        reference_column,
        tolerance,
    ) in structural_definitions:

        diagnostic = (
            empirical_quantile_support_diagnostic(
                samples[
                    "Low"
                ],
                float(
                    low_reference[
                        reference_column
                    ]
                ),
                tolerance,
                quantity,
            )
        )

        diagnostic[
            "scenario"
        ] = "Low"

        diagnostic[
            "representation"
        ] = "Empirical"

        structural_records.append(
            diagnostic
        )

        log(
            f"  {quantity}: "
            f"reference="
            f"{diagnostic['reference_value']:.4f}; "
            f"nearest support="
            f"{diagnostic['nearest_observed_support_value']:.4f}; "
            f"minimum support error="
            f"{diagnostic['minimum_support_relative_error']:.4%}; "
            f"tolerance="
            f"{diagnostic['prespecified_tolerance']:.4%}; "
            f"attainable="
            f"{diagnostic['support_value_within_tolerance']}"
        )

    structural_diagnostic = (
        pd.DataFrame(
            structural_records
        )
    )

    median_diagnostic = (
        structural_diagnostic[
            structural_diagnostic[
                "quantity"
            ]
            == "Median"
        ]
        .iloc[0]
    )

    low_empirical_median_support_conflict = bool(
        not median_diagnostic[
            "support_value_within_tolerance"
        ]
    )

    if (
        low_empirical_median_support_conflict
    ):

        log("")

        log(
            "  STRUCTURAL FINDING:"
        )

        log(
            "  The nearest observed support value cannot satisfy "
            "the prespecified 1% median relative-error tolerance."
        )

        log(
            "  This is a finite-support property and is not treated "
            "automatically as evidence that more Monte Carlo "
            "iterations are required."
        )

    else:

        log(
            "  No structural median-support conflict detected."
        )


    # =========================================================================
    # 12. ORIGINAL BASE GRID
    # =========================================================================

    log("")

    log(
        "[12] Running original prespecified convergence grid..."
    )

    base_runs = run_grid(
        experiments,
        BASE_GRID,
        samples,
        lognormal_params,
        exceedance_thresholds,
        reference_summary,
    )

    base_summary = (
        summarize_convergence(
            base_runs
        )
    )

    log(
        f"  Candidate simulation runs: {len(base_runs):,}"
    )

    log(
        "  Original convergence grid completed."
    )


    # =========================================================================
    # 13. BASE GRID CLASSIFICATION
    # =========================================================================

    log("")

    log(
        "[13] Classifying base-grid convergence outcomes..."
    )

    preliminary_records = []

    for experiment in experiments:

        scenario = (
            experiment[
                "scenario"
            ]
        )

        representation = (
            experiment[
                "representation"
            ]
        )

        scientific_role = (
            experiment[
                "scientific_role"
            ]
        )

        subset = (
            base_summary[
                (
                    base_summary[
                        "scenario"
                    ]
                    == scenario
                )
                &
                (
                    base_summary[
                        "representation"
                    ]
                    == representation
                )
            ]
            .sort_values(
                "iterations"
            )
        )

        passing = (
            subset[
                subset[
                    "persistent_from_here"
                ]
            ]
        )

        # ---------------------------------------------------------------------
        # Already converged
        # ---------------------------------------------------------------------

        if len(passing) > 0:

            minimum_n = int(
                passing.iloc[0][
                    "iterations"
                ]
            )

            status = (
                "CONVERGED_IN_BASE_GRID"
            )

            next_action = (
                "NO_EXTENSION_REQUIRED"
            )

        # ---------------------------------------------------------------------
        # Structural empirical issue
        # ---------------------------------------------------------------------

        elif (
            scenario
            == "Low"
            and
            representation
            == "Empirical"
            and
            low_empirical_median_support_conflict
        ):

            minimum_n = np.nan

            status = (
                "STRICT_CRITERION_BLOCKED_BY_DISCRETE_SUPPORT"
            )

            next_action = (
                "USE_EXACT_EMPIRICAL_FUNCTIONALS_NO_GRID_CHASING"
            )

        # ---------------------------------------------------------------------
        # Genuine unresolved numerical convergence
        # ---------------------------------------------------------------------

        else:

            minimum_n = np.nan

            status = (
                "NOT_CONVERGED_IN_BASE_GRID"
            )

            next_action = (
                "EXTEND_GRID_PROSPECTIVELY"
            )

        preliminary_records.append(
            {
                "scenario":
                    scenario,

                "representation":
                    representation,

                "scientific_role":
                    scientific_role,

                "base_grid_status":
                    status,

                "base_grid_minimum_sufficient_iterations":
                    minimum_n,

                "next_action":
                    next_action,
            }
        )

        log(
            f"  {scenario} | {representation}: "
            f"{status}"
        )

        log(
            f"    Next action: {next_action}"
        )


    preliminary_decisions = (
        pd.DataFrame(
            preliminary_records
        )
    )


    # =========================================================================
    # 14. PROSPECTIVE GRID EXTENSION
    # =========================================================================

    log("")

    log(
        "[14] Applying prospective grid-extension rule..."
    )

    extension_experiments = []

    for experiment in experiments:

        scenario = (
            experiment[
                "scenario"
            ]
        )

        representation = (
            experiment[
                "representation"
            ]
        )

        decision = (
            preliminary_decisions[
                (
                    preliminary_decisions[
                        "scenario"
                    ]
                    == scenario
                )
                &
                (
                    preliminary_decisions[
                        "representation"
                    ]
                    == representation
                )
            ]
        )

        if len(decision) != 1:

            fail(
                "Unexpected preliminary decision count "
                f"for {scenario}/{representation}."
            )

        if (
            decision.iloc[0][
                "next_action"
            ]
            ==
            "EXTEND_GRID_PROSPECTIVELY"
        ):

            extension_experiments.append(
                experiment
            )


    if extension_experiments:

        log(
            "  Genuine unresolved numerical convergence detected."
        )

        log(
            "  Extension grid will be evaluated only for:"
        )

        for experiment in extension_experiments:

            log(
                f"    {experiment['scenario']} | "
                f"{experiment['representation']}"
            )

        extension_runs = (
            run_grid(
                extension_experiments,
                EXTENSION_GRID,
                samples,
                lognormal_params,
                exceedance_thresholds,
                reference_summary,
            )
        )

        convergence_runs = (
            pd.concat(
                [
                    base_runs,
                    extension_runs,
                ],
                ignore_index=True,
            )
        )

    else:

        log(
            "  No genuine numerical grid extension is required."
        )

        extension_runs = (
            pd.DataFrame(
                columns=base_runs.columns
            )
        )

        convergence_runs = (
            base_runs.copy()
        )


    # =========================================================================
    # 15. FINAL CONVERGENCE SUMMARY
    # =========================================================================

    log("")

    log(
        "[15] Recomputing convergence with all authorized grid points..."
    )

    convergence_summary = (
        summarize_convergence(
            convergence_runs
        )
    )

    log(
        "  Convergence summary completed."
    )


    # =========================================================================
    # 16. EXPERIMENT-SPECIFIC DECISIONS
    # =========================================================================

    log("")

    log(
        "[16] Determining experiment-specific numerical decisions..."
    )

    decision_records = []

    for experiment in experiments:

        scenario = (
            experiment[
                "scenario"
            ]
        )

        representation = (
            experiment[
                "representation"
            ]
        )

        scientific_role = (
            experiment[
                "scientific_role"
            ]
        )

        subset = (
            convergence_summary[
                (
                    convergence_summary[
                        "scenario"
                    ]
                    == scenario
                )
                &
                (
                    convergence_summary[
                        "representation"
                    ]
                    == representation
                )
            ]
            .sort_values(
                "iterations"
            )
        )

        passing = (
            subset[
                subset[
                    "persistent_from_here"
                ]
            ]
        )

        # ---------------------------------------------------------------------
        # Numerical convergence achieved
        # ---------------------------------------------------------------------

        if len(passing) > 0:

            minimum_n = int(
                passing.iloc[0][
                    "iterations"
                ]
            )

            status = (
                "CONVERGED"
            )

            numerical_role = (
                "MONTE_CARLO_N_REQUIRED"
            )

        # ---------------------------------------------------------------------
        # Low empirical finite-support structural issue
        # ---------------------------------------------------------------------

        elif (
            scenario
            == "Low"
            and
            representation
            == "Empirical"
            and
            low_empirical_median_support_conflict
        ):

            minimum_n = np.nan

            status = (
                "STRUCTURAL_DISCRETE_SUPPORT"
            )

            numerical_role = (
                "EXACT_EMPIRICAL_REFERENCE_PREFERRED"
            )

        # ---------------------------------------------------------------------
        # Still not converged
        # ---------------------------------------------------------------------

        else:

            minimum_n = np.nan

            status = (
                "NOT_CONVERGED_WITHIN_RULE_BASED_GRID"
            )

            numerical_role = (
                "FURTHER_ASSESSMENT_REQUIRED"
            )

        decision_records.append(
            {
                "scenario":
                    scenario,

                "representation":
                    representation,

                "scientific_role":
                    scientific_role,

                "minimum_sufficient_iterations":
                    minimum_n,

                "status":
                    status,

                "numerical_role":
                    numerical_role,

                "selection_rule":
                    (
                        "Smallest tested N for which all deterministic "
                        "seeds satisfy all unchanged prespecified "
                        "tolerances and compliance persists at every "
                        "larger tested N. Finite empirical support is "
                        "audited separately and does not trigger "
                        "arbitrary iteration inflation."
                    ),
            }
        )

        if pd.notna(
            minimum_n
        ):

            n_text = (
                f"{int(minimum_n):,}"
            )

        else:

            n_text = "N/A"

        log(
            f"  {scenario} | {representation}: "
            f"{status}; N={n_text}"
        )


    experiment_decisions = (
        pd.DataFrame(
            decision_records
        )
    )


    # =========================================================================
    # 17. COMMON OPERATIONAL MONTE CARLO N
    # =========================================================================

    log("")

    log(
        "[17] Determining common operational Monte Carlo iteration count..."
    )

    # -------------------------------------------------------------------------
    # IMPORTANT SCIENTIFIC DISTINCTION
    #
    # The Low empirical representation is scientifically primary for Low.
    # However, its exact empirical functionals are directly calculable.
    #
    # Therefore it does not logically require Monte Carlo integration
    # to discover its own empirical mean, median or quantiles.
    #
    # The common numerical Monte Carlo N is consequently determined
    # from the PRIMARY PARAMETRIC representations that genuinely
    # require random simulation:
    #
    # Medium Lognormal
    # High Lognormal
    #
    # Low empirical remains fully present in Script 14, but with its
    # exact empirical benchmarks explicitly retained.
    # -------------------------------------------------------------------------

    primary_parametric = (
        experiment_decisions[
            experiment_decisions[
                "scientific_role"
            ]
            ==
            "PRIMARY_PARAMETRIC_CANDIDATE"
        ]
        .copy()
    )

    if (
        len(primary_parametric)
        == 2
        and
        (
            primary_parametric[
                "status"
            ]
            == "CONVERGED"
        ).all()
    ):

        final_required_n = int(
            primary_parametric[
                "minimum_sufficient_iterations"
            ].max()
        )

        final_status = (
            "AUTHORIZED_FOR_FINAL_SIMULATION"
        )

        log(
            "  All primary parametric representations converged."
        )

        log(
            "  Common operational Monte Carlo count: "
            f"{final_required_n:,}"
        )

        if (
            low_empirical_median_support_conflict
        ):

            log("")

            log(
                "  Low empirical representation retains exact "
                "empirical benchmarks."
            )

            log(
                "  Its structural median-support conflict is "
                "reported separately and does not inflate the "
                "common Monte Carlo iteration count."
            )

    else:

        final_required_n = np.nan

        final_status = (
            "NOT_AUTHORIZED_"
            "FURTHER_NUMERICAL_ASSESSMENT_REQUIRED"
        )

        log(
            "  At least one primary parametric representation "
            "did not converge under the rule-based grid."
        )


    # =========================================================================
    # 18. AUDIT ORIGINAL 10,000 ITERATIONS
    # =========================================================================

    log("")

    log(
        "[18] Auditing the originally proposed 10,000 iterations..."
    )

    ten_thousand = (
        convergence_summary[
            convergence_summary[
                "iterations"
            ]
            == 10_000
        ]
        .copy()
    )

    primary_parametric_10k = (
        ten_thousand[
            ten_thousand[
                "scientific_role"
            ]
            ==
            "PRIMARY_PARAMETRIC_CANDIDATE"
        ]
    )

    if (
        len(
            primary_parametric_10k
        )
        == 2
        and
        primary_parametric_10k[
            "all_seeds_within_tolerance"
        ].all()
        and
        primary_parametric_10k[
            "persistent_from_here"
        ].all()
    ):

        ten_thousand_status = (
            "SUPPORTED_FOR_PRIMARY_PARAMETRIC_MODELS"
        )

    else:

        ten_thousand_status = (
            "NOT_SUPPORTED_AS_COMMON_OPERATIONAL_MINIMUM"
        )


    if np.isfinite(
        final_required_n
    ):

        if (
            final_required_n
            > 10_000
        ):

            ten_thousand_interpretation = (
                "10,000 iterations are below the empirically "
                "supported common operational requirement of "
                f"{final_required_n:,}."
            )

        elif (
            final_required_n
            == 10_000
        ):

            ten_thousand_interpretation = (
                "10,000 iterations equal the empirically "
                "supported common operational requirement."
            )

        else:

            ten_thousand_interpretation = (
                "10,000 iterations exceed the empirically "
                "supported common operational requirement."
            )

    else:

        ten_thousand_interpretation = (
            "A common operational iteration requirement "
            "remains unresolved."
        )


    log(
        "  10,000-iteration status: "
        f"{ten_thousand_status}"
    )

    log(
        "  Interpretation: "
        f"{ten_thousand_interpretation}"
    )


    # =========================================================================
    # 19. CONVERGENCE CRITERIA AUDIT
    # =========================================================================

    log("")

    log(
        "[19] Building unchanged convergence-criterion audit..."
    )

    tolerance_audit = pd.DataFrame(
        [

            {
                "quantity":
                    "Mean",

                "error_metric":
                    "Relative absolute error",

                "tolerance":
                    REL_TOL_MEAN,

                "tolerance_display":
                    "1.0%",

                "changed_after_observing_results":
                    False,
            },

            {
                "quantity":
                    "Median",

                "error_metric":
                    "Relative absolute error",

                "tolerance":
                    REL_TOL_MEDIAN,

                "tolerance_display":
                    "1.0%",

                "changed_after_observing_results":
                    False,
            },

            {
                "quantity":
                    "Standard deviation",

                "error_metric":
                    "Relative absolute error",

                "tolerance":
                    REL_TOL_STD,

                "tolerance_display":
                    "2.0%",

                "changed_after_observing_results":
                    False,
            },

            {
                "quantity":
                    "P90",

                "error_metric":
                    "Relative absolute error",

                "tolerance":
                    REL_TOL_P90,

                "tolerance_display":
                    "2.0%",

                "changed_after_observing_results":
                    False,
            },

            {
                "quantity":
                    "P95",

                "error_metric":
                    "Relative absolute error",

                "tolerance":
                    REL_TOL_P95,

                "tolerance_display":
                    "2.5%",

                "changed_after_observing_results":
                    False,
            },

            {
                "quantity":
                    "Exceedance probability",

                "error_metric":
                    "Absolute probability error",

                "tolerance":
                    ABS_TOL_EXCEEDANCE,

                "tolerance_display":
                    "0.01",

                "changed_after_observing_results":
                    False,
            },
        ]
    )


    # =========================================================================
    # 20. GRID AUDIT
    # =========================================================================

    grid_audit = pd.DataFrame(
        {
            "iterations":
                BASE_GRID
                +
                EXTENSION_GRID,

            "grid_role":
                (
                    [
                        "SCRIPT12_PRESPECIFIED_BASE"
                    ]
                    * len(
                        BASE_GRID
                    )
                )
                +
                (
                    [
                        "PROSPECTIVE_RULE_BASED_EXTENSION"
                    ]
                    * len(
                        EXTENSION_GRID
                    )
                ),
        }
    )


    # =========================================================================
    # 21. AUTHORIZATION DECISION
    # =========================================================================

    log("")

    log(
        "[20] Building Monte Carlo authorization decision..."
    )

    authorization = pd.DataFrame(
        [

            {
                "decision":
                    "Monte Carlo methodological role",

                "status":
                    "SUPPORTED",

                "value":
                    (
                        "Uncertainty propagation under "
                        "prespecified scenario-specific "
                        "representations"
                    ),

                "basis":
                    (
                        "Inherited from Scripts 11 and 12."
                    ),
            },

            {
                "decision":
                    "Low primary representation",

                "status":
                    "SUPPORTED_WITH_EXACT_EMPIRICAL_BENCHMARK",

                "value":
                    "Empirical/nonparametric",

                "basis":
                    (
                        "Finite empirical distribution retained "
                        "because the simple Lognormal representation "
                        "failed goodness-of-fit diagnostics."
                    ),
            },

            {
                "decision":
                    "Low empirical convergence interpretation",

                "status":
                    (
                        "STRUCTURAL_DISCRETE_SUPPORT"
                        if
                        low_empirical_median_support_conflict
                        else
                        "NO_STRUCTURAL_CONFLICT_DETECTED"
                    ),

                "value":
                    (
                        "Exact empirical functionals plus "
                        "Monte Carlo diagnostic"
                    ),

                "basis":
                    (
                        "Original numerical tolerances are preserved. "
                        "Finite-support quantile attainability is "
                        "audited separately."
                    ),
            },

            {
                "decision":
                    "Medium representation",

                "status":
                    "SUPPORTED_FOR_SIMULATION",

                "value":
                    "Lognormal",

                "basis":
                    (
                        "Authorized by Scripts 09 and 12."
                    ),
            },

            {
                "decision":
                    "High representation",

                "status":
                    "SUPPORTED_FOR_SIMULATION",

                "value":
                    "Lognormal",

                "basis":
                    (
                        "Authorized by Scripts 09 and 12."
                    ),
            },

            {
                "decision":
                    "Final operational iteration count",

                "status":
                    final_status,

                "value":
                    (
                        int(
                            final_required_n
                        )
                        if
                        np.isfinite(
                            final_required_n
                        )
                        else
                        "UNRESOLVED"
                    ),

                "basis":
                    (
                        "Maximum persistent minimum N among "
                        "primary parametric representations "
                        "requiring Monte Carlo numerical simulation."
                    ),
            },

            {
                "decision":
                    "Original 10,000 iterations",

                "status":
                    ten_thousand_status,

                "value":
                    10_000,

                "basis":
                    ten_thousand_interpretation,
            },
        ]
    )


    # =========================================================================
    # 22. INTERPRETATION AUDIT
    # =========================================================================

    interpretation_audit = pd.DataFrame(
        [

            {
                "issue":
                    "Convergence versus model validity",

                "interpretation":
                    (
                        "Numerical convergence controls Monte Carlo "
                        "sampling error. It does not prove that the "
                        "underlying stochastic model is scientifically true."
                    ),
            },

            {
                "issue":
                    "Prespecified tolerances",

                "interpretation":
                    (
                        "All numerical tolerances are retained unchanged "
                        "from the previous Script 13. No criterion is "
                        "relaxed after observing the results."
                    ),
            },

            {
                "issue":
                    "Grid extension",

                "interpretation":
                    (
                        "Extension is prospective and rule-based. "
                        "It is used only when failure is consistent "
                        "with genuine numerical non-convergence."
                    ),
            },

            {
                "issue":
                    "Low empirical distribution",

                "interpretation":
                    (
                        "The empirical distribution has deterministic "
                        "descriptive functionals available directly "
                        "from its finite observed support."
                    ),
            },

            {
                "issue":
                    "Discrete empirical quantiles",

                "interpretation":
                    (
                        "Monte Carlo resampling from a finite empirical "
                        "distribution produces discrete quantile behavior. "
                        "A narrow relative-error criterion can therefore "
                        "remain unsatisfied even when increasing N does "
                        "not represent a meaningful scientific improvement."
                    ),
            },

            {
                "issue":
                    "Common operational N",

                "interpretation":
                    (
                        "The common Monte Carlo N is determined from "
                        "primary parametric representations that require "
                        "numerical stochastic simulation. The Low empirical "
                        "representation retains exact empirical benchmarks."
                    ),
            },

            {
                "issue":
                    "10,000 iterations",

                "interpretation":
                    (
                        "The originally proposed 10,000 iterations are "
                        "not accepted because they appeared in the thesis "
                        "proposal. They are evaluated empirically against "
                        "the same convergence rules as every other N."
                    ),
            },

            {
                "issue":
                    "Final simulation",

                "interpretation":
                    (
                        "No substantive final Monte Carlo findings "
                        "are generated by Script 13. Final stochastic "
                        "simulation remains reserved for Script 14."
                    ),
            },
        ]
    )


    # =========================================================================
    # 23. SAVE OUTPUTS
    # =========================================================================

    log("")

    log(
        "[21] Saving reproducible convergence outputs..."
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        reference_df.to_excel(
            writer,
            sheet_name="reference_runs",
            index=False,
        )

        reference_summary.to_excel(
            writer,
            sheet_name="reference_summary",
            index=False,
        )

        base_runs.to_excel(
            writer,
            sheet_name="base_grid_runs",
            index=False,
        )

        extension_runs.to_excel(
            writer,
            sheet_name="extension_runs",
            index=False,
        )

        convergence_runs.to_excel(
            writer,
            sheet_name="convergence_runs",
            index=False,
        )

        convergence_summary.to_excel(
            writer,
            sheet_name="convergence_summary",
            index=False,
        )

        preliminary_decisions.to_excel(
            writer,
            sheet_name="preliminary_decisions",
            index=False,
        )

        structural_diagnostic.to_excel(
            writer,
            sheet_name="structural_diagnostic",
            index=False,
        )

        experiment_decisions.to_excel(
            writer,
            sheet_name="experiment_decisions",
            index=False,
        )

        tolerance_audit.to_excel(
            writer,
            sheet_name="tolerance_audit",
            index=False,
        )

        grid_audit.to_excel(
            writer,
            sheet_name="grid_audit",
            index=False,
        )

        authorization.to_excel(
            writer,
            sheet_name="authorization",
            index=False,
        )

        interpretation_audit.to_excel(
            writer,
            sheet_name="interpretation_audit",
            index=False,
        )

        convergence_grid_12.to_excel(
            writer,
            sheet_name="script12_grid",
            index=False,
        )

        convergence_criteria_12.to_excel(
            writer,
            sheet_name="script12_criteria",
            index=False,
        )

        low_protocol.to_excel(
            writer,
            sheet_name="low_protocol",
            index=False,
        )


    log(
        f"  Output workbook: {OUTPUT_FILE.name}"
    )

    log(
        f"  Log file: {LOG_FILE.name}"
    )


    # =========================================================================
    # FINAL AUDIT
    # =========================================================================

    log("")

    separator()

    log(
        "MONTE CARLO CONVERGENCE AUDIT - IMPROVED"
    )

    separator()

    log(
        f"Master analytical procedures:          {len(master)}"
    )

    log(
        f"Available total award times:           {available_award_times}"
    )

    log(
        f"Independent deterministic seeds:       {len(SEEDS)}"
    )

    log(
        f"Parametric reference N per seed:       {REFERENCE_N:,}"
    )


    log("")

    log(
        "BASE GRID"
    )

    log(
        "-" * 78
    )

    log(
        ", ".join(
            f"{x:,}"
            for x in BASE_GRID
        )
    )


    log("")

    log(
        "PROSPECTIVE EXTENSION GRID"
    )

    log(
        "-" * 78
    )

    log(
        ", ".join(
            f"{x:,}"
            for x in EXTENSION_GRID
        )
    )


    log("")

    log(
        "EXPERIMENT-SPECIFIC DECISIONS"
    )

    log(
        "-" * 78
    )

    for _, row in (
        experiment_decisions.iterrows()
    ):

        if pd.notna(
            row[
                "minimum_sufficient_iterations"
            ]
        ):

            n_text = (
                f"{int(row['minimum_sufficient_iterations']):,}"
            )

        else:

            n_text = "N/A"

        log(
            f"{row['scenario']:<10} "
            f"{row['representation']:<12} "
            f"{row['status']:<40} "
            f"{n_text}"
        )


    log("")

    log(
        "LOW EMPIRICAL STRUCTURAL DIAGNOSTIC"
    )

    log(
        "-" * 78
    )

    log(
        "Median support conflict:               "
        f"{low_empirical_median_support_conflict}"
    )


    log("")

    log(
        "PRIMARY MONTE CARLO DECISION"
    )

    log(
        "-" * 78
    )

    if np.isfinite(
        final_required_n
    ):

        log(
            "Common operational iterations:         "
            f"{final_required_n:,}"
        )

    else:

        log(
            "Common operational iterations:         "
            "NOT RESOLVED"
        )

    log(
        "Final convergence status:              "
        f"{final_status}"
    )

    log(
        "Original 10,000-iteration proposal:    "
        f"{ten_thousand_status}"
    )


    log("")

    log(
        "UNCHANGED CONVERGENCE TOLERANCES"
    )

    log(
        "-" * 78
    )

    log(
        "Mean relative error:                   "
        f"<= {REL_TOL_MEAN:.1%}"
    )

    log(
        "Median relative error:                 "
        f"<= {REL_TOL_MEDIAN:.1%}"
    )

    log(
        "SD relative error:                     "
        f"<= {REL_TOL_STD:.1%}"
    )

    log(
        "P90 relative error:                    "
        f"<= {REL_TOL_P90:.1%}"
    )

    log(
        "P95 relative error:                    "
        f"<= {REL_TOL_P95:.1%}"
    )

    log(
        "Exceedance probability absolute error: "
        f"<= {ABS_TOL_EXCEEDANCE:.3f}"
    )


    log("")

    log(
        "SCIENTIFIC SCOPE"
    )

    log(
        "- The original convergence tolerances were not changed."
    )

    log(
        "- Script 12's original iteration grid remains explicitly preserved."
    )

    log(
        "- Grid extension is prospective and rule-based rather than "
        "manually chosen after observing a favorable result."
    )

    log(
        "- Low empirical finite-support behavior is diagnosed separately "
        "from genuine numerical non-convergence."
    )

    log(
        "- Exact empirical functionals are used as the reference for "
        "the Low empirical representation."
    )

    log(
        "- Medium and High Lognormal models remain the primary "
        "parametric Monte Carlo convergence targets."
    )

    log(
        "- Low Lognormal remains a parametric sensitivity analysis only."
    )

    log(
        "- Numerical convergence does not establish distributional truth."
    )

    log(
        "- Numerical convergence does not establish causality."
    )

    log(
        "- No observations are deleted."
    )

    log(
        "- No missing temporal values are imputed."
    )

    log(
        "- No discrete-event simulation is performed."
    )

    log(
        "- Final substantive stochastic results remain reserved "
        "for Script 14."
    )


    log("")

    separator()


    if (
        final_status
        ==
        "AUTHORIZED_FOR_FINAL_SIMULATION"
    ):

        log(
            "PIPELINE STATUS: "
            "MONTE_CARLO_NUMERICALLY_AUTHORIZED_FOR_SCRIPT_14"
        )

    else:

        log(
            "PIPELINE STATUS: "
            "MONTE_CARLO_CONVERGENCE_REQUIRES_FURTHER_ASSESSMENT"
        )


    separator()

    save_log()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        try:

            log("")

            separator()

            log(
                "PIPELINE STATUS: FAILED"
            )

            log(
                str(exc)
            )

            separator()

            save_log()

        finally:

            raise
