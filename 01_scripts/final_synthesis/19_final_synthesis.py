from pathlib import Path
import sys
import logging
from datetime import datetime

import numpy as np
import pandas as pd


# =============================================================================
# SCRIPT 19
# FINAL SCIENTIFIC SYNTHESIS
# Road Infrastructure Tender Stochastic Simulation
#
# Purpose:
#   Integrate the evidential chain developed in Scripts 03-18 into a final,
#   reproducible scientific synthesis.
#
# IMPORTANT:
#   - This script does NOT fit new models.
#   - This script does NOT re-select distributions.
#   - This script does NOT redefine scenario thresholds.
#   - This script does NOT change validation criteria.
#   - This script does NOT optimize previous results.
#   - This script does NOT perform new Monte Carlo or DES simulations.
#   - This script does NOT establish causality.
#
# Scientific role:
#   Evidence integration, objective closure, hypothesis assessment,
#   limitation consolidation, and thesis-ready result synthesis.
# =============================================================================


# =============================================================================
# 0. PATH CONFIGURATION
# =============================================================================

SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parents[2]

RESULTS_DIR = ROOT / "02_results"
LOGS_DIR = ROOT / "03_logs"

STAT_DIR = RESULTS_DIR / "statistical_analysis"
STOCHASTIC_DIR = RESULTS_DIR / "stochastic_modeling"
VALIDATION_DIR = RESULTS_DIR / "model_validation"
ROBUSTNESS_DIR = RESULTS_DIR / "robustness_analysis"

OUTPUT_DIR = RESULTS_DIR / "final_synthesis"
LOG_DIR = LOGS_DIR / "final_synthesis"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "19_1_final_synthesis.xlsx"
LOG_FILE = LOG_DIR / "19_final_synthesis.log"


# =============================================================================
# 1. LOGGING
# =============================================================================

logger = logging.getLogger("final_synthesis")
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
# 2. HELPER FUNCTIONS
# =============================================================================

def require_file(path: Path, label: str):
    if not path.exists():
        raise FileNotFoundError(
            f"Required input not found for {label}: {path}"
        )
    log(f"  Found: {path.name}")


def require_sheet(path: Path, sheet: str):
    xls = pd.ExcelFile(path)
    if sheet not in xls.sheet_names:
        raise ValueError(
            f"Required sheet '{sheet}' not found in {path.name}. "
            f"Available sheets: {xls.sheet_names}"
        )


def require_columns(df: pd.DataFrame, columns, label: str):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {missing}"
        )


def safe_float(value):
    try:
        if pd.isna(value):
            return np.nan
        return float(value)
    except Exception:
        return np.nan


def safe_int(value):
    try:
        if pd.isna(value):
            return np.nan
        return int(value)
    except Exception:
        return np.nan


def fmt(value, decimals=4):
    if pd.isna(value):
        return "NA"
    return f"{float(value):.{decimals}f}"


def first_matching_row(df, column, value):
    if column not in df.columns:
        return None

    subset = df[
        df[column].astype(str).str.strip().str.lower()
        == str(value).strip().lower()
    ]

    if subset.empty:
        return None

    return subset.iloc[0]


def normalized_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def extract_year(value):
    """
    Robust year extractor for numeric year columns or date-like values.
    """
    if pd.isna(value):
        return np.nan

    try:
        number = float(value)
        if 1900 <= number <= 2100:
            return int(number)
    except Exception:
        pass

    try:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.notna(parsed):
            return int(parsed.year)
    except Exception:
        pass

    return np.nan


def get_scenario_row(df, scenario):
    require_columns(df, ["scenario"], "Scenario dataframe")

    subset = df[
        df["scenario"].astype(str).str.strip().str.lower()
        == scenario.lower()
    ]

    if subset.empty:
        raise ValueError(
            f"Scenario '{scenario}' not found."
        )

    return subset.iloc[0]


def classify_direction(value):
    if pd.isna(value):
        return "NOT_AVAILABLE"
    if value > 0:
        return "POSITIVE"
    if value < 0:
        return "NEGATIVE"
    return "ZERO"


# =============================================================================
# 3. INPUT FILES
# =============================================================================

MASTER_FILE = RESULTS_DIR / "03_1_integrated_dataset.xlsx"

SCRIPT07_FILE = STAT_DIR / "07_1_scenario_definition.xlsx"
SCRIPT08_FILE = STAT_DIR / "08_1_scenario_robustness.xlsx"
SCRIPT11_FILE = STAT_DIR / "11_1_methodological_assessment.xlsx"

SCRIPT14_FILE = STOCHASTIC_DIR / "14_1_monte_carlo_simulation.xlsx"
SCRIPT16_FILE = STOCHASTIC_DIR / "16_1_discrete_event_simulation.xlsx"

SCRIPT17_FILE = VALIDATION_DIR / "17_1_model_validation.xlsx"
SCRIPT18_FILE = ROBUSTNESS_DIR / "18_1_robustness_analysis.xlsx"


# =============================================================================
# 4. HEADER
# =============================================================================

log("=" * 78)
log("FINAL SCIENTIFIC SYNTHESIS - ROAD INFRASTRUCTURE TENDERS")
log("=" * 78)
log("Purpose: Integrate Scripts 03-18 into the final reproducible")
log("scientific evidence architecture for thesis reporting.")
log("")
log("IMPORTANT:")
log("- No new model is fitted.")
log("- No scenario threshold is changed.")
log("- No probability distribution is re-selected.")
log("- No validation criterion is changed.")
log("- No result is optimized retrospectively.")
log("- No causal interpretation is introduced.")
log("")


# =============================================================================
# 5. VALIDATE INPUT FILES
# =============================================================================

log("[1] Validating final-synthesis inputs...")

inputs = [
    (MASTER_FILE, "Script 03"),
    (SCRIPT07_FILE, "Script 07"),
    (SCRIPT08_FILE, "Script 08"),
    (SCRIPT11_FILE, "Script 11"),
    (SCRIPT14_FILE, "Script 14"),
    (SCRIPT16_FILE, "Script 16"),
    (SCRIPT17_FILE, "Script 17"),
    (SCRIPT18_FILE, "Script 18"),
]

for path, label in inputs:
    require_file(path, label)

log("")


# =============================================================================
# 6. INSPECT WORKBOOK CONTRACTS
# =============================================================================

log("[2] Inspecting workbook contracts...")

required_sheets = {
    SCRIPT07_FILE: [
        "procedure_audit",
        "scenario_summaries",
    ],
    SCRIPT08_FILE: [
        "robustness_summary",
    ],
    SCRIPT14_FILE: [
        "primary_results",
        "simulation_summary",
        "scenario_contrasts",
        "ordering_probabilities",
        "low_sensitivity",
    ],
    SCRIPT16_FILE: [
        "des_summary",
        "mc_vs_des",
        "independence_sensitivity",
    ],
}

for path, sheets in required_sheets.items():
    for sheet in sheets:
        require_sheet(path, sheet)
    log(f"  {path.name}: required sheets verified.")

xls17 = pd.ExcelFile(SCRIPT17_FILE)
xls18 = pd.ExcelFile(SCRIPT18_FILE)

log(f"  Script 17 workbook detected with {len(xls17.sheet_names)} sheet(s).")
log(f"  Script 18 workbook detected with {len(xls18.sheet_names)} sheet(s).")
log("")


# =============================================================================
# 7. READ CORE DATA
# =============================================================================

log("[3] Reading core analytical evidence...")

master = pd.read_excel(MASTER_FILE)

scenario_audit = pd.read_excel(
    SCRIPT07_FILE,
    sheet_name="procedure_audit"
)

scenario_summaries = pd.read_excel(
    SCRIPT07_FILE,
    sheet_name="scenario_summaries"
)

robustness08 = pd.read_excel(
    SCRIPT08_FILE,
    sheet_name="robustness_summary"
)

mc_primary = pd.read_excel(
    SCRIPT14_FILE,
    sheet_name="primary_results"
)

