from pathlib import Path
import sys
import logging
import warnings

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import durbin_watson


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
    / "06_1_relationship_diagnostics.xlsx"
)

LOG_FILE = (
    LOGS_DIR
    / "06_relationship_diagnostics.log"
)

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("relationship_diagnostics")
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
# HELPER FUNCTIONS
# =============================================================================

def validate_numeric(df, columns):
    for column in columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )


def safe_pearson(x, y):
    mask = x.notna() & y.notna()
    x2 = x.loc[mask]
    y2 = y.loc[mask]

    if len(x2) < 3:
        return np.nan, np.nan

    result = stats.pearsonr(x2, y2)

    return float(result.statistic), float(result.pvalue)


def safe_spearman(x, y):
    mask = x.notna() & y.notna()
    x2 = x.loc[mask]
    y2 = y.loc[mask]

    if len(x2) < 3:
        return np.nan, np.nan

    result = stats.spearmanr(x2, y2)

    return float(result.statistic), float(result.pvalue)


def fit_ols(x, y):
    """
    Ordinary least squares with intercept.
    """
    data = pd.DataFrame(
        {
            "x": x,
            "y": y,
        }
    ).dropna()

    X = sm.add_constant(
        data["x"],
        has_constant="add",
    )

    model = sm.OLS(
        data["y"],
        X,
    ).fit()

    return model, data, X


def fit_quadratic(x, y):
    """
    Quadratic model:
        y = beta0 + beta1*x + beta2*x^2
    """
    data = pd.DataFrame(
        {
            "x": x,
            "y": y,
        }
    ).dropna()

    X = pd.DataFrame(
        {
            "x": data["x"],
            "x_squared": data["x"] ** 2,
        },
        index=data.index,
    )

    X = sm.add_constant(
        X,
        has_constant="add",
    )

    model = sm.OLS(
        data["y"],
        X,
    ).fit()

    return model, data, X


def fit_robust_linear(x, y):
    """
    Robust linear model using Huber's T norm.
    Used as a sensitivity diagnostic, not as an automatic replacement for OLS.
    """
    data = pd.DataFrame(
        {
            "x": x,
            "y": y,
        }
    ).dropna()

    X = sm.add_constant(
        data["x"],
        has_constant="add",
    )

    model = sm.RLM(
        data["y"],
        X,
        M=sm.robust.norms.HuberT(),
    ).fit()

    return model, data, X


def model_summary_row(
    model_name,
    model,
    n,
    x_definition,
    y_definition,
):
    return {
        "model": model_name,
        "n": n,
        "predictor": x_definition,
        "outcome": y_definition,
        "r_squared": getattr(
            model,
            "rsquared",
            np.nan,
        ),
        "adjusted_r_squared": getattr(
            model,
            "rsquared_adj",
            np.nan,
        ),
        "aic": getattr(
            model,
            "aic",
            np.nan,
        ),
        "bic": getattr(
            model,
            "bic",
            np.nan,
        ),
        "rmse": float(
            np.sqrt(
                np.mean(
                    np.asarray(model.resid) ** 2
                )
            )
        ),
    }


def coefficient_rows(model_name, model):
    rows = []

    params = model.params
    bse = model.bse
    pvalues = model.pvalues

    try:
        conf = model.conf_int(alpha=0.05)
    except Exception:
        conf = None

    for parameter in params.index:

        if conf is not None:
            ci_lower = float(
                conf.loc[parameter].iloc[0]
            )
            ci_upper = float(
                conf.loc[parameter].iloc[1]
            )
        else:
            ci_lower = np.nan
            ci_upper = np.nan

        rows.append(
            {
                "model": model_name,
                "parameter": parameter,
                "estimate": float(
                    params.loc[parameter]
                ),
                "standard_error": float(
                    bse.loc[parameter]
                ),
                "p_value": float(
                    pvalues.loc[parameter]
                ),
                "ci_95_lower": ci_lower,
                "ci_95_upper": ci_upper,
            }
        )

    return rows


