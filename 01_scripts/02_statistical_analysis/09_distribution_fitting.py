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
ALPHA = 0.05

# Bootstrap is used only for parameter / model-selection stability diagnostics.
# It is NOT the later Monte Carlo simulation of the thesis.
BOOTSTRAP_ITERATIONS = 1000
RANDOM_SEED = 2026

SCENARIO_ORDER = ["Low", "Medium", "High"]

CANDIDATE_DISTRIBUTIONS = {
    "Lognormal": stats.lognorm,
    "Weibull": stats.weibull_min,
    "Gamma": stats.gamma,
    "Exponential": stats.expon,
}

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
    / "09_1_distribution_fitting.xlsx"
)

LOG_FILE = (
    LOGS_DIR
    / "09_distribution_fitting.log"
)

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("distribution_fitting")
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
# DISTRIBUTION HELPERS
# =============================================================================

def parameter_count(distribution_name):
    """
    Number of free parameters when loc is fixed at zero.

    Lognormal: shape + scale = 2
    Weibull:   shape + scale = 2
    Gamma:     shape + scale = 2
    Exponential: scale = 1
    """
    if distribution_name == "Exponential":
        return 1

    return 2


def fit_distribution(distribution_name, values):
    """
    Maximum-likelihood fit with loc fixed at zero.

    Fixing loc=0 is scientifically appropriate here because award times
    are strictly positive durations and it also provides a common support
    assumption across candidate families.
    """

    distribution = CANDIDATE_DISTRIBUTIONS[
        distribution_name
    ]

    values = np.asarray(values, dtype=float)

    if np.any(~np.isfinite(values)):
        raise ValueError(
            "Non-finite observations detected."
        )

    if np.any(values <= 0):
        raise ValueError(
            "Candidate positive-support distributions require "
            "strictly positive observations."
        )

    params = distribution.fit(
        values,
        floc=0,
    )

    return tuple(
        float(x)
        for x in params
    )


def log_likelihood(
    distribution_name,
    values,
    params,
):
    distribution = CANDIDATE_DISTRIBUTIONS[
        distribution_name
    ]

    logpdf = distribution.logpdf(
        values,
        *params,
    )

    if np.any(~np.isfinite(logpdf)):
        return -np.inf

    return float(
        np.sum(logpdf)
    )


def information_criteria(
    loglik,
    n,
    k,
):
    aic = (
        2 * k
        - 2 * loglik
    )

    bic = (
        np.log(n) * k
        - 2 * loglik
    )

    denominator = (
        n - k - 1
    )

    if denominator > 0:
        aicc = (
            aic
            + (
                2
                * k
                * (k + 1)
                / denominator
            )
        )
    else:
        aicc = np.inf

    return (
        float(aic),
        float(aicc),
        float(bic),
    )


def goodness_of_fit(
    distribution_name,
    values,
    params,
):
    """
    KS and Cramer-von Mises statistics.

    Important:
    scipy's nominal p-values are reported as diagnostics only because
    parameters were estimated from the same data. They must not be treated
    as exact post-estimation goodness-of-fit tests.
    """

    distribution = CANDIDATE_DISTRIBUTIONS[
        distribution_name
    ]

    cdf = lambda x: distribution.cdf(
        x,
        *params,
    )

    ks = stats.kstest(
        values,
        cdf,
    )

    cvm = stats.cramervonmises(
        values,
        cdf,
    )

    return {
        "ks_statistic":
            float(ks.statistic),
        "ks_nominal_p":
            float(ks.pvalue),
        "cvm_statistic":
            float(cvm.statistic),
        "cvm_nominal_p":
            float(cvm.pvalue),
    }


def quantile_diagnostics(
    distribution_name,
    values,
    params,
):
    distribution = CANDIDATE_DISTRIBUTIONS[
        distribution_name
    ]

    probabilities = np.array(
        [
            0.10,
            0.25,
            0.50,
            0.75,
            0.90,
        ],
        dtype=float,
    )

    empirical = np.quantile(
        values,
        probabilities,
    )

    fitted = distribution.ppf(
        probabilities,
        *params,
    )

    absolute_errors = np.abs(
        empirical - fitted
    )

    relative_errors = (
        absolute_errors
        / np.maximum(
            empirical,
            1e-12,
        )
    )

    return {
        "quantile_mae":
            float(
                np.mean(
                    absolute_errors
                )
            ),
        "quantile_rmse":
            float(
                np.sqrt(
                    np.mean(
                        (
                            empirical
                            - fitted
                        ) ** 2
                    )
                )
            ),
        "quantile_mean_relative_error":
            float(
                np.mean(
                    relative_errors
                )
            ),
        "probabilities":
            probabilities,
        "empirical":
            empirical,
        "fitted":
            fitted,
    }


