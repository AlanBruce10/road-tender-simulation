"""
===============================================================================
SCRIPT 12 - STOCHASTIC MODEL SPECIFICATION
===============================================================================

Project:
    Stochastic simulation of information asymmetry and award-time uncertainty
    in Peruvian road-infrastructure tenders.

Purpose:
    Convert the empirical evidence produced by Scripts 03-11 into an explicit,
    reproducible, and auditable stochastic-model specification.

Scientific role:
    This script DOES NOT perform Monte Carlo simulation.
    This script DOES NOT perform discrete-event simulation.
    This script DOES NOT choose an iteration count.

    Instead, it establishes:

    1. The primary stochastic outcome.
    2. The information-asymmetry exposure variable.
    3. The primary scenario representation.
    4. Scenario-specific probability-model readiness.
    5. The treatment of the Low-scenario distributional caution.
    6. The role of alternative scenario definitions.
    7. The quantities that a later simulation should estimate.
    8. Explicit authorization gates for Monte Carlo and DES.
    9. A prespecified convergence protocol for a later script.

Inputs:
    02_results/03_1_integrated_dataset.xlsx
    02_results/statistical_analysis/07_1_scenario_definition.xlsx
    02_results/statistical_analysis/08_1_scenario_robustness.xlsx
    02_results/statistical_analysis/09_1_distribution_fitting.xlsx
    02_results/statistical_analysis/10_1_distribution_diagnostics.xlsx
    02_results/statistical_analysis/11_1_methodological_assessment.xlsx

Outputs:
    02_results/stochastic_modeling/12_1_model_specification.xlsx
    03_logs/stochastic_modeling/12_model_specification.log

Important:
    The specification is evidence-driven but deliberately conservative.
    No final stochastic model is declared valid merely because it was proposed
    in the original thesis protocol.

===============================================================================
"""

from pathlib import Path
import sys
import logging
import platform
from datetime import datetime

import numpy as np
import pandas as pd


# =============================================================================
# CONFIGURATION
# =============================================================================

MASTER_SAMPLE_SIZE = 137
RANDOM_SEED = 2026

ROOT = Path(__file__).resolve().parents[2]

INPUT_MASTER = ROOT / "02_results" / "03_1_integrated_dataset.xlsx"

STAT_RESULTS = ROOT / "02_results" / "statistical_analysis"

INPUT_07 = STAT_RESULTS / "07_1_scenario_definition.xlsx"
INPUT_08 = STAT_RESULTS / "08_1_scenario_robustness.xlsx"
INPUT_09 = STAT_RESULTS / "09_1_distribution_fitting.xlsx"
INPUT_10 = STAT_RESULTS / "10_1_distribution_diagnostics.xlsx"
INPUT_11 = STAT_RESULTS / "11_1_methodological_assessment.xlsx"

OUTPUT_DIR = ROOT / "02_results" / "stochastic_modeling"
LOG_DIR = ROOT / "03_logs" / "stochastic_modeling"

OUTPUT_FILE = OUTPUT_DIR / "12_1_model_specification.xlsx"
LOG_FILE = LOG_DIR / "12_model_specification.log"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("model_specification")
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


def separator():
    log("=" * 78)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def require_file(path):
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")


def require_columns(df, columns, dataset_name):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"{dataset_name} is missing required columns: {missing}"
        )


def safe_sheet(path, sheet_name):
    xls = pd.ExcelFile(path)

    if sheet_name not in xls.sheet_names:
        raise ValueError(
            f"Required sheet '{sheet_name}' not found in "
            f"{path.name}. Available sheets: {xls.sheet_names}"
        )

    return pd.read_excel(path, sheet_name=sheet_name)


def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def readiness_from_bootstrap_p(p_value, alpha=0.05):
    if pd.isna(p_value):
        return "NOT_ASSESSED"
    if p_value >= alpha:
        return "READY"
    return "CAUTION"


# =============================================================================
# HEADER
# =============================================================================

separator()
log("STOCHASTIC MODEL SPECIFICATION - ROAD INFRASTRUCTURE TENDERS")
separator()
log("Purpose: Translate Scripts 03-11 into an explicit stochastic-model protocol")
log("IMPORTANT: No Monte Carlo or discrete-event simulation is performed here.")
log()


# =============================================================================
# 1. VALIDATE INPUT FILES
# =============================================================================

log("[1] Validating analytical inputs...")

input_files = [
    INPUT_MASTER,
    INPUT_07,
    INPUT_08,
    INPUT_09,
    INPUT_10,
    INPUT_11,
]

for path in input_files:
    require_file(path)
    log(f"  Found: {path.name}")

log()


# =============================================================================
# 2. READ CORE DATASETS
# =============================================================================