def robust_coefficient_rows(model_name, model):
    rows = []

    params = model.params
    bse = model.bse
    pvalues = model.pvalues

    conf = model.conf_int(alpha=0.05)

    for parameter in params.index:
        rows.append(
            {
                "model": model_name,
                "parameter": parameter,
                "estimate": float(
                    params.loc[parameter]
                ),
                "standard_error": float(
                    bse.loc[parameter]
                ),
                "p_value": float(
                    pvalues.loc[parameter]
                ),
                "ci_95_lower": float(
                    conf.loc[parameter].iloc[0]
                ),
                "ci_95_upper": float(
                    conf.loc[parameter].iloc[1]
                ),
            }
        )

    return rows


def calculate_ols_diagnostics(
    model_name,
    model,
    X,
):
    residuals = pd.Series(
        np.asarray(model.resid)
    )

    shapiro_w = np.nan
    shapiro_p = np.nan

    if 3 <= len(residuals) <= 5000:
        shapiro_result = stats.shapiro(
            residuals
        )
        shapiro_w = float(
            shapiro_result.statistic
        )
        shapiro_p = float(
            shapiro_result.pvalue
        )

    try:
        bp = het_breuschpagan(
            model.resid,
            X,
        )

        bp_lm = float(bp[0])
        bp_lm_p = float(bp[1])
        bp_f = float(bp[2])
        bp_f_p = float(bp[3])

    except Exception:
        bp_lm = np.nan
        bp_lm_p = np.nan
        bp_f = np.nan
        bp_f_p = np.nan

    dw = float(
        durbin_watson(model.resid)
    )

    return {
        "model": model_name,
        "residual_shapiro_w": shapiro_w,
        "residual_shapiro_p": shapiro_p,
        "breusch_pagan_lm": bp_lm,
        "breusch_pagan_lm_p": bp_lm_p,
        "breusch_pagan_f": bp_f,
        "breusch_pagan_f_p": bp_f_p,
        "durbin_watson": dw,
    }


def calculate_influence(
    df_model,
    model,
):
    influence = model.get_influence()

    frame = influence.summary_frame()

    result = pd.DataFrame(
        {
            "procedure_code":
                df_model["procedure_code"].values,
            "queries_observations_count":
                df_model[
                    "queries_observations_count"
                ].values,
            "total_award_time_days":
                df_model[
                    "total_award_time_days"
                ].values,
            "leverage":
                frame["hat_diag"].values,
            "cooks_distance":
                frame["cooks_d"].values,
            "studentized_residual":
                frame[
                    "student_resid"
                ].values,
        }
    )

    n = len(result)

    result["cooks_threshold_4_over_n"] = (
        4 / n
    )

    result["cooks_flag"] = (
        result["cooks_distance"]
        > result["cooks_threshold_4_over_n"]
    )

    # For simple regression with intercept:
    # p = 2 model parameters.
    p = 2

    result["leverage_threshold_2p_over_n"] = (
        2 * p / n
    )

    result["leverage_flag"] = (
        result["leverage"]
        > result[
            "leverage_threshold_2p_over_n"
        ]
    )

    result["absolute_studentized_residual"] = (
        result["studentized_residual"].abs()
    )

    result["studentized_residual_flag"] = (
        result[
            "absolute_studentized_residual"
        ] > 3
    )

    result["any_influence_flag"] = (
        result["cooks_flag"]
        | result["leverage_flag"]
        | result[
            "studentized_residual_flag"
        ]
    )

    return result.sort_values(
        by="cooks_distance",
        ascending=False,
    )


