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
RANDOM_SEED = 2026

SCENARIO_ORDER = ["Low", "Medium", "High"]

# Primary distribution identified in Script 09.
# This is evaluated diagnostically here; it is NOT imposed as final model.
PRIMARY_DISTRIBUTION_NAME = "Lognormal"
PRIMARY_DISTRIBUTION = stats.lognorm

# Candidate families retained only for comparative diagnostics.
CANDIDATE_DISTRIBUTIONS = {
    "Lognormal": stats.lognorm,
    "Weibull": stats.weibull_min,
    "Gamma": stats.gamma,
    "Exponential": stats.expon,
}

# Quantiles used for empirical-vs-fitted diagnostics.
DIAGNOSTIC_PROBABILITIES = np.array(
    [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95],
    dtype=float,
)

# Leave-one-out empirical predictive diagnostic.
# Small smoothing is required because a pure empirical distribution assigns
# zero probability outside observed support.
EMPIRICAL_SMOOTHING = 0.5

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]

SCENARIO_INPUT_FILE = (
    PROJECT_ROOT
    / "02_results"
    / "statistical_analysis"
    / "07_1_scenario_definition.xlsx"
)

FIT_INPUT_FILE = (
    PROJECT_ROOT
    / "02_results"
    / "statistical_analysis"
    / "09_1_distribution_fitting.xlsx"
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
    / "10_1_distribution_diagnostics.xlsx"
)

LOG_FILE = (
    LOGS_DIR
    / "10_distribution_diagnostics.log"
)

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("distribution_diagnostics")
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
# GENERAL HELPERS
# =============================================================================

def fit_distribution(distribution_name, values):
    """
    Maximum-likelihood fit with loc fixed at zero.
    Same support convention used in Script 09.
    """

    values = np.asarray(values, dtype=float)

    if np.any(~np.isfinite(values)):
        raise ValueError("Non-finite values detected.")

    if np.any(values <= 0):
        raise ValueError(
            "Positive-support distributions require strictly positive values."
        )

    distribution = CANDIDATE_DISTRIBUTIONS[distribution_name]

    params = distribution.fit(
        values,
        floc=0,
    )

    return tuple(float(x) for x in params)


def empirical_cdf_coordinates(values):
    values = np.sort(
        np.asarray(values, dtype=float)
    )

    n = len(values)

    ecdf = (
        np.arange(1, n + 1, dtype=float)
        / n
    )

    ecdf_left = (
        np.arange(0, n, dtype=float)
        / n
    )

    return values, ecdf, ecdf_left


def ks_location_diagnostic(
    values,
    distribution_name,
    params,
):
    """
    Locate the largest empirical-vs-model CDF discrepancy.

    Reports both D+ and D- components so we can identify where
    the fitted model departs most strongly from the observed data.
    """

    distribution = CANDIDATE_DISTRIBUTIONS[
        distribution_name
    ]

    x, ecdf, ecdf_left = (
        empirical_cdf_coordinates(values)
    )

    fitted_cdf = distribution.cdf(
        x,
        *params,
    )

    d_plus = ecdf - fitted_cdf
    d_minus = fitted_cdf - ecdf_left

    idx_plus = int(
        np.argmax(d_plus)
    )

    idx_minus = int(
        np.argmax(d_minus)
    )

    max_plus = float(
        d_plus[idx_plus]
    )

    max_minus = float(
        d_minus[idx_minus]
    )

    if max_plus >= max_minus:
        maximum_type = "D_PLUS"
        maximum_value = max_plus
        maximum_x = float(
            x[idx_plus]
        )
        empirical_at_max = float(
            ecdf[idx_plus]
        )
        fitted_at_max = float(
            fitted_cdf[idx_plus]
        )
    else:
        maximum_type = "D_MINUS"
        maximum_value = max_minus
        maximum_x = float(
            x[idx_minus]
        )
        empirical_at_max = float(
            ecdf_left[idx_minus]
        )
        fitted_at_max = float(
            fitted_cdf[idx_minus]
        )

    empirical_quantile_position = float(
        np.mean(
            x <= maximum_x
        )
    )

    return {
        "distribution": distribution_name,
        "ks_component": maximum_type,
        "ks_maximum": maximum_value,
        "time_at_maximum_days": maximum_x,
        "empirical_cdf_at_maximum": empirical_at_max,
        "fitted_cdf_at_maximum": fitted_at_max,
        "empirical_quantile_position": empirical_quantile_position,
        "d_plus": max_plus,
        "d_minus": max_minus,
    }