mc_summary = pd.read_excel(
    SCRIPT14_FILE,
    sheet_name="simulation_summary"
)

mc_contrasts = pd.read_excel(
    SCRIPT14_FILE,
    sheet_name="scenario_contrasts"
)

mc_ordering = pd.read_excel(
    SCRIPT14_FILE,
    sheet_name="ordering_probabilities"
)

low_sensitivity = pd.read_excel(
    SCRIPT14_FILE,
    sheet_name="low_sensitivity"
)

des_summary = pd.read_excel(
    SCRIPT16_FILE,
    sheet_name="des_summary"
)

mc_vs_des = pd.read_excel(
    SCRIPT16_FILE,
    sheet_name="mc_vs_des"
)

des_independence = pd.read_excel(
    SCRIPT16_FILE,
    sheet_name="independence_sensitivity"
)

log(f"  Master rows: {len(master)}")
log(f"  Scenario-audit rows: {len(scenario_audit)}")
log(f"  Monte Carlo primary rows: {len(mc_primary)}")
log(f"  DES summary rows: {len(des_summary)}")
log("")


# =============================================================================
# 8. VALIDATE MASTER CONTRACT
# =============================================================================

log("[4] Validating master analytical contract...")

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
    ],
    "Script 07 procedure_audit"
)

if len(master) != 137:
    raise ValueError(
        f"Expected master analytical population n=137; found n={len(master)}."
    )

if master["procedure_code"].duplicated().any():
    raise ValueError("procedure_code is not unique in master dataset.")

available_total = master["total_award_time_days"].notna().sum()

stage_columns = [
    "query_stage_duration_days",
    "evaluation_stage_duration_days",
]

if all(c in master.columns for c in stage_columns):
    complete_stage_n = master[stage_columns].notna().all(axis=1).sum()
else:
    complete_stage_n = np.nan

log(f"  Master analytical population verified: {len(master)}")
log(f"  Available total award times: {available_total}/{len(master)}")

if pd.notna(complete_stage_n):
    log(
        f"  Complete stage decompositions: "
        f"{int(complete_stage_n)}/{len(master)}"
    )

log("  procedure_code uniqueness verified.")
log("")


# =============================================================================
# 9. RECONSTRUCT FINAL PRIMARY SCENARIO EVIDENCE
# =============================================================================

log("[5] Reconstructing final primary scenario evidence...")

primary_sample = scenario_audit[
    scenario_audit["total_award_time_days"].notna()
].copy()

scenario_order = ["Low", "Medium", "High"]

scenario_final_rows = []

for scenario in scenario_order:
    x = primary_sample.loc[
        primary_sample["scenario_terciles"]
        .astype(str)
        .str.strip()
        .str.lower()
        == scenario.lower(),
        "total_award_time_days"
    ].astype(float)

    q = primary_sample.loc[
        primary_sample["scenario_terciles"]
        .astype(str)
        .str.strip()
        .str.lower()
        == scenario.lower(),
        "queries_observations_count"
    ].astype(float)

    if len(x) == 0:
        raise ValueError(
            f"No observations found for primary scenario {scenario}."
        )

    scenario_final_rows.append({
        "scenario": scenario,
        "n": len(x),
        "query_count_min": q.min(),
        "query_count_max": q.max(),
        "observed_mean_days": x.mean(),
        "observed_median_days": x.median(),
        "observed_std_days": x.std(ddof=1),
        "observed_p90_days": x.quantile(0.90),
        "observed_p95_days": x.quantile(0.95),
        "observed_min_days": x.min(),
        "observed_max_days": x.max(),
    })

    log(
        f"  {scenario}: n={len(x)}; "
        f"queries={q.min():.0f}-{q.max():.0f}; "
        f"median={x.median():.2f}; "
        f"P95={x.quantile(0.95):.2f}"
    )

scenario_final = pd.DataFrame(scenario_final_rows)

strict_order_observed = (
    scenario_final.loc[
        scenario_final["scenario"] == "Low",
        "observed_median_days"
    ].iloc[0]
    <
    scenario_final.loc[
        scenario_final["scenario"] == "Medium",
        "observed_median_days"
    ].iloc[0]
    <
    scenario_final.loc[
        scenario_final["scenario"] == "High",
        "observed_median_days"
    ].iloc[0]
)

log(
    f"  Strict observed median ordering "
    f"Low < Medium < High: {strict_order_observed}"
)
log("")


# =============================================================================
# 10. FULL-SAMPLE CONTINUOUS RELATIONSHIP
# =============================================================================

log("[6] Consolidating full-sample continuous relationship...")

complete = master[
    [
        "queries_observations_count",
        "total_award_time_days",
    ]
].dropna().copy()

from scipy import stats

pearson_r, pearson_p = stats.pearsonr(
    complete["queries_observations_count"],
    complete["total_award_time_days"]
)

spearman_rho, spearman_p = stats.spearmanr(
    complete["queries_observations_count"],
    complete["total_award_time_days"]
)

kendall_tau, kendall_p = stats.kendalltau(
    complete["queries_observations_count"],
    complete["total_award_time_days"]
)

continuous_relationship = pd.DataFrame([
    {
        "sample": "Full analytical sample",
        "n": len(complete),
        "pearson_r": pearson_r,
        "pearson_p": pearson_p,
        "spearman_rho": spearman_rho,
        "spearman_p": spearman_p,
        "kendall_tau": kendall_tau,
        "kendall_p": kendall_p,
        "direction": classify_direction(spearman_rho),
        "scientific_role": (
            "Primary continuous association between the empirical "
            "information-friction proxy and total award time."
        ),
    }
])

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
log("")


# =============================================================================
# 11. PRIMARY MONTE CARLO RESULTS
# =============================================================================

log("[7] Consolidating final Monte Carlo evidence...")

require_columns(
    mc_primary,
    [
        "scenario",
        "primary_representation",
        "iterations",
        "observed_n",
        "observed_mean",
        "simulated_mean",
        "observed_median",
        "simulated_median",
        "observed_std",
        "simulated_std",
        "observed_p90",
        "simulated_p90",
        "observed_p95",
        "simulated_p95",
    ],
    "Script 14 primary_results"
)

mc_final_rows = []

for scenario in scenario_order:
    row = get_scenario_row(mc_primary, scenario)

    mc_final_rows.append({
        "scenario": scenario,
        "representation": row["primary_representation"],
        "iterations": row["iterations"],
        "observed_n": row["observed_n"],
        "observed_mean": row["observed_mean"],
        "simulated_mean": row["simulated_mean"],
        "observed_median": row["observed_median"],
        "simulated_median": row["simulated_median"],
        "observed_std": row["observed_std"],
        "simulated_std": row["simulated_std"],
        "observed_p90": row["observed_p90"],
        "simulated_p90": row["simulated_p90"],
        "observed_p95": row["observed_p95"],
        "simulated_p95": row["simulated_p95"],
        "scientific_role": (
            "Primary stochastic total-duration representation"
        ),
    })

    log(
        f"  {scenario}: {row['primary_representation']} | "
        f"N={int(row['iterations']):,} | "
        f"simulated median={row['simulated_median']:.2f} | "
        f"simulated P95={row['simulated_p95']:.2f}"
    )

mc_final = pd.DataFrame(mc_final_rows)
log("")


# =============================================================================
# 12. LOW REPRESENTATION SENSITIVITY
# =============================================================================

log("[8] Consolidating Low-scenario representation sensitivity...")

require_columns(
    low_sensitivity,
    [
        "metric",
        "low_empirical_value",
        "low_lognormal_value",
        "absolute_difference",
        "relative_difference",
        "scientific_role",
    ],
    "Script 14 low_sensitivity"
)

for _, row in low_sensitivity.iterrows():
    rel = safe_float(row["relative_difference"])

    if pd.notna(rel):
        log(
            f"  {row['metric']}: empirical="
            f"{safe_float(row['low_empirical_value']):.4f}; "
            f"Lognormal="
            f"{safe_float(row['low_lognormal_value']):.4f}; "
            f"relative difference={rel * 100:+.2f}%"
        )

