#!/usr/bin/env python

# -*- coding: utf-8 -*-



"""

18_robustness_analysis.py



ROBUSTNESS AND SENSITIVITY ANALYSIS

Road Infrastructure Tenders - Peru



Purpose

-------

Evaluate whether the principal empirical and stochastic conclusions developed

in Scripts 03-17 remain stable under prespecified, scientifically reasonable

alternative analytical choices.



This script does NOT:

- redefine the primary model,

- optimize scenario thresholds using outcomes,

- re-select probability distributions after validation,

- delete observations because they are inconvenient,

- impute missing temporal values,

- modify Monte Carlo convergence criteria,

- claim causal effects.



Primary questions

-----------------

R1. Does the positive relationship between queries/observations and award time

    persist under alternative association measures and temporal subsets?



R2. Does the Low -> Medium -> High award-time structure remain broadly present

    under alternative scenario definitions already prespecified in Script 07?



R3. Are the principal Monte Carlo conclusions sensitive to the Low-scenario

    probability representation?



R4. Are conclusions materially altered when the two-stage DES is compared with

    the direct total-duration Monte Carlo model?



R5. Does temporal validation alter the substantive direction of the principal

    empirical relationship?



R6. Which findings are ROBUST, PARTIALLY ROBUST, SENSITIVE, or

    DATA-LIMITED?



Scientific rule

---------------

No analytical choice is changed retrospectively to obtain a more favorable

result. Sensitivity analysis diagnoses dependence on reasonable modeling

choices; it does not replace the primary specification.

"""



from pathlib import Path

import sys

import warnings

import logging

from datetime import datetime



import numpy as np

import pandas as pd

from scipy import stats





# =============================================================================

# 0. CONFIGURATION

# =============================================================================



warnings.filterwarnings("ignore")



SCRIPT_NAME = "18_robustness_analysis.py"

RANDOM_SEED = 2026



EXPECTED_MASTER_N = 137



PRIMARY_SCENARIO_ORDER = ["Low", "Medium", "High"]



ROOT = Path(__file__).resolve().parents[2]



INPUT_MASTER = ROOT / "02_results" / "03_1_integrated_dataset.xlsx"



INPUT_SCENARIOS = (

    ROOT

    / "02_results"

    / "statistical_analysis"

    / "07_1_scenario_definition.xlsx"

)



INPUT_ROBUSTNESS_08 = (

    ROOT

    / "02_results"

    / "statistical_analysis"

    / "08_1_scenario_robustness.xlsx"

)



INPUT_MC = (

    ROOT

    / "02_results"

    / "stochastic_modeling"

    / "14_1_monte_carlo_simulation.xlsx"

)



INPUT_DES = (

    ROOT

    / "02_results"

    / "stochastic_modeling"

    / "16_1_discrete_event_simulation.xlsx"

)



INPUT_VALIDATION = (

    ROOT

    / "02_results"

    / "model_validation"

    / "17_1_model_validation.xlsx"

)



OUTPUT_DIR = ROOT / "02_results" / "robustness_analysis"

LOG_DIR = ROOT / "03_logs" / "robustness_analysis"



OUTPUT_FILE = OUTPUT_DIR / "18_1_robustness_analysis.xlsx"

LOG_FILE = LOG_DIR / "18_robustness_analysis.log"



OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR.mkdir(parents=True, exist_ok=True)





# =============================================================================

# 1. LOGGING

# =============================================================================



logger = logging.getLogger("robustness_analysis")

logger.setLevel(logging.INFO)

logger.handlers.clear()



formatter = logging.Formatter("%(message)s")



file_handler = logging.FileHandler(

    LOG_FILE,

    mode="w",

    encoding="utf-8"

)

file_handler.setFormatter(formatter)



stream_handler = logging.StreamHandler(sys.stdout)

stream_handler.setFormatter(formatter)



logger.addHandler(file_handler)

logger.addHandler(stream_handler)





def log(message=""):

    logger.info(message)





# =============================================================================

# 2. GENERAL HELPERS

# =============================================================================



def require_file(path):

    if not path.exists():

        raise FileNotFoundError(f"Required input not found: {path}")

    log(f"  Found: {path.name}")





def require_columns(df, columns, label):

    missing = [c for c in columns if c not in df.columns]

    if missing:

        raise ValueError(

            f"{label} is missing required columns: {missing}"

        )





def safe_float(x):

    try:

        if pd.isna(x):

            return np.nan

        return float(x)

    except Exception:

        return np.nan





def clean_numeric(series):

    return pd.to_numeric(series, errors="coerce")





def epsilon_squared_kruskal(h, n, k):

    if n <= k:

        return np.nan

    value = (h - k + 1) / (n - k)

    return max(0.0, float(value))





def rank_biserial_from_u(u, n1, n2):

    if n1 == 0 or n2 == 0:

        return np.nan

    return (2.0 * u / (n1 * n2)) - 1.0





def scenario_sort_key(value):

    try:

        return PRIMARY_SCENARIO_ORDER.index(value)

    except ValueError:

        return 999





def descriptive_summary(values):

    x = np.asarray(values, dtype=float)

    x = x[np.isfinite(x)]



    if len(x) == 0:

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

        "n": len(x),

        "mean": float(np.mean(x)),

        "median": float(np.median(x)),

        "std_dev": float(np.std(x, ddof=1)) if len(x) > 1 else np.nan,

        "p25": float(np.quantile(x, 0.25)),

        "p75": float(np.quantile(x, 0.75)),

        "p90": float(np.quantile(x, 0.90)),

        "p95": float(np.quantile(x, 0.95)),

        "minimum": float(np.min(x)),

        "maximum": float(np.max(x)),

    }





def correlation_summary(x, y):

    temp = pd.DataFrame({"x": x, "y": y}).dropna()



    if len(temp) < 3:

        return {

            "n": len(temp),

            "pearson_r": np.nan,

            "pearson_p": np.nan,

            "spearman_rho": np.nan,

            "spearman_p": np.nan,

            "kendall_tau": np.nan,

            "kendall_p": np.nan,

        }



    pearson = stats.pearsonr(temp["x"], temp["y"])

    spearman = stats.spearmanr(temp["x"], temp["y"])

    kendall = stats.kendalltau(temp["x"], temp["y"])



    return {

        "n": len(temp),

        "pearson_r": float(pearson.statistic),

        "pearson_p": float(pearson.pvalue),

        "spearman_rho": float(spearman.statistic),

        "spearman_p": float(spearman.pvalue),

        "kendall_tau": float(kendall.statistic),

        "kendall_p": float(kendall.pvalue),

    }