def compare_full_vs_sensitivity(
    analysis_df,
    influence_df,
):
    """
    Sensitivity analysis only.

    Refit the original linear relationship after excluding observations
    flagged by Cook's distance > 4/n.

    This DOES NOT redefine the analytical sample and DOES NOT justify
    automatic deletion of influential observations.
    """

    full_model, _, _ = fit_ols(
        analysis_df[
            "queries_observations_count"
        ],
        analysis_df[
            "total_award_time_days"
        ],
    )

    flagged_codes = set(
        influence_df.loc[
            influence_df["cooks_flag"],
            "procedure_code",
        ].tolist()
    )

    sensitivity_df = analysis_df.loc[
        ~analysis_df[
            "procedure_code"
        ].isin(flagged_codes)
    ].copy()

    sensitivity_model, _, _ = fit_ols(
        sensitivity_df[
            "queries_observations_count"
        ],
        sensitivity_df[
            "total_award_time_days"
        ],
    )

    rows = [
        {
            "analysis":
                "Full analytical sample",
            "n":
                int(full_model.nobs),
            "excluded_by_cooks_rule":
                0,
            "intercept":
                float(
                    full_model.params[
                        "const"
                    ]
                ),
            "slope":
                float(
                    full_model.params[
                        "x"
                    ]
                ),
            "slope_p_value":
                float(
                    full_model.pvalues[
                        "x"
                    ]
                ),
            "r_squared":
                float(
                    full_model.rsquared
                ),
            "adjusted_r_squared":
                float(
                    full_model.rsquared_adj
                ),
        },
        {
            "analysis":
                "Sensitivity excluding Cook-flagged cases",
            "n":
                int(
                    sensitivity_model.nobs
                ),
            "excluded_by_cooks_rule":
                len(flagged_codes),
            "intercept":
                float(
                    sensitivity_model.params[
                        "const"
                    ]
                ),
            "slope":
                float(
                    sensitivity_model.params[
                        "x"
                    ]
                ),
            "slope_p_value":
                float(
                    sensitivity_model.pvalues[
                        "x"
                    ]
                ),
            "r_squared":
                float(
                    sensitivity_model.rsquared
                ),
            "adjusted_r_squared":
                float(
                    sensitivity_model.rsquared_adj
                ),
        },
    ]

    return pd.DataFrame(rows)


# =============================================================================
# MAIN
# =============================================================================