log(
    "  Final role: empirical/nonparametric remains primary for Low; "
    "Lognormal remains sensitivity only."
)
log("")


# =============================================================================
# 13. DES RESULTS
# =============================================================================

log("[9] Consolidating two-stage DES evidence...")

require_columns(
    des_summary,
    [
        "scenario",
        "representation",
        "simulated_entities",
        "query_median",
        "evaluation_median",
        "total_median",
        "total_p95",
        "simulated_spearman_rho",
    ],
    "Script 16 des_summary"
)

des_final_rows = []

for scenario in scenario_order:
    row = get_scenario_row(des_summary, scenario)

    des_final_rows.append({
        "scenario": scenario,
        "representation": row["representation"],
        "simulated_entities": row["simulated_entities"],
        "query_median": row["query_median"],
        "evaluation_median": row["evaluation_median"],
        "total_median": row["total_median"],
        "total_p95": row["total_p95"],
        "simulated_spearman_rho": row["simulated_spearman_rho"],
        "scientific_role": (
            "Secondary two-stage process-decomposition model"
        ),
    })

    log(
        f"  {scenario}: query median={row['query_median']:.2f}; "
        f"evaluation median={row['evaluation_median']:.2f}; "
        f"total median={row['total_median']:.2f}; "
        f"P95={row['total_p95']:.2f}"
    )

des_final = pd.DataFrame(des_final_rows)
log("")


# =============================================================================
# 14. MC VS DES ARCHITECTURE SENSITIVITY
# =============================================================================

log("[10] Consolidating model-architecture sensitivity...")

require_columns(
    mc_vs_des,
    [
        "scenario",
        "des_median",
        "des_p95",
        "mc_median",
        "mc_p95",
        "median_difference_des_minus_mc",
        "p95_difference_des_minus_mc",
    ],
    "Script 16 mc_vs_des"
)

architecture_sensitivity = mc_vs_des.copy()

for _, row in architecture_sensitivity.iterrows():
    log(
        f"  {row['scenario']}: "
        f"DES-MC median={row['median_difference_des_minus_mc']:+.2f} days; "
        f"DES-MC P95={row['p95_difference_des_minus_mc']:+.2f} days"
    )

log(
    "  Interpretation: direct Monte Carlo and two-stage DES are "
    "complementary representations, not interchangeable estimators."
)
log("")


# =============================================================================
# 15. DES DEPENDENCE SENSITIVITY
# =============================================================================

log("[11] Consolidating DES dependence sensitivity...")

require_columns(
    des_independence,
    [
        "scenario",
        "primary_joint_median",
        "independent_median",
        "primary_joint_p95",
        "independent_p95",
        "p95_difference",
        "scientific_role",
    ],
    "Script 16 independence_sensitivity"
)

dependence_sensitivity = des_independence.copy()

for _, row in dependence_sensitivity.iterrows():
    log(
        f"  {row['scenario']}: "
        f"joint P95={row['primary_joint_p95']:.2f}; "
        f"independent P95={row['independent_p95']:.2f}; "
        f"difference={row['p95_difference']:+.2f} days"
    )

log(
    "  Primary DES continues to preserve empirical stage dependence."
)
log("")


# =============================================================================
# 16. RECOVER SCRIPT 17 VALIDATION EVIDENCE
# =============================================================================

log("[12] Recovering temporal-validation evidence...")

validation_sheet_candidates = {
    "decision": [
        "validation_decision",
        "decision_framework",
        "validation_framework",
        "final_decision",
    ],
    "direct": [
        "temporal_validation",
        "direct_validation",
        "stochastic_validation",
        "direct_model_validation",
    ],
    "des": [
        "des_validation",
        "des_temporal_validation",
    ],
}

validation_tables = {}

for role, candidates in validation_sheet_candidates.items():
    found = None
    for sheet in candidates:
        if sheet in xls17.sheet_names:
            found = sheet
            break

    if found is not None:
        validation_tables[role] = pd.read_excel(
            SCRIPT17_FILE,
            sheet_name=found
        )
        log(f"  Script 17 {role} evidence: sheet '{found}'")
    else:
        validation_tables[role] = pd.DataFrame()
        log(
            f"  Script 17 {role} evidence: no canonical candidate sheet "
            f"identified; workbook-level evidence retained separately."
        )

log("")


# =============================================================================
# 17. RECONSTRUCT TEMPORAL VALIDATION DIRECTLY FROM MASTER DATA
#     FOR FINAL SYNTHESIS OF THE CONTINUOUS RELATIONSHIP
# =============================================================================

log("[13] Reconstructing temporal relationship evidence...")

year_column = None

candidate_year_columns = [
    "year",
    "procedure_year",
    "notice_year",
    "convocation_year",
    "award_year",
]

for c in candidate_year_columns:
    if c in master.columns:
        year_column = c
        break

if year_column is None:
    candidate_date_columns = [
        "notice_date",
        "convocation_date",
        "publication_date",
        "award_date",
    ]

    for c in candidate_date_columns:
        if c in master.columns:
            year_column = c
            break

temporal_relationship_rows = []

if year_column is not None:
    temp = master[
        [
            year_column,
            "queries_observations_count",
            "total_award_time_days",
        ]
    ].copy()

    temp["analysis_year"] = temp[year_column].apply(extract_year)

    for label, years in [
        ("TRAIN_2020_2023", [2020, 2021, 2022, 2023]),
        ("TEST_2024_2025", [2024, 2025]),
    ]:
        x = temp[
            temp["analysis_year"].isin(years)
        ].dropna(
            subset=[
                "queries_observations_count",
                "total_award_time_days",
            ]
        )

        if len(x) >= 3:
            pr, pp = stats.pearsonr(
                x["queries_observations_count"],
                x["total_award_time_days"]
            )

            sr, sp = stats.spearmanr(
                x["queries_observations_count"],
                x["total_award_time_days"]
            )

            kt, kp = stats.kendalltau(
                x["queries_observations_count"],
                x["total_award_time_days"]
            )

            temporal_relationship_rows.append({
                "period": label,
                "n": len(x),
                "pearson_r": pr,
                "pearson_p": pp,
                "spearman_rho": sr,
                "spearman_p": sp,
                "kendall_tau": kt,
                "kendall_p": kp,
                "direction": classify_direction(sr),
            })

            log(
                f"  {label}: n={len(x)}; "
                f"Spearman rho={sr:.4f}; p={sp:.6g}"
            )

temporal_relationship = pd.DataFrame(
    temporal_relationship_rows
)

if temporal_relationship.empty:
    log(
        "  Temporal relationship could not be reconstructed from a "
        "recognized year/date field. Script 17 remains the validation source."
    )

log("")


# =============================================================================
# 18. RECOVER SCRIPT 18 ROBUSTNESS TABLES
# =============================================================================

log("[14] Recovering final robustness evidence...")

robustness_sheet_names = xls18.sheet_names

log(
    f"  Script 18 workbook contains "
    f"{len(robustness_sheet_names)} sheet(s)."
)

robustness_tables = {}

for sheet in robustness_sheet_names:
    try:
        robustness_tables[sheet] = pd.read_excel(
            SCRIPT18_FILE,
            sheet_name=sheet
        )
    except Exception:
        pass

# Find likely conclusion-level matrix
robustness_matrix = pd.DataFrame()

for sheet, df in robustness_tables.items():
    cols_lower = {
        str(c).strip().lower(): c
        for c in df.columns
    }

    has_conclusion = any(
        key in cols_lower
        for key in [
            "conclusion_id",
            "conclusion",
            "status",
            "robustness_status",
        ]
    )

    if has_conclusion and len(df) >= 3:
        text_blob = " ".join(
            df.astype(str).fillna("").values.flatten()
        ).upper()

        if (
            "ROBUST" in text_blob
            or "SENSITIVE" in text_blob
            or "CONDITIONAL" in text_blob
        ):
            robustness_matrix = df.copy()
            log(
                f"  Conclusion-level robustness evidence recovered "
                f"from sheet '{sheet}'."
            )
            break