def classify_direction(value, tolerance=0.0):

    if pd.isna(value):

        return "UNAVAILABLE"

    if value > tolerance:

        return "POSITIVE"

    if value < -tolerance:

        return "NEGATIVE"

    return "NEAR_ZERO"





def bool_to_text(value):

    return "True" if bool(value) else "False"





# =============================================================================

# 3. HEADER

# =============================================================================



log("=" * 78)

log("ROBUSTNESS AND SENSITIVITY ANALYSIS - ROAD INFRASTRUCTURE TENDERS")

log("=" * 78)

log("Purpose: Stress-test the principal conclusions developed in Scripts 03-17.")

log("")

log("IMPORTANT:")

log("- No primary model is redefined.")

log("- No validation result is used to retrospectively optimize prior choices.")

log("- Sensitivity analyses are prespecified from alternatives already developed.")

log("- Robustness is assessed conclusion by conclusion, not by a single omnibus score.")

log("")





# =============================================================================

# 4. VALIDATE INPUT FILES

# =============================================================================



log("[1] Validating analytical inputs...")



for path in [

    INPUT_MASTER,

    INPUT_SCENARIOS,

    INPUT_ROBUSTNESS_08,

    INPUT_MC,

    INPUT_DES,

    INPUT_VALIDATION,

]:

    require_file(path)





# =============================================================================

# 5. INSPECT WORKBOOK CONTRACTS

# =============================================================================



log("")

log("[2] Inspecting workbook contracts...")



scenario_sheets = pd.ExcelFile(INPUT_SCENARIOS).sheet_names

robustness08_sheets = pd.ExcelFile(INPUT_ROBUSTNESS_08).sheet_names

mc_sheets = pd.ExcelFile(INPUT_MC).sheet_names

des_sheets = pd.ExcelFile(INPUT_DES).sheet_names

validation_sheets = pd.ExcelFile(INPUT_VALIDATION).sheet_names



required_sheet_contract = {

    "Script 07": (

        scenario_sheets,

        ["procedure_audit"]

    ),

    "Script 08": (

        robustness08_sheets,

        ["robustness_summary"]

    ),

    "Script 14": (

        mc_sheets,

        ["primary_results"]

    ),

    "Script 16": (

        des_sheets,

        ["des_summary", "mc_vs_des"]

    ),

}



for label, (available, required) in required_sheet_contract.items():

    missing = [s for s in required if s not in available]

    if missing:

        raise ValueError(

            f"{label} workbook is missing required sheets: {missing}. "

            f"Available sheets: {available}"

        )

    log(f"  {label}: required sheets verified.")



log(

    f"  Script 17 workbook detected with "

    f"{len(validation_sheets)} sheet(s)."

)





# =============================================================================

# 6. READ DATA

# =============================================================================



log("")

log("[3] Reading analytical datasets...")



master = pd.read_excel(INPUT_MASTER)



scenario_audit = pd.read_excel(

    INPUT_SCENARIOS,

    sheet_name="procedure_audit"

)



scenario_robustness_08 = pd.read_excel(

    INPUT_ROBUSTNESS_08,

    sheet_name="robustness_summary"

)



mc_primary = pd.read_excel(

    INPUT_MC,

    sheet_name="primary_results"

)


mc_low_sensitivity_source = pd.read_excel(

    INPUT_MC,

    sheet_name="low_sensitivity"

)



des_summary = pd.read_excel(

    INPUT_DES,

    sheet_name="des_summary"

)



mc_vs_des = pd.read_excel(

    INPUT_DES,

    sheet_name="mc_vs_des"

)



log(f"  Master rows: {len(master)}")

log(f"  Scenario-audit rows: {len(scenario_audit)}")

log(f"  Script 08 robustness rows: {len(scenario_robustness_08)}")

log(f"  Monte Carlo primary rows: {len(mc_primary)}")

log(f"  DES summary rows: {len(des_summary)}")





# =============================================================================

# 7. VALIDATE CORE CONTRACT

# =============================================================================



log("")

log("[4] Validating analytical contract...")



if len(master) != EXPECTED_MASTER_N:

    raise ValueError(

        f"Expected master analytical sample n={EXPECTED_MASTER_N}, "

        f"found n={len(master)}."

    )



require_columns(

    master,

    [

        "procedure_code",

        "queries_observations_count",

        "total_award_time_days",

    ],

    "Master dataset"

)



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

    "Script 07 procedure_audit"

)



if master["procedure_code"].duplicated().any():

    raise ValueError("Duplicate procedure_code found in master dataset.")



if scenario_audit["procedure_code"].duplicated().any():

    raise ValueError("Duplicate procedure_code found in scenario audit.")



master["queries_observations_count"] = clean_numeric(

    master["queries_observations_count"]

)

master["total_award_time_days"] = clean_numeric(

    master["total_award_time_days"]

)



scenario_audit["queries_observations_count"] = clean_numeric(

    scenario_audit["queries_observations_count"]

)

scenario_audit["total_award_time_days"] = clean_numeric(

    scenario_audit["total_award_time_days"]

)



available_total = int(master["total_award_time_days"].notna().sum())



log(f"  Master analytical sample verified: {len(master)}")

log(f"  Available total award times: {available_total}/{len(master)}")

log("  procedure_code uniqueness verified.")





# =============================================================================

# 8. CONTINUOUS RELATIONSHIP ROBUSTNESS

# =============================================================================



log("")

log("[5] Evaluating robustness of the continuous relationship...")



relationship_records = []



full_rel = correlation_summary(

    master["queries_observations_count"],

    master["total_award_time_days"]

)



relationship_records.append({

    "analysis": "FULL_SAMPLE",

    "period": "2020-2025",

    **full_rel

})



log(

    f"  Full sample: n={full_rel['n']}; "

    f"Pearson={full_rel['pearson_r']:.4f}; "

    f"Spearman={full_rel['spearman_rho']:.4f}; "

    f"Kendall={full_rel['kendall_tau']:.4f}"

)



# Try to recover year using the same logic as prior scripts.

year_column = None