def unpack_parameters(
    distribution_name,
    params,
):
    """
    Store parameters in interpretable generic fields.
    """

    if distribution_name == "Lognormal":
        shape, loc, scale = params

        return {
            "shape_1": shape,
            "shape_2": np.nan,
            "loc": loc,
            "scale": scale,
            "parameterization_note":
                "scipy.stats.lognorm: shape=sigma; "
                "scale=exp(mu); loc fixed at 0",
        }

    if distribution_name == "Weibull":
        shape, loc, scale = params

        return {
            "shape_1": shape,
            "shape_2": np.nan,
            "loc": loc,
            "scale": scale,
            "parameterization_note":
                "scipy.stats.weibull_min: "
                "shape=c; loc fixed at 0",
        }

    if distribution_name == "Gamma":
        shape, loc, scale = params

        return {
            "shape_1": shape,
            "shape_2": np.nan,
            "loc": loc,
            "scale": scale,
            "parameterization_note":
                "scipy.stats.gamma: "
                "shape=a; loc fixed at 0",
        }

    if distribution_name == "Exponential":
        loc, scale = params

        return {
            "shape_1": np.nan,
            "shape_2": np.nan,
            "loc": loc,
            "scale": scale,
            "parameterization_note":
                "scipy.stats.expon: "
                "loc fixed at 0",
        }

    raise ValueError(
        f"Unsupported distribution: {distribution_name}"
    )


def calculate_aic_weights(aic_values):
    aic_values = np.asarray(
        aic_values,
        dtype=float,
    )

    minimum = np.min(
        aic_values
    )

    delta = (
        aic_values
        - minimum
    )

    relative = np.exp(
        -0.5 * delta
    )

    weights = (
        relative
        / relative.sum()
    )

    return (
        delta,
        weights,
    )


def calculate_bic_weights(bic_values):
    bic_values = np.asarray(
        bic_values,
        dtype=float,
    )

    minimum = np.min(
        bic_values
    )

    delta = (
        bic_values
        - minimum
    )

    relative = np.exp(
        -0.5 * delta
    )

    weights = (
        relative
        / relative.sum()
    )

    return (
        delta,
        weights,
    )


# =============================================================================
# FITTING
# =============================================================================