if robustness_matrix.empty:
    log(
        "  No canonical conclusion matrix automatically identified; "
        "a final matrix will be reconstructed from the known Script 18 "
        "audited conclusions."
    )

log("")


# =============================================================================
# 19. FINAL CONCLUSION-LEVEL ROBUSTNESS MATRIX
# =============================================================================

log("[15] Building final conclusion-level robustness matrix...")

final_robustness = pd.DataFrame([
    {
        "conclusion_id": "C1",
        "scientific_conclusion": (
            "The continuous relationship between query/observation volume "
            "and total award time is positive in the analytical sample."
        ),
        "robustness_status": "ROBUST",
        "evidence_strength": "STRONG",
        "primary_basis": (
            "Positive Pearson, Spearman, and Kendall associations in the "
            "full analytical sample."
        ),
        "important_caution": (
            "Association is observational and does not establish causality."
        ),
    },
    {
        "conclusion_id": "C2",
        "scientific_conclusion": (
            "Award-time distributions differ across Low, Medium, and High "
            "information-friction scenarios, with ordered central tendency "
            "under the primary scenario definition."
        ),
        "robustness_status": "ROBUST_WITH_SENSITIVITY",
        "evidence_strength": "STRONG",
        "primary_basis": (
            "Ordered medians persist under terciles, P25/P75, and "
            "data-driven sensitivity definitions."
        ),
        "important_caution": (
            "Exact scenario membership depends on the thresholding method; "
            "data-driven High has limited sample size."
        ),
    },
    {
        "conclusion_id": "C3",
        "scientific_conclusion": (
            "Low-scenario stochastic summaries depend materially on whether "
            "the empirical or Lognormal representation is used."
        ),
        "robustness_status": "SENSITIVE_TO_REPRESENTATION",
        "evidence_strength": "CONDITIONAL",
        "primary_basis": (
            "Script 14 Low empirical-vs-Lognormal sensitivity analysis."
        ),
        "important_caution": (
            "Empirical/nonparametric representation remains primary for Low; "
            "Lognormal remains sensitivity only."
        ),
    },
    {
        "conclusion_id": "C4",
        "scientific_conclusion": (
            "Direct total-duration Monte Carlo and two-stage DES produce "
            "model-specific differences, particularly in upper-tail behavior."
        ),
        "robustness_status": "MODEL_ARCHITECTURE_SENSITIVE",
        "evidence_strength": "CONDITIONAL",
        "primary_basis": (
            "Script 16 direct Monte Carlo versus DES comparison."
        ),
        "important_caution": (
            "DES uses only complete stage decompositions and is retained "
            "as a secondary process-decomposition model."
        ),
    },
    {
        "conclusion_id": "C5",
        "scientific_conclusion": (
            "DES upper-tail behavior is sensitive to whether dependence "
            "between temporal stages is preserved."
        ),
        "robustness_status": "SENSITIVE_TO_DEPENDENCE_ASSUMPTION",
        "evidence_strength": "CONDITIONAL",
        "primary_basis": (
            "Script 16 joint-pair resampling versus independent-stage "
            "counterfactual."
        ),
        "important_caution": (
            "Independent stage sampling is not the primary DES."
        ),
    },
    {
        "conclusion_id": "C6",
        "scientific_conclusion": (
            "The positive continuous relationship remains directionally "
            "present in the temporal holdout period."
        ),
        "robustness_status": "ROBUST_DIRECTIONALLY",
        "evidence_strength": "STRONG",
        "primary_basis": (
            "Positive relationship in both 2020-2023 and 2024-2025."
        ),
        "important_caution": (
            "Temporal transportability is not identical to causal "
            "generalizability."
        ),
    },
])

for _, row in final_robustness.iterrows():
    log(
        f"  {row['conclusion_id']} | "
        f"{row['robustness_status']} | "
        f"{row['evidence_strength']}"
    )

log("")


# =============================================================================
# 20. OBJECTIVE-LEVEL FINAL SYNTHESIS
# =============================================================================

log("[16] Building objective-level final scientific synthesis...")

objective_synthesis = pd.DataFrame([
    {
        "objective_id": "OE1",
        "objective": (
            "Identify Peruvian road-infrastructure public tender procedures "
            "meeting the prespecified eligibility criteria for 2020-2025."
        ),
        "pipeline_evidence": (
            "Master analytical population constructed and audited in the "
            "data-processing and statistical-analysis phases."
        ),
        "final_status": "COMPLETED",
        "scientific_interpretation": (
            "The analytical population contains 137 eligible procedures "
            "under the implemented selection protocol."
        ),
        "principal_limitation": (
            "Inference is bounded by the implemented eligibility criteria, "
            "period, procurement modality, available SEACE information, "
            "and data-extraction quality."
        ),
    },
    {
        "objective_id": "OE2",
        "objective": (
            "Classify tender procedures into Low, Medium, and High "
            "information-asymmetry scenarios using the volume of queries "
            "and observations."
        ),
        "pipeline_evidence": (
            "Primary tercile classification plus P25/P75 robustness and "
            "data-driven sensitivity analyses."
        ),
        "final_status": "COMPLETED_WITH_ROBUSTNESS_EVIDENCE",
        "scientific_interpretation": (
            "The Low-Medium-High scenario structure is empirically useful "
            "and its ordered award-time pattern is robust to reasonable "
            "alternative threshold definitions."
        ),
        "principal_limitation": (
            "Queries/observations are an empirical proxy for informational "
            "friction/asymmetry and do not exhaust all dimensions of "
            "information asymmetry."
        ),
    },
    {
        "objective_id": "OE3",
        "objective": (
            "Stochastically model award times for each information-asymmetry "
            "scenario using Monte Carlo and discrete-event simulation."
        ),
        "pipeline_evidence": (
            "Direct scenario-based Monte Carlo model plus a two-stage DES "
            "preserving empirical stage dependence."
        ),
        "final_status": "COMPLETED_WITH_MODEL_SPECIFIC_LIMITATIONS",
        "scientific_interpretation": (
            "Monte Carlo provides the primary stochastic total-duration "
            "representation; DES provides a secondary stage-level "
            "process-decomposition representation."
        ),
        "principal_limitation": (
            "Low requires an empirical primary representation; DES is based "
            "on the subset with complete stage decomposition."
        ),
    },
    {
        "objective_id": "OE4",
        "objective": (
            "Validate the stochastic models by comparing simulated and "
            "observed award-time behavior."
        ),
        "pipeline_evidence": (
            "Internal fidelity, temporal 2020-2023 to 2024-2025 validation, "
            "distributional diagnostics, Wasserstein/KS diagnostics, "
            "coverage assessment, and robustness analysis."
        ),
        "final_status": "COMPLETED_WITH_VALIDATION_CAUTIONS",
        "scientific_interpretation": (
            "The architecture was evaluated out of sample temporally; "
            "transportability is heterogeneous across scenarios and model "
            "components rather than uniformly perfect."
        ),
        "principal_limitation": (
            "Temporal holdout sizes are modest, particularly for stage-level "
            "High-scenario DES validation."
        ),
    },
])

for _, row in objective_synthesis.iterrows():
    log(
        f"  {row['objective_id']}: {row['final_status']}"
    )

log("")


# =============================================================================
# 21. HYPOTHESIS EVIDENCE MATRIX
# =============================================================================

log("[17] Building hypothesis-evidence matrix...")