candidate_year_columns = [

    "notice_year",

    "year",

    "procurement_year",

    "convocation_year",

]



for candidate in candidate_year_columns:

    if candidate in master.columns:

        year_column = candidate

        break



if year_column is None:

    candidate_date_columns = [

        "notice_date",

        "procurement_notice_date",

        "convocation_date",

        "publication_date",

    ]



    for candidate in candidate_date_columns:

        if candidate in master.columns:

            parsed = pd.to_datetime(master[candidate], errors="coerce")

            if parsed.notna().sum() > 0:

                master["_derived_year"] = parsed.dt.year

                year_column = "_derived_year"

                break



if year_column is not None:

    master["_analysis_year"] = pd.to_numeric(

        master[year_column],

        errors="coerce"

    )



    temporal_subsets = [

        ("TRAIN_REFERENCE", "2020-2023", 2020, 2023),

        ("TEMPORAL_HOLDOUT", "2024-2025", 2024, 2025),

    ]



    for analysis_name, period_name, start_year, end_year in temporal_subsets:

        subset = master[

            master["_analysis_year"].between(

                start_year,

                end_year,

                inclusive="both"

            )

        ].copy()



        result = correlation_summary(

            subset["queries_observations_count"],

            subset["total_award_time_days"]

        )



        relationship_records.append({

            "analysis": analysis_name,

            "period": period_name,

            **result

        })



        log(

            f"  {period_name}: n={result['n']}; "

            f"Pearson={result['pearson_r']:.4f}; "

            f"Spearman={result['spearman_rho']:.4f}; "

            f"Kendall={result['kendall_tau']:.4f}"

        )

else:

    log(

        "  WARNING: Year could not be independently reconstructed from the "

        "master dataset. Temporal relationship robustness will rely on "

        "Script 17 evidence where available."

    )



relationship_df = pd.DataFrame(relationship_records)





# =============================================================================

# 9. SCENARIO-DEFINITION ROBUSTNESS

# =============================================================================



log("")

log("[6] Re-evaluating scenario-definition robustness...")



scenario_method_map = {

    "Terciles": "scenario_terciles",

    "P25_P75": "scenario_p25_p75",

    "Data_driven_1D": "scenario_data_driven",

}



scenario_summary_records = []

scenario_test_records = []

pairwise_records = []



for method_name, column in scenario_method_map.items():



    temp = scenario_audit[

        ["procedure_code", column, "total_award_time_days"]

    ].copy()



    temp = temp.dropna(

        subset=[column, "total_award_time_days"]

    )



    groups = {}



    for scenario in PRIMARY_SCENARIO_ORDER:

        values = temp.loc[

            temp[column] == scenario,

            "total_award_time_days"

        ].astype(float).values



        groups[scenario] = values



        desc = descriptive_summary(values)



        scenario_summary_records.append({

            "method": method_name,

            "scenario": scenario,

            **desc

        })



    valid_groups = [

        groups[s]

        for s in PRIMARY_SCENARIO_ORDER

        if len(groups[s]) > 0

    ]



    if len(valid_groups) == 3:

        kw = stats.kruskal(*valid_groups)

        total_n = sum(len(g) for g in valid_groups)



        medians = [

            np.median(groups[s])

            for s in PRIMARY_SCENARIO_ORDER

        ]



        strict_order = bool(

            medians[0] < medians[1] < medians[2]

        )



        eps2 = epsilon_squared_kruskal(

            kw.statistic,

            total_n,

            3

        )



        scenario_test_records.append({

            "method": method_name,

            "low_median": medians[0],

            "medium_median": medians[1],

            "high_median": medians[2],

            "strictly_increasing_medians": strict_order,

            "kruskal_h": float(kw.statistic),

            "kruskal_p": float(kw.pvalue),

            "epsilon_squared": eps2,

            "minimum_group_n": min(len(g) for g in valid_groups),

        })



        log(

            f"  {method_name}: "

            f"medians={medians[0]:.2f}/{medians[1]:.2f}/{medians[2]:.2f}; "

            f"ordered={strict_order}; "

            f"KW p={kw.pvalue:.6g}; "

            f"epsilon²={eps2:.4f}"

        )



        comparisons = [

            ("Low", "Medium"),

            ("Low", "High"),

            ("Medium", "High"),

        ]



        raw_pairwise = []



        for a, b in comparisons:

            x = groups[a]

            y = groups[b]



            test = stats.mannwhitneyu(

                x,

                y,

                alternative="two-sided"

            )



            raw_pairwise.append({

                "method": method_name,

                "comparison": f"{a} vs {b}",

                "group_a": a,

                "group_b": b,

                "n_a": len(x),

                "n_b": len(y),

                "median_a": float(np.median(x)),

                "median_b": float(np.median(y)),

                "u_statistic": float(test.statistic),

                "raw_p": float(test.pvalue),

                "rank_biserial": rank_biserial_from_u(

                    test.statistic,

                    len(x),

                    len(y)

                ),

            })



        # Holm correction implemented directly.

        pvals = np.array(

            [r["raw_p"] for r in raw_pairwise],

            dtype=float

        )



        order = np.argsort(pvals)

        adjusted = np.empty_like(pvals)



        running_max = 0.0

        m = len(pvals)



        for rank_position, original_index in enumerate(order):

            multiplier = m - rank_position

            candidate = min(

                1.0,

                multiplier * pvals[original_index]

            )

            running_max = max(running_max, candidate)

            adjusted[original_index] = running_max



        for i, record in enumerate(raw_pairwise):

            record["holm_p"] = float(adjusted[i])

            record["holm_significant_0_05"] = bool(

                adjusted[i] < 0.05

            )

            pairwise_records.append(record)



scenario_summary_df = pd.DataFrame(scenario_summary_records)

scenario_tests_df = pd.DataFrame(scenario_test_records)

pairwise_df = pd.DataFrame(pairwise_records)





# =============================================================================

# 10. CROSS-METHOD ASSIGNMENT ROBUSTNESS

# =============================================================================



log("")

log("[7] Auditing cross-method scenario assignment robustness...")



assignment_records = []



method_pairs = [

    (

        "Terciles",

        "P25_P75",

        "scenario_terciles",

        "scenario_p25_p75"

    ),

    (

        "Terciles",

        "Data_driven_1D",

        "scenario_terciles",

        "scenario_data_driven"

    ),

    (

        "P25_P75",

        "Data_driven_1D",

        "scenario_p25_p75",

        "scenario_data_driven"

    ),

]