log("[2] Reading source datasets...")

master = pd.read_excel(INPUT_MASTER)

scenario_audit = safe_sheet(INPUT_07, "procedure_audit")
scenario_framework = safe_sheet(INPUT_07, "decision_framework")

robustness = safe_sheet(INPUT_08, "robustness_summary")
modeling_readiness = safe_sheet(INPUT_08, "modeling_readiness")

distribution_fits = safe_sheet(INPUT_09, "distribution_fits")
bootstrap_gof = safe_sheet(INPUT_09, "bootstrap_gof")
selection_audit = safe_sheet(INPUT_09, "selection_audit")

shape_diagnostics = safe_sheet(INPUT_10, "shape_diagnostics")
tail_sensitivity = safe_sheet(INPUT_10, "tail_sensitivity")
diagnostic_framework = safe_sheet(INPUT_10, "diagnostic_framework")

log(f"  Master rows: {len(master)}")
log(f"  Scenario-audit rows: {len(scenario_audit)}")
log(f"  Distribution-fit rows: {len(distribution_fits)}")
log()


# =============================================================================
# 3. VALIDATE ANALYTICAL CONTRACT
# =============================================================================

log("[3] Validating analytical contract...")

require_columns(
    master,
    [
        "procedure_code",
        "queries_observations_count",
        "total_award_time_days",
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
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
    "Script 07 procedure audit"
)

require_columns(
    selection_audit,
    [
        "method",
        "scenario",
        "n",
        "aic_preferred_distribution",
        "bootstrap_ks_p",
        "decision_flag",
    ],
    "Script 09 selection audit"
)

if len(master) != MASTER_SAMPLE_SIZE:
    raise ValueError(
        f"Expected master analytical sample n={MASTER_SAMPLE_SIZE}, "
        f"found n={len(master)}"
    )

if master["procedure_code"].duplicated().any():
    raise ValueError("Duplicate procedure_code values detected in master dataset.")

if scenario_audit["procedure_code"].duplicated().any():
    raise ValueError("Duplicate procedure_code values detected in scenario audit.")

master_codes = set(master["procedure_code"].astype(int))
scenario_codes = set(scenario_audit["procedure_code"].astype(int))

if master_codes != scenario_codes:
    raise ValueError(
        "Procedure-code mismatch between master dataset and Script 07."
    )

query_coverage = master["queries_observations_count"].notna().sum()
total_time_coverage = master["total_award_time_days"].notna().sum()

stage_complete = master[
    [
        "query_stage_duration_days",
        "evaluation_stage_duration_days"
    ]
].notna().all(axis=1).sum()

log(f"  Master analytical sample verified: {len(master)}")
log(f"  Query-count coverage: {query_coverage}/{len(master)}")
log(f"  Total-award-time coverage: {total_time_coverage}/{len(master)}")
log(f"  Complete stage decompositions: {stage_complete}/{len(master)}")
log()


# =============================================================================
# 4. DEFINE PRIMARY SCIENTIFIC VARIABLES
# =============================================================================

log("[4] Defining primary scientific variables...")

variable_specification = pd.DataFrame([
    {
        "role": "exposure",
        "variable": "queries_observations_count",
        "concept": "Observed volume of queries and observations",
        "analytical_role":
            "Primary empirical proxy for information-asymmetry / "
            "pre-award informational friction",
        "scale": "Count",
        "primary_or_secondary": "PRIMARY",
        "missing_n": int(
            master["queries_observations_count"].isna().sum()
        ),
        "scientific_note":
            "Retained continuously for relationship analysis and categorized "
            "only when scenario-based stochastic representation is required."
    },
    {
        "role": "outcome",
        "variable": "total_award_time_days",
        "concept": "Total award time",
        "analytical_role":
            "Primary stochastic outcome from notice date to award date",
        "scale": "Positive duration in calendar days",
        "primary_or_secondary": "PRIMARY",
        "missing_n": int(
            master["total_award_time_days"].isna().sum()
        ),
        "scientific_note":
            "Primary outcome because coverage is substantially higher than "
            "stage-level temporal decomposition."
    },
    {
        "role": "secondary_outcome",
        "variable": "query_stage_duration_days",
        "concept": "Query/integration-stage duration",
        "analytical_role":
            "Stage-level outcome for possible process decomposition",
        "scale": "Positive duration in calendar days",
        "primary_or_secondary": "SECONDARY",
        "missing_n": int(
            master["query_stage_duration_days"].isna().sum()
        ),
        "scientific_note":
            "Reserved for DES feasibility and secondary analysis because "
            "stage-level coverage is incomplete."
    },
    {
        "role": "secondary_outcome",
        "variable": "evaluation_stage_duration_days",
        "concept": "Evaluation/award-stage duration",
        "analytical_role":
            "Stage-level outcome for possible process decomposition",
        "scale": "Positive duration in calendar days",
        "primary_or_secondary": "SECONDARY",
        "missing_n": int(
            master["evaluation_stage_duration_days"].isna().sum()
        ),
        "scientific_note":
            "Reserved for DES feasibility and secondary analysis because "
            "stage-level coverage is incomplete."
    }
])

for _, row in variable_specification.iterrows():
    log(
        f"  {row['primary_or_secondary']}: "
        f"{row['variable']} -> {row['analytical_role']}"
    )

log()


# =============================================================================
# 5. SPECIFY SCENARIO ROLES
# =============================================================================

log("[5] Specifying scenario-definition roles...")

scenario_roles = pd.DataFrame([
    {
        "method": "Terciles",
        "source_column": "scenario_terciles",
        "modeling_role": "PRIMARY",
        "rationale":
            "Balanced group sizes, strong ordered award-time pattern, "
            "and adequate sample size in all three scenarios.",
        "threshold_optimization_on_outcome": False
    },
    {
        "method": "P25_P75",
        "source_column": "scenario_p25_p75",
        "modeling_role": "ROBUSTNESS",
        "rationale":
            "Alternative quantile-based definition used to test sensitivity "
            "of conclusions to scenario thresholds.",
        "threshold_optimization_on_outcome": False
    },
    {
        "method": "Data_driven_1D",
        "source_column": "scenario_data_driven",
        "modeling_role": "SENSITIVITY_ONLY",
        "rationale":
            "Query-count-only clustering retained for sensitivity; high "
            "scenario is too small for equal modeling status.",
        "threshold_optimization_on_outcome": False
    }
])

for _, row in scenario_roles.iterrows():
    log(
        f"  {row['method']}: {row['modeling_role']} | "
        f"{row['rationale']}"
    )

log()


# =============================================================================
# 6. AUDIT PRIMARY TERCILE SAMPLE
# =============================================================================

log("[6] Auditing primary tercile scenario sample...")

primary = scenario_audit.copy()

primary["scenario"] = primary["scenario_terciles"]

scenario_order = ["Low", "Medium", "High"]

primary_rows = []

for scenario in scenario_order:
    group = primary.loc[
        primary["scenario"] == scenario,
        "total_award_time_days"
    ].dropna()

    query_group = primary.loc[
        primary["scenario"] == scenario,
        "queries_observations_count"
    ].dropna()

    if len(group) == 0:
        raise ValueError(f"No award-time observations for scenario {scenario}")

    primary_rows.append({
        "scenario": scenario,
        "n_scenario_total": int(
            (primary["scenario"] == scenario).sum()
        ),
        "n_award_time_available": int(len(group)),
        "n_award_time_missing": int(
            (primary["scenario"] == scenario).sum() - len(group)
        ),
        "query_min": float(query_group.min()),
        "query_max": float(query_group.max()),
        "award_time_min": float(group.min()),
        "award_time_median": float(group.median()),
        "award_time_mean": float(group.mean()),
        "award_time_std": float(group.std(ddof=1)),
        "award_time_p90": float(group.quantile(0.90)),
        "award_time_max": float(group.max()),
        "unique_award_times": int(group.nunique())
    })

primary_scenario_audit = pd.DataFrame(primary_rows)

for _, row in primary_scenario_audit.iterrows():
    log(
        f"  {row['scenario']}: "
        f"n={int(row['n_award_time_available'])}; "
        f"queries={row['query_min']:.0f}-{row['query_max']:.0f}; "
        f"median={row['award_time_median']:.2f}; "
        f"SD={row['award_time_std']:.2f}"
    )

log()


# =============================================================================
# 7. CONSOLIDATE PROBABILITY-MODEL EVIDENCE
# =============================================================================

log("[7] Consolidating probability-model evidence...")

primary_selection = selection_audit[
    selection_audit["method"].astype(str).str.lower().eq("terciles")
].copy()

if primary_selection.empty:
    # Defensive fallback in case method naming differs slightly.
    primary_selection = selection_audit[
        selection_audit["scenario"].isin(scenario_order)
    ].copy()

probability_rows = []

for scenario in scenario_order:
    subset = primary_selection[
        primary_selection["scenario"].astype(str).str.lower()
        == scenario.lower()
    ]

    if subset.empty:
        raise ValueError(
            f"Script 09 selection audit contains no record for {scenario}."
        )

    row = subset.iloc[0]

    preferred_distribution = normalize_text(
        row["aic_preferred_distribution"]
    )

    bootstrap_p = pd.to_numeric(
        pd.Series([row["bootstrap_ks_p"]]),
        errors="coerce"
    ).iloc[0]

    gof_status = readiness_from_bootstrap_p(bootstrap_p)

    if scenario == "Low" and gof_status == "CAUTION":
        final_role = "UNRESOLVED_PRIMARY_CAUTION"
        authorization = "NOT_AUTHORIZED_AS_SOLE_PARAMETRIC_MODEL"
    elif gof_status == "READY":
        final_role = "PARAMETRIC_CANDIDATE"
        authorization = "AUTHORIZED_FOR_CONVERGENCE_TESTING"
    else:
        final_role = "REQUIRES_REVIEW"
        authorization = "NOT_YET_AUTHORIZED"

    probability_rows.append({
        "scenario": scenario,
        "n": int(row["n"]),
        "aic_preferred_distribution": preferred_distribution,
        "bootstrap_ks_p": float(bootstrap_p)
            if pd.notna(bootstrap_p) else np.nan,
        "goodness_of_fit_readiness": gof_status,
        "modeling_status": final_role,
        "simulation_authorization": authorization,
        "script09_decision_flag": normalize_text(
            row["decision_flag"]
        )
    })

probability_specification = pd.DataFrame(probability_rows)

for _, row in probability_specification.iterrows():
    log(
        f"  {row['scenario']}: "
        f"{row['aic_preferred_distribution']} | "
        f"bootstrap KS p={row['bootstrap_ks_p']:.4f} | "
        f"{row['simulation_authorization']}"
    )

log()


# =============================================================================
# 8. SPECIFY LOW-SCENARIO MODELING PROTOCOL
# =============================================================================

log("[8] Specifying Low-scenario modeling protocol...")

low_row = probability_specification[
    probability_specification["scenario"] == "Low"
].iloc[0]

low_protocol = pd.DataFrame([
    {
        "priority": 1,
        "representation":
            "Observed empirical distribution / nonparametric resampling",
        "role": "PRIMARY_ROBUST_REPRESENTATION_CANDIDATE",
        "reason":
            "The preferred simple parametric distribution does not pass "
            "the bootstrap goodness-of-fit diagnostic.",
        "allowed_in_next_phase": True,
        "restriction":
            "Must preserve the observed Low-scenario sample and must not "
            "manufacture additional independent information."
    },
    {
        "priority": 2,
        "representation":
            f"{low_row['aic_preferred_distribution']} parametric model",
        "role": "PARAMETRIC_SENSITIVITY",
        "reason":
            "Retained because it was information-criterion preferred, but "
            "goodness-of-fit caution prevents sole-model status.",
        "allowed_in_next_phase": True,
        "restriction":
            "Results must be reported as sensitivity analysis and not as "
            "the uniquely validated Low-scenario data-generating process."
    },
    {
        "priority": 3,
        "representation":
            "Alternative flexible model",
        "role": "FUTURE_OPTION_IF_NEEDED",
        "reason":
            "May be evaluated only if empirical and simple parametric "
            "representations are insufficient for the scientific target.",
        "allowed_in_next_phase": False,
        "restriction":
            "Must not be selected opportunistically solely to obtain a "
            "non-significant goodness-of-fit p-value."
    }
])

for _, row in low_protocol.iterrows():
    log(
        f"  Priority {row['priority']}: "
        f"{row['representation']} -> {row['role']}"
    )

log("  NOTE: No new distribution is selected in Script 12.")
log()


# =============================================================================
# 9. DEFINE STOCHASTIC TARGETS
# =============================================================================

log("[9] Defining stochastic quantities of interest...")

simulation_targets = pd.DataFrame([
    {
        "target_id": "T1",
        "quantity": "Expected award time",
        "symbolic_target": "E[T | scenario]",
        "purpose":
            "Estimate scenario-specific central expected duration.",
        "priority": "PRIMARY"
    },
    {
        "target_id": "T2",
        "quantity": "Median award time",
        "symbolic_target": "Median[T | scenario]",
        "purpose":
            "Provide a robust scenario-specific central duration.",
        "priority": "PRIMARY"
    },
    {
        "target_id": "T3",
        "quantity": "Award-time standard deviation",
        "symbolic_target": "SD[T | scenario]",
        "purpose":
            "Quantify scenario-specific temporal uncertainty.",
        "priority": "PRIMARY"
    },
    {
        "target_id": "T4",
        "quantity": "Upper quantiles",
        "symbolic_target": "Q90, Q95",
        "purpose":
            "Characterize upper-tail scheduling risk.",
        "priority": "PRIMARY"
    },
    {
        "target_id": "T5",
        "quantity": "Exceedance probability",
        "symbolic_target": "P(T > t*)",
        "purpose":
            "Estimate probability of exceeding prespecified duration "
            "thresholds.",
        "priority": "SECONDARY"
    },
    {
        "target_id": "T6",
        "quantity": "Scenario contrasts",
        "symbolic_target":
            "Delta(Low,Medium,High)",
        "purpose":
            "Quantify how simulated temporal distributions differ across "
            "information-asymmetry scenarios.",
        "priority": "PRIMARY"
    }
])

for _, row in simulation_targets.iterrows():
    log(
        f"  {row['target_id']}: {row['quantity']} "
        f"[{row['priority']}]"
    )

log()


# =============================================================================
# 10. DEFINE MONTE CARLO AUTHORIZATION GATES
# =============================================================================

log("[10] Defining Monte Carlo authorization gates...")

mc_gates = pd.DataFrame([
    {
        "gate_id": "MC1",
        "criterion": "Empirical stochastic variability exists",
        "status": "PASS",
        "evidence":
            "Scripts 04, 08, and 11 show non-degenerate within-scenario "
            "award-time variability."
    },
    {
        "gate_id": "MC2",
        "criterion": "Scenario structure is empirically reproducible",
        "status": "PASS",
        "evidence":
            "Scripts 07, 08, and 11 show ordered and robust "
            "Low-Medium-High patterns."
    },
    {
        "gate_id": "MC3",
        "criterion": "Probability representation specified by scenario",
        "status": "PARTIAL",
        "evidence":
            "Medium and High have supported parametric candidates; "
            "Low requires dual empirical/parametric treatment."
    },
    {
        "gate_id": "MC4",
        "criterion": "Simulation estimands are prespecified",
        "status": "PASS",
        "evidence":
            "Script 12 prespecifies central tendency, dispersion, "
            "upper quantiles, exceedance, and scenario contrasts."
    },
    {
        "gate_id": "MC5",
        "criterion": "Iteration count empirically justified",
        "status": "PENDING",
        "evidence":
            "No fixed iteration count is accepted yet. "
            "A convergence experiment is required."
    },
    {
        "gate_id": "MC6",
        "criterion": "Reproducibility protocol established",
        "status": "PASS",
        "evidence":
            f"Fixed seed framework established; base seed={RANDOM_SEED}."
    }
])

for _, row in mc_gates.iterrows():
    log(
        f"  {row['gate_id']} | {row['status']:<7} | "
        f"{row['criterion']}"
    )

log()


# =============================================================================
# 11. PRESPECIFY MONTE CARLO CONVERGENCE EXPERIMENT
# =============================================================================

log("[11] Prespecifying Monte Carlo convergence experiment...")

iteration_grid = [
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

convergence_rows = []

for n_iter in iteration_grid:
    convergence_rows.append({
        "iterations": n_iter,
        "evaluate_mean": True,
        "evaluate_median": True,
        "evaluate_std": True,
        "evaluate_p90": True,
        "evaluate_p95": True,
        "evaluate_exceedance_probability": True,
        "status": "TO_BE_TESTED_IN_SCRIPT_13"
    })

convergence_protocol = pd.DataFrame(convergence_rows)

convergence_criteria = pd.DataFrame([
    {
        "criterion_id": "C1",
        "quantity": "Mean",
        "proposed_rule":
            "Assess stabilization relative to a high-iteration reference "
            "and across independent seeds.",
        "final_tolerance_selected": False
    },
    {
        "criterion_id": "C2",
        "quantity": "Standard deviation",
        "proposed_rule":
            "Assess stabilization relative to a high-iteration reference "
            "and across independent seeds.",
        "final_tolerance_selected": False
    },
    {
        "criterion_id": "C3",
        "quantity": "P90 and P95",
        "proposed_rule":
            "Assess upper-quantile stabilization because tail estimates "
            "generally converge more slowly than means.",
        "final_tolerance_selected": False
    },
    {
        "criterion_id": "C4",
        "quantity": "Between-seed variability",
        "proposed_rule":
            "Repeat simulation under multiple deterministic seeds and "
            "quantify numerical variability.",
        "final_tolerance_selected": False
    },
    {
        "criterion_id": "C5",
        "quantity": "Minimum sufficient iterations",
        "proposed_rule":
            "Select the smallest iteration count after which all primary "
            "targets remain numerically stable under prespecified tolerances.",
        "final_tolerance_selected": False
    }
])

log("  Candidate iteration grid:")
log(
    "  " + ", ".join(f"{x:,}" for x in iteration_grid)
)

log()
log("  IMPORTANT:")
log("  10,000 iterations is included as a candidate, not as a predetermined answer.")
log("  Script 13 must determine whether fewer or more iterations are required.")
log()


# =============================================================================
# 12. DEFINE DISCRETE-EVENT SIMULATION GATES
# =============================================================================

log("[12] Defining discrete-event simulation authorization gates...")

stage_coverage_pct = stage_complete / len(master) * 100

stage_complete_df = master[
    [
        "query_stage_duration_days",
        "evaluation_stage_duration_days"
    ]
].dropna()

if len(stage_complete_df) > 2:
    stage_spearman = stage_complete_df.corr(
        method="spearman"
    ).iloc[0, 1]
else:
    stage_spearman = np.nan

des_gates = pd.DataFrame([
    {
        "gate_id": "DES1",
        "criterion": "Stage-level durations available",
        "status": "CAUTION",
        "evidence":
            f"{stage_complete}/{len(master)} "
            f"({stage_coverage_pct:.2f}%) complete stage decompositions."
    },
    {
        "gate_id": "DES2",
        "criterion": "Stage arithmetic is structurally interpretable",
        "status": "PASS",
        "evidence":
            "Earlier diagnostics verified exact reconstruction of total "
            "duration for complete stage records."
    },
    {
        "gate_id": "DES3",
        "criterion": "Dependence between stages explicitly considered",
        "status": "CAUTION",
        "evidence":
            f"Observed stage-duration Spearman correlation="
            f"{stage_spearman:.4f}; independent stage generation must not "
            f"be assumed automatically."
    },
    {
        "gate_id": "DES4",
        "criterion": "Incremental scientific value beyond direct duration simulation",
        "status": "PENDING",
        "evidence":
            "A later assessment must show that modeling process stages adds "
            "information beyond scenario-level total-time simulation."
    },
    {
        "gate_id": "DES5",
        "criterion": "Final DES authorization",
        "status": "PENDING",
        "evidence":
            "DES remains conditional and is not authorized by Script 12."
    }
])

for _, row in des_gates.iterrows():
    log(
        f"  {row['gate_id']} | {row['status']:<7} | "
        f"{row['criterion']}"
    )

log()


# =============================================================================
# 13. DEFINE MODEL HIERARCHY
# =============================================================================

log("[13] Defining model hierarchy...")

model_hierarchy = pd.DataFrame([
    {
        "level": 1,
        "model_component": "Continuous empirical relationship",
        "role":
            "Scientific reference relationship between query/observation "
            "count and total award time",
        "status": "SUPPORTED",
        "source_evidence": "Scripts 04, 06, 11"
    },
    {
        "level": 2,
        "model_component": "Tercile scenario representation",
        "role":
            "Primary categorical representation for scenario-based "
            "stochastic analysis",
        "status": "SUPPORTED",
        "source_evidence": "Scripts 07, 08, 11"
    },
    {
        "level": 3,
        "model_component": "Scenario-specific probability representation",
        "role":
            "Generate or resample plausible award-time realizations "
            "conditional on scenario",
        "status": "PARTIALLY_SUPPORTED",
        "source_evidence": "Scripts 09, 10, 11, 12"
    },
    {
        "level": 4,
        "model_component": "Monte Carlo uncertainty propagation",
        "role":
            "Propagate scenario-specific stochastic uncertainty and estimate "
            "prespecified simulation targets",
        "status": "CONDITIONAL",
        "source_evidence":
            "Requires successful Script 13 convergence analysis"
    },
    {
        "level": 5,
        "model_component": "Discrete-event representation",
        "role":
            "Potentially represent temporal stages explicitly if incremental "
            "scientific value is demonstrated",
        "status": "CONDITIONAL",
        "source_evidence":
            "Requires separate DES assessment"
    },
    {
        "level": 6,
        "model_component": "Validation and sensitivity analysis",
        "role":
            "Evaluate whether conclusions survive alternative representations, "
            "time periods, and stochastic assumptions",
        "status": "REQUIRED_LATER",
        "source_evidence": "Future scripts"
    }
])

for _, row in model_hierarchy.iterrows():
    log(
        f"  Level {row['level']}: "
        f"{row['model_component']} -> {row['status']}"
    )

log()


# =============================================================================
# 14. DEFINE MODELING DECISIONS AND NON-DECISIONS
# =============================================================================

log("[14] Recording methodological decisions and unresolved decisions...")

decision_register = pd.DataFrame([
    {
        "decision": "Primary stochastic outcome",
        "status": "DECIDED",
        "value": "total_award_time_days",
        "basis": "Coverage and direct alignment with award-time objective."
    },
    {
        "decision": "Primary information-asymmetry proxy",
        "status": "DECIDED",
        "value": "queries_observations_count",
        "basis": "Prespecified empirical variable and complete coverage."
    },
    {
        "decision": "Primary scenario definition",
        "status": "DECIDED_FOR_MODELING",
        "value": "Terciles",
        "basis":
            "Balanced sample sizes and robust ordered temporal differences."
    },
    {
        "decision": "Robustness scenario definition",
        "status": "DECIDED",
        "value": "P25/P75",
        "basis":
            "Alternative quantile-based thresholds for sensitivity analysis."
    },
    {
        "decision": "Data-driven scenario role",
        "status": "DECIDED",
        "value": "Sensitivity only",
        "basis":
            "Small High group prevents equal inferential/modeling status."
    },
    {
        "decision": "Medium probability representation",
        "status": "CANDIDATE_AUTHORIZED",
        "value": "Script 09 AIC-preferred supported distribution",
        "basis": "Bootstrap goodness-of-fit support."
    },
    {
        "decision": "High probability representation",
        "status": "CANDIDATE_AUTHORIZED",
        "value": "Script 09 AIC-preferred supported distribution",
        "basis": "Bootstrap goodness-of-fit support."
    },
    {
        "decision": "Low probability representation",
        "status": "UNRESOLVED_WITH_PROTOCOL",
        "value":
            "Empirical/nonparametric primary robust candidate + "
            "parametric sensitivity",
        "basis":
            "Simple preferred parametric fit has bootstrap GOF caution."
    },
    {
        "decision": "Use Monte Carlo",
        "status": "CONDITIONAL",
        "value": "Not yet finally authorized",
        "basis":
            "Requires numerical convergence and final scenario probability "
            "representation."
    },
    {
        "decision": "Monte Carlo iterations",
        "status": "NOT_DECIDED",
        "value": "To be determined empirically",
        "basis":
            "10,000 cannot be justified merely because it appeared in the "
            "original protocol."
    },
    {
        "decision": "Use discrete-event simulation",
        "status": "CONDITIONAL",
        "value": "Not yet authorized",
        "basis":
            "Incomplete stage coverage, stage dependence, and incremental "
            "value must be evaluated."
    },
    {
        "decision": "Causal interpretation",
        "status": "NOT_AUTHORIZED",
        "value": "No",
        "basis":
            "Observational association does not establish causal effect."
    }
])

for _, row in decision_register.iterrows():
    log(
        f"  {row['decision']}: {row['status']} -> {row['value']}"
    )

log()


# =============================================================================
# 15. DEFINE NEXT-PHASE PROTOCOL
# =============================================================================

log("[15] Building prespecified next-phase protocol...")

next_phase_protocol = pd.DataFrame([
    {
        "order": 1,
        "script": "13_monte_carlo_convergence.py",
        "objective":
            "Evaluate numerical convergence across candidate iteration counts "
            "and independent deterministic seeds.",
        "decision_enabled":
            "Minimum sufficient Monte Carlo iteration count."
    },
    {
        "order": 2,
        "script": "14_monte_carlo_simulation.py",
        "objective":
            "Run final scenario-based stochastic simulation using only "
            "representations authorized by Scripts 12-13.",
        "decision_enabled":
            "Scenario-specific stochastic estimates and uncertainty."
    },
    {
        "order": 3,
        "script": "15_discrete_event_assessment.py",
        "objective":
            "Test whether explicit stage-level process simulation is feasible "
            "and scientifically additive.",
        "decision_enabled":
            "Whether DES should be implemented, modified, or omitted."
    },
    {
        "order": 4,
        "script": "16_model_validation.py",
        "objective":
            "Compare stochastic outputs against observed empirical behavior "
            "and temporal subsets.",
        "decision_enabled":
            "Validation status of the stochastic model."
    },
    {
        "order": 5,
        "script": "17_sensitivity_robustness.py",
        "objective":
            "Evaluate sensitivity to scenario thresholds, Low representation, "
            "distributional assumptions, and modeling choices.",
        "decision_enabled":
            "Robustness of substantive conclusions."
    }
])

for _, row in next_phase_protocol.iterrows():
    log(
        f"  {int(row['order'])}. {row['script']}: "
        f"{row['objective']}"
    )

log()


# =============================================================================
# 16. BUILD REPRODUCIBILITY METADATA
# =============================================================================

log("[16] Building reproducibility metadata...")

metadata = pd.DataFrame([
    {"field": "script", "value": "12_model_specification.py"},
    {"field": "generated_at", "value": datetime.now().isoformat()},
    {"field": "python_version", "value": platform.python_version()},
    {"field": "pandas_version", "value": pd.__version__},
    {"field": "numpy_version", "value": np.__version__},
    {"field": "master_sample_n", "value": len(master)},
    {"field": "primary_outcome_n", "value": total_time_coverage},
    {"field": "stage_complete_n", "value": stage_complete},
    {"field": "base_random_seed", "value": RANDOM_SEED},
    {
        "field": "monte_carlo_performed",
        "value": False
    },
    {
        "field": "discrete_event_simulation_performed",
        "value": False
    }
])

log("  Reproducibility metadata created.")
log()


# =============================================================================
# 17. SAVE OUTPUT WORKBOOK
# =============================================================================

log("[17] Saving reproducible model specification...")

with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl"
) as writer:

    variable_specification.to_excel(
        writer,
        sheet_name="variable_specification",
        index=False
    )

    scenario_roles.to_excel(
        writer,
        sheet_name="scenario_roles",
        index=False
    )

    primary_scenario_audit.to_excel(
        writer,
        sheet_name="primary_scenario_audit",
        index=False
    )

    probability_specification.to_excel(
        writer,
        sheet_name="probability_specification",
        index=False
    )

    low_protocol.to_excel(
        writer,
        sheet_name="low_scenario_protocol",
        index=False
    )

    simulation_targets.to_excel(
        writer,
        sheet_name="simulation_targets",
        index=False
    )

    mc_gates.to_excel(
        writer,
        sheet_name="monte_carlo_gates",
        index=False
    )

    convergence_protocol.to_excel(
        writer,
        sheet_name="convergence_grid",
        index=False
    )

    convergence_criteria.to_excel(
        writer,
        sheet_name="convergence_criteria",
        index=False
    )

    des_gates.to_excel(
        writer,
        sheet_name="des_gates",
        index=False
    )

    model_hierarchy.to_excel(
        writer,
        sheet_name="model_hierarchy",
        index=False
    )

    decision_register.to_excel(
        writer,
        sheet_name="decision_register",
        index=False
    )

    next_phase_protocol.to_excel(
        writer,
        sheet_name="next_phase_protocol",
        index=False
    )

    metadata.to_excel(
        writer,
        sheet_name="metadata",
        index=False
    )


log(f"  Output workbook: {OUTPUT_FILE.name}")
log(f"  Log file: {LOG_FILE.name}")
log()


# =============================================================================
# FINAL AUDIT
# =============================================================================

separator()
log("STOCHASTIC MODEL SPECIFICATION AUDIT")
separator()

log(f"Master analytical procedures:          {len(master)}")
log(f"Available total award times:           {total_time_coverage}")
log(f"Complete temporal decompositions:      {stage_complete}")
log()

log("PRIMARY MODEL ARCHITECTURE")
log("-" * 78)
log("Exposure:                              queries_observations_count")
log("Primary outcome:                       total_award_time_days")
log("Primary scenario definition:           Terciles")
log("Robustness scenario definition:        P25/P75")
log("Data-driven partition:                 Sensitivity only")
log()

log("PROBABILITY REPRESENTATION")
log("-" * 78)

for _, row in probability_specification.iterrows():
    log(
        f"{row['scenario']:<10} "
        f"{row['aic_preferred_distribution']:<15} "
        f"{row['goodness_of_fit_readiness']:<10} "
        f"{row['simulation_authorization']}"
    )

log()
log("MONTE CARLO STATUS")
log("-" * 78)
log("Empirical stochastic rationale:        SUPPORTED")
log("Simulation targets:                    PRESPECIFIED")
log("Medium/High probability models:        CANDIDATE AUTHORIZED")
log("Low probability model:                 CAUTION / DUAL PROTOCOL")
log("Iteration count:                       NOT YET DETERMINED")
log("Final Monte Carlo authorization:        PENDING CONVERGENCE")
log()

log("DISCRETE-EVENT STATUS")
log("-" * 78)
log(f"Stage-level coverage:                   {stage_coverage_pct:.2f}%")
log(f"Stage-duration Spearman correlation:    {stage_spearman:.4f}")
log("Final DES authorization:                PENDING")
log()

log("SCIENTIFIC SCOPE")
log("- No Monte Carlo award-time simulation was performed.")
log("- No discrete-event simulation was performed.")
log("- No iteration count was selected.")
log("- 10,000 iterations remains a candidate value, not a predetermined answer.")
log("- Terciles are specified as the primary scenario representation.")
log("- P25/P75 is prespecified for robustness analysis.")
log("- The data-driven partition remains a sensitivity analysis.")
log("- Medium and High may proceed to convergence testing with supported candidates.")
log("- Low requires empirical/nonparametric representation plus parametric sensitivity.")
log("- No new distribution was selected opportunistically.")
log("- No observations were deleted.")
log("- No missing temporal values were imputed.")
log("- No causal interpretation is imposed.")
log()

separator()
log("PIPELINE STATUS: READY_FOR_MONTE_CARLO_CONVERGENCE_ASSESSMENT")
separator()