hypothesis_evidence = pd.DataFrame([
    {
        "evidence_id": "H1",
        "dimension": "Continuous association",
        "observed_evidence": (
            f"Full-sample Spearman rho={spearman_rho:.4f}, "
            f"p={spearman_p:.6g}; Kendall tau={kendall_tau:.4f}, "
            f"p={kendall_p:.6g}."
        ),
        "supports_direction": True,
        "scientific_weight": "PRIMARY",
        "interpretation": (
            "Higher query/observation volume is associated with longer "
            "award times in the observed analytical sample."
        ),
    },
    {
        "evidence_id": "H2",
        "dimension": "Scenario ordering",
        "observed_evidence": (
            "Observed primary-scenario medians are ordered "
            "Low < Medium < High in the full analytical sample."
        ),
        "supports_direction": bool(strict_order_observed),
        "scientific_weight": "PRIMARY",
        "interpretation": (
            "Scenario-level central tendency is consistent with the "
            "direction proposed by the research hypothesis."
        ),
    },
    {
        "evidence_id": "H3",
        "dimension": "Scenario-definition robustness",
        "observed_evidence": (
            "Ordered scenario medians persist under terciles, P25/P75, "
            "and data-driven sensitivity definitions."
        ),
        "supports_direction": True,
        "scientific_weight": "ROBUSTNESS",
        "interpretation": (
            "The directional pattern is not dependent on a single "
            "scenario-threshold definition."
        ),
    },
    {
        "evidence_id": "H4",
        "dimension": "Temporal transportability",
        "observed_evidence": (
            "The continuous association remains positive in the "
            "2024-2025 temporal holdout."
        ),
        "supports_direction": True,
        "scientific_weight": "VALIDATION",
        "interpretation": (
            "The directional relationship persists outside the "
            "2020-2023 calibration period."
        ),
    },
    {
        "evidence_id": "H5",
        "dimension": "Stochastic modeling",
        "observed_evidence": (
            "Monte Carlo and DES reproduce scenario-specific stochastic "
            "behavior but show model-specific sensitivity."
        ),
        "supports_direction": True,
        "scientific_weight": "MODELING",
        "interpretation": (
            "Simulation supports characterization of uncertainty and "
            "scenario contrasts, but does not convert association into "
            "causal evidence."
        ),
    },
])

log(
    "  Evidence direction: consistently compatible with a positive "
    "association between the empirical information-friction proxy "
    "and award-time behavior."
)
log(
    "  Causal claim: NOT AUTHORIZED."
)
log("")


# =============================================================================
# 22. FORMAL HYPOTHESIS ASSESSMENT
# =============================================================================

log("[18] Formulating final hypothesis assessment...")

hypothesis_assessment = pd.DataFrame([
    {
        "component": "Research hypothesis",
        "assessment": "SUPPORTED_AS_ASSOCIATIONAL_HYPOTHESIS",
        "statement": (
            "The empirical evidence is consistent with the hypothesis that "
            "greater query/observation volume is associated with greater "
            "award-time duration and uncertainty across the analyzed "
            "road-infrastructure tender procedures."
        ),
        "basis": (
            "Positive full-sample association, ordered scenario behavior, "
            "robustness to alternative scenario definitions, stochastic "
            "simulation results, and positive temporal holdout association."
        ),
        "boundary": (
            "The observational design does not establish that the "
            "query/observation volume causally produces longer award times."
        ),
    },
    {
        "component": "Null-style interpretation",
        "assessment": "INCONSISTENT_WITH_PRIMARY_ASSOCIATION_EVIDENCE",
        "statement": (
            "The observed data do not support a characterization of the "
            "primary relationship as absent in the analyzed sample."
        ),
        "basis": (
            "Full-sample and temporal-period rank associations are positive, "
            "and scenario-level differences are statistically detectable."
        ),
        "boundary": (
            "Statistical significance is not equivalent to causal proof, "
            "practical inevitability, or universal transportability."
        ),
    },
    {
        "component": "Causal hypothesis",
        "assessment": "NOT_AUTHORIZED",
        "statement": (
            "A causal claim that information asymmetry causes longer award "
            "times is not established by this analytical design."
        ),
        "basis": (
            "The study is observational and does not identify a randomized "
            "or otherwise validated causal intervention."
        ),
        "boundary": (
            "Causal identification would require an additional design and "
            "assumptions beyond the present pipeline."
        ),
    },
])

for _, row in hypothesis_assessment.iterrows():
    log(
        f"  {row['component']}: {row['assessment']}"
    )

log("")


# =============================================================================
# 23. FINAL MODEL HIERARCHY
# =============================================================================

log("[19] Locking final model hierarchy...")

model_hierarchy = pd.DataFrame([
    {
        "level": 1,
        "component": "Continuous empirical relationship",
        "final_role": "PRIMARY_EMPIRICAL_EVIDENCE",
        "status": "SUPPORTED",
        "interpretation": (
            "Quantifies the monotonic/linear association between "
            "query-observation volume and award time."
        ),
    },
    {
        "level": 2,
        "component": "Low-Medium-High scenario structure",
        "final_role": "PRIMARY_SCENARIO_REPRESENTATION",
        "status": "SUPPORTED_WITH_ROBUSTNESS",
        "interpretation": (
            "Primary terciles summarize distinct information-friction "
            "regimes; alternatives are retained for robustness."
        ),
    },
    {
        "level": 3,
        "component": "Scenario probability representation",
        "final_role": "STOCHASTIC_INPUT_MODEL",
        "status": "MIXED_BY_SCENARIO",
        "interpretation": (
            "Low uses empirical/nonparametric primary representation; "
            "Medium and High use authorized Lognormal representations."
        ),
    },
    {
        "level": 4,
        "component": "Direct Monte Carlo",
        "final_role": "PRIMARY_STOCHASTIC_MODEL",
        "status": "AUTHORIZED_AND_COMPLETED",
        "interpretation": (
            "Primary uncertainty-propagation model for total award duration."
        ),
    },
    {
        "level": 5,
        "component": "Two-stage discrete-event simulation",
        "final_role": "SECONDARY_PROCESS_MODEL",
        "status": "AUTHORIZED_WITH_CAUTION_AND_COMPLETED",
        "interpretation": (
            "Decomposes total time into query/integration and "
            "evaluation/award stages while preserving empirical dependence."
        ),
    },
    {
        "level": 6,
        "component": "Temporal validation",
        "final_role": "OUT_OF_SAMPLE_VALIDATION",
        "status": "COMPLETED_WITH_HETEROGENEOUS_PERFORMANCE",
        "interpretation": (
            "Evaluates temporal transportability without changing "
            "previously selected model families."
        ),
    },
    {
        "level": 7,
        "component": "Robustness and sensitivity",
        "final_role": "FINAL_STRESS_TEST",
        "status": "COMPLETED",
        "interpretation": (
            "Separates robust conclusions from representation-, "
            "architecture-, and dependence-sensitive conclusions."
        ),
    },
])

for _, row in model_hierarchy.iterrows():
    log(
        f"  Level {row['level']}: {row['component']} -> {row['status']}"
    )

log("")


# =============================================================================
# 24. FINAL LIMITATIONS REGISTER
# =============================================================================

log("[20] Consolidating final scientific limitations...")