for method_a, method_b, col_a, col_b in method_pairs:



    valid = scenario_audit[[col_a, col_b]].dropna()



    agreement = float(

        (valid[col_a] == valid[col_b]).mean()

    )



    assignment_records.append({

        "method_a": method_a,

        "method_b": method_b,

        "n_compared": len(valid),

        "assignment_agreement": agreement,

    })



    log(

        f"  {method_a} vs {method_b}: "

        f"{agreement:.2%} same assignments"

    )



assignment_df = pd.DataFrame(assignment_records)





# =============================================================================

# 11. MONTE CARLO REPRESENTATION SENSITIVITY

# =============================================================================



log("")

log("[8] Evaluating Monte Carlo representation sensitivity...")



# Script 14 already contains the prespecified Low-scenario sensitivity analysis.
# Reuse that interface directly instead of reconstructing alternative models
# from primary_results.
require_columns(

    mc_low_sensitivity_source,

    ["metric", "low_empirical_value", "low_lognormal_value",
     "absolute_difference", "relative_difference", "scientific_role"],

    "Script 14 low_sensitivity"

)



mc_sensitivity_df = mc_low_sensitivity_source.copy()

mc_sensitivity_df.insert(0, "scenario", "Low")

mc_sensitivity_df["primary_representation"] = "Empirical/nonparametric"

mc_sensitivity_df["sensitivity_representation"] = "Lognormal"



# Preserve Script 14 values exactly. No new percentage cutoff is introduced.
for _, row in mc_sensitivity_df.iterrows():

    metric = str(row["metric"])
    empirical_value = safe_float(row["low_empirical_value"])
    lognormal_value = safe_float(row["low_lognormal_value"])
    absolute_difference = safe_float(row["absolute_difference"])
    relative_difference = safe_float(row["relative_difference"])

    if metric == "exceedance_probability":
        log(
            f"  Low {metric}: empirical={empirical_value:.5f}; "
            f"Lognormal={lognormal_value:.5f}; "
            f"difference={absolute_difference:+.5f}; "
            f"relative={relative_difference:+.2%}"
        )
    else:
        log(
            f"  Low {metric}: empirical={empirical_value:.2f}; "
            f"Lognormal={lognormal_value:.2f}; "
            f"difference={absolute_difference:+.2f}; "
            f"relative={relative_difference:+.2%}"
        )

log(
    "  Interpretation: Low-scenario summaries vary across the empirical and "
    "Lognormal representations; empirical/nonparametric remains primary."
)



# =============================================================================

# 12. DIRECT MONTE CARLO VS DES SENSITIVITY

# =============================================================================



log("")

log("[9] Evaluating direct Monte Carlo vs DES sensitivity...")



require_columns(

    mc_vs_des,

    ["scenario"],

    "Script 16 mc_vs_des"

)



mc_des_records = []



for _, row in mc_vs_des.iterrows():



    scenario = str(row["scenario"])



    record = {

        "scenario": scenario

    }



    direct_pairs = [

        ("mean", "mc_mean", "des_mean"),

        ("median", "mc_median", "des_median"),

        ("p95", "mc_p95", "des_p95"),

    ]



    for metric, mc_col, des_col in direct_pairs:



        if mc_col in mc_vs_des.columns and des_col in mc_vs_des.columns:

            mc_value = safe_float(row[mc_col])

            des_value = safe_float(row[des_col])



            record[f"mc_{metric}"] = mc_value

            record[f"des_{metric}"] = des_value

            record[f"des_minus_mc_{metric}"] = (

                des_value - mc_value

                if np.isfinite(mc_value)

                and np.isfinite(des_value)

                else np.nan

            )



            record[f"absolute_difference_{metric}"] = (

                abs(des_value - mc_value)

                if np.isfinite(mc_value)

                and np.isfinite(des_value)

                else np.nan

            )



            record[f"relative_difference_{metric}"] = (

                abs(des_value - mc_value) / abs(mc_value)

                if np.isfinite(mc_value)

                and np.isfinite(des_value)

                and mc_value != 0

                else np.nan

            )



    mc_des_records.append(record)



mc_des_df = pd.DataFrame(mc_des_records)



if not mc_des_df.empty:

    mc_des_df["_order"] = mc_des_df["scenario"].map(

        lambda x: scenario_sort_key(str(x))

    )

    mc_des_df = (

        mc_des_df

        .sort_values("_order")

        .drop(columns="_order")

        .reset_index(drop=True)

    )



    for _, row in mc_des_df.iterrows():

        scenario = row["scenario"]



        median_diff = row.get(

            "des_minus_mc_median",

            np.nan

        )



        p95_diff = row.get(

            "des_minus_mc_p95",

            np.nan

        )



        log(

            f"  {scenario}: "

            f"DES-MC median difference={median_diff:+.2f} days; "

            f"DES-MC P95 difference={p95_diff:+.2f} days"

        )





# =============================================================================

# 13. DES DEPENDENCE-SPECIFICATION SENSITIVITY

# =============================================================================



log("")

log("[10] Evaluating DES dependence-specification sensitivity...")



des_sensitivity_records = []



if "independence_sensitivity" in des_sheets:



    independence_df = pd.read_excel(

        INPUT_DES,

        sheet_name="independence_sensitivity"

    )



    for _, row in independence_df.iterrows():



        scenario = str(row.get("scenario", ""))



        record = {

            "scenario": scenario,

            "scientific_role": row.get(

                "scientific_role",

                "SENSITIVITY_ONLY"

            ),

        }



        metric_pairs = [

            (

                "median",

                "primary_joint_median",

                "independent_median"

            ),

            (

                "sd",

                "primary_joint_sd",

                "independent_sd"

            ),

            (

                "p95",

                "primary_joint_p95",

                "independent_p95"

            ),

        ]



        for metric, joint_col, independent_col in metric_pairs:



            if (

                joint_col in independence_df.columns

                and independent_col in independence_df.columns

            ):

                joint_value = safe_float(row[joint_col])

                independent_value = safe_float(

                    row[independent_col]

                )



                record[f"joint_{metric}"] = joint_value

                record[f"independent_{metric}"] = independent_value



                record[

                    f"independent_minus_joint_{metric}"

                ] = (

                    independent_value - joint_value

                    if np.isfinite(joint_value)

                    and np.isfinite(independent_value)

                    else np.nan

                )



        des_sensitivity_records.append(record)



    log(

        f"  Independence counterfactual rows evaluated: "

        f"{len(des_sensitivity_records)}"

    )