def fit_candidate_set(
    values,
    method,
    scenario,
):
    values = np.asarray(
        values,
        dtype=float,
    )

    rows = []
    quantile_rows = []

    for distribution_name in (
        CANDIDATE_DISTRIBUTIONS.keys()
    ):

        try:
            params = fit_distribution(
                distribution_name,
                values,
            )

            ll = log_likelihood(
                distribution_name,
                values,
                params,
            )

            k = parameter_count(
                distribution_name
            )

            aic, aicc, bic = (
                information_criteria(
                    ll,
                    len(values),
                    k,
                )
            )

            gof = goodness_of_fit(
                distribution_name,
                values,
                params,
            )

            q = quantile_diagnostics(
                distribution_name,
                values,
                params,
            )

            param_record = (
                unpack_parameters(
                    distribution_name,
                    params,
                )
            )

            row = {
                "method": method,
                "scenario": scenario,
                "distribution":
                    distribution_name,
                "n": len(values),
                "parameter_count": k,
                "log_likelihood": ll,
                "aic": aic,
                "aicc": aicc,
                "bic": bic,
                "ks_statistic":
                    gof["ks_statistic"],
                "ks_nominal_p":
                    gof["ks_nominal_p"],
                "cvm_statistic":
                    gof["cvm_statistic"],
                "cvm_nominal_p":
                    gof["cvm_nominal_p"],
                "quantile_mae":
                    q["quantile_mae"],
                "quantile_rmse":
                    q["quantile_rmse"],
                "quantile_mean_relative_error":
                    q[
                        "quantile_mean_relative_error"
                    ],
                "fit_status": "OK",
                **param_record,
            }

            rows.append(
                row
            )

            for (
                probability,
                empirical,
                fitted,
            ) in zip(
                q["probabilities"],
                q["empirical"],
                q["fitted"],
            ):

                quantile_rows.append(
                    {
                        "method":
                            method,
                        "scenario":
                            scenario,
                        "distribution":
                            distribution_name,
                        "probability":
                            float(
                                probability
                            ),
                        "empirical_quantile":
                            float(
                                empirical
                            ),
                        "fitted_quantile":
                            float(
                                fitted
                            ),
                        "absolute_error":
                            float(
                                abs(
                                    empirical
                                    - fitted
                                )
                            ),
                    }
                )

        except Exception as exc:

            rows.append(
                {
                    "method":
                        method,
                    "scenario":
                        scenario,
                    "distribution":
                        distribution_name,
                    "n":
                        len(values),
                    "fit_status":
                        "FAILED",
                    "fit_error":
                        str(exc),
                }
            )

    result = pd.DataFrame(
        rows
    )

    successful = (
        result[
            "fit_status"
        ] == "OK"
    )

    if successful.sum() > 0:

        idx = result.index[
            successful
        ]

        aic_values = (
            result.loc[
                idx,
                "aic",
            ].astype(float).values
        )

        delta_aic, aic_weights = (
            calculate_aic_weights(
                aic_values
            )
        )

        result.loc[
            idx,
            "delta_aic",
        ] = delta_aic

        result.loc[
            idx,
            "aic_weight",
        ] = aic_weights

        bic_values = (
            result.loc[
                idx,
                "bic",
            ].astype(float).values
        )

        delta_bic, bic_weights = (
            calculate_bic_weights(
                bic_values
            )
        )

        result.loc[
            idx,
            "delta_bic",
        ] = delta_bic

        result.loc[
            idx,
            "bic_weight",
        ] = bic_weights

        result.loc[
            idx,
            "aic_rank",
        ] = (
            result.loc[
                idx,
                "aic",
            ]
            .rank(
                method="min",
                ascending=True,
            )
        )

        result.loc[
            idx,
            "aicc_rank",
        ] = (
            result.loc[
                idx,
                "aicc",
            ]
            .rank(
                method="min",
                ascending=True,
            )
        )

        result.loc[
            idx,
            "bic_rank",
        ] = (
            result.loc[
                idx,
                "bic",
            ]
            .rank(
                method="min",
                ascending=True,
            )
        )

        result.loc[
            idx,
            "ks_rank",
        ] = (
            result.loc[
                idx,
                "ks_statistic",
            ]
            .rank(
                method="min",
                ascending=True,
            )
        )

        result.loc[
            idx,
            "cvm_rank",
        ] = (
            result.loc[
                idx,
                "cvm_statistic",
            ]
            .rank(
                method="min",
                ascending=True,
            )
        )

        result.loc[
            idx,
            "quantile_rmse_rank",
        ] = (
            result.loc[
                idx,
                "quantile_rmse",
            ]
            .rank(
                method="min",
                ascending=True,
            )
        )

    return (
        result,
        pd.DataFrame(
            quantile_rows
        ),
    )


# =============================================================================
# PARAMETRIC BOOTSTRAP GOF
# =============================================================================

def parametric_bootstrap_ks(
    values,
    distribution_name,
    fitted_params,
    iterations,
    seed,
):
    """
    Parametric bootstrap KS calibration.

    For each bootstrap sample:
      1. simulate from fitted candidate,
      2. refit the same distribution,
      3. compute KS statistic against the refitted model.

    This accounts for the fact that model parameters were estimated from
    the observed data and is preferable to interpreting the nominal KS
    p-value as an exact Lilliefors-type test.
    """

    values = np.asarray(
        values,
        dtype=float,
    )

    n = len(values)

    distribution = (
        CANDIDATE_DISTRIBUTIONS[
            distribution_name
        ]
    )

    observed_ks = stats.kstest(
        values,
        lambda x: distribution.cdf(
            x,
            *fitted_params,
        ),
    ).statistic

    rng = np.random.default_rng(
        seed
    )

    bootstrap_statistics = []

    failures = 0

    for _ in range(iterations):

        try:
            simulated = (
                distribution.rvs(
                    *fitted_params,
                    size=n,
                    random_state=rng,
                )
            )

            simulated = np.asarray(
                simulated,
                dtype=float,
            )

            if (
                np.any(
                    ~np.isfinite(
                        simulated
                    )
                )
                or
                np.any(
                    simulated <= 0
                )
            ):
                failures += 1
                continue

            refitted = (
                fit_distribution(
                    distribution_name,
                    simulated,
                )
            )

            bootstrap_ks = (
                stats.kstest(
                    simulated,
                    lambda x: (
                        distribution.cdf(
                            x,
                            *refitted,
                        )
                    ),
                ).statistic
            )

            bootstrap_statistics.append(
                float(
                    bootstrap_ks
                )
            )

        except Exception:
            failures += 1

    bootstrap_statistics = np.asarray(
        bootstrap_statistics,
        dtype=float,
    )

    valid = len(
        bootstrap_statistics
    )

    if valid == 0:
        return {
            "observed_ks":
                float(observed_ks),
            "bootstrap_valid":
                0,
            "bootstrap_failures":
                failures,
            "bootstrap_p":
                np.nan,
        }

    exceedances = np.sum(
        bootstrap_statistics
        >= observed_ks
    )

    bootstrap_p = (
        exceedances + 1
    ) / (
        valid + 1
    )

    return {
        "observed_ks":
            float(observed_ks),
        "bootstrap_valid":
            int(valid),
        "bootstrap_failures":
            int(failures),
        "bootstrap_p":
            float(bootstrap_p),
    }