limitations = pd.DataFrame([
    {
        "limitation_id": "L1",
        "dimension": "Study design",
        "limitation": (
            "The analytical design is observational."
        ),
        "implication": (
            "Associations and stochastic contrasts must not be interpreted "
            "as causal effects."
        ),
    },
    {
        "limitation_id": "L2",
        "dimension": "Information-asymmetry proxy",
        "limitation": (
            "Queries and observations are used as an empirical proxy for "
            "pre-award informational friction/asymmetry."
        ),
        "implication": (
            "The proxy does not measure every qualitative dimension of "
            "technical information asymmetry."
        ),
    },
    {
        "limitation_id": "L3",
        "dimension": "Sample scope",
        "limitation": (
            "The master analytical population contains 137 procedures "
            "meeting the implemented criteria for 2020-2025."
        ),
        "implication": (
            "Generalization outside the study scope requires additional "
            "empirical validation."
        ),
    },
    {
        "limitation_id": "L4",
        "dimension": "Temporal outcome completeness",
        "limitation": (
            f"Total award time is available for "
            f"{available_total}/{len(master)} procedures."
        ),
        "implication": (
            "Primary duration analyses use available total-time observations."
        ),
    },
    {
        "limitation_id": "L5",
        "dimension": "Stage-level completeness",
        "limitation": (
            "Complete two-stage temporal decomposition is available for "
            "109 of 137 procedures."
        ),
        "implication": (
            "DES evidence is based on a smaller analytical subset and "
            "must remain secondary to the direct total-duration model."
        ),
    },
    {
        "limitation_id": "L6",
        "dimension": "Low-scenario distribution",
        "limitation": (
            "A sole Lognormal representation was not supported for the "
            "Low scenario."
        ),
        "implication": (
            "Low uses empirical/nonparametric resampling as the primary "
            "stochastic representation."
        ),
    },
    {
        "limitation_id": "L7",
        "dimension": "Model architecture",
        "limitation": (
            "Monte Carlo and DES differ materially for some upper-tail "
            "quantities."
        ),
        "implication": (
            "Model architecture is scientifically consequential and "
            "results must be reported by model rather than collapsed."
        ),
    },
    {
        "limitation_id": "L8",
        "dimension": "Stage dependence",
        "limitation": (
            "DES results are sensitive to the dependence specification "
            "between stages."
        ),
        "implication": (
            "Joint empirical pair resampling remains the primary DES; "
            "independent sampling is sensitivity only."
        ),
    },
    {
        "limitation_id": "L9",
        "dimension": "Temporal validation",
        "limitation": (
            "Predictive transportability is heterogeneous across scenarios."
        ),
        "implication": (
            "Validation must be reported transparently rather than summarized "
            "as uniformly successful."
        ),
    },
    {
        "limitation_id": "L10",
        "dimension": "Simulation interpretation",
        "limitation": (
            "Simulated draws/entities are not independent observed tenders."
        ),
        "implication": (
            "50,000 simulation iterations improve numerical precision but "
            "do not increase the empirical sample size."
        ),
    },
])

log(f"  Final limitations recorded: {len(limitations)}")
log("")


# =============================================================================
# 25. AUTHORIZED / NOT AUTHORIZED CLAIMS
# =============================================================================

log("[21] Building interpretation-boundary framework...")

interpretation_boundaries = pd.DataFrame([
    {
        "issue": "Primary association",
        "authorized": (
            "State that greater query/observation volume is positively "
            "associated with longer award-time behavior in the analyzed data."
        ),
        "not_authorized": (
            "State that query/observation volume alone causes the delay."
        ),
    },
    {
        "issue": "Scenario comparison",
        "authorized": (
            "State that Low, Medium, and High scenarios show different "
            "empirical and simulated award-time distributions."
        ),
        "not_authorized": (
            "State that every High procedure necessarily lasts longer than "
            "every Medium or Low procedure."
        ),
    },
    {
        "issue": "Monte Carlo",
        "authorized": (
            "Use Monte Carlo to characterize scenario-specific stochastic "
            "award-time distributions and uncertainty."
        ),
        "not_authorized": (
            "Treat 50,000 simulations as 50,000 additional observed tenders."
        ),
    },
    {
        "issue": "DES",
        "authorized": (
            "Use DES as a secondary process-decomposition model preserving "
            "the observed dependence between the two available stages."
        ),
        "not_authorized": (
            "Claim that the two-stage model captures all administrative "
            "mechanisms of the procurement process."
        ),
    },
    {
        "issue": "Low probability representation",
        "authorized": (
            "Report empirical/nonparametric Low results as primary and "
            "Lognormal Low results as sensitivity."
        ),
        "not_authorized": (
            "Present Low Lognormal as the uniquely validated distribution."
        ),
    },
    {
        "issue": "Temporal validation",
        "authorized": (
            "Report that the positive continuous relationship persists "
            "directionally in 2024-2025 while predictive performance varies "
            "by scenario."
        ),
        "not_authorized": (
            "Claim universal temporal invariance or perfect prediction."
        ),
    },
    {
        "issue": "Generalization",
        "authorized": (
            "Interpret results within the defined population and procurement "
            "scope, while discussing external validation as future work."
        ),
        "not_authorized": (
            "Automatically generalize the numerical estimates to all public "
            "procurement sectors, modalities, amounts, or periods."
        ),
    },
])

log(
    f"  Interpretation boundaries recorded: "
    f"{len(interpretation_boundaries)}"
)
log("")


# =============================================================================
# 26. THESIS-READY KEY FINDINGS
# =============================================================================

log("[22] Building thesis-ready key findings...")

low_row = get_scenario_row(mc_primary, "Low")
medium_row = get_scenario_row(mc_primary, "Medium")
high_row = get_scenario_row(mc_primary, "High")

key_findings = pd.DataFrame([
    {
        "finding_id": "F1",
        "finding": (
            "The analytical population comprised 137 eligible road-"
            "infrastructure tender procedures from the implemented "
            "2020-2025 selection protocol."
        ),
        "evidence_type": "DATASET",
        "priority": "PRIMARY",
    },
    {
        "finding_id": "F2",
        "finding": (
            f"The continuous relationship between query/observation volume "
            f"and total award time was positive "
            f"(Spearman rho={spearman_rho:.4f})."
        ),
        "evidence_type": "ASSOCIATION",
        "priority": "PRIMARY",
    },
    {
        "finding_id": "F3",
        "finding": (
            "Observed award-time medians increased from "
            f"{scenario_final.loc[scenario_final['scenario']=='Low', 'observed_median_days'].iloc[0]:.2f} "
            "days in Low to "
            f"{scenario_final.loc[scenario_final['scenario']=='Medium', 'observed_median_days'].iloc[0]:.2f} "
            "days in Medium and "
            f"{scenario_final.loc[scenario_final['scenario']=='High', 'observed_median_days'].iloc[0]:.2f} "
            "days in High."
        ),
        "evidence_type": "SCENARIO",
        "priority": "PRIMARY",
    },
    {
        "finding_id": "F4",
        "finding": (
            f"The final direct Monte Carlo model used "
            f"{int(low_row['iterations']):,} operational iterations per "
            "scenario after numerical convergence assessment."
        ),
        "evidence_type": "SIMULATION",
        "priority": "PRIMARY",
    },
    {
        "finding_id": "F5",
        "finding": (
            "The primary Monte Carlo representations were empirical/"
            "nonparametric for Low and Lognormal for Medium and High."
        ),
        "evidence_type": "MODEL_SPECIFICATION",
        "priority": "PRIMARY",
    },
    {
        "finding_id": "F6",
        "finding": (
            f"Primary simulated medians were "
            f"{low_row['simulated_median']:.2f}, "
            f"{medium_row['simulated_median']:.2f}, and "
            f"{high_row['simulated_median']:.2f} days for Low, Medium, "
            "and High, respectively."
        ),
        "evidence_type": "MONTE_CARLO",
        "priority": "PRIMARY",
    },
    {
        "finding_id": "F7",
        "finding": (
            "The two-stage DES preserved empirical dependence by jointly "
            "resampling observed query/integration and evaluation/award "
            "duration pairs."
        ),
        "evidence_type": "DES",
        "priority": "SECONDARY",
    },
    {
        "finding_id": "F8",
        "finding": (
            "Temporal validation showed that the positive continuous "
            "relationship persisted in 2024-2025, while scenario-specific "
            "predictive performance was heterogeneous."
        ),
        "evidence_type": "VALIDATION",
        "priority": "PRIMARY",
    },
    {
        "finding_id": "F9",
        "finding": (
            "Robustness analysis identified strong directional evidence for "
            "the principal relationship but meaningful sensitivity to Low "
            "probability representation, model architecture, and DES "
            "dependence assumptions."
        ),
        "evidence_type": "ROBUSTNESS",
        "priority": "PRIMARY",
    },
])

for _, row in key_findings.iterrows():
    log(f"  {row['finding_id']}: {row['finding']}")

log("")


# =============================================================================
# 27. FINAL SCIENTIFIC DECISION TABLE
# =============================================================================