else:

    log(

        "  WARNING: independence_sensitivity sheet not found in Script 16."

    )



des_sensitivity_df = pd.DataFrame(

    des_sensitivity_records

)





# =============================================================================

# 14. TEMPORAL ROBUSTNESS FROM SCRIPT 17

# =============================================================================



log("")

log("[11] Recovering temporal-validation robustness evidence...")



validation_evidence_records = []



# We deliberately inspect known possible sheets rather than assuming one

# fixed interface.

for sheet in validation_sheets:



    try:

        df = pd.read_excel(

            INPUT_VALIDATION,

            sheet_name=sheet

        )

    except Exception:

        continue



    lower_columns = {

        c.lower(): c

        for c in df.columns

    }



    # Capture validation decision framework if available.

    if (

        "status" in lower_columns

        and (

            "criterion" in lower_columns

            or "component" in lower_columns

        )

    ):

        label_col = (

            lower_columns.get("criterion")

            or lower_columns.get("component")

        )



        status_col = lower_columns["status"]



        for _, row in df.iterrows():

            validation_evidence_records.append({

                "source_sheet": sheet,

                "dimension": row.get(label_col),

                "status": row.get(status_col),

                "observed_result": row.get(

                    lower_columns.get(

                        "observed_result",

                        ""

                    ),

                    np.nan

                )

                if lower_columns.get("observed_result")

                else np.nan,

            })



validation_evidence_df = pd.DataFrame(

    validation_evidence_records

)



log(

    f"  Script 17 sheets inspected: {len(validation_sheets)}"

)



if len(validation_evidence_df) > 0:

    log(

        f"  Structured validation decision records recovered: "

        f"{len(validation_evidence_df)}"

    )

else:

    log(

        "  Structured decision records were not required for the core "

        "robustness calculations; temporal results remain represented "

        "through independently reconstructed subsets where available."

    )





# =============================================================================

# 15. BUILD CONCLUSION-LEVEL ROBUSTNESS FRAMEWORK

# =============================================================================



log("")

log("[12] Building conclusion-level robustness framework...")



conclusion_records = []



# -------------------------------------------------------------------------

# Conclusion 1:

# Positive continuous relationship

# -------------------------------------------------------------------------



available_rhos = relationship_df[

    "spearman_rho"

].dropna()



positive_rhos = (

    available_rhos > 0

).all() if len(available_rhos) > 0 else False



significant_rhos = (

    relationship_df

    .dropna(subset=["spearman_p"])["spearman_p"] < 0.05

).all() if relationship_df["spearman_p"].notna().sum() > 0 else False



if positive_rhos and significant_rhos:

    status_relationship = "ROBUST"

elif positive_rhos:

    status_relationship = "PARTIALLY_ROBUST"

else:

    status_relationship = "SENSITIVE"



conclusion_records.append({

    "conclusion_id": "C1",

    "scientific_conclusion":

        "Higher query/observation counts are associated with longer "

        "award times.",

    "primary_evidence":

        f"Full-sample Spearman rho={full_rel['spearman_rho']:.4f}",

    "sensitivity_dimension":

        "Correlation estimator and temporal subset",

    "robustness_status":

        status_relationship,

    "authorized_interpretation":

        "Association direction is evaluated for stability; no causal "

        "effect is inferred.",

})





# -------------------------------------------------------------------------

# Conclusion 2:

# Scenario structure

# -------------------------------------------------------------------------



scenario_tests_available = scenario_tests_df.copy()



quantile_methods = scenario_tests_available[

    scenario_tests_available["method"].isin(

        ["Terciles", "P25_P75"]

    )

]



quantile_order = (

    quantile_methods["strictly_increasing_medians"].all()

    if len(quantile_methods) > 0

    else False

)



quantile_kw = (

    (quantile_methods["kruskal_p"] < 0.05).all()

    if len(quantile_methods) > 0

    else False

)



data_driven_row = scenario_tests_available[

    scenario_tests_available["method"] == "Data_driven_1D"

]



data_driven_small = False



if len(data_driven_row) > 0:

    data_driven_small = bool(

        data_driven_row.iloc[0]["minimum_group_n"] < 20

    )



if quantile_order and quantile_kw:

    status_scenarios = "ROBUST_WITH_SENSITIVITY"

else:

    status_scenarios = "SENSITIVE"



conclusion_records.append({

    "conclusion_id": "C2",

    "scientific_conclusion":

        "Award-time distributions differ across Low, Medium, and High "

        "query/observation scenarios.",

    "primary_evidence":

        "Primary tercile structure from Scripts 07-08",

    "sensitivity_dimension":

        "Terciles, P25/P75, and data-driven partition",

    "robustness_status":

        status_scenarios,

    "authorized_interpretation":

        "Quantile-based scenario conclusions may be considered more "

        "stable than the small high-group data-driven partition."

})





# -------------------------------------------------------------------------

# Conclusion 3:

# Low representation

# -------------------------------------------------------------------------



if len(mc_sensitivity_df) > 0:

    # Diagnose representation sensitivity across substantive distributional
    # dimensions without introducing a retrospective percentage threshold.
    finite_sensitivity = mc_sensitivity_df.copy()
    finite_sensitivity["relative_difference"] = pd.to_numeric(
        finite_sensitivity["relative_difference"], errors="coerce"
    )

    changed_metrics = finite_sensitivity.loc[
        finite_sensitivity["relative_difference"].notna()
        & (finite_sensitivity["relative_difference"].abs() > 0),
        "metric"
    ].astype(str).tolist()

    key_dimensions = {
        "median": "location",
        "std": "dispersion",
        "p90": "tail",
        "p95": "tail",
        "p99": "extreme_tail",
        "exceedance_probability": "exceedance",
    }
    changed_dimensions = {
        key_dimensions[m] for m in changed_metrics if m in key_dimensions
    }

    if len(changed_dimensions) >= 2:
        status_low = "SENSITIVE_TO_REPRESENTATION"
    else:
        status_low = "LIMITED_REPRESENTATION_SENSITIVITY"

else:
    status_low = "DATA_INTERFACE_LIMITED"