# =============================================================================
# MODEL-SELECTION STABILITY BOOTSTRAP
# =============================================================================

def bootstrap_aic_selection(
    values,
    iterations,
    seed,
):
    """
    Nonparametric bootstrap diagnostic:
    how often each candidate distribution obtains the lowest AIC
    across bootstrap resamples of the observed scenario data.

    This is a stability diagnostic, not the thesis Monte Carlo model.
    """

    values = np.asarray(
        values,
        dtype=float,
    )

    rng = np.random.default_rng(
        seed
    )

    wins = {
        name: 0
        for name
        in CANDIDATE_DISTRIBUTIONS
    }

    valid_iterations = 0
    failed_iterations = 0

    for _ in range(iterations):

        sample = rng.choice(
            values,
            size=len(values),
            replace=True,
        )

        candidate_aic = {}

        for distribution_name in (
            CANDIDATE_DISTRIBUTIONS
        ):

            try:
                params = fit_distribution(
                    distribution_name,
                    sample,
                )

                ll = log_likelihood(
                    distribution_name,
                    sample,
                    params,
                )

                k = parameter_count(
                    distribution_name
                )

                aic, _, _ = (
                    information_criteria(
                        ll,
                        len(sample),
                        k,
                    )
                )

                if np.isfinite(aic):
                    candidate_aic[
                        distribution_name
                    ] = aic

            except Exception:
                pass

        if len(candidate_aic) == 0:
            failed_iterations += 1
            continue

        winner = min(
            candidate_aic,
            key=candidate_aic.get,
        )

        wins[winner] += 1
        valid_iterations += 1

    rows = []

    for distribution_name in (
        CANDIDATE_DISTRIBUTIONS
    ):

        frequency = (
            wins[
                distribution_name
            ]
            / valid_iterations
            if valid_iterations > 0
            else np.nan
        )

        rows.append(
            {
                "distribution":
                    distribution_name,
                "aic_bootstrap_wins":
                    wins[
                        distribution_name
                    ],
                "valid_iterations":
                    valid_iterations,
                "failed_iterations":
                    failed_iterations,
                "selection_frequency":
                    frequency,
            }
        )

    return pd.DataFrame(
        rows
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    separator()
    log(
        "PROBABILITY-DISTRIBUTION FITTING - "
        "ROAD INFRASTRUCTURE TENDERS"
    )
    separator()

    log(
        "Input: Script 07 procedure-level scenario assignments"
    )

    log(
        "Purpose: Compare plausible positive-support probability "
        "distributions for award time before stochastic simulation"
    )

    log()

    # =========================================================================
    # 1. VALIDATE INPUT
    # =========================================================================

    log(
        "[1] Validating Script 07 input..."
    )

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    log(
        f"  Input file: "
        f"{INPUT_FILE.name}"
    )

    log(
        "  Input file found."
    )

    log()

    # =========================================================================
    # 2. READ DATA
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
            + ", ".join(
                missing_columns
            )
        )

    if (
        len(df)
        != EXPECTED_MASTER_SAMPLE_SIZE
    ):
        raise ValueError(
            f"Expected "
            f"{EXPECTED_MASTER_SAMPLE_SIZE} "
            f"procedures, found "
            f"{len(df)}."
        )

    if df[
        "procedure_code"
    ].duplicated().any():
        raise ValueError(
            "Duplicate procedure_code values detected."
        )

    available = int(
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
        f"{available}/{len(df)}"
    )

    log(
        "  procedure_code uniqueness verified."
    )

    log()

    # =========================================================================
    # 4. VERIFY SUPPORT
    # =========================================================================

    log(
        "[4] Verifying positive-support assumption..."
    )

    observed = (
        df[
            "total_award_time_days"
        ]
        .dropna()
        .astype(float)
    )

    nonpositive = int(
        (observed <= 0).sum()
    )

    log(
        f"  Non-positive award times: "
        f"{nonpositive}"
    )

    if nonpositive > 0:
        raise ValueError(
            "Positive-support candidate distributions cannot be "
            "applied because non-positive award times were detected."
        )

    log(
        f"  Observed range: "
        f"{observed.min():.2f} - "
        f"{observed.max():.2f} days"
    )

    log(
        "  Positive-support assumption verified."
    )

    log()

    # =========================================================================
    # 5. REGISTER CANDIDATES
    # =========================================================================

    log(
        "[5] Registering candidate distributions..."
    )

    for name in (
        CANDIDATE_DISTRIBUTIONS
    ):
        log(
            f"  {name}"
        )

    log()

    log(
        "  All candidates are fitted by maximum likelihood "
        "with loc fixed at zero."
    )

    log(
        "  Lognormal and Weibull are retained from the approved "
        "research design but are not privileged in model selection."
    )

    log(
        "  Gamma provides an additional flexible positive-support "
        "alternative; Exponential provides a simpler benchmark."
    )

    log()

    # =========================================================================
    # 6. DEFINE ANALYSES
    # =========================================================================

    analyses = [
        (
            "Terciles",
            "scenario_terciles",
            "PRIMARY",
        ),
        (
            "P25_P75",
            "scenario_p25_p75",
            "ROBUSTNESS",
        ),
    ]

    log(
        "[6] Registering scenario analyses..."
    )

    for method, _, role in analyses:
        log(
            f"  {method}: {role}"
        )

    log()

    log(
        "  Data_driven_1D is not used for primary distribution "
        "fitting because Script 08 identified only n=8 in its High "
        "scenario and no significant Medium-vs-High separation."
    )

    log(
        "  It remains documented in Scripts 07-08 as sensitivity evidence."
    )

    log()

    # =========================================================================
    # 7. FIT DISTRIBUTIONS
    # =========================================================================

    log(
        "[7] Fitting candidate distributions..."
    )

    all_fit_rows = []
    all_quantile_rows = []

    scenario_data = {}

    for method, scenario_column, role in analyses:

        log(
            f"  {method}:"
        )

        for scenario in SCENARIO_ORDER:

            values = (
                df.loc[
                    (
                        df[
                            scenario_column
                        ].astype(str)
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

            scenario_data[
                (
                    method,
                    scenario,
                )
            ] = values

            log(
                f"    {scenario}: "
                f"n={len(values)}"
            )

            fits, quantiles = (
                fit_candidate_set(
                    values,
                    method,
                    scenario,
                )
            )

            fits[
                "analysis_role"
            ] = role

            all_fit_rows.append(
                fits
            )

            all_quantile_rows.append(
                quantiles
            )

    fits_df = pd.concat(
        all_fit_rows,
        ignore_index=True,
    )

    quantiles_df = pd.concat(
        all_quantile_rows,
        ignore_index=True,
    )

    failed_fits = int(
        (
            fits_df[
                "fit_status"
            ]
            != "OK"
        ).sum()
    )

    log()

    log(
        f"  Candidate fits completed: "
        f"{len(fits_df) - failed_fits}"
    )

    log(
        f"  Failed fits: "
        f"{failed_fits}"
    )

    log()

    # =========================================================================
    # 8. REPORT MODEL COMPARISON
    # =========================================================================

    log(
        "[8] Comparing fitted distributions..."
    )

    comparison_rows = []

    for method, _, role in analyses:

        log(
            f"  {method}:"
        )

        for scenario in SCENARIO_ORDER:

            subset = (
                fits_df.loc[
                    (
                        fits_df[
                            "method"
                        ]
                        == method
                    )
                    & (
                        fits_df[
                            "scenario"
                        ]
                        == scenario
                    )
                    & (
                        fits_df[
                            "fit_status"
                        ]
                        == "OK"
                    )
                ]
                .sort_values(
                    "aic"
                )
                .copy()
            )

            if subset.empty:
                log(
                    f"    {scenario}: "
                    f"NO SUCCESSFUL FIT"
                )
                continue

            best_aic = (
                subset.iloc[0]
            )

            best_bic = (
                subset.sort_values(
                    "bic"
                ).iloc[0]
            )

            best_cvm = (
                subset.sort_values(
                    "cvm_statistic"
                ).iloc[0]
            )

            best_quantile = (
                subset.sort_values(
                    "quantile_rmse"
                ).iloc[0]
            )

            comparison_rows.append(
                {
                    "method":
                        method,
                    "analysis_role":
                        role,
                    "scenario":
                        scenario,
                    "n":
                        int(
                            best_aic["n"]
                        ),
                    "best_aic":
                        best_aic[
                            "distribution"
                        ],
                    "best_aicc":
                        subset.sort_values(
                            "aicc"
                        ).iloc[0][
                            "distribution"
                        ],
                    "best_bic":
                        best_bic[
                            "distribution"
                        ],
                    "best_cvm":
                        best_cvm[
                            "distribution"
                        ],
                    "best_quantile_rmse":
                        best_quantile[
                            "distribution"
                        ],
                    "aic_bic_agree":
                        bool(
                            best_aic[
                                "distribution"
                            ]
                            == best_bic[
                                "distribution"
                            ]
                        ),
                    "aic_cvm_agree":
                        bool(
                            best_aic[
                                "distribution"
                            ]
                            == best_cvm[
                                "distribution"
                            ]
                        ),
                }
            )

            log(
                f"    {scenario}: "
                f"best AIC="
                f"{best_aic['distribution']}; "
                f"best BIC="
                f"{best_bic['distribution']}; "
                f"best CvM="
                f"{best_cvm['distribution']}; "
                f"best quantile RMSE="
                f"{best_quantile['distribution']}"
            )

            for _, row in (
                subset.iterrows()
            ):

                log(
                    f"      "
                    f"{row['distribution']:<12} "
                    f"AIC={row['aic']:.3f}; "
                    f"AICc={row['aicc']:.3f}; "
                    f"BIC={row['bic']:.3f}; "
                    f"ΔAIC={row['delta_aic']:.3f}; "
                    f"wAIC={row['aic_weight']:.3f}; "
                    f"KS={row['ks_statistic']:.4f}; "
                    f"CvM={row['cvm_statistic']:.4f}"
                )

    comparison_df = pd.DataFrame(
        comparison_rows
    )

    log()

    # =========================================================================
    # 9. PARAMETRIC BOOTSTRAP KS
    # =========================================================================

    log(
        "[9] Calibrating goodness-of-fit with parametric bootstrap..."
    )

    log(
        f"  Bootstrap iterations per fitted model: "
        f"{BOOTSTRAP_ITERATIONS:,}"
    )

    bootstrap_gof_rows = []

    for row_index, row in (
        fits_df.loc[
            fits_df[
                "fit_status"
            ]
            == "OK"
        ].iterrows()
    ):

        method = row["method"]
        scenario = row["scenario"]
        distribution_name = (
            row["distribution"]
        )

        values = scenario_data[
            (
                method,
                scenario,
            )
        ]

        params = fit_distribution(
            distribution_name,
            values,
        )

        seed = (
            RANDOM_SEED
            + row_index * 101
        )

        result = (
            parametric_bootstrap_ks(
                values,
                distribution_name,
                params,
                BOOTSTRAP_ITERATIONS,
                seed,
            )
        )

        bootstrap_gof_rows.append(
            {
                "method":
                    method,
                "scenario":
                    scenario,
                "distribution":
                    distribution_name,
                "n":
                    len(values),
                "observed_ks":
                    result[
                        "observed_ks"
                    ],
                "bootstrap_valid":
                    result[
                        "bootstrap_valid"
                    ],
                "bootstrap_failures":
                    result[
                        "bootstrap_failures"
                    ],
                "bootstrap_ks_p":
                    result[
                        "bootstrap_p"
                    ],
                "diagnostic_at_alpha_0_05":
                    (
                        "NO_EVIDENCE_OF_POOR_FIT"
                        if (
                            np.isfinite(
                                result[
                                    "bootstrap_p"
                                ]
                            )
                            and result[
                                "bootstrap_p"
                            ] >= ALPHA
                        )
                        else
                        "EVIDENCE_OF_POOR_FIT"
                    ),
            }
        )

        log(
            f"  {method} | "
            f"{scenario} | "
            f"{distribution_name}: "
            f"bootstrap KS p="
            f"{result['bootstrap_p']:.4f}"
        )

    bootstrap_gof_df = pd.DataFrame(
        bootstrap_gof_rows
    )

    log()

    log(
        "  NOTE: Parametric-bootstrap KS calibration accounts "
        "for parameter estimation more appropriately than treating "
        "the nominal scipy KS p-value as exact."
    )

    log()

    # =========================================================================
    # 10. AIC SELECTION STABILITY
    # =========================================================================

    log(
        "[10] Evaluating model-selection stability..."
    )

    stability_rows = []

    for method, _, role in analyses:

        log(
            f"  {method}:"
        )

        for scenario_index, scenario in enumerate(
            SCENARIO_ORDER
        ):

            values = scenario_data[
                (
                    method,
                    scenario,
                )
            ]

            seed = (
                RANDOM_SEED
                + 10000
                + scenario_index * 1000
                + sum(
                    ord(c)
                    for c in method
                )
            )

            stability = (
                bootstrap_aic_selection(
                    values,
                    BOOTSTRAP_ITERATIONS,
                    seed,
                )
            )

            stability[
                "method"
            ] = method

            stability[
                "analysis_role"
            ] = role

            stability[
                "scenario"
            ] = scenario

            stability_rows.append(
                stability
            )

            ordered = (
                stability.sort_values(
                    "selection_frequency",
                    ascending=False,
                )
            )

            winner = (
                ordered.iloc[0]
            )

            log(
                f"    {scenario}: "
                f"most frequent AIC winner="
                f"{winner['distribution']} "
                f"({winner['selection_frequency']:.3f})"
            )

    stability_df = pd.concat(
        stability_rows,
        ignore_index=True,
    )

    log()

    log(
        "  NOTE: This bootstrap evaluates stability of distribution "
        "selection under resampling."
    )

    log(
        "  It is not the Monte Carlo simulation of procurement durations."
    )

    log()

    # =========================================================================
    # 11. BUILD DECISION AUDIT
    # =========================================================================

    log(
        "[11] Building distribution-selection audit..."
    )

    decision_rows = []

    for method, _, role in analyses:

        for scenario in SCENARIO_ORDER:

            subset = (
                fits_df.loc[
                    (
                        fits_df[
                            "method"
                        ]
                        == method
                    )
                    & (
                        fits_df[
                            "scenario"
                        ]
                        == scenario
                    )
                    & (
                        fits_df[
                            "fit_status"
                        ]
                        == "OK"
                    )
                ]
                .sort_values(
                    "aic"
                )
                .copy()
            )

            if subset.empty:
                continue

            best = subset.iloc[0]

            gof_match = (
                bootstrap_gof_df.loc[
                    (
                        bootstrap_gof_df[
                            "method"
                        ]
                        == method
                    )
                    & (
                        bootstrap_gof_df[
                            "scenario"
                        ]
                        == scenario
                    )
                    & (
                        bootstrap_gof_df[
                            "distribution"
                        ]
                        == best[
                            "distribution"
                        ]
                    )
                ]
            )

            if len(gof_match):
                bootstrap_p = float(
                    gof_match.iloc[0][
                        "bootstrap_ks_p"
                    ]
                )
            else:
                bootstrap_p = np.nan

            stability_match = (
                stability_df.loc[
                    (
                        stability_df[
                            "method"
                        ]
                        == method
                    )
                    & (
                        stability_df[
                            "scenario"
                        ]
                        == scenario
                    )
                    & (
                        stability_df[
                            "distribution"
                        ]
                        == best[
                            "distribution"
                        ]
                    )
                ]
            )

            if len(stability_match):
                stability_frequency = (
                    float(
                        stability_match.iloc[0][
                            "selection_frequency"
                        ]
                    )
                )
            else:
                stability_frequency = np.nan

            second = (
                subset.iloc[1]
                if len(subset) > 1
                else None
            )

            delta_second = (
                float(
                    second[
                        "aic"
                    ]
                    - best[
                        "aic"
                    ]
                )
                if second is not None
                else np.nan
            )

            if (
                np.isfinite(
                    bootstrap_p
                )
                and bootstrap_p < ALPHA
            ):
                decision_flag = (
                    "BEST_AIC_BUT_GOF_CAUTION"
                )

            elif (
                np.isfinite(
                    delta_second
                )
                and delta_second < 2
            ):
                decision_flag = (
                    "COMPETING_MODELS"
                )

            else:
                decision_flag = (
                    "SUPPORTED_CANDIDATE"
                )

            decision_rows.append(
                {
                    "method":
                        method,
                    "analysis_role":
                        role,
                    "scenario":
                        scenario,
                    "n":
                        int(
                            best[
                                "n"
                            ]
                        ),
                    "aic_preferred_distribution":
                        best[
                            "distribution"
                        ],
                    "best_aic":
                        float(
                            best[
                                "aic"
                            ]
                        ),
                    "best_bic":
                        float(
                            best[
                                "bic"
                            ]
                        ),
                    "best_aic_weight":
                        float(
                            best[
                                "aic_weight"
                            ]
                        ),
                    "delta_aic_to_second":
                        delta_second,
                    "bootstrap_ks_p":
                        bootstrap_p,
                    "bootstrap_aic_selection_frequency":
                        stability_frequency,
                    "decision_flag":
                        decision_flag,
                    "scientific_note":
                        (
                            "Distribution preference is based on "
                            "comparative evidence and must be interpreted "
                            "together with goodness-of-fit, quantile "
                            "diagnostics, and bootstrap stability."
                        ),
                }
            )

    decision_df = pd.DataFrame(
        decision_rows
    )

    for _, row in (
        decision_df.iterrows()
    ):

        log(
            f"  {row['method']} | "
            f"{row['scenario']}: "
            f"{row['aic_preferred_distribution']} | "
            f"ΔAIC2={row['delta_aic_to_second']:.3f} | "
            f"bootstrap KS p="
            f"{row['bootstrap_ks_p']:.4f} | "
            f"AIC stability="
            f"{row['bootstrap_aic_selection_frequency']:.3f} | "
            f"{row['decision_flag']}"
        )

    log()

    # =========================================================================
    # 12. SAVE OUTPUTS
    # =========================================================================

    log(
        "[12] Saving reproducible distribution-fitting outputs..."
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        fits_df.to_excel(
            writer,
            sheet_name="distribution_fits",
            index=False,
        )

        comparison_df.to_excel(
            writer,
            sheet_name="model_comparison",
            index=False,
        )

        quantiles_df.to_excel(
            writer,
            sheet_name="quantile_diagnostics",
            index=False,
        )

        bootstrap_gof_df.to_excel(
            writer,
            sheet_name="bootstrap_gof",
            index=False,
        )

        stability_df.to_excel(
            writer,
            sheet_name="selection_stability",
            index=False,
        )

        decision_df.to_excel(
            writer,
            sheet_name="selection_audit",
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
        "DISTRIBUTION-FITTING AUDIT"
    )
    separator()

    log(
        f"Master analytical procedures:          "
        f"{len(df)}"
    )

    log(
        f"Available total award times:           "
        f"{available}"
    )

    log(
        f"Candidate distributions:               "
        f"{len(CANDIDATE_DISTRIBUTIONS)}"
    )

    log(
        f"Scenario definitions fitted:           "
        f"{len(analyses)}"
    )

    log(
        f"Scenario-specific datasets:            "
        f"{len(analyses) * len(SCENARIO_ORDER)}"
    )

    log(
        f"Successful candidate fits:             "
        f"{len(fits_df) - failed_fits}"
    )

    log(
        f"Failed candidate fits:                 "
        f"{failed_fits}"
    )

    log(
        f"Bootstrap iterations per diagnostic:   "
        f"{BOOTSTRAP_ITERATIONS:,}"
    )

    log()

    log(
        "PRIMARY TERCILE RESULTS"
    )

    log("-" * 78)

    primary_decisions = (
        decision_df.loc[
            decision_df[
                "method"
            ]
            == "Terciles"
        ]
    )

    for _, row in (
        primary_decisions.iterrows()
    ):

        log(
            f"{row['scenario']:<8} | "
            f"{row['aic_preferred_distribution']:<12} | "
            f"ΔAIC2={row['delta_aic_to_second']:.3f} | "
            f"KSboot p={row['bootstrap_ks_p']:.4f} | "
            f"stability={row['bootstrap_aic_selection_frequency']:.3f} | "
            f"{row['decision_flag']}"
        )

    log()

    log(
        "SCIENTIFIC SCOPE"
    )

    log(
        "- Candidate distributions are compared rather than imposed."
    )

    log(
        "- Lognormal and Weibull from the approved research design "
        "are evaluated alongside Gamma and Exponential."
    )

    log(
        "- All models use maximum-likelihood estimation with loc=0."
    )

    log(
        "- AIC/AICc/BIC compare relative model support; "
        "they do not prove that a distribution is true."
    )

    log(
        "- Nominal KS/CvM p-values are retained only as diagnostics "
        "because parameters are estimated from the same observations."
    )

    log(
        "- Parametric-bootstrap KS calibration is therefore reported."
    )

    log(
        "- Quantile diagnostics evaluate practical reproduction of "
        "the observed award-time distribution."
    )

    log(
        "- Bootstrap model-selection frequencies evaluate stability "
        "under resampling."
    )

    log(
        "- P25/P75 fitting is retained as scenario-definition robustness."
    )

    log(
        "- Data-driven scenarios are not used for primary fitting "
        "because the High group has only n=8."
    )

    log(
        "- No observations are deleted."
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

    if failed_fits == 0:
        log(
            "PIPELINE STATUS: COMPLETE"
        )
    else:
        log(
            "PIPELINE STATUS: COMPLETE WITH FIT WARNINGS"
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