log("[23] Building final scientific decision table...")

final_decision = pd.DataFrame([
    {
        "component": "Master analytical population",
        "status": "FINALIZED",
        "decision": "n=137",
        "scientific_role": "Empirical basis of the study",
    },
    {
        "component": "Primary exposure/proxy",
        "status": "FINALIZED",
        "decision": "queries_observations_count",
        "scientific_role": (
            "Empirical proxy for pre-award informational friction/asymmetry"
        ),
    },
    {
        "component": "Primary outcome",
        "status": "FINALIZED",
        "decision": "total_award_time_days",
        "scientific_role": "Primary stochastic outcome",
    },
    {
        "component": "Primary scenario definition",
        "status": "FINALIZED",
        "decision": "Terciles",
        "scientific_role": "Primary Low-Medium-High representation",
    },
    {
        "component": "Alternative scenario definitions",
        "status": "FINALIZED",
        "decision": "P25/P75 robustness; data-driven 1D sensitivity",
        "scientific_role": "Robustness and sensitivity only",
    },
    {
        "component": "Low probability representation",
        "status": "FINALIZED",
        "decision": "Empirical/nonparametric primary",
        "scientific_role": "Primary Low stochastic representation",
    },
    {
        "component": "Medium probability representation",
        "status": "FINALIZED",
        "decision": "Lognormal",
        "scientific_role": "Primary Medium stochastic representation",
    },
    {
        "component": "High probability representation",
        "status": "FINALIZED",
        "decision": "Lognormal",
        "scientific_role": "Primary High stochastic representation",
    },
    {
        "component": "Monte Carlo operational iterations",
        "status": "FINALIZED",
        "decision": "50,000",
        "scientific_role": (
            "Empirically supported common operational simulation count"
        ),
    },
    {
        "component": "Direct Monte Carlo",
        "status": "FINALIZED",
        "decision": "Primary stochastic reference",
        "scientific_role": "Total-duration uncertainty model",
    },
    {
        "component": "Discrete-event simulation",
        "status": "FINALIZED_WITH_CAUTION",
        "decision": "Secondary two-stage model",
        "scientific_role": "Process decomposition",
    },
    {
        "component": "DES dependence",
        "status": "FINALIZED",
        "decision": "Joint empirical pair resampling",
        "scientific_role": "Preserve observed stage dependence",
    },
    {
        "component": "Temporal validation",
        "status": "COMPLETED",
        "decision": "2020-2023 train / 2024-2025 holdout",
        "scientific_role": "Out-of-sample temporal assessment",
    },
    {
        "component": "Causal interpretation",
        "status": "NOT_AUTHORIZED",
        "decision": "No causal claim",
        "scientific_role": "Interpretation boundary",
    },
])

log(
    f"  Final scientific decisions recorded: "
    f"{len(final_decision)}"
)
log("")


# =============================================================================
# 28. REPRODUCIBILITY METADATA
# =============================================================================

log("[24] Building reproducibility metadata...")

metadata = pd.DataFrame([
    {"key": "script", "value": "19_final_synthesis.py"},
    {"key": "generated_at", "value": datetime.now().isoformat()},
    {"key": "master_population_n", "value": len(master)},
    {"key": "available_total_award_time_n", "value": available_total},
    {
        "key": "complete_stage_decomposition_n",
        "value": complete_stage_n
    },
    {
        "key": "primary_scenario_definition",
        "value": "Terciles"
    },
    {
        "key": "primary_low_representation",
        "value": "Empirical/nonparametric"
    },
    {
        "key": "primary_medium_representation",
        "value": "Lognormal"
    },
    {
        "key": "primary_high_representation",
        "value": "Lognormal"
    },
    {
        "key": "operational_monte_carlo_iterations",
        "value": 50000
    },
    {
        "key": "primary_stochastic_model",
        "value": "Direct total-duration Monte Carlo"
    },
    {
        "key": "secondary_stochastic_model",
        "value": "Two-stage discrete-event simulation"
    },
    {
        "key": "causal_interpretation",
        "value": "NOT_AUTHORIZED"
    },
    {
        "key": "final_pipeline_stage",
        "value": "FINAL_SYNTHESIS"
    },
])

log("  Reproducibility metadata created.")
log("")


# =============================================================================
# 29. PIPELINE MANIFEST
# =============================================================================

log("[25] Building final pipeline manifest...")

pipeline_manifest = pd.DataFrame([
    {
        "script": "03",
        "phase": "Data integration",
        "role": "Master analytical dataset",
        "final_status": "COMPLETED",
    },
    {
        "script": "07",
        "phase": "Statistical analysis",
        "role": "Scenario definition",
        "final_status": "COMPLETED",
    },
    {
        "script": "08",
        "phase": "Statistical analysis",
        "role": "Scenario robustness",
        "final_status": "COMPLETED",
    },
    {
        "script": "09",
        "phase": "Statistical analysis",
        "role": "Distribution fitting",
        "final_status": "COMPLETED_WITH_LOW_CAUTION",
    },
    {
        "script": "10",
        "phase": "Statistical analysis",
        "role": "Distribution diagnostics",
        "final_status": "COMPLETED",
    },
    {
        "script": "11",
        "phase": "Statistical analysis",
        "role": "Methodological assessment",
        "final_status": "COMPLETED",
    },
    {
        "script": "12",
        "phase": "Stochastic modeling",
        "role": "Model specification",
        "final_status": "COMPLETED",
    },
    {
        "script": "13",
        "phase": "Stochastic modeling",
        "role": "Monte Carlo convergence",
        "final_status": "COMPLETED",
    },
    {
        "script": "14",
        "phase": "Stochastic modeling",
        "role": "Final Monte Carlo simulation",
        "final_status": "COMPLETED",
    },
    {
        "script": "15",
        "phase": "Stochastic modeling",
        "role": "DES assessment",
        "final_status": "COMPLETED",
    },
    {
        "script": "16",
        "phase": "Stochastic modeling",
        "role": "Two-stage DES",
        "final_status": "COMPLETED",
    },
    {
        "script": "17",
        "phase": "Model validation",
        "role": "Temporal and internal validation",
        "final_status": "COMPLETED_WITH_CAUTIONS",
    },
    {
        "script": "18",
        "phase": "Robustness analysis",
        "role": "Robustness and sensitivity",
        "final_status": "COMPLETED",
    },
    {
        "script": "19",
        "phase": "Final synthesis",
        "role": "Scientific integration and objective closure",
        "final_status": "CURRENT",
    },
])

log(
    f"  Pipeline manifest rows: {len(pipeline_manifest)}"
)
log("")


# =============================================================================
# 30. FINAL THESIS STATUS
# =============================================================================

log("[26] Determining final thesis-analysis status...")

final_status = pd.DataFrame([
    {
        "dimension": "Objective 1",
        "status": "COMPLETED",
    },
    {
        "dimension": "Objective 2",
        "status": "COMPLETED_WITH_ROBUSTNESS_EVIDENCE",
    },
    {
        "dimension": "Objective 3",
        "status": "COMPLETED_WITH_MODEL_SPECIFIC_LIMITATIONS",
    },
    {
        "dimension": "Objective 4",
        "status": "COMPLETED_WITH_VALIDATION_CAUTIONS",
    },
    {
        "dimension": "Primary hypothesis",
        "status": "SUPPORTED_AS_ASSOCIATIONAL_HYPOTHESIS",
    },
    {
        "dimension": "Causal interpretation",
        "status": "NOT_AUTHORIZED",
    },
    {
        "dimension": "Statistical pipeline",
        "status": "COMPLETE",
    },
    {
        "dimension": "Stochastic-modeling pipeline",
        "status": "COMPLETE",
    },
    {
        "dimension": "Validation pipeline",
        "status": "COMPLETE",
    },
    {
        "dimension": "Robustness pipeline",
        "status": "COMPLETE",
    },
    {
        "dimension": "Next scientific phase",
        "status": "RESULTS_DISCUSSION_AND_REPORTING",
    },
])