conclusion_records.append({

    "conclusion_id": "C3",

    "scientific_conclusion":

        "Low-scenario stochastic summaries depend on the representation "

        "used for its nonstandard empirical distribution.",

    "primary_evidence":

        "Script 14 low_sensitivity: empirical/nonparametric Low is primary; Lognormal is sensitivity only.",

    "sensitivity_dimension":

        "Empirical Low vs Lognormal Low sensitivity",

    "robustness_status":

        status_low,

    "authorized_interpretation":

        "Sensitivity is present across location, dispersion, tail, and/or exceedance summaries. Low Lognormal remains sensitivity only and cannot replace the primary empirical representation."

})





# -------------------------------------------------------------------------

# Conclusion 4:

# MC vs DES

# -------------------------------------------------------------------------



if len(mc_des_df) > 0:



    median_relative_cols = [

        c

        for c in mc_des_df.columns

        if c == "relative_difference_median"

    ]



    if median_relative_cols:

        median_rel = mc_des_df[

            median_relative_cols[0]

        ].dropna()



        max_median_rel = (

            float(median_rel.max())

            if len(median_rel) > 0

            else np.nan

        )

    else:

        max_median_rel = np.nan



    status_mc_des = "MODEL_ARCHITECTURE_SENSITIVE"



else:

    max_median_rel = np.nan

    status_mc_des = "DATA_INTERFACE_LIMITED"



conclusion_records.append({

    "conclusion_id": "C4",

    "scientific_conclusion":

        "Direct total-duration Monte Carlo and two-stage DES provide "

        "complementary rather than identical stochastic summaries.",

    "primary_evidence":

        "Direct Monte Carlo remains primary; DES remains secondary.",

    "sensitivity_dimension":

        "Direct duration simulation vs two-stage process decomposition",

    "robustness_status":

        status_mc_des,

    "authorized_interpretation":

        "Differences between MC and DES reflect model architecture and "

        "stage-complete sample coverage; they are not automatically "

        "model failures."

})





# -------------------------------------------------------------------------

# Conclusion 5:

# DES dependence

# -------------------------------------------------------------------------



if len(des_sensitivity_df) > 0:

    p95_diff_col = "independent_minus_joint_p95"



    if p95_diff_col in des_sensitivity_df.columns:

        max_abs_p95_dep = float(

            des_sensitivity_df[

                p95_diff_col

            ].abs().max()

        )



        if max_abs_p95_dep >= 10:

            status_dependence = "SENSITIVE_TO_DEPENDENCE_ASSUMPTION"

        else:

            status_dependence = "LIMITED_SENSITIVITY"

    else:

        max_abs_p95_dep = np.nan

        status_dependence = "EVALUATED"

else:

    max_abs_p95_dep = np.nan

    status_dependence = "DATA_INTERFACE_LIMITED"



conclusion_records.append({

    "conclusion_id": "C5",

    "scientific_conclusion":

        "Preserving dependence between query/integration and "

        "evaluation/award stages matters for DES tail behavior.",

    "primary_evidence":

        "Joint empirical stage-pair resampling is the primary DES.",

    "sensitivity_dimension":

        "Joint resampling vs independence counterfactual",

    "robustness_status":

        status_dependence,

    "authorized_interpretation":

        "Independent stage sampling remains a counterfactual sensitivity "

        "analysis, not the primary DES."

})





# -------------------------------------------------------------------------

# Conclusion 6:

# Temporal transportability

# -------------------------------------------------------------------------



holdout_row = relationship_df[

    relationship_df["analysis"] == "TEMPORAL_HOLDOUT"

]



if len(holdout_row) > 0:



    holdout_rho = safe_float(

        holdout_row.iloc[0]["spearman_rho"]

    )



    holdout_p = safe_float(

        holdout_row.iloc[0]["spearman_p"]

    )



    if (

        np.isfinite(holdout_rho)

        and holdout_rho > 0

        and np.isfinite(holdout_p)

        and holdout_p < 0.05

    ):

        status_temporal = "ROBUST_DIRECTIONALLY"

    elif np.isfinite(holdout_rho) and holdout_rho > 0:

        status_temporal = "PARTIALLY_ROBUST"

    else:

        status_temporal = "SENSITIVE"



    temporal_evidence = (

        f"2024-2025 Spearman rho={holdout_rho:.4f}; "

        f"p={holdout_p:.6g}"

    )



else:

    status_temporal = "REFER_TO_SCRIPT_17"

    temporal_evidence = (

        "Temporal transportability evaluated in Script 17."

    )



conclusion_records.append({

    "conclusion_id": "C6",

    "scientific_conclusion":

        "The positive continuous relationship is transportable in "

        "direction to the later temporal period.",

    "primary_evidence":

        temporal_evidence,

    "sensitivity_dimension":

        "2020-2023 vs 2024-2025",

    "robustness_status":

        status_temporal,

    "authorized_interpretation":

        "Temporal persistence supports transportability of association, "

        "not causality or invariant predictive calibration."

})



conclusion_df = pd.DataFrame(conclusion_records)





# =============================================================================

# 16. BUILD ROBUSTNESS MATRIX

# =============================================================================



log("")

log("[13] Building robustness matrix...")



robustness_matrix_records = []



for _, row in conclusion_df.iterrows():



    status = str(row["robustness_status"])



    if status.startswith("ROBUST"):

        evidence_strength = "STRONG"

    elif (

        "PARTIALLY" in status

        or "WITH_SENSITIVITY" in status

        or "LIMITED" in status

    ):

        evidence_strength = "MODERATE"

    elif "SENSITIVE" in status:

        evidence_strength = "CONDITIONAL"

    else:

        evidence_strength = "REQUIRES_CONTEXT"



    robustness_matrix_records.append({

        "conclusion_id": row["conclusion_id"],

        "conclusion": row["scientific_conclusion"],

        "sensitivity_dimension": row["sensitivity_dimension"],

        "robustness_status": status,

        "evidence_strength_descriptor": evidence_strength,

        "interpretation_boundary":

            row["authorized_interpretation"],

    })



robustness_matrix_df = pd.DataFrame(

    robustness_matrix_records

)



for _, row in robustness_matrix_df.iterrows():

    log(

        f"  {row['conclusion_id']} | "

        f"{row['robustness_status']} | "

        f"{row['evidence_strength_descriptor']}"

    )