def quantile_diagnostic(
    values,
    distribution_name,
    params,
):
    distribution = CANDIDATE_DISTRIBUTIONS[
        distribution_name
    ]

    empirical = np.quantile(
        values,
        DIAGNOSTIC_PROBABILITIES,
    )

    fitted = distribution.ppf(
        DIAGNOSTIC_PROBABILITIES,
        *params,
    )

    rows = []

    for probability, empirical_q, fitted_q in zip(
        DIAGNOSTIC_PROBABILITIES,
        empirical,
        fitted,
    ):
        error = float(
            fitted_q - empirical_q
        )

        rows.append(
            {
                "distribution": distribution_name,
                "probability": float(probability),
                "empirical_quantile": float(empirical_q),
                "fitted_quantile": float(fitted_q),
                "signed_error_days": error,
                "absolute_error_days": abs(error),
                "relative_absolute_error": (
                    abs(error) / empirical_q
                    if empirical_q != 0
                    else np.nan
                ),
            }
        )

    return rows


def value_concentration_diagnostic(values):
    """
    Diagnose repeated observed durations.

    Procurement durations are integer-day observations, so ties are expected.
    This diagnostic quantifies concentration without labeling ties as errors.
    """

    series = pd.Series(
        np.asarray(values, dtype=float)
    )

    counts = (
        series.value_counts()
        .sort_values(
            ascending=False
        )
    )

    n = len(series)
    unique_values = int(
        series.nunique()
    )

    repeated_observations = int(
        counts[counts > 1].sum()
    )

    repeated_value_levels = int(
        (counts > 1).sum()
    )

    maximum_frequency = int(
        counts.iloc[0]
    )

    maximum_frequency_share = (
        maximum_frequency / n
    )

    top_rows = []

    for value, frequency in (
        counts.head(10).items()
    ):
        top_rows.append(
            {
                "duration_days": float(value),
                "frequency": int(frequency),
                "share": float(
                    frequency / n
                ),
            }
        )

    summary = {
        "n": n,
        "unique_duration_values": unique_values,
        "unique_ratio": (
            unique_values / n
        ),
        "repeated_value_levels": repeated_value_levels,
        "observations_in_repeated_values": repeated_observations,
        "share_observations_in_repeated_values": (
            repeated_observations / n
        ),
        "maximum_single_value_frequency": maximum_frequency,
        "maximum_single_value_share": maximum_frequency_share,
    }

    return summary, top_rows


def tail_summary(values):
    values = np.asarray(
        values,
        dtype=float,
    )

    q75 = float(
        np.quantile(values, 0.75)
    )

    q90 = float(
        np.quantile(values, 0.90)
    )

    q95 = float(
        np.quantile(values, 0.95)
    )

    iqr = float(
        np.quantile(values, 0.75)
        - np.quantile(values, 0.25)
    )

    upper_iqr_fence = (
        q75 + 1.5 * iqr
    )

    return {
        "n": len(values),
        "minimum": float(np.min(values)),
        "median": float(np.median(values)),
        "mean": float(np.mean(values)),
        "std_dev": float(
            np.std(
                values,
                ddof=1,
            )
        ),
        "p75": q75,
        "p90": q90,
        "p95": q95,
        "maximum": float(np.max(values)),
        "iqr": iqr,
        "upper_iqr_fence": float(
            upper_iqr_fence
        ),
        "n_above_upper_iqr_fence": int(
            np.sum(
                values
                > upper_iqr_fence
            )
        ),
        "share_above_upper_iqr_fence": float(
            np.mean(
                values
                > upper_iqr_fence
            )
        ),
    }


def trimmed_fit_sensitivity(
    values,
    distribution_name,
):
    """
    Diagnostic sensitivity only.

    Refit after removing the single largest observation and after restricting
    to observations <= empirical P95. This does NOT authorize deletion from
    the scientific sample.
    """

    values = np.asarray(
        values,
        dtype=float,
    )

    full_params = fit_distribution(
        distribution_name,
        values,
    )

    full_ks = stats.kstest(
        values,
        lambda x: CANDIDATE_DISTRIBUTIONS[
            distribution_name
        ].cdf(
            x,
            *full_params,
        ),
    ).statistic

    max_removed = np.sort(values)[:-1]

    max_removed_params = (
        fit_distribution(
            distribution_name,
            max_removed,
        )
    )

    max_removed_ks = stats.kstest(
        max_removed,
        lambda x: CANDIDATE_DISTRIBUTIONS[
            distribution_name
        ].cdf(
            x,
            *max_removed_params,
        ),
    ).statistic

    p95 = float(
        np.quantile(
            values,
            0.95,
        )
    )

    p95_subset = values[
        values <= p95
    ]

    p95_params = fit_distribution(
        distribution_name,
        p95_subset,
    )

    p95_ks = stats.kstest(
        p95_subset,
        lambda x: CANDIDATE_DISTRIBUTIONS[
            distribution_name
        ].cdf(
            x,
            *p95_params,
        ),
    ).statistic

    return {
        "distribution": distribution_name,
        "full_n": len(values),
        "full_ks": float(full_ks),
        "max_removed_n": len(max_removed),
        "max_removed_ks": float(
            max_removed_ks
        ),
        "p95_threshold": p95,
        "p95_subset_n": len(
            p95_subset
        ),
        "p95_subset_ks": float(
            p95_ks
        ),
        "ks_change_after_max_removed": float(
            max_removed_ks
            - full_ks
        ),
        "ks_change_after_p95_restriction": float(
            p95_ks
            - full_ks
        ),
    }