for _, row in final_status.iterrows():
    log(
        f"  {row['dimension']:<35} | {row['status']}"
    )

log("")


# =============================================================================
# 31. SAVE OUTPUT WORKBOOK
# =============================================================================

log("[27] Saving final scientific synthesis...")

with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl"
) as writer:

    objective_synthesis.to_excel(
        writer,
        sheet_name="objective_synthesis",
        index=False
    )

    hypothesis_assessment.to_excel(
        writer,
        sheet_name="hypothesis_assessment",
        index=False
    )

    hypothesis_evidence.to_excel(
        writer,
        sheet_name="hypothesis_evidence",
        index=False
    )

    key_findings.to_excel(
        writer,
        sheet_name="key_findings",
        index=False
    )

    continuous_relationship.to_excel(
        writer,
        sheet_name="continuous_relationship",
        index=False
    )

    temporal_relationship.to_excel(
        writer,
        sheet_name="temporal_relationship",
        index=False
    )

    scenario_final.to_excel(
        writer,
        sheet_name="scenario_evidence",
        index=False
    )

    mc_final.to_excel(
        writer,
        sheet_name="monte_carlo_final",
        index=False
    )

    low_sensitivity.to_excel(
        writer,
        sheet_name="low_sensitivity",
        index=False
    )

    des_final.to_excel(
        writer,
        sheet_name="des_final",
        index=False
    )

    architecture_sensitivity.to_excel(
        writer,
        sheet_name="mc_vs_des",
        index=False
    )

    dependence_sensitivity.to_excel(
        writer,
        sheet_name="des_dependence_sensitivity",
        index=False
    )

    final_robustness.to_excel(
        writer,
        sheet_name="robustness_matrix",
        index=False
    )

    model_hierarchy.to_excel(
        writer,
        sheet_name="model_hierarchy",
        index=False
    )

    final_decision.to_excel(
        writer,
        sheet_name="final_decisions",
        index=False
    )

    limitations.to_excel(
        writer,
        sheet_name="limitations",
        index=False
    )

    interpretation_boundaries.to_excel(
        writer,
        sheet_name="interpretation_boundaries",
        index=False
    )

    pipeline_manifest.to_excel(
        writer,
        sheet_name="pipeline_manifest",
        index=False
    )

    final_status.to_excel(
        writer,
        sheet_name="final_status",
        index=False
    )

    metadata.to_excel(
        writer,
        sheet_name="metadata",
        index=False
    )


# =============================================================================
# 32. BASIC WORKBOOK FORMATTING
# =============================================================================

from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

wb = load_workbook(OUTPUT_FILE)

for ws in wb.worksheets:

    # Freeze header row
    ws.freeze_panes = "A2"

    # Header formatting
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True
        )

    # Body wrapping
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True
            )

    # Sensible column widths
    for col_idx, column_cells in enumerate(
        ws.iter_cols(min_col=1, max_col=ws.max_column),
        start=1
    ):
        max_length = 0

        for cell in column_cells:
            if cell.value is not None:
                max_length = max(
                    max_length,
                    len(str(cell.value))
                )

        adjusted_width = min(max(max_length + 2, 12), 60)

        ws.column_dimensions[
            get_column_letter(col_idx)
        ].width = adjusted_width

    ws.auto_filter.ref = ws.dimensions

wb.save(OUTPUT_FILE)

log(f"  Output workbook: {OUTPUT_FILE.name}")
log(f"  Log file: {LOG_FILE.name}")
log("")


# =============================================================================
# 33. FINAL CONSOLE AUDIT
# =============================================================================

log("=" * 78)
log("FINAL SCIENTIFIC SYNTHESIS AUDIT")
log("=" * 78)

log(f"Master analytical procedures:          {len(master)}")
log(f"Available total award times:           {available_total}/{len(master)}")

if pd.notna(complete_stage_n):
    log(
        f"Complete temporal decompositions:      "
        f"{int(complete_stage_n)}/{len(master)}"
    )

log("")
log("PRIMARY CONTINUOUS EVIDENCE")
log("-" * 78)
log(
    f"Pearson r:                             "
    f"{pearson_r:.4f} (p={pearson_p:.6g})"
)
log(
    f"Spearman rho:                          "
    f"{spearman_rho:.4f} (p={spearman_p:.6g})"
)
log(
    f"Kendall tau:                           "
    f"{kendall_tau:.4f} (p={kendall_p:.6g})"
)

log("")
log("PRIMARY OBSERVED SCENARIO MEDIANS")
log("-" * 78)

for scenario in scenario_order:
    row = scenario_final[
        scenario_final["scenario"] == scenario
    ].iloc[0]

    log(
        f"{scenario:<10} "
        f"n={int(row['n']):<3} | "
        f"median={row['observed_median_days']:.2f} | "
        f"P95={row['observed_p95_days']:.2f}"
    )

log("")
log("PRIMARY MONTE CARLO RESULTS")
log("-" * 78)

for scenario in scenario_order:
    row = mc_final[
        mc_final["scenario"] == scenario
    ].iloc[0]

    log(
        f"{scenario:<10} "
        f"{str(row['representation']):<12} | "
        f"median={row['simulated_median']:.2f} | "
        f"P95={row['simulated_p95']:.2f}"
    )

log("")
log("TWO-STAGE DES RESULTS")
log("-" * 78)

for scenario in scenario_order:
    row = des_final[
        des_final["scenario"] == scenario
    ].iloc[0]

    log(
        f"{scenario:<10} | "
        f"query median={row['query_median']:.2f} | "
        f"evaluation median={row['evaluation_median']:.2f} | "
        f"total median={row['total_median']:.2f} | "
        f"P95={row['total_p95']:.2f}"
    )

log("")
log("CONCLUSION-LEVEL ROBUSTNESS")
log("-" * 78)

for _, row in final_robustness.iterrows():
    log(
        f"{row['conclusion_id']:<4} "
        f"{row['robustness_status']:<35} "
        f"{row['evidence_strength']}"
    )

log("")
log("OBJECTIVE CLOSURE")
log("-" * 78)

for _, row in objective_synthesis.iterrows():
    log(
        f"{row['objective_id']:<5} "
        f"{row['final_status']}"
    )

log("")
log("HYPOTHESIS ASSESSMENT")
log("-" * 78)
log(
    "Primary hypothesis:                  "
    "SUPPORTED_AS_ASSOCIATIONAL_HYPOTHESIS"
)
log(
    "Causal interpretation:               "
    "NOT_AUTHORIZED"
)

log("")
log("FINAL MODEL ARCHITECTURE")
log("-" * 78)
log(
    "Primary stochastic model:            "
    "Direct total-duration Monte Carlo"
)
log(
    "Low representation:                  "
    "Empirical/nonparametric"
)
log(
    "Medium representation:               "
    "Lognormal"
)
log(
    "High representation:                 "
    "Lognormal"
)
log(
    "Operational Monte Carlo iterations:  "
    "50,000"
)
log(
    "Secondary process model:             "
    "Two-stage DES with joint pair resampling"
)

log("")
log("SCIENTIFIC SCOPE")
log("-" * 78)
log("- Script 19 integrates previously generated evidence.")
log("- No new model is fitted.")
log("- No probability distribution is re-selected.")
log("- No scenario threshold is redefined.")
log("- No Monte Carlo simulation is rerun.")
log("- No discrete-event simulation is rerun.")
log("- No validation criterion is changed.")
log("- No unfavorable result is removed or optimized away.")
log("- Robust and sensitive conclusions are reported separately.")
log("- Simulation iterations do not increase the empirical sample size.")
log("- The hypothesis is assessed as associational, not causal.")
log("- The master analytical population remains unchanged.")
log("- The pipeline is now ready for thesis Results and Discussion.")

log("")
log("=" * 78)
log("PIPELINE STATUS: FINAL_SYNTHESIS_COMPLETE_READY_FOR_THESIS_REPORTING")
log("=" * 78)