# =============================================================================

# 17. OBJECTIVE-LEVEL SCIENTIFIC SYNTHESIS

# =============================================================================



log("")

log("[14] Building objective-level scientific synthesis...")



objective_records = [

    {

        "objective": "Objective 1",

        "component":

            "Identification of eligible road-infrastructure tenders",

        "status": "COMPLETED_PREVIOUSLY",

        "robustness_role":

            "Master analytical population retained at n=137.",

        "scientific_note":

            "Script 18 does not redefine eligibility criteria or the "

            "master analytical population.",

    },

    {

        "objective": "Objective 2",

        "component":

            "Low/Medium/High classification by query/observation volume",

        "status": "SUPPORTED_WITH_ROBUSTNESS_EVIDENCE",

        "robustness_role":

            "Primary terciles compared against P25/P75 and data-driven "

            "alternatives.",

        "scientific_note":

            "Primary terciles remain locked; alternative definitions are "

            "sensitivity analyses.",

    },

    {

        "objective": "Objective 3",

        "component":

            "Stochastic modeling through Monte Carlo and DES",

        "status": "COMPLETED_WITH_MODEL_SPECIFIC_LIMITATIONS",

        "robustness_role":

            "Representation and architecture sensitivity evaluated.",

        "scientific_note":

            "Monte Carlo remains the primary stochastic reference; DES "

            "remains a secondary process-decomposition model.",

    },

    {

        "objective": "Objective 4",

        "component":

            "Validation of stochastic results",

        "status": "VALIDATION_AND_ROBUSTNESS_EVALUATED",

        "robustness_role":

            "Script 17 temporal validation is complemented by Script 18 "

            "sensitivity analysis.",

        "scientific_note":

            "Validation does not require every model component to reproduce "

            "every holdout statistic exactly.",

    },

]



objective_df = pd.DataFrame(objective_records)



for _, row in objective_df.iterrows():

    log(

        f"  {row['objective']}: {row['status']}"

    )





# =============================================================================

# 18. LIMITATIONS

# =============================================================================



log("")

log("[15] Recording robustness-analysis limitations...")



limitations_records = [

    {

        "limitation":

            "Master analytical population size",

        "observed_result":

            "n=137 procedures; 136 with total award time.",

        "implication":

            "Sensitivity analysis evaluates stability within the observed "

            "analytical population; it does not create new independent "

            "evidence."

    },

    {

        "limitation":

            "Stage-level coverage",

        "observed_result":

            "DES uses only procedures with complete stage decomposition.",

        "implication":

            "DES robustness cannot be generalized as strongly as the "

            "direct total-duration model."

    },

    {

        "limitation":

            "Low-scenario probability representation",

        "observed_result":

            "A sole Lognormal model was previously rejected as the primary "

            "Low representation.",

        "implication":

            "Low stochastic conclusions must retain empirical/nonparametric "

            "results as primary."

    },

    {

        "limitation":

            "Temporal predictive calibration",

        "observed_result":

            "Script 17 identified nonuniform predictive performance across "

            "scenarios.",

        "implication":

            "Transportability of association does not imply identical "

            "predictive calibration across periods."

    },

    {

        "limitation":

            "Observational research design",

        "observed_result":

            "No randomized assignment or exogenous intervention.",

        "implication":

            "Robust association remains distinct from causal identification."

    },

    {

        "limitation":

            "Scenario categorization",

        "observed_result":

            "Low/Medium/High categories discretize an underlying continuous "

            "query/observation count.",

        "implication":

            "Continuous-variable results remain an essential reference."

    },

    {

        "limitation":

            "Simulation size",

        "observed_result":

            "Simulation iterations improve numerical precision but do not "

            "increase the number of observed tenders.",

        "implication":

            "50,000 simulated draws/entities must not be interpreted as "

            "50,000 independent empirical procedures."

    },

]



limitations_df = pd.DataFrame(limitations_records)



log(f"  Recorded limitations: {len(limitations_df)}")





# =============================================================================

# 19. SCIENTIFIC INTERPRETATION AUDIT

# =============================================================================



log("")

log("[16] Building scientific interpretation audit...")



interpretation_records = [

    {

        "issue": "Robustness",

        "authorized_interpretation":

            "A conclusion is robust when its substantive direction or "

            "structure persists across prespecified reasonable alternatives.",

        "not_authorized":

            "Robustness is not proof that the model is universally true."

    },

    {

        "issue": "Sensitivity",

        "authorized_interpretation":

            "Sensitivity identifies conclusions that depend materially on "

            "representation, thresholds, dependence assumptions, or sample "

            "coverage.",

        "not_authorized":

            "A sensitive result is not automatically invalid."

    },

    {

        "issue": "Scenario alternatives",

        "authorized_interpretation":

            "P25/P75 and data-driven partitions test sensitivity to the "

            "primary tercile definition.",

        "not_authorized":

            "Alternative scenarios do not replace the locked primary "

            "terciles after outcomes are observed."

    },

    {

        "issue": "Low distribution",

        "authorized_interpretation":

            "Empirical resampling remains the primary robust representation "

            "for Low.",

        "not_authorized":

            "Low Lognormal cannot be promoted to primary merely because it "

            "produces convenient simulation behavior."

    },

    {

        "issue": "Monte Carlo vs DES",

        "authorized_interpretation":

            "The models answer related but nonidentical stochastic questions.",

        "not_authorized":

            "Different numerical outputs do not by themselves establish "

            "that one model is erroneous."

    },

    {

        "issue": "Temporal validation",

        "authorized_interpretation":

            "Later-period evidence evaluates transportability and predictive "

            "behavior.",

        "not_authorized":

            "A nonsignificant or imperfect holdout result must not be "

            "retrofitted away."

    },

    {

        "issue": "Causality",

        "authorized_interpretation":

            "Queries/observations are associated with temporal uncertainty "

            "and scenario differences.",

        "not_authorized":

            "The observational pipeline does not establish that additional "

            "queries causally create additional award time."

    },

]



interpretation_df = pd.DataFrame(

    interpretation_records

)



log("  Interpretation boundaries recorded.")





# =============================================================================

# 20. REPRODUCIBILITY METADATA

# =============================================================================



log("")

log("[17] Building reproducibility metadata...")