# =============================================================================
# EMPIRICAL PREDICTIVE DIAGNOSTIC
# =============================================================================

def empirical_interval_probability(
    training_values,
    lower,
    upper,
):
    """
    Smoothed empirical probability for a finite interval.

    This is used only as a predictive diagnostic and is not a KDE or
    a final simulation model.
    """

    training_values = np.asarray(
        training_values,
        dtype=float,
    )

    n = len(training_values)

    inside = np.sum(
        (training_values >= lower)
        & (training_values <= upper)
    )

    return (
        inside + EMPIRICAL_SMOOTHING
    ) / (
        n + EMPIRICAL_SMOOTHING * 2
    )


def leave_one_out_predictive_scores(
    values,
):
    """
    Compare a fitted Lognormal predictive representation with a simple
    empirical predictive representation using leave-one-out observations.

    Because durations are recorded in integer days, probability mass for the
    parametric model is evaluated over [y-0.5, y+0.5].

    The empirical comparator is deliberately simple. It is diagnostic only.
    """

    values = np.asarray(
        values,
        dtype=float,
    )

    rows = []

    for i in range(len(values)):

        test_value = float(
            values[i]
        )

        training = np.delete(
            values,
            i,
        )

        params = fit_distribution(
            PRIMARY_DISTRIBUTION_NAME,
            training,
        )

        lower = max(
            0.0,
            test_value - 0.5,
        )

        upper = (
            test_value + 0.5
        )

        parametric_probability = (
            PRIMARY_DISTRIBUTION.cdf(
                upper,
                *params,
            )
            - PRIMARY_DISTRIBUTION.cdf(
                lower,
                *params,
            )
        )

        parametric_probability = max(
            float(
                parametric_probability
            ),
            1e-300,
        )

        empirical_probability = (
            empirical_interval_probability(
                training,
                lower,
                upper,
            )
        )

        empirical_probability = max(
            float(
                empirical_probability
            ),
            1e-300,
        )

        rows.append(
            {
                "observation_index": i,
                "observed_duration_days": test_value,
                "log_score_lognormal": float(
                    np.log(
                        parametric_probability
                    )
                ),
                "log_score_empirical": float(
                    np.log(
                        empirical_probability
                    )
                ),
                "log_score_difference_empirical_minus_lognormal": float(
                    np.log(
                        empirical_probability
                    )
                    - np.log(
                        parametric_probability
                    )
                ),
            }
        )

    result = pd.DataFrame(
        rows
    )

    summary = {
        "n": len(result),
        "mean_log_score_lognormal": float(
            result[
                "log_score_lognormal"
            ].mean()
        ),
        "mean_log_score_empirical": float(
            result[
                "log_score_empirical"
            ].mean()
        ),
        "mean_difference_empirical_minus_lognormal": float(
            result[
                "log_score_difference_empirical_minus_lognormal"
            ].mean()
        ),
        "median_difference_empirical_minus_lognormal": float(
            result[
                "log_score_difference_empirical_minus_lognormal"
            ].median()
        ),
        "empirical_better_share": float(
            (
                result[
                    "log_score_difference_empirical_minus_lognormal"
                ]
                > 0
            ).mean()
        ),
    }

    return result, summary


# =============================================================================
# MAIN
# =============================================================================