def main():

    separator()
    log(
        "RELATIONSHIP DIAGNOSTICS - "
        "ROAD INFRASTRUCTURE TENDERS"
    )
    separator()

    log(
        "Input: Script 03 integrated analytical dataset"
    )
    log(
        "Purpose: Diagnose the form, robustness, "
        "and influence structure of the relationship "
        "between queries/observations and award time"
    )
    log()

    # =========================================================================
    # 1. INPUT VALIDATION
    # =========================================================================

    log("[1] Validating Script 03 input...")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: "
            f"{INPUT_FILE}"
        )

    log(
        f"  Input file: {INPUT_FILE.name}"
    )
    log("  Input file found.")
    log()

    # =========================================================================
    # 2. READ DATA
    # =========================================================================

    log("[2] Reading analytical dataset...")

    df = pd.read_excel(INPUT_FILE)

    log(f"  Rows: {len(df)}")
    log(f"  Columns: {len(df.columns)}")
    log()

    # =========================================================================
    # 3. ANALYTICAL CONTRACT
    # =========================================================================

    log("[3] Validating analytical contract...")

    required_columns = [
        "procedure_code",
        "queries_observations_count",
        "total_award_time_days",
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
    ]

    missing_columns = [
        col
        for col in required_columns
        if col not in df.columns
    ]

    if missing_columns:
        raise KeyError(
            "Input dataset is missing required columns: "
            + ", ".join(missing_columns)
        )

    if len(df) != EXPECTED_MASTER_SAMPLE_SIZE:
        raise ValueError(
            f"Expected master sample size "
            f"{EXPECTED_MASTER_SAMPLE_SIZE}, "
            f"found {len(df)}."
        )

    if df["procedure_code"].duplicated().any():
        raise ValueError(
            "Duplicate procedure_code values detected."
        )

    validate_numeric(
        df,
        [
            "queries_observations_count",
            "total_award_time_days",
            "query_stage_duration_days",
            "evaluation_stage_duration_days",
        ],
    )

    log(
        f"  Master analytical sample verified: "
        f"{EXPECTED_MASTER_SAMPLE_SIZE}"
    )
    log("  Required columns verified.")
    log("  procedure_code uniqueness verified.")
    log()

    # =========================================================================
    # 4. PRIMARY ANALYTICAL SAMPLE
    # =========================================================================

    log("[4] Preparing primary relationship sample...")

    analysis_df = df[
        [
            "procedure_code",
            "queries_observations_count",
            "total_award_time_days",
        ]
    ].dropna().copy()

    n_primary = len(analysis_df)

    if n_primary < 3:
        raise ValueError(
            "Insufficient complete observations "
            "for relationship analysis."
        )

    log(
        f"  Master sample: "
        f"{len(df)}"
    )
    log(
        f"  Primary complete cases: "
        f"{n_primary}"
    )
    log(
        f"  Excluded from primary relationship "
        f"because total award time is unavailable: "
        f"{len(df) - n_primary}"
    )
    log(
        "  NOTE: This is analysis-specific complete-case "
        "selection; the master sample remains unchanged."
    )
    log()

    # =========================================================================
    # 5. BIVARIATE ASSOCIATION
    # =========================================================================

    log("[5] Evaluating bivariate association...")

    x = analysis_df[
        "queries_observations_count"
    ]

    y = analysis_df[
        "total_award_time_days"
    ]

    pearson_r, pearson_p = safe_pearson(
        x,
        y,
    )

    spearman_rho, spearman_p = safe_spearman(
        x,
        y,
    )

    kendall_result = stats.kendalltau(
        x,
        y,
        nan_policy="omit",
    )

    kendall_tau = float(
        kendall_result.statistic
    )

    kendall_p = float(
        kendall_result.pvalue
    )

    associations = pd.DataFrame(
        [
            {
                "relationship":
                    "queries_observations_count vs total_award_time_days",
                "method":
                    "Pearson",
                "coefficient":
                    pearson_r,
                "p_value":
                    pearson_p,
                "n":
                    n_primary,
            },
            {
                "relationship":
                    "queries_observations_count vs total_award_time_days",
                "method":
                    "Spearman",
                "coefficient":
                    spearman_rho,
                "p_value":
                    spearman_p,
                "n":
                    n_primary,
            },
            {
                "relationship":
                    "queries_observations_count vs total_award_time_days",
                "method":
                    "Kendall",
                "coefficient":
                    kendall_tau,
                "p_value":
                    kendall_p,
                "n":
                    n_primary,
            },
        ]
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
        "  NOTE: Association coefficients do not "
        "establish causality."
    )
    log()

    # =========================================================================
    # 6. MODEL 1: ORIGINAL LINEAR SCALE
    # =========================================================================

    log(
        "[6] Fitting original-scale linear model..."
    )

    linear_model, linear_data, linear_X = (
        fit_ols(x, y)
    )

    linear_slope = float(
        linear_model.params["x"]
    )

    linear_slope_p = float(
        linear_model.pvalues["x"]
    )

    log(
        f"  Slope: {linear_slope:.6f}"
    )
    log(
        f"  Slope p-value: "
        f"{linear_slope_p:.6g}"
    )
    log(
        f"  R-squared: "
        f"{linear_model.rsquared:.4f}"
    )
    log(
        f"  Adjusted R-squared: "
        f"{linear_model.rsquared_adj:.4f}"
    )
    log(
        f"  AIC: {linear_model.aic:.3f}"
    )
    log(
        f"  BIC: {linear_model.bic:.3f}"
    )
    log()

    # =========================================================================
    # 7. MODEL 2: LOG1P PREDICTOR
    # =========================================================================

    log(
        "[7] Fitting log-transformed predictor model..."
    )

    log_x = np.log1p(x)

    log_model, log_data, log_X = fit_ols(
        log_x,
        y,
    )

    log_slope = float(
        log_model.params["x"]
    )

    log_slope_p = float(
        log_model.pvalues["x"]
    )

    log(
        "  Predictor transformation: "
        "log(1 + queries_observations_count)"
    )

    log(
        f"  Slope: {log_slope:.6f}"
    )

    log(
        f"  Slope p-value: "
        f"{log_slope_p:.6g}"
    )

    log(
        f"  R-squared: "
        f"{log_model.rsquared:.4f}"
    )

    log(
        f"  Adjusted R-squared: "
        f"{log_model.rsquared_adj:.4f}"
    )

    log(
        f"  AIC: {log_model.aic:.3f}"
    )

    log(
        f"  BIC: {log_model.bic:.3f}"
    )

    log()

    # =========================================================================
    # 8. MODEL 3: QUADRATIC
    # =========================================================================

    log(
        "[8] Fitting quadratic relationship model..."
    )

    quadratic_model, quadratic_data, quadratic_X = (
        fit_quadratic(
            x,
            y,
        )
    )

    quadratic_term = float(
        quadratic_model.params[
            "x_squared"
        ]
    )

    quadratic_p = float(
        quadratic_model.pvalues[
            "x_squared"
        ]
    )

    log(
        f"  Quadratic term: "
        f"{quadratic_term:.8f}"
    )

    log(
        f"  Quadratic-term p-value: "
        f"{quadratic_p:.6g}"
    )

    log(
        f"  R-squared: "
        f"{quadratic_model.rsquared:.4f}"
    )

    log(
        f"  Adjusted R-squared: "
        f"{quadratic_model.rsquared_adj:.4f}"
    )

    log(
        f"  AIC: {quadratic_model.aic:.3f}"
    )

    log(
        f"  BIC: {quadratic_model.bic:.3f}"
    )

    log()

    # =========================================================================
    # 9. ROBUST LINEAR SENSITIVITY
    # =========================================================================

    log(
        "[9] Fitting robust linear sensitivity model..."
    )

    robust_model, robust_data, robust_X = (
        fit_robust_linear(
            x,
            y,
        )
    )

    robust_slope = float(
        robust_model.params["x"]
    )

    robust_slope_p = float(
        robust_model.pvalues["x"]
    )

    log(
        "  Estimator: Robust Linear Model "
        "(Huber T)"
    )

    log(
        f"  Robust slope: "
        f"{robust_slope:.6f}"
    )

    log(
        f"  Robust slope p-value: "
        f"{robust_slope_p:.6g}"
    )

    log(
        "  NOTE: Robust regression is used as a "
        "sensitivity diagnostic, not as an automatic "
        "replacement for the primary model."
    )

    log()

    # =========================================================================
    # 10. MODEL COMPARISON
    # =========================================================================

    log("[10] Comparing candidate functional forms...")

    model_rows = []

    model_rows.append(
        model_summary_row(
            "OLS_original_scale",
            linear_model,
            n_primary,
            "queries_observations_count",
            "total_award_time_days",
        )
    )

    model_rows.append(
        model_summary_row(
            "OLS_log1p_predictor",
            log_model,
            n_primary,
            "log(1 + queries_observations_count)",
            "total_award_time_days",
        )
    )

    model_rows.append(
        model_summary_row(
            "OLS_quadratic",
            quadratic_model,
            n_primary,
            "queries_observations_count + squared term",
            "total_award_time_days",
        )
    )

    model_comparison = pd.DataFrame(
        model_rows
    )

    for _, row in model_comparison.iterrows():
        log(
            f"  {row['model']}: "
            f"R2={row['r_squared']:.4f}; "
            f"Adj.R2="
            f"{row['adjusted_r_squared']:.4f}; "
            f"AIC={row['aic']:.3f}; "
            f"BIC={row['bic']:.3f}; "
            f"RMSE={row['rmse']:.3f}"
        )

    log()
    log(
        "  NOTE: Model-comparison metrics are "
        "diagnostic. No final functional form is "
        "selected in this script."
    )
    log()

    # =========================================================================
    # 11. COEFFICIENT TABLE
    # =========================================================================

    log(
        "[11] Building coefficient diagnostics..."
    )

    coefficient_data = []

    coefficient_data.extend(
        coefficient_rows(
            "OLS_original_scale",
            linear_model,
        )
    )

    coefficient_data.extend(
        coefficient_rows(
            "OLS_log1p_predictor",
            log_model,
        )
    )

    coefficient_data.extend(
        coefficient_rows(
            "OLS_quadratic",
            quadratic_model,
        )
    )

    coefficient_data.extend(
        robust_coefficient_rows(
            "RLM_HuberT_original_scale",
            robust_model,
        )
    )

    coefficients = pd.DataFrame(
        coefficient_data
    )

    log(
        f"  Coefficient records: "
        f"{len(coefficients)}"
    )
    log()

    # =========================================================================
    # 12. RESIDUAL DIAGNOSTICS
    # =========================================================================

    log("[12] Running OLS residual diagnostics...")

    residual_diagnostics = pd.DataFrame(
        [
            calculate_ols_diagnostics(
                "OLS_original_scale",
                linear_model,
                linear_X,
            ),
            calculate_ols_diagnostics(
                "OLS_log1p_predictor",
                log_model,
                log_X,
            ),
            calculate_ols_diagnostics(
                "OLS_quadratic",
                quadratic_model,
                quadratic_X,
            ),
        ]
    )

    for _, row in residual_diagnostics.iterrows():

        log(
            f"  {row['model']}: "
            f"Shapiro p="
            f"{row['residual_shapiro_p']:.6g}; "
            f"Breusch-Pagan p="
            f"{row['breusch_pagan_lm_p']:.6g}; "
            f"Durbin-Watson="
            f"{row['durbin_watson']:.3f}"
        )

    log()
    log(
        "  NOTE: Residual diagnostics evaluate model "
        "assumptions; they do not determine causality."
    )
    log()

    # =========================================================================
    # 13. INFLUENCE DIAGNOSTICS
    # =========================================================================

    log(
        "[13] Evaluating influential observations..."
    )

    influence_input = analysis_df.copy()

    influence_model, _, influence_X = fit_ols(
        influence_input[
            "queries_observations_count"
        ],
        influence_input[
            "total_award_time_days"
        ],
    )

    influence = calculate_influence(
        influence_input,
        influence_model,
    )

    cooks_flagged = int(
        influence["cooks_flag"].sum()
    )

    leverage_flagged = int(
        influence["leverage_flag"].sum()
    )

    residual_flagged = int(
        influence[
            "studentized_residual_flag"
        ].sum()
    )

    any_flagged = int(
        influence[
            "any_influence_flag"
        ].sum()
    )

    log(
        f"  Cook's distance > 4/n: "
        f"{cooks_flagged}"
    )

    log(
        f"  Leverage > 2p/n: "
        f"{leverage_flagged}"
    )

    log(
        f"  |Studentized residual| > 3: "
        f"{residual_flagged}"
    )

    log(
        f"  Flagged by at least one rule: "
        f"{any_flagged}"
    )

    log(
        "  NOTE: Flagging does not imply that an "
        "observation is erroneous or should be deleted."
    )
    log()

    # =========================================================================
    # 14. INFLUENCE SENSITIVITY
    # =========================================================================

    log(
        "[14] Running influence sensitivity analysis..."
    )

    sensitivity = compare_full_vs_sensitivity(
        analysis_df,
        influence,
    )

    for _, row in sensitivity.iterrows():
        log(
            f"  {row['analysis']}: "
            f"n={int(row['n'])}; "
            f"slope={row['slope']:.6f}; "
            f"p={row['slope_p_value']:.6g}; "
            f"R2={row['r_squared']:.4f}"
        )

    log()
    log(
        "  NOTE: The sensitivity refit does not redefine "
        "the analytical sample and does not authorize "
        "automatic exclusion of influential observations."
    )
    log()

    # =========================================================================
    # 15. SECONDARY TEMPORAL-STAGE ASSOCIATIONS
    # =========================================================================

    log(
        "[15] Evaluating secondary temporal-stage associations..."
    )

    secondary_rows = []

    secondary_variables = [
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
    ]

    for outcome in secondary_variables:

        subset = df[
            [
                "queries_observations_count",
                outcome,
            ]
        ].dropna()

        px, pp = safe_pearson(
            subset[
                "queries_observations_count"
            ],
            subset[outcome],
        )

        sx, sp = safe_spearman(
            subset[
                "queries_observations_count"
            ],
            subset[outcome],
        )

        kt = stats.kendalltau(
            subset[
                "queries_observations_count"
            ],
            subset[outcome],
            nan_policy="omit",
        )

        secondary_rows.extend(
            [
                {
                    "outcome": outcome,
                    "method": "Pearson",
                    "coefficient": px,
                    "p_value": pp,
                    "n": len(subset),
                    "coverage_note":
                        "Secondary analysis; incomplete temporal-stage coverage",
                },
                {
                    "outcome": outcome,
                    "method": "Spearman",
                    "coefficient": sx,
                    "p_value": sp,
                    "n": len(subset),
                    "coverage_note":
                        "Secondary analysis; incomplete temporal-stage coverage",
                },
                {
                    "outcome": outcome,
                    "method": "Kendall",
                    "coefficient":
                        float(kt.statistic),
                    "p_value":
                        float(kt.pvalue),
                    "n": len(subset),
                    "coverage_note":
                        "Secondary analysis; incomplete temporal-stage coverage",
                },
            ]
        )

        log(
            f"  {outcome}: "
            f"n={len(subset)}; "
            f"Pearson={px:.4f}; "
            f"Spearman={sx:.4f}; "
            f"Kendall={float(kt.statistic):.4f}"
        )

    secondary_associations = pd.DataFrame(
        secondary_rows
    )

    log(
        "  NOTE: These stage-specific analyses use "
        "n=109 and must be interpreted together with "
        "the missing-data findings from Script 05."
    )
    log()

    # =========================================================================
    # 16. PRIMARY ANALYTICAL DATA
    # =========================================================================

    log(
        "[16] Preparing primary analytical data audit..."
    )

    primary_data = analysis_df.copy()

    primary_data[
        "log1p_queries_observations_count"
    ] = np.log1p(
        primary_data[
            "queries_observations_count"
        ]
    )

    log(
        f"  Primary analytical rows: "
        f"{len(primary_data)}"
    )
    log()

    # =========================================================================
    # 17. SAVE OUTPUTS
    # =========================================================================

    log(
        "[17] Saving reproducible relationship diagnostics..."
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        associations.to_excel(
            writer,
            sheet_name="associations",
            index=False,
        )

        model_comparison.to_excel(
            writer,
            sheet_name="model_comparison",
            index=False,
        )

        coefficients.to_excel(
            writer,
            sheet_name="coefficients",
            index=False,
        )

        residual_diagnostics.to_excel(
            writer,
            sheet_name="residual_diagnostics",
            index=False,
        )

        influence.to_excel(
            writer,
            sheet_name="influence_diagnostics",
            index=False,
        )

        sensitivity.to_excel(
            writer,
            sheet_name="influence_sensitivity",
            index=False,
        )

        secondary_associations.to_excel(
            writer,
            sheet_name="secondary_associations",
            index=False,
        )

        primary_data.to_excel(
            writer,
            sheet_name="primary_analysis_data",
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
    log("RELATIONSHIP DIAGNOSTICS AUDIT")
    separator()

    log(
        f"Master analytical procedures:          "
        f"{len(df)}"
    )

    log(
        f"Primary relationship sample:           "
        f"{n_primary}"
    )

    log(
        f"Primary outcome coverage:              "
        f"{100*n_primary/len(df):.2f}%"
    )

    log(
        f"Secondary stage-analysis sample:        "
        f"{df[['query_stage_duration_days', 'evaluation_stage_duration_days']].notna().all(axis=1).sum()}"
    )

    log(
        f"Cook-flagged observations:             "
        f"{cooks_flagged}"
    )

    log(
        f"Any influence-rule flags:              "
        f"{any_flagged}"
    )

    log()
    log("SCIENTIFIC SCOPE")

    log(
        "- The master analytical sample remains "
        f"unchanged at n={EXPECTED_MASTER_SAMPLE_SIZE}."
    )

    log(
        "- The primary relationship uses available "
        "total-award-time observations only."
    )

    log(
        "- Pearson, Spearman, and Kendall associations "
        "are reported without causal interpretation."
    )

    log(
        "- Linear, log-predictor, and quadratic forms "
        "are compared diagnostically."
    )

    log(
        "- Robust regression is used only as a "
        "sensitivity diagnostic."
    )

    log(
        "- Influential observations are flagged, "
        "not automatically deleted."
    )

    log(
        "- No scenario thresholds are defined."
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
        "- No final model is selected in this script."
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