metadata_records = [

    {

        "item": "script",

        "value": SCRIPT_NAME

    },

    {

        "item": "execution_timestamp",

        "value": datetime.now().isoformat(timespec="seconds")

    },

    {

        "item": "random_seed",

        "value": RANDOM_SEED

    },

    {

        "item": "master_expected_n",

        "value": EXPECTED_MASTER_N

    },

    {

        "item": "master_observed_n",

        "value": len(master)

    },

    {

        "item": "available_total_award_times",

        "value": available_total

    },

    {

        "item": "primary_scenario_definition",

        "value": "Terciles"

    },

    {

        "item": "robustness_scenario_definition",

        "value": "P25/P75"

    },

    {

        "item": "sensitivity_scenario_definition",

        "value": "Data-driven 1D"

    },

    {

        "item": "primary_stochastic_reference",

        "value": "Direct total-duration Monte Carlo"

    },

    {

        "item": "secondary_process_model",

        "value": "Two-stage discrete-event simulation"

    },

    {

        "item": "retrospective_model_optimization",

        "value": "NOT_PERFORMED"

    },

    {

        "item": "missing_value_imputation",

        "value": "NOT_PERFORMED"

    },

    {

        "item": "causal_interpretation",

        "value": "NOT_AUTHORIZED"

    },

]



metadata_df = pd.DataFrame(metadata_records)





# =============================================================================

# 21. SAVE OUTPUTS

# =============================================================================



log("")

log("[18] Saving reproducible robustness outputs...")



with pd.ExcelWriter(

    OUTPUT_FILE,

    engine="openpyxl"

) as writer:



    relationship_df.to_excel(

        writer,

        sheet_name="relationship_robustness",

        index=False

    )



    scenario_summary_df.to_excel(

        writer,

        sheet_name="scenario_descriptives",

        index=False

    )



    scenario_tests_df.to_excel(

        writer,

        sheet_name="scenario_tests",

        index=False

    )



    pairwise_df.to_excel(

        writer,

        sheet_name="scenario_pairwise",

        index=False

    )



    assignment_df.to_excel(

        writer,

        sheet_name="assignment_robustness",

        index=False

    )



    mc_sensitivity_df.to_excel(

        writer,

        sheet_name="mc_low_sensitivity",

        index=False

    )



    mc_des_df.to_excel(

        writer,

        sheet_name="mc_vs_des_sensitivity",

        index=False

    )



    des_sensitivity_df.to_excel(

        writer,

        sheet_name="des_dependence_sensitivity",

        index=False

    )



    validation_evidence_df.to_excel(

        writer,

        sheet_name="validation_evidence",

        index=False

    )



    conclusion_df.to_excel(

        writer,

        sheet_name="conclusion_robustness",

        index=False

    )



    robustness_matrix_df.to_excel(

        writer,

        sheet_name="robustness_matrix",

        index=False

    )



    objective_df.to_excel(

        writer,

        sheet_name="objective_synthesis",

        index=False

    )



    limitations_df.to_excel(

        writer,

        sheet_name="limitations",

        index=False

    )



    interpretation_df.to_excel(

        writer,

        sheet_name="interpretation_audit",

        index=False

    )



    metadata_df.to_excel(

        writer,

        sheet_name="reproducibility",

        index=False

    )



log(f"  Output workbook: {OUTPUT_FILE.name}")

log(f"  Log file: {LOG_FILE.name}")





# =============================================================================

# 22. FINAL AUDIT

# =============================================================================



log("")

log("=" * 78)

log("ROBUSTNESS AND SENSITIVITY ANALYSIS AUDIT")

log("=" * 78)



log(

    f"Master analytical procedures:          {len(master)}"

)

log(

    f"Available total award times:           "

    f"{available_total}/{len(master)}"

)



log("")

log("CONTINUOUS RELATIONSHIP")

log("-" * 78)



for _, row in relationship_df.iterrows():



    log(

        f"{row['period']:<12} | "

        f"n={int(row['n']):<3} | "

        f"Pearson={row['pearson_r']:.4f} | "

        f"Spearman={row['spearman_rho']:.4f} | "

        f"Kendall={row['kendall_tau']:.4f}"

    )



log("")

log("SCENARIO-DEFINITION ROBUSTNESS")

log("-" * 78)



for _, row in scenario_tests_df.iterrows():



    log(

        f"{row['method']:<16} | "

        f"medians="

        f"{row['low_median']:.2f}/"

        f"{row['medium_median']:.2f}/"

        f"{row['high_median']:.2f} | "

        f"ordered={bool_to_text(row['strictly_increasing_medians']):<5} | "

        f"KW p={row['kruskal_p']:.3g} | "

        f"min n={int(row['minimum_group_n'])}"

    )



log("")

log("CONCLUSION-LEVEL ROBUSTNESS")

log("-" * 78)



for _, row in robustness_matrix_df.iterrows():



    log(

        f"{row['conclusion_id']:<4} "

        f"{row['robustness_status']:<35} "

        f"{row['evidence_strength_descriptor']}"

    )



log("")

log("SCIENTIFIC INTERPRETATION")

log("-" * 78)

log(

    "- Robustness is evaluated across prespecified reasonable analytical "

    "alternatives."

)

log(

    "- Primary tercile thresholds are not redefined."

)

log(

    "- P25/P75 remains a robustness specification."

)

log(

    "- Data-driven 1D partition remains sensitivity only."

)

log(

    "- Low empirical/nonparametric representation remains primary."

)

log(

    "- Low Lognormal remains parametric sensitivity only."

)

log(

    "- Direct total-duration Monte Carlo remains the primary stochastic "

    "reference."

)

log(

    "- Two-stage DES remains a secondary process-decomposition model."

)

log(

    "- Independent DES stage sampling remains counterfactual sensitivity "

    "only."

)

log(

    "- Script 17 temporal validation results are not altered or optimized "

    "away."

)

log(

    "- Simulation iterations do not create additional independent tenders."

)

log(

    "- No observations are deleted because of unfavorable results."

)

log(

    "- No missing temporal values are imputed."

)

log(

    "- No probability family is re-selected after validation."

)

log(

    "- No causal interpretation is imposed."

)



log("")

log("=" * 78)

log(

    "PIPELINE STATUS: "

    "ROBUSTNESS_ANALYSIS_COMPLETE_READY_FOR_FINAL_SYNTHESIS"

)

log("=" * 78)