def main():

    separator()
    log(
        "DISTRIBUTION DIAGNOSTICS - "
        "ROAD INFRASTRUCTURE TENDERS"
    )
    separator()

    log(
        "Input 1: Script 07 scenario assignments"
    )

    log(
        "Input 2: Script 09 distribution-fitting results"
    )

    log(
        "Purpose: Diagnose the source and location of distributional "
        "misfit before stochastic simulation"
    )

    log()

    # =========================================================================
    # 1. VALIDATE INPUTS
    # =========================================================================

    log(
        "[1] Validating input files..."
    )

    if not SCENARIO_INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing Script 07 input: "
            f"{SCENARIO_INPUT_FILE}"
        )

    if not FIT_INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing Script 09 input: "
            f"{FIT_INPUT_FILE}"
        )

    log(
        f"  Script 07: "
        f"{SCENARIO_INPUT_FILE.name}"
    )

    log(
        f"  Script 09: "
        f"{FIT_INPUT_FILE.name}"
    )

    log(
        "  Input files found."
    )

    log()

    # =========================================================================
    # 2. READ INPUTS
    # =========================================================================

    log(
        "[2] Reading source datasets..."
    )

    df = pd.read_excel(
        SCENARIO_INPUT_FILE,
        sheet_name="procedure_audit",
    )

    fit_results = pd.read_excel(
        FIT_INPUT_FILE,
        sheet_name="distribution_fits",
    )

    selection_audit = pd.read_excel(
        FIT_INPUT_FILE,
        sheet_name="selection_audit",
    )

    log(
        f"  Procedure-level rows: "
        f"{len(df)}"
    )

    log(
        f"  Distribution-fit rows: "
        f"{len(fit_results)}"
    )

    log(
        f"  Selection-audit rows: "
        f"{len(selection_audit)}"
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
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise KeyError(
            "Script 07 dataset is missing required columns: "
            + ", ".join(missing)
        )

    if len(df) != EXPECTED_MASTER_SAMPLE_SIZE:
        raise ValueError(
            f"Expected "
            f"{EXPECTED_MASTER_SAMPLE_SIZE} procedures; "
            f"found {len(df)}."
        )

    if df[
        "procedure_code"
    ].duplicated().any():
        raise ValueError(
            "Duplicate procedure codes detected."
        )

    available_total = int(
        df[
            "total_award_time_days"
        ].notna().sum()
    )

    log(
        f"  Master analytical sample verified: "
        f"{len(df)}"
    )

    log(
        f"  Available total award times: "
        f"{available_total}"
    )

    log(
        "  procedure_code uniqueness verified."
    )

    log()

    # =========================================================================
    # 4. CONFIRM SCRIPT 09 SIGNAL
    # =========================================================================

    log(
        "[4] Confirming Script 09 diagnostic signal..."
    )

    primary_selection = (
        selection_audit.loc[
            selection_audit[
                "method"
            ]
            == "Terciles"
        ]
        .copy()
    )

    if primary_selection.empty:
        raise ValueError(
            "Script 09 does not contain primary Terciles selection results."
        )

    for scenario in SCENARIO_ORDER:

        row = primary_selection.loc[
            primary_selection[
                "scenario"
            ]
            == scenario
        ]

        if row.empty:
            raise ValueError(
                f"Missing Script 09 selection result "
                f"for scenario {scenario}."
            )

        row = row.iloc[0]

        log(
            f"  {scenario}: "
            f"{row['aic_preferred_distribution']} | "
            f"bootstrap KS p="
            f"{row['bootstrap_ks_p']:.4f} | "
            f"{row['decision_flag']}"
        )

    log()

    # =========================================================================
    # 5. PREPARE PRIMARY SCENARIOS
    # =========================================================================

    log(
        "[5] Preparing primary tercile scenario samples..."
    )

    scenario_values = {}

    for scenario in SCENARIO_ORDER:

        values = (
            df.loc[
                (
                    df[
                        "scenario_terciles"
                    ]
                    == scenario
                )
                & df[
                    "total_award_time_days"
                ].notna(),
                "total_award_time_days",
            ]
            .astype(float)
            .values
        )

        scenario_values[
            scenario
        ] = values

        log(
            f"  {scenario}: "
            f"n={len(values)}; "
            f"range="
            f"{np.min(values):.0f}-"
            f"{np.max(values):.0f} days"
        )

    log()

    # =========================================================================
    # 6. DESCRIBE DISTRIBUTIONAL SHAPE
    # =========================================================================

    log(
        "[6] Diagnosing empirical distributional shape..."
    )

    shape_rows = []

    for scenario in SCENARIO_ORDER:

        values = scenario_values[
            scenario
        ]

        row = {
            "scenario": scenario,
            "n": len(values),
            "mean": float(
                np.mean(values)
            ),
            "median": float(
                np.median(values)
            ),
            "std_dev": float(
                np.std(
                    values,
                    ddof=1,
                )
            ),
            "coefficient_of_variation": float(
                np.std(
                    values,
                    ddof=1,
                )
                / np.mean(values)
            ),
            "skewness": float(
                stats.skew(
                    values,
                    bias=False,
                )
            ),
            "excess_kurtosis": float(
                stats.kurtosis(
                    values,
                    fisher=True,
                    bias=False,
                )
            ),
            "minimum": float(
                np.min(values)
            ),
            "p10": float(
                np.quantile(
                    values,
                    0.10,
                )
            ),
            "p25": float(
                np.quantile(
                    values,
                    0.25,
                )
            ),
            "p50": float(
                np.quantile(
                    values,
                    0.50,
                )
            ),
            "p75": float(
                np.quantile(
                    values,
                    0.75,
                )
            ),
            "p90": float(
                np.quantile(
                    values,
                    0.90,
                )
            ),
            "maximum": float(
                np.max(values)
            ),
        }

        shape_rows.append(
            row
        )

        log(
            f"  {scenario}: "
            f"mean={row['mean']:.2f}; "
            f"median={row['median']:.2f}; "
            f"skewness={row['skewness']:.3f}; "
            f"excess kurtosis="
            f"{row['excess_kurtosis']:.3f}"
        )

    shape_df = pd.DataFrame(
        shape_rows
    )

    log()

    # =========================================================================
    # 7. DIAGNOSE VALUE CONCENTRATION
    # =========================================================================

    log(
        "[7] Auditing concentration and repeated durations..."
    )

    concentration_rows = []
    top_frequency_rows = []

    for scenario in SCENARIO_ORDER:

        values = scenario_values[
            scenario
        ]

        summary, top_values = (
            value_concentration_diagnostic(
                values
            )
        )

        summary[
            "scenario"
        ] = scenario

        concentration_rows.append(
            summary
        )

        for row in top_values:
            row[
                "scenario"
            ] = scenario

            top_frequency_rows.append(
                row
            )

        log(
            f"  {scenario}: "
            f"unique values="
            f"{summary['unique_duration_values']}/{summary['n']}; "
            f"observations in repeated values="
            f"{summary['share_observations_in_repeated_values']:.2%}; "
            f"largest single-value share="
            f"{summary['maximum_single_value_share']:.2%}"
        )

    concentration_df = pd.DataFrame(
        concentration_rows
    )

    top_frequency_df = pd.DataFrame(
        top_frequency_rows
    )

    log()

    log(
        "  NOTE: Integer-day ties are expected and are not treated as "
        "measurement errors."
    )

    log()

    # =========================================================================
    # 8. LOCATE KS DISCREPANCIES
    # =========================================================================

    log(
        "[8] Locating maximum empirical-vs-fitted CDF discrepancies..."
    )

    ks_rows = []

    for scenario in SCENARIO_ORDER:

        values = scenario_values[
            scenario
        ]

        log(
            f"  {scenario}:"
        )

        for distribution_name in (
            CANDIDATE_DISTRIBUTIONS
        ):

            params = fit_distribution(
                distribution_name,
                values,
            )

            diagnostic = (
                ks_location_diagnostic(
                    values,
                    distribution_name,
                    params,
                )
            )

            diagnostic[
                "scenario"
            ] = scenario

            ks_rows.append(
                diagnostic
            )

            log(
                f"    {distribution_name:<12} "
                f"KS={diagnostic['ks_maximum']:.4f}; "
                f"location="
                f"{diagnostic['time_at_maximum_days']:.1f} days; "
                f"empirical position="
                f"{diagnostic['empirical_quantile_position']:.3f}"
            )

    ks_df = pd.DataFrame(
        ks_rows
    )

    log()

    # =========================================================================
    # 9. QUANTILE DIAGNOSTICS
    # =========================================================================

    log(
        "[9] Comparing empirical and fitted quantiles..."
    )

    quantile_rows = []

    for scenario in SCENARIO_ORDER:

        values = scenario_values[
            scenario
        ]

        for distribution_name in (
            CANDIDATE_DISTRIBUTIONS
        ):

            params = fit_distribution(
                distribution_name,
                values,
            )

            rows = quantile_diagnostic(
                values,
                distribution_name,
                params,
            )

            for row in rows:
                row[
                    "scenario"
                ] = scenario

                quantile_rows.append(
                    row
                )

    quantile_df = pd.DataFrame(
        quantile_rows
    )

    for scenario in SCENARIO_ORDER:

        subset = quantile_df.loc[
            (
                quantile_df[
                    "scenario"
                ]
                == scenario
            )
            & (
                quantile_df[
                    "distribution"
                ]
                == PRIMARY_DISTRIBUTION_NAME
            )
        ]

        mae = float(
            subset[
                "absolute_error_days"
            ].mean()
        )

        max_error = float(
            subset[
                "absolute_error_days"
            ].max()
        )

        log(
            f"  {scenario} | Lognormal: "
            f"mean absolute quantile error="
            f"{mae:.2f} days; "
            f"maximum="
            f"{max_error:.2f} days"
        )

    log()

    # =========================================================================
    # 10. TAIL DIAGNOSTICS
    # =========================================================================

    log(
        "[10] Auditing upper-tail structure..."
    )

    tail_rows = []

    for scenario in SCENARIO_ORDER:

        values = scenario_values[
            scenario
        ]

        summary = tail_summary(
            values
        )

        summary[
            "scenario"
        ] = scenario

        tail_rows.append(
            summary
        )

        log(
            f"  {scenario}: "
            f"P90={summary['p90']:.2f}; "
            f"P95={summary['p95']:.2f}; "
            f"max={summary['maximum']:.2f}; "
            f"above 1.5*IQR fence="
            f"{summary['n_above_upper_iqr_fence']}"
        )

    tail_df = pd.DataFrame(
        tail_rows
    )

    log()

    # =========================================================================
    # 11. LOGNORMAL TAIL SENSITIVITY
    # =========================================================================

    log(
        "[11] Evaluating Lognormal sensitivity to upper-tail observations..."
    )

    sensitivity_rows = []

    for scenario in SCENARIO_ORDER:

        values = scenario_values[
            scenario
        ]

        result = trimmed_fit_sensitivity(
            values,
            PRIMARY_DISTRIBUTION_NAME,
        )

        result[
            "scenario"
        ] = scenario

        sensitivity_rows.append(
            result
        )

        log(
            f"  {scenario}: "
            f"full KS={result['full_ks']:.4f}; "
            f"remove-max KS="
            f"{result['max_removed_ks']:.4f}; "
            f"<=P95 KS="
            f"{result['p95_subset_ks']:.4f}"
        )

    sensitivity_df = pd.DataFrame(
        sensitivity_rows
    )

    log()

    log(
        "  NOTE: These are sensitivity refits only. "
        "No observation is removed from the analytical sample."
    )

    log()

    # =========================================================================
    # 12. LOW-SCENARIO INTERNAL STRUCTURE
    # =========================================================================

    log(
        "[12] Diagnosing internal structure of the Low scenario..."
    )

    low_df = (
        df.loc[
            (
                df[
                    "scenario_terciles"
                ]
                == "Low"
            )
            & df[
                "total_award_time_days"
            ].notna(),
            [
                "procedure_code",
                "queries_observations_count",
                "total_award_time_days",
            ],
        ]
        .copy()
        .sort_values(
            [
                "queries_observations_count",
                "total_award_time_days",
            ]
        )
    )

    low_query_summary = (
        low_df.groupby(
            "queries_observations_count",
            dropna=False,
        )
        .agg(
            n=(
                "procedure_code",
                "size",
            ),
            mean_award_time=(
                "total_award_time_days",
                "mean",
            ),
            median_award_time=(
                "total_award_time_days",
                "median",
            ),
            min_award_time=(
                "total_award_time_days",
                "min",
            ),
            max_award_time=(
                "total_award_time_days",
                "max",
            ),
        )
        .reset_index()
    )

    low_query_counts = (
        low_df[
            "queries_observations_count"
        ]
        .value_counts()
        .sort_index()
    )

    log(
        f"  Low-scenario procedures: "
        f"{len(low_df)}"
    )

    log(
        f"  Distinct query-count values: "
        f"{low_df['queries_observations_count'].nunique()}"
    )

    log(
        f"  Minimum query count: "
        f"{low_df['queries_observations_count'].min()}"
    )

    log(
        f"  Maximum query count: "
        f"{low_df['queries_observations_count'].max()}"
    )

    log(
        f"  Most frequent query-count value: "
        f"{int(low_query_counts.idxmax())} "
        f"(n={int(low_query_counts.max())})"
    )

    low_spearman = stats.spearmanr(
        low_df[
            "queries_observations_count"
        ],
        low_df[
            "total_award_time_days"
        ],
    )

    low_kendall = stats.kendalltau(
        low_df[
            "queries_observations_count"
        ],
        low_df[
            "total_award_time_days"
        ],
    )

    log(
        f"  Within-Low Spearman rho="
        f"{low_spearman.statistic:.4f}; "
        f"p={low_spearman.pvalue:.6g}"
    )

    log(
        f"  Within-Low Kendall tau="
        f"{low_kendall.statistic:.4f}; "
        f"p={low_kendall.pvalue:.6g}"
    )

    log()

    log(
        "  NOTE: This is an internal heterogeneity diagnostic. "
        "It does not redefine the Low threshold."
    )

    log()

    # =========================================================================
    # 13. EMPIRICAL VS PARAMETRIC PREDICTIVE DIAGNOSTIC
    # =========================================================================

    log(
        "[13] Comparing empirical and Lognormal leave-one-out predictive scores..."
    )

    predictive_rows = []
    predictive_summary_rows = []

    for scenario in SCENARIO_ORDER:

        values = scenario_values[
            scenario
        ]

        detailed, summary = (
            leave_one_out_predictive_scores(
                values
            )
        )

        detailed[
            "scenario"
        ] = scenario

        predictive_rows.append(
            detailed
        )

        summary[
            "scenario"
        ] = scenario

        predictive_summary_rows.append(
            summary
        )

        log(
            f"  {scenario}: "
            f"mean log-score Lognormal="
            f"{summary['mean_log_score_lognormal']:.4f}; "
            f"empirical="
            f"{summary['mean_log_score_empirical']:.4f}; "
            f"empirical-better share="
            f"{summary['empirical_better_share']:.2%}"
        )

    predictive_df = pd.concat(
        predictive_rows,
        ignore_index=True,
    )

    predictive_summary_df = pd.DataFrame(
        predictive_summary_rows
    )

    log()

    log(
        "  NOTE: The empirical comparator is a diagnostic benchmark, "
        "not a selected simulation model."
    )

    log()

    # =========================================================================
    # 14. BUILD PROCEDURE-LEVEL LOW AUDIT
    # =========================================================================

    log(
        "[14] Building Low-scenario procedure-level diagnostic audit..."
    )

    low_params = fit_distribution(
        PRIMARY_DISTRIBUTION_NAME,
        low_df[
            "total_award_time_days"
        ].values,
    )

    low_df[
        "lognormal_cdf"
    ] = PRIMARY_DISTRIBUTION.cdf(
        low_df[
            "total_award_time_days"
        ].astype(float),
        *low_params,
    )

    low_df[
        "empirical_percentile_rank"
    ] = (
        low_df[
            "total_award_time_days"
        ]
        .rank(
            method="average",
            pct=True,
        )
    )

    low_df[
        "cdf_difference_empirical_minus_lognormal"
    ] = (
        low_df[
            "empirical_percentile_rank"
        ]
        - low_df[
            "lognormal_cdf"
        ]
    )

    low_df[
        "absolute_cdf_difference"
    ] = (
        low_df[
            "cdf_difference_empirical_minus_lognormal"
        ]
        .abs()
    )

    low_df = low_df.sort_values(
        "absolute_cdf_difference",
        ascending=False,
    )

    log(
        f"  Procedure-level Low audit rows: "
        f"{len(low_df)}"
    )

    log()

    # =========================================================================
    # 15. BUILD SCIENTIFIC DECISION FRAMEWORK
    # =========================================================================

    log(
        "[15] Building scientific diagnostic framework..."
    )

    low_ks = ks_df.loc[
        (
            ks_df[
                "scenario"
            ]
            == "Low"
        )
        & (
            ks_df[
                "distribution"
            ]
            == PRIMARY_DISTRIBUTION_NAME
        )
    ].iloc[0]

    low_concentration = (
        concentration_df.loc[
            concentration_df[
                "scenario"
            ]
            == "Low"
        ].iloc[0]
    )

    low_tail = tail_df.loc[
        tail_df[
            "scenario"
        ]
        == "Low"
    ].iloc[0]

    low_sensitivity = (
        sensitivity_df.loc[
            sensitivity_df[
                "scenario"
            ]
            == "Low"
        ].iloc[0]
    )

    diagnostic_framework = pd.DataFrame(
        [
            {
                "diagnostic_dimension":
                    "Location of maximum CDF discrepancy",
                "observed_result":
                    (
                        f"{low_ks['time_at_maximum_days']:.1f} days "
                        f"(empirical position "
                        f"{low_ks['empirical_quantile_position']:.3f})"
                    ),
                "interpretation_rule":
                    (
                        "Identifies where the Lognormal representation "
                        "departs most strongly from the empirical Low distribution."
                    ),
            },
            {
                "diagnostic_dimension":
                    "Repeated-duration concentration",
                "observed_result":
                    (
                        f"{low_concentration['share_observations_in_repeated_values']:.2%} "
                        f"of observations occur at repeated duration values"
                    ),
                "interpretation_rule":
                    (
                        "High concentration may contribute to mismatch between "
                        "continuous distributions and integer-day empirical data."
                    ),
            },
            {
                "diagnostic_dimension":
                    "Upper-tail structure",
                "observed_result":
                    (
                        f"{int(low_tail['n_above_upper_iqr_fence'])} observations "
                        f"above the 1.5*IQR upper fence"
                    ),
                "interpretation_rule":
                    (
                        "Evaluates whether a small number of long-duration "
                        "observations dominate the lack of fit."
                    ),
            },
            {
                "diagnostic_dimension":
                    "Tail-sensitivity refit",
                "observed_result":
                    (
                        f"Full KS={low_sensitivity['full_ks']:.4f}; "
                        f"<=P95 KS={low_sensitivity['p95_subset_ks']:.4f}"
                    ),
                "interpretation_rule":
                    (
                        "A large improvement after tail restriction would suggest "
                        "tail-driven misfit; this does not justify deletion."
                    ),
            },
            {
                "diagnostic_dimension":
                    "Within-Low continuous association",
                "observed_result":
                    (
                        f"Spearman rho={low_spearman.statistic:.4f}; "
                        f"p={low_spearman.pvalue:.6g}"
                    ),
                "interpretation_rule":
                    (
                        "Assesses whether substantial systematic variation "
                        "remains inside the Low query-count interval."
                    ),
            },
        ]
    )

    log(
        "  Diagnostic framework created."
    )

    log()

    # =========================================================================
    # 16. SAVE OUTPUTS
    # =========================================================================

    log(
        "[16] Saving reproducible diagnostic outputs..."
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        shape_df.to_excel(
            writer,
            sheet_name="shape_diagnostics",
            index=False,
        )

        concentration_df.to_excel(
            writer,
            sheet_name="concentration_summary",
            index=False,
        )

        top_frequency_df.to_excel(
            writer,
            sheet_name="top_duration_values",
            index=False,
        )

        ks_df.to_excel(
            writer,
            sheet_name="ks_location",
            index=False,
        )

        quantile_df.to_excel(
            writer,
            sheet_name="quantile_diagnostics",
            index=False,
        )

        tail_df.to_excel(
            writer,
            sheet_name="tail_diagnostics",
            index=False,
        )

        sensitivity_df.to_excel(
            writer,
            sheet_name="tail_sensitivity",
            index=False,
        )

        low_query_summary.to_excel(
            writer,
            sheet_name="low_internal_structure",
            index=False,
        )

        predictive_summary_df.to_excel(
            writer,
            sheet_name="predictive_summary",
            index=False,
        )

        predictive_df.to_excel(
            writer,
            sheet_name="predictive_detail",
            index=False,
        )

        low_df.to_excel(
            writer,
            sheet_name="low_procedure_audit",
            index=False,
        )

        diagnostic_framework.to_excel(
            writer,
            sheet_name="diagnostic_framework",
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
        "DISTRIBUTION-DIAGNOSTICS AUDIT"
    )
    separator()

    log(
        f"Master analytical procedures:          "
        f"{len(df)}"
    )

    log(
        f"Available total award times:           "
        f"{available_total}"
    )

    log(
        f"Primary scenario definition:           "
        f"Terciles"
    )

    log(
        f"Low observations diagnosed:            "
        f"{len(scenario_values['Low'])}"
    )

    log(
        f"Medium observations diagnosed:         "
        f"{len(scenario_values['Medium'])}"
    )

    log(
        f"High observations diagnosed:           "
        f"{len(scenario_values['High'])}"
    )

    log()

    log(
        "LOW-SCENARIO DIAGNOSTIC SNAPSHOT"
    )

    log("-" * 78)

    log(
        f"Lognormal maximum CDF discrepancy:     "
        f"{low_ks['ks_maximum']:.4f}"
    )

    log(
        f"Maximum discrepancy location:          "
        f"{low_ks['time_at_maximum_days']:.1f} days"
    )

    log(
        f"Empirical position at discrepancy:     "
        f"{low_ks['empirical_quantile_position']:.3f}"
    )

    log(
        f"Repeated-duration observation share:   "
        f"{low_concentration['share_observations_in_repeated_values']:.2%}"
    )

    log(
        f"Upper-IQR-fence observations:          "
        f"{int(low_tail['n_above_upper_iqr_fence'])}"
    )

    log(
        f"Full Lognormal KS:                     "
        f"{low_sensitivity['full_ks']:.4f}"
    )

    log(
        f"Lognormal KS after <=P95 sensitivity:  "
        f"{low_sensitivity['p95_subset_ks']:.4f}"
    )

    log(
        f"Within-Low Spearman rho:               "
        f"{low_spearman.statistic:.4f}"
    )

    log()

    log(
        "SCIENTIFIC SCOPE"
    )

    log(
        "- Script 10 diagnoses the distributional mismatch identified "
        "in Script 09."
    )

    log(
        "- No new probability distribution is introduced or selected."
    )

    log(
        "- No distribution is searched opportunistically to obtain "
        "a non-significant goodness-of-fit test."
    )

    log(
        "- The primary tercile thresholds remain unchanged."
    )

    log(
        "- Repeated integer-day durations are quantified but are not "
        "treated automatically as data errors."
    )

    log(
        "- Tail-restricted refits are sensitivity diagnostics only; "
        "no observations are deleted."
    )

    log(
        "- The empirical predictive representation is a diagnostic "
        "benchmark, not a selected stochastic model."
    )

    log(
        "- The master analytical sample remains unchanged at n=137."
    )

    log(
        "- No Monte Carlo award-time simulation is performed."
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
