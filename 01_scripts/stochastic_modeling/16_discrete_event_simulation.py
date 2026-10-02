import os
import sys
import platform
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


# =============================================================================
# CONFIGURATION
# =============================================================================

MASTER_N = 137
EXPECTED_STAGE_N = 109
OPERATIONAL_N = 50_000
BASE_SEED = 2026

SCENARIO_ORDER = ["Low", "Medium", "High"]

ROOT = Path(__file__).resolve().parents[2]

INPUT_15 = (
    ROOT
    / "02_results"
    / "stochastic_modeling"
    / "15_1_discrete_event_assessment.xlsx"
)

INPUT_14 = (
    ROOT
    / "02_results"
    / "stochastic_modeling"
    / "14_1_monte_carlo_simulation.xlsx"
)

OUTPUT_DIR = ROOT / "02_results" / "stochastic_modeling"
LOG_DIR = ROOT / "03_logs" / "stochastic_modeling"

OUTPUT_FILE = OUTPUT_DIR / "16_1_discrete_event_simulation.xlsx"
LOG_FILE = LOG_DIR / "16_discrete_event_simulation.log"


# =============================================================================
# LOGGING
# =============================================================================

class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

log_handle = open(LOG_FILE, "w", encoding="utf-8")
original_stdout = sys.stdout
sys.stdout = Tee(sys.stdout, log_handle)


# =============================================================================
# HELPERS
# =============================================================================

def section(title):
    print()
    print(title)


def describe_array(x):
    x = np.asarray(x, dtype=float)

    return {
        "n": len(x),
        "mean": float(np.mean(x)),
        "median": float(np.median(x)),
        "std_dev": float(np.std(x, ddof=1)),
        "minimum": float(np.min(x)),
        "p25": float(np.percentile(x, 25)),
        "p75": float(np.percentile(x, 75)),
        "p90": float(np.percentile(x, 90)),
        "p95": float(np.percentile(x, 95)),
        "maximum": float(np.max(x)),
    }


def safe_spearman(x, y):
    if len(x) < 3:
        return np.nan, np.nan

    result = stats.spearmanr(x, y)
    return float(result.statistic), float(result.pvalue)


def safe_pearson(x, y):
    if len(x) < 3:
        return np.nan, np.nan

    result = stats.pearsonr(x, y)
    return float(result.statistic), float(result.pvalue)


def rank_biserial_from_mannwhitney(x, y):
    """
    Rank-biserial correlation associated with Mann-Whitney U.
    Negative values indicate that x tends to be smaller than y.
    """
    x = np.asarray(x)
    y = np.asarray(y)

    u = stats.mannwhitneyu(
        x,
        y,
        alternative="two-sided",
        method="auto"
    ).statistic

    return float((2.0 * u) / (len(x) * len(y)) - 1.0)


def relative_error(simulated, observed):
    observed = float(observed)

    if observed == 0:
        return np.nan

    return float(abs(simulated - observed) / abs(observed))


def infer_mc_primary_table(excel_file):
    """
    Attempts to identify the primary Monte Carlo results sheet from Script 14.
    This function is deliberately tolerant to sheet naming, but it does not
    fabricate results if the required information cannot be found.
    """

    xls = pd.ExcelFile(excel_file)

    preferred_sheets = [
        "primary_results",
        "primary_stochastic_results",
        "simulation_summary",
        "scenario_results",
        "final_results",
    ]

    search_order = preferred_sheets + [
        s for s in xls.sheet_names if s not in preferred_sheets
    ]

    scenario_candidates = [
        "scenario",
        "Scenario",
    ]

    representation_candidates = [
        "representation",
        "Representation",
        "model",
        "simulation_model",
    ]

    median_candidates = [
        "simulated_median",
        "median",
        "simulation_median",
    ]

    mean_candidates = [
        "simulated_mean",
        "mean",
        "simulation_mean",
    ]

    p95_candidates = [
        "simulated_p95",
        "p95",
        "simulation_p95",
    ]

    for sheet in search_order:
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet)
        except Exception:
            continue

        if df.empty:
            continue

        scenario_col = next(
            (c for c in scenario_candidates if c in df.columns),
            None
        )
        median_col = next(
            (c for c in median_candidates if c in df.columns),
            None
        )

        if scenario_col is None or median_col is None:
            continue

        representation_col = next(
            (c for c in representation_candidates if c in df.columns),
            None
        )
        mean_col = next(
            (c for c in mean_candidates if c in df.columns),
            None
        )
        p95_col = next(
            (c for c in p95_candidates if c in df.columns),
            None
        )

        out = pd.DataFrame()
        out["scenario"] = df[scenario_col].astype(str)

        if representation_col is not None:
            out["representation"] = df[representation_col].astype(str)
        else:
            out["representation"] = ""

        if mean_col is not None:
            out["mc_mean"] = pd.to_numeric(df[mean_col], errors="coerce")
        else:
            out["mc_mean"] = np.nan

        out["mc_median"] = pd.to_numeric(
            df[median_col],
            errors="coerce"
        )

        if p95_col is not None:
            out["mc_p95"] = pd.to_numeric(df[p95_col], errors="coerce")
        else:
            out["mc_p95"] = np.nan

        out = out[out["scenario"].isin(SCENARIO_ORDER)].copy()

        if len(out) == 0:
            continue

        # Prefer the authorized primary representation where identifiable.
        selected_rows = []

        for scenario in SCENARIO_ORDER:
            temp = out[out["scenario"] == scenario].copy()

            if temp.empty:
                continue

            if scenario == "Low":
                primary = temp[
                    temp["representation"]
                    .str.contains("Empirical", case=False, na=False)
                ]
            else:
                primary = temp[
                    temp["representation"]
                    .str.contains("Lognormal", case=False, na=False)
                ]

            if not primary.empty:
                selected_rows.append(primary.iloc[0])
            else:
                selected_rows.append(temp.iloc[0])

        if selected_rows:
            result = pd.DataFrame(selected_rows).reset_index(drop=True)
            return result, sheet

    return pd.DataFrame(), None


# =============================================================================
# START
# =============================================================================

try:
    print("=" * 78)
    print("TWO-STAGE DISCRETE-EVENT SIMULATION - ROAD INFRASTRUCTURE TENDERS")
    print("=" * 78)
    print(
        "Purpose: Implement the stage-level stochastic process authorized by "
        "Script 15 and evaluate its behavior relative to observed data and "
        "the direct Monte Carlo reference."
    )
    print()
    print(
        "IMPORTANT: The model preserves empirical dependence between stages "
        "through joint pair resampling."
    )
    print(
        "The direct total-duration Monte Carlo model from Script 14 remains "
        "the primary stochastic reference."
    )

    # =========================================================================
    # 1. INPUT VALIDATION
    # =========================================================================

    section("[1] Validating analytical inputs...")

    required_files = [INPUT_15, INPUT_14]

    for f in required_files:
        if not f.exists():
            raise FileNotFoundError(f"Required input not found: {f}")

        print(f"  Found: {f.name}")

    # =========================================================================
    # 2. READ SCRIPT 15
    # =========================================================================

    section("[2] Reading Script 15 stage-level analytical data...")

    xls15 = pd.ExcelFile(INPUT_15)

    required_sheets_15 = [
        "procedure_stage_audit",
        "final_decision",
        "authorization_gates",
    ]

    missing_sheets = [
        s for s in required_sheets_15
        if s not in xls15.sheet_names
    ]

    if missing_sheets:
        raise ValueError(
            f"Script 15 workbook is missing sheets: {missing_sheets}"
        )

    stage_df = pd.read_excel(
        INPUT_15,
        sheet_name="procedure_stage_audit"
    )

    final_decision = pd.read_excel(
        INPUT_15,
        sheet_name="final_decision"
    )

    authorization_gates = pd.read_excel(
        INPUT_15,
        sheet_name="authorization_gates"
    )

    print(f"  Procedure-level rows: {len(stage_df)}")
    print(f"  Final-decision rows: {len(final_decision)}")
    print(f"  Authorization-gate rows: {len(authorization_gates)}")

    # =========================================================================
    # 3. ANALYTICAL CONTRACT
    # =========================================================================

    section("[3] Validating stage-level analytical contract...")

    required_columns = [
        "procedure_code",
        "queries_observations_count",
        "scenario_terciles",
        "query_stage_duration_days",
        "evaluation_stage_duration_days",
        "total_award_time_days",
        "complete_stage_decomposition",
        "reconstructed_total_days",
        "reconstruction_difference",
    ]

    missing_columns = [
        c for c in required_columns
        if c not in stage_df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    if len(stage_df) != MASTER_N:
        raise ValueError(
            f"Expected master sample n={MASTER_N}, found {len(stage_df)}"
        )

    if stage_df["procedure_code"].duplicated().any():
        raise ValueError("procedure_code is not unique.")

    print(f"  Master analytical sample verified: {len(stage_df)}")
    print("  procedure_code uniqueness verified.")

    # =========================================================================
    # 4. VERIFY SCRIPT 15 AUTHORIZATION
    # =========================================================================

    section("[4] Verifying Script 15 DES authorization...")

    decision_text = " ".join(
        final_decision.astype(str).fillna("").values.flatten()
    )

    if "DES_AUTHORIZED_WITH_CAUTION" not in decision_text:
        raise ValueError(
            "Script 15 did not authorize DES with the expected caution status."
        )

    print("  Script 15 status: DES_AUTHORIZED_WITH_CAUTION")

    if "status" in authorization_gates.columns:
        gate_statuses = (
            authorization_gates["status"]
            .astype(str)
            .str.upper()
            .tolist()
        )

        if not all(s == "PASS" for s in gate_statuses):
            print(
                "  WARNING: Not every Script 15 authorization gate is PASS."
            )
        else:
            print("  Script 15 authorization gates verified.")

    # =========================================================================
    # 5. COMPLETE STAGE SAMPLE
    # =========================================================================

    section("[5] Preparing complete stage-decomposition sample...")

    complete = stage_df[
        stage_df["complete_stage_decomposition"].astype(bool)
    ].copy()

    complete = complete.dropna(
        subset=[
            "scenario_terciles",
            "query_stage_duration_days",
            "evaluation_stage_duration_days",
            "total_award_time_days",
        ]
    ).copy()

    stage_n = len(complete)

    print(f"  Complete stage decompositions: {stage_n}/{MASTER_N}")
    print(f"  Stage coverage: {100 * stage_n / MASTER_N:.2f}%")

    if stage_n != EXPECTED_STAGE_N:
        raise ValueError(
            f"Expected {EXPECTED_STAGE_N} complete decompositions, "
            f"found {stage_n}."
        )

    reconstruction = (
        complete["query_stage_duration_days"].astype(float)
        + complete["evaluation_stage_duration_days"].astype(float)
    )

    max_reconstruction_error = float(
        np.max(
            np.abs(
                reconstruction
                - complete["total_award_time_days"].astype(float)
            )
        )
    )

    print(
        "  Maximum stage-sum reconstruction error: "
        f"{max_reconstruction_error:.6f} days"
    )

    if max_reconstruction_error > 1e-9:
        raise ValueError(
            "Stage durations do not exactly reconstruct total award time."
        )

    # =========================================================================
    # 6. DEFINE DES PROCESS
    # =========================================================================

    section("[6] Defining explicit two-stage event process...")

    event_definition = pd.DataFrame(
        [
            {
                "event_order": 0,
                "event": "NOTICE",
                "state_after_event": "QUERY_INTEGRATION_STAGE",
                "clock_definition": "t = 0",
                "scientific_role":
                    "Procedure enters the observed pre-award process.",
            },
            {
                "event_order": 1,
                "event": "INTEGRATED_TERMS",
                "state_after_event": "EVALUATION_AWARD_STAGE",
                "clock_definition":
                    "t = query_stage_duration_days",
                "scientific_role":
                    "Query/integration stage ends and evaluation stage begins.",
            },
            {
                "event_order": 2,
                "event": "AWARD",
                "state_after_event": "ABSORBING_COMPLETED_STATE",
                "clock_definition":
                    "t = query_stage_duration_days + "
                    "evaluation_stage_duration_days",
                "scientific_role":
                    "Procedure reaches award and exits the simulated process.",
            },
        ]
    )

    for _, row in event_definition.iterrows():
        print(
            f"  Event {int(row['event_order'])}: "
            f"{row['event']} -> {row['state_after_event']}"
        )

    print()
    print(
        "  DES architecture: each simulated tender is an entity moving "
        "through ordered events on a simulation clock."
    )
    print(
        "  No queue, resource capacity, or artificial waiting mechanism is "
        "introduced because those mechanisms are not observed in the dataset."
    )

    # =========================================================================
    # 7. EMPIRICAL DEPENDENCE
    # =========================================================================

    section("[7] Auditing empirical dependence before simulation...")

    dependence_rows = []

    for scenario in SCENARIO_ORDER:
        temp = complete[
            complete["scenario_terciles"] == scenario
        ].copy()

        q = temp["query_stage_duration_days"].to_numpy(dtype=float)
        e = temp["evaluation_stage_duration_days"].to_numpy(dtype=float)

        pearson_r, pearson_p = safe_pearson(q, e)
        spearman_rho, spearman_p = safe_spearman(q, e)

        dependence_rows.append(
            {
                "scenario": scenario,
                "n": len(temp),
                "pearson_r": pearson_r,
                "pearson_p": pearson_p,
                "spearman_rho": spearman_rho,
                "spearman_p": spearman_p,
            }
        )

        print(
            f"  {scenario}: n={len(temp)}; "
            f"Pearson={pearson_r:.4f}; "
            f"Spearman={spearman_rho:.4f}"
        )

    dependence_df = pd.DataFrame(dependence_rows)

    print()
    print(
        "  Modeling rule: observed stage pairs are resampled jointly within "
        "scenario; query and evaluation durations are never sampled "
        "independently in the primary DES."
    )

    # =========================================================================
    # 8. OBSERVED BENCHMARKS
    # =========================================================================

    section("[8] Computing observed stage-level benchmarks...")

    observed_rows = []

    for scenario in SCENARIO_ORDER:
        temp = complete[
            complete["scenario_terciles"] == scenario
        ].copy()

        q = temp["query_stage_duration_days"].to_numpy(dtype=float)
        e = temp["evaluation_stage_duration_days"].to_numpy(dtype=float)
        total = q + e

        q_desc = describe_array(q)
        e_desc = describe_array(e)
        t_desc = describe_array(total)

        observed_rows.append(
            {
                "scenario": scenario,
                "n": len(temp),

                "query_mean": q_desc["mean"],
                "query_median": q_desc["median"],
                "query_sd": q_desc["std_dev"],
                "query_p90": q_desc["p90"],
                "query_p95": q_desc["p95"],

                "evaluation_mean": e_desc["mean"],
                "evaluation_median": e_desc["median"],
                "evaluation_sd": e_desc["std_dev"],
                "evaluation_p90": e_desc["p90"],
                "evaluation_p95": e_desc["p95"],

                "total_mean": t_desc["mean"],
                "total_median": t_desc["median"],
                "total_sd": t_desc["std_dev"],
                "total_p90": t_desc["p90"],
                "total_p95": t_desc["p95"],
            }
        )

        print(
            f"  {scenario}: n={len(temp)}; "
            f"query median={q_desc['median']:.2f}; "
            f"evaluation median={e_desc['median']:.2f}; "
            f"total median={t_desc['median']:.2f}"
        )

    observed_benchmarks = pd.DataFrame(observed_rows)

    # =========================================================================
    # 9. OPERATIONAL SIMULATION SIZE
    # =========================================================================

    section("[9] Defining operational DES simulation size...")

    print(f"  Operational entities per scenario: {OPERATIONAL_N:,}")
    print(f"  Reproducibility base seed: {BASE_SEED}")
    print()
    print(
        "  NOTE: 50,000 is inherited from Script 13 as a common operational "
        "simulation budget for comparability."
    )
    print(
        "  It is not interpreted as proof that the Monte Carlo convergence "
        "experiment automatically establishes DES convergence."
    )

    # =========================================================================
    # 10. PRIMARY JOINT-RESAMPLING DES
    # =========================================================================

    section("[10] Running primary two-stage discrete-event simulation...")

    simulation_rows = []
    event_audit_rows = []
    simulated_arrays = {}

    scenario_seed_map = {
        "Low": BASE_SEED + 101,
        "Medium": BASE_SEED + 202,
        "High": BASE_SEED + 303,
    }

    for scenario in SCENARIO_ORDER:
        temp = complete[
            complete["scenario_terciles"] == scenario
        ].copy()

        q_obs = temp["query_stage_duration_days"].to_numpy(dtype=float)
        e_obs = temp["evaluation_stage_duration_days"].to_numpy(dtype=float)

        pair_matrix = np.column_stack([q_obs, e_obs])

        rng = np.random.default_rng(scenario_seed_map[scenario])

        sampled_indices = rng.integers(
            0,
            len(pair_matrix),
            size=OPERATIONAL_N
        )

        sampled_pairs = pair_matrix[sampled_indices]

        q_sim = sampled_pairs[:, 0]
        e_sim = sampled_pairs[:, 1]

        t_notice = np.zeros(OPERATIONAL_N, dtype=float)
        t_integrated = q_sim.copy()
        t_award = q_sim + e_sim

        simulated_arrays[scenario] = {
            "query": q_sim,
            "evaluation": e_sim,
            "total": t_award,
        }

        q_desc = describe_array(q_sim)
        e_desc = describe_array(e_sim)
        t_desc = describe_array(t_award)

        pearson_r, pearson_p = safe_pearson(q_sim, e_sim)
        spearman_rho, spearman_p = safe_spearman(q_sim, e_sim)

        simulation_rows.append(
            {
                "scenario": scenario,
                "representation":
                    "JOINT_EMPIRICAL_PAIR_RESAMPLING",
                "simulated_entities": OPERATIONAL_N,
                "seed": scenario_seed_map[scenario],

                "query_mean": q_desc["mean"],
                "query_median": q_desc["median"],
                "query_sd": q_desc["std_dev"],
                "query_p90": q_desc["p90"],
                "query_p95": q_desc["p95"],

                "evaluation_mean": e_desc["mean"],
                "evaluation_median": e_desc["median"],
                "evaluation_sd": e_desc["std_dev"],
                "evaluation_p90": e_desc["p90"],
                "evaluation_p95": e_desc["p95"],

                "total_mean": t_desc["mean"],
                "total_median": t_desc["median"],
                "total_sd": t_desc["std_dev"],
                "total_p90": t_desc["p90"],
                "total_p95": t_desc["p95"],

                "simulated_pearson_r": pearson_r,
                "simulated_pearson_p": pearson_p,
                "simulated_spearman_rho": spearman_rho,
                "simulated_spearman_p": spearman_p,
            }
        )

        audit_n = min(1000, OPERATIONAL_N)

        for i in range(audit_n):
            event_audit_rows.append(
                {
                    "scenario": scenario,
                    "entity_id": i + 1,
                    "source_pair_index":
                        int(sampled_indices[i]),
                    "notice_time": t_notice[i],
                    "integrated_terms_time": t_integrated[i],
                    "award_time": t_award[i],
                    "query_stage_duration_days": q_sim[i],
                    "evaluation_stage_duration_days": e_sim[i],
                    "reconstructed_total_days": t_award[i],
                }
            )

        print(
            f"  {scenario}: N={OPERATIONAL_N:,}; "
            f"query median={q_desc['median']:.2f}; "
            f"evaluation median={e_desc['median']:.2f}; "
            f"total median={t_desc['median']:.2f}; "
            f"Spearman={spearman_rho:.4f}"
        )

    simulation_summary = pd.DataFrame(simulation_rows)
    event_audit = pd.DataFrame(event_audit_rows)

    # =========================================================================
    # 11. DEPENDENCE PRESERVATION
    # =========================================================================

    section("[11] Evaluating dependence preservation...")

    dependence_preservation_rows = []

    for scenario in SCENARIO_ORDER:
        obs = dependence_df[
            dependence_df["scenario"] == scenario
        ].iloc[0]

        sim = simulation_summary[
            simulation_summary["scenario"] == scenario
        ].iloc[0]

        rho_difference = (
            sim["simulated_spearman_rho"]
            - obs["spearman_rho"]
        )

        dependence_preservation_rows.append(
            {
                "scenario": scenario,
                "observed_n": int(obs["n"]),
                "observed_spearman_rho":
                    float(obs["spearman_rho"]),
                "simulated_spearman_rho":
                    float(sim["simulated_spearman_rho"]),
                "difference":
                    float(rho_difference),
                "absolute_difference":
                    float(abs(rho_difference)),
                "dependence_preservation_method":
                    "JOINT_EMPIRICAL_PAIR_RESAMPLING",
            }
        )

        print(
            f"  {scenario}: observed rho={obs['spearman_rho']:.4f}; "
            f"simulated rho={sim['simulated_spearman_rho']:.4f}; "
            f"difference={rho_difference:+.4f}"
        )

    dependence_preservation = pd.DataFrame(
        dependence_preservation_rows
    )

    # =========================================================================
    # 12. OBSERVED VS DES
    # =========================================================================

    section("[12] Comparing DES outputs with observed stage-complete data...")

    validation_rows = []

    for scenario in SCENARIO_ORDER:
        obs = observed_benchmarks[
            observed_benchmarks["scenario"] == scenario
        ].iloc[0]

        sim = simulation_summary[
            simulation_summary["scenario"] == scenario
        ].iloc[0]

        metrics = [
            ("query_mean", "query_mean"),
            ("query_median", "query_median"),
            ("query_sd", "query_sd"),
            ("query_p90", "query_p90"),
            ("query_p95", "query_p95"),

            ("evaluation_mean", "evaluation_mean"),
            ("evaluation_median", "evaluation_median"),
            ("evaluation_sd", "evaluation_sd"),
            ("evaluation_p90", "evaluation_p90"),
            ("evaluation_p95", "evaluation_p95"),

            ("total_mean", "total_mean"),
            ("total_median", "total_median"),
            ("total_sd", "total_sd"),
            ("total_p90", "total_p90"),
            ("total_p95", "total_p95"),
        ]

        for label, col in metrics:
            observed_value = float(obs[col])
            simulated_value = float(sim[col])

            validation_rows.append(
                {
                    "scenario": scenario,
                    "metric": label,
                    "observed_value": observed_value,
                    "simulated_value": simulated_value,
                    "absolute_difference":
                        abs(simulated_value - observed_value),
                    "relative_error":
                        relative_error(
                            simulated_value,
                            observed_value
                        ),
                }
            )

        total_median_error = relative_error(
            sim["total_median"],
            obs["total_median"]
        )

        print(
            f"  {scenario}: total median observed="
            f"{obs['total_median']:.2f}; simulated="
            f"{sim['total_median']:.2f}; relative error="
            f"{100 * total_median_error:.2f}%"
        )

    observed_vs_des = pd.DataFrame(validation_rows)

    # =========================================================================
    # 13. STAGE CONTRIBUTIONS
    # =========================================================================

    section("[13] Quantifying simulated stage contributions...")

    stage_share_rows = []

    for scenario in SCENARIO_ORDER:
        q = simulated_arrays[scenario]["query"]
        e = simulated_arrays[scenario]["evaluation"]
        total = simulated_arrays[scenario]["total"]

        with np.errstate(divide="ignore", invalid="ignore"):
            q_share = np.where(total > 0, q / total, np.nan)
            e_share = np.where(total > 0, e / total, np.nan)

        valid_q = q_share[np.isfinite(q_share)]
        valid_e = e_share[np.isfinite(e_share)]

        q_desc = describe_array(valid_q)
        e_desc = describe_array(valid_e)

        stage_share_rows.append(
            {
                "scenario": scenario,
                "stage": "Query/integration",
                "mean_share": q_desc["mean"],
                "median_share": q_desc["median"],
                "p25_share": q_desc["p25"],
                "p75_share": q_desc["p75"],
            }
        )

        stage_share_rows.append(
            {
                "scenario": scenario,
                "stage": "Evaluation/award",
                "mean_share": e_desc["mean"],
                "median_share": e_desc["median"],
                "p25_share": e_desc["p25"],
                "p75_share": e_desc["p75"],
            }
        )

        print(
            f"  {scenario}: median query-stage share="
            f"{q_desc['median']:.3f}; "
            f"median evaluation-stage share="
            f"{e_desc['median']:.3f}"
        )

    simulated_stage_shares = pd.DataFrame(stage_share_rows)

    # =========================================================================
    # 14. SCENARIO CONTRASTS
    # =========================================================================

    section("[14] Quantifying DES scenario contrasts...")

    contrast_rows = []

    comparisons = [
        ("Medium", "Low"),
        ("High", "Low"),
        ("High", "Medium"),
    ]

    for higher, lower in comparisons:
        higher_total = simulated_arrays[higher]["total"]
        lower_total = simulated_arrays[lower]["total"]

        rng = np.random.default_rng(
            BASE_SEED
            + 1000
            + SCENARIO_ORDER.index(higher) * 10
            + SCENARIO_ORDER.index(lower)
        )

        idx_h = rng.integers(
            0,
            len(higher_total),
            size=OPERATIONAL_N
        )

        idx_l = rng.integers(
            0,
            len(lower_total),
            size=OPERATIONAL_N
        )

        probability = float(
            np.mean(
                higher_total[idx_h]
                > lower_total[idx_l]
            )
        )

        higher_desc = describe_array(higher_total)
        lower_desc = describe_array(lower_total)

        contrast_rows.append(
            {
                "comparison": f"{higher}_vs_{lower}",
                "higher_scenario": higher,
                "lower_scenario": lower,
                "median_difference_days":
                    higher_desc["median"]
                    - lower_desc["median"],
                "mean_difference_days":
                    higher_desc["mean"]
                    - lower_desc["mean"],
                "p95_difference_days":
                    higher_desc["p95"]
                    - lower_desc["p95"],
                "probability_higher_total_time":
                    probability,
            }
        )

        print(
            f"  {higher} vs {lower}: "
            f"median difference="
            f"{higher_desc['median'] - lower_desc['median']:.2f} days; "
            f"P(T_{higher} > T_{lower})={probability:.4f}"
        )

    scenario_contrasts = pd.DataFrame(contrast_rows)

    # =========================================================================
    # 15. INTERNAL STABILITY AUDIT
    # =========================================================================

    section("[15] Auditing internal numerical stability of DES outputs...")

    checkpoints = [
        1_000,
        5_000,
        10_000,
        25_000,
        50_000,
    ]

    stability_rows = []

    for scenario in SCENARIO_ORDER:
        q = simulated_arrays[scenario]["query"]
        e = simulated_arrays[scenario]["evaluation"]
        total = simulated_arrays[scenario]["total"]

        full_desc = describe_array(total)
        full_rho, _ = safe_spearman(q, e)

        for n in checkpoints:
            q_n = q[:n]
            e_n = e[:n]
            total_n = total[:n]

            desc_n = describe_array(total_n)
            rho_n, _ = safe_spearman(q_n, e_n)

            stability_rows.append(
                {
                    "scenario": scenario,
                    "entities": n,
                    "mean": desc_n["mean"],
                    "median": desc_n["median"],
                    "std_dev": desc_n["std_dev"],
                    "p90": desc_n["p90"],
                    "p95": desc_n["p95"],
                    "spearman_rho": rho_n,

                    "mean_relative_difference_vs_50000":
                        relative_error(
                            desc_n["mean"],
                            full_desc["mean"]
                        ),

                    "median_relative_difference_vs_50000":
                        relative_error(
                            desc_n["median"],
                            full_desc["median"]
                        ),

                    "sd_relative_difference_vs_50000":
                        relative_error(
                            desc_n["std_dev"],
                            full_desc["std_dev"]
                        ),

                    "p95_relative_difference_vs_50000":
                        relative_error(
                            desc_n["p95"],
                            full_desc["p95"]
                        ),

                    "spearman_absolute_difference_vs_50000":
                        abs(rho_n - full_rho),
                }
            )

        print(
            f"  {scenario}: checkpoints evaluated through "
            f"{OPERATIONAL_N:,} entities."
        )

    stability_audit = pd.DataFrame(stability_rows)

    print()
    print(
        "  NOTE: This is an internal stability audit relative to the fixed "
        "50,000-entity run."
    )
    print(
        "  It is not a replacement for Script 13 and does not redefine "
        "the Monte Carlo convergence criteria."
    )

    # =========================================================================
    # 16. DIRECT MC COMPARISON
    # =========================================================================

    section("[16] Comparing DES totals with Script 14 direct Monte Carlo...")

    mc_primary, mc_sheet = infer_mc_primary_table(INPUT_14)

    mc_comparison_rows = []

    if mc_primary.empty:
        print(
            "  WARNING: A compatible Script 14 primary-results table could "
            "not be identified automatically."
        )
        print(
            "  DES outputs remain valid, but direct MC-vs-DES comparison "
            "will be deferred to formal validation."
        )
    else:
        print(f"  Script 14 comparison source sheet: {mc_sheet}")

        for scenario in SCENARIO_ORDER:
            des = simulation_summary[
                simulation_summary["scenario"] == scenario
            ]

            mc = mc_primary[
                mc_primary["scenario"] == scenario
            ]

            if des.empty or mc.empty:
                continue

            des = des.iloc[0]
            mc = mc.iloc[0]

            row = {
                "scenario": scenario,
                "mc_representation":
                    mc.get("representation", ""),
                "des_representation":
                    "JOINT_EMPIRICAL_PAIR_RESAMPLING",
                "des_mean":
                    float(des["total_mean"]),
                "des_median":
                    float(des["total_median"]),
                "des_p95":
                    float(des["total_p95"]),
                "mc_mean":
                    mc.get("mc_mean", np.nan),
                "mc_median":
                    mc.get("mc_median", np.nan),
                "mc_p95":
                    mc.get("mc_p95", np.nan),
            }

            if pd.notna(row["mc_mean"]):
                row["mean_difference_des_minus_mc"] = (
                    row["des_mean"] - row["mc_mean"]
                )
            else:
                row["mean_difference_des_minus_mc"] = np.nan

            if pd.notna(row["mc_median"]):
                row["median_difference_des_minus_mc"] = (
                    row["des_median"] - row["mc_median"]
                )
            else:
                row["median_difference_des_minus_mc"] = np.nan

            if pd.notna(row["mc_p95"]):
                row["p95_difference_des_minus_mc"] = (
                    row["des_p95"] - row["mc_p95"]
                )
            else:
                row["p95_difference_des_minus_mc"] = np.nan

            mc_comparison_rows.append(row)

            print(
                f"  {scenario}: DES median={row['des_median']:.2f}; "
                f"MC median={row['mc_median']:.2f}"
                if pd.notna(row["mc_median"])
                else
                f"  {scenario}: MC median unavailable"
            )

    mc_vs_des = pd.DataFrame(mc_comparison_rows)

    # =========================================================================
    # 17. INDEPENDENCE COUNTERFACTUAL
    # =========================================================================

    section("[17] Running independence counterfactual sensitivity analysis...")

    independence_rows = []

    for scenario in SCENARIO_ORDER:
        temp = complete[
            complete["scenario_terciles"] == scenario
        ].copy()

        q_obs = temp["query_stage_duration_days"].to_numpy(dtype=float)
        e_obs = temp["evaluation_stage_duration_days"].to_numpy(dtype=float)

        rng_q = np.random.default_rng(
            BASE_SEED + 2000 + SCENARIO_ORDER.index(scenario) * 2
        )
        rng_e = np.random.default_rng(
            BASE_SEED + 2001 + SCENARIO_ORDER.index(scenario) * 2
        )

        q_ind = rng_q.choice(
            q_obs,
            size=OPERATIONAL_N,
            replace=True
        )

        e_ind = rng_e.choice(
            e_obs,
            size=OPERATIONAL_N,
            replace=True
        )

        total_ind = q_ind + e_ind

        primary_total = simulated_arrays[scenario]["total"]

        primary_desc = describe_array(primary_total)
        independent_desc = describe_array(total_ind)

        rho_ind, p_ind = safe_spearman(q_ind, e_ind)

        independence_rows.append(
            {
                "scenario": scenario,
                "primary_joint_median":
                    primary_desc["median"],
                "independent_median":
                    independent_desc["median"],
                "median_difference":
                    independent_desc["median"]
                    - primary_desc["median"],

                "primary_joint_sd":
                    primary_desc["std_dev"],
                "independent_sd":
                    independent_desc["std_dev"],
                "sd_difference":
                    independent_desc["std_dev"]
                    - primary_desc["std_dev"],

                "primary_joint_p95":
                    primary_desc["p95"],
                "independent_p95":
                    independent_desc["p95"],
                "p95_difference":
                    independent_desc["p95"]
                    - primary_desc["p95"],

                "independent_spearman_rho":
                    rho_ind,
                "independent_spearman_p":
                    p_ind,

                "scientific_role":
                    "SENSITIVITY_ONLY_NOT_AUTHORIZED_PRIMARY_MODEL",
            }
        )

        print(
            f"  {scenario}: joint P95={primary_desc['p95']:.2f}; "
            f"independent P95={independent_desc['p95']:.2f}; "
            f"difference="
            f"{independent_desc['p95'] - primary_desc['p95']:+.2f}"
        )

    independence_sensitivity = pd.DataFrame(independence_rows)

    print()
    print(
        "  NOTE: Independent sampling is intentionally retained only as a "
        "counterfactual sensitivity analysis."
    )
    print(
        "  It is not promoted to the primary DES because Script 15 rejected "
        "automatic independence."
    )

    # =========================================================================
    # 18. INCREMENTAL VALUE
    # =========================================================================

    section("[18] Assessing incremental analytical value of the DES...")

    incremental_rows = [
        {
            "dimension": "Process representation",
            "direct_monte_carlo":
                "Simulates total award duration directly.",
            "two_stage_des":
                "Represents notice -> integrated terms -> award as "
                "explicit sequential events.",
            "incremental_value":
                "YES",
            "interpretation":
                "DES exposes where simulated time accumulates within the "
                "observed two-stage process.",
        },
        {
            "dimension": "Stage-specific outputs",
            "direct_monte_carlo":
                "Not available from total-duration simulation alone.",
            "two_stage_des":
                "Produces query/integration and evaluation/award "
                "durations separately.",
            "incremental_value":
                "YES",
            "interpretation":
                "Allows stage-specific temporal interpretation.",
        },
        {
            "dimension": "Dependence",
            "direct_monte_carlo":
                "Not required because total duration is simulated directly.",
            "two_stage_des":
                "Preserves observed joint dependence through paired "
                "empirical resampling.",
            "incremental_value":
                "YES",
            "interpretation":
                "Avoids imposing unsupported independence between stages.",
        },
        {
            "dimension": "Data coverage",
            "direct_monte_carlo":
                "Uses 136 available total durations.",
            "two_stage_des":
                "Uses 109 complete stage decompositions.",
            "incremental_value":
                "LIMITATION",
            "interpretation":
                "DES has lower empirical coverage and inherits the "
                "missing-data caution identified previously.",
        },
        {
            "dimension": "Primary scientific role",
            "direct_monte_carlo":
                "Primary stochastic reference.",
            "two_stage_des":
                "Secondary process-decomposition model.",
            "incremental_value":
                "COMPLEMENTARY",
            "interpretation":
                "DES should complement rather than replace the direct "
                "Monte Carlo model unless later validation demonstrates "
                "a compelling reason.",
        },
    ]

    incremental_value = pd.DataFrame(incremental_rows)

    print("  Incremental-value framework created.")
    print(
        "  Current role: DES = secondary process-decomposition model; "
        "direct Monte Carlo = primary stochastic reference."
    )

    # =========================================================================
    # 19. LIMITATIONS
    # =========================================================================

    section("[19] Recording DES-specific limitations...")

    limitations = pd.DataFrame(
        [
            {
                "limitation":
                    "Stage-level coverage",
                "observed_result":
                    f"{stage_n}/{MASTER_N} complete decompositions "
                    f"({100 * stage_n / MASTER_N:.2f}%)",
                "implication":
                    "DES results apply to the observed complete-stage "
                    "subset and must be interpreted with Script 05 "
                    "missingness findings.",
            },
            {
                "limitation":
                    "Process resolution",
                "observed_result":
                    "Only two empirical temporal stages are available.",
                "implication":
                    "The model cannot represent unobserved internal "
                    "administrative subprocesses, queues, resources, or "
                    "decision nodes.",
            },
            {
                "limitation":
                    "Empirical pair resampling",
                "observed_result":
                    "Primary DES samples observed stage-duration pairs "
                    "with replacement within scenario.",
                "implication":
                    "Dependence is preserved robustly, but the model does "
                    "not extrapolate novel joint stage combinations beyond "
                    "the observed empirical support.",
            },
            {
                "limitation":
                    "Observational design",
                "observed_result":
                    "No randomized intervention is present.",
                "implication":
                    "Scenario differences and simulated contrasts must not "
                    "be interpreted causally.",
            },
            {
                "limitation":
                    "Operational simulation size",
                "observed_result":
                    f"{OPERATIONAL_N:,} entities per scenario.",
                "implication":
                    "This value is inherited for comparability and is "
                    "accompanied by an internal stability audit; it is not "
                    "claimed to be independently optimized for DES.",
            },
        ]
    )

    for _, row in limitations.iterrows():
        print(
            f"  - {row['limitation']}: {row['observed_result']}"
        )

    # =========================================================================
    # 20. MODEL ARCHITECTURE AUDIT
    # =========================================================================

    section("[20] Building model-architecture audit...")

    architecture_audit = pd.DataFrame(
        [
            {
                "component": "Entity",
                "specification": "One procurement procedure / tender",
                "status": "DEFINED",
            },
            {
                "component": "Initial event",
                "specification": "NOTICE at simulation time 0",
                "status": "DEFINED",
            },
            {
                "component": "Stage 1",
                "specification":
                    "Query/integration duration",
                "status": "DEFINED",
            },
            {
                "component": "Intermediate event",
                "specification":
                    "INTEGRATED_TERMS",
                "status": "DEFINED",
            },
            {
                "component": "Stage 2",
                "specification":
                    "Evaluation/award duration",
                "status": "DEFINED",
            },
            {
                "component": "Terminal event",
                "specification":
                    "AWARD",
                "status": "DEFINED",
            },
            {
                "component": "Stage dependence",
                "specification":
                    "Preserved through joint empirical pair resampling "
                    "within scenario",
                "status": "DEFINED",
            },
            {
                "component": "Queues/resources",
                "specification":
                    "Not modeled because no empirical queue/resource data "
                    "are available",
                "status": "NOT_INTRODUCED",
            },
            {
                "component": "Primary DES role",
                "specification":
                    "Secondary process-decomposition stochastic model",
                "status": "DEFINED",
            },
            {
                "component": "Primary stochastic reference",
                "specification":
                    "Direct total-duration Monte Carlo from Script 14",
                "status": "PRESERVED",
            },
        ]
    )

    print("  DES architecture audit created.")

    # =========================================================================
    # 21. SCIENTIFIC INTERPRETATION AUDIT
    # =========================================================================

    section("[21] Building scientific interpretation audit...")

    interpretation_audit = pd.DataFrame(
        [
            {
                "issue":
                    "Meaning of DES output",
                "authorized_interpretation":
                    "A stochastic representation of the observed "
                    "two-stage pre-award temporal process.",
                "not_authorized":
                    "A complete mechanistic representation of every "
                    "administrative activity in procurement.",
            },
            {
                "issue":
                    "Stage dependence",
                "authorized_interpretation":
                    "Observed dependence is preserved empirically through "
                    "joint pair resampling.",
                "not_authorized":
                    "A claim that one stage causally determines the other.",
            },
            {
                "issue":
                    "Scenario comparison",
                "authorized_interpretation":
                    "Simulated temporal behavior differs across empirical "
                    "Low/Medium/High query-count scenarios.",
                "not_authorized":
                    "A causal effect of additional queries on award time.",
            },
            {
                "issue":
                    "Simulation size",
                "authorized_interpretation":
                    "50,000 entities provide a reproducible operational "
                    "budget accompanied by an internal stability audit.",
                "not_authorized":
                    "A claim that Script 13 mathematically proved 50,000 "
                    "to be the unique optimal DES iteration count.",
            },
            {
                "issue":
                    "Comparison with direct Monte Carlo",
                "authorized_interpretation":
                    "The two models answer related but different questions: "
                    "total-duration uncertainty versus stage-level process "
                    "decomposition.",
                "not_authorized":
                    "A claim that greater model complexity automatically "
                    "makes DES superior.",
            },
        ]
    )

    print("  Interpretation audit created.")

    # =========================================================================
    # 22. REPRODUCIBILITY METADATA
    # =========================================================================

    section("[22] Building reproducibility metadata...")

    metadata = pd.DataFrame(
        [
            {
                "item": "script",
                "value": "16_discrete_event_simulation.py",
            },
            {
                "item": "python_version",
                "value": platform.python_version(),
            },
            {
                "item": "platform",
                "value": platform.platform(),
            },
            {
                "item": "numpy_version",
                "value": np.__version__,
            },
            {
                "item": "pandas_version",
                "value": pd.__version__,
            },
            {
                "item": "scipy_version",
                "value": getattr(stats, "__version__", "See scipy package"),
            },
            {
                "item": "master_population_n",
                "value": MASTER_N,
            },
            {
                "item": "stage_complete_n",
                "value": stage_n,
            },
            {
                "item": "operational_entities_per_scenario",
                "value": OPERATIONAL_N,
            },
            {
                "item": "base_seed",
                "value": BASE_SEED,
            },
            {
                "item": "primary_dependence_method",
                "value": "Joint empirical pair resampling",
            },
            {
                "item": "primary_des_role",
                "value": "Secondary process-decomposition model",
            },
        ]
    )

    print("  Reproducibility metadata created.")

    # =========================================================================
    # 23. SAVE OUTPUT
    # =========================================================================

    section("[23] Saving reproducible DES outputs...")

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl"
    ) as writer:

        event_definition.to_excel(
            writer,
            sheet_name="event_definition",
            index=False
        )

        observed_benchmarks.to_excel(
            writer,
            sheet_name="observed_benchmarks",
            index=False
        )

        dependence_df.to_excel(
            writer,
            sheet_name="observed_dependence",
            index=False
        )

        simulation_summary.to_excel(
            writer,
            sheet_name="des_summary",
            index=False
        )

        dependence_preservation.to_excel(
            writer,
            sheet_name="dependence_preservation",
            index=False
        )

        observed_vs_des.to_excel(
            writer,
            sheet_name="observed_vs_des",
            index=False
        )

        simulated_stage_shares.to_excel(
            writer,
            sheet_name="stage_shares",
            index=False
        )

        scenario_contrasts.to_excel(
            writer,
            sheet_name="scenario_contrasts",
            index=False
        )

        stability_audit.to_excel(
            writer,
            sheet_name="stability_audit",
            index=False
        )

        if not mc_vs_des.empty:
            mc_vs_des.to_excel(
                writer,
                sheet_name="mc_vs_des",
                index=False
            )

        independence_sensitivity.to_excel(
            writer,
            sheet_name="independence_sensitivity",
            index=False
        )

        incremental_value.to_excel(
            writer,
            sheet_name="incremental_value",
            index=False
        )

        limitations.to_excel(
            writer,
            sheet_name="limitations",
            index=False
        )

        architecture_audit.to_excel(
            writer,
            sheet_name="architecture_audit",
            index=False
        )

        interpretation_audit.to_excel(
            writer,
            sheet_name="interpretation_audit",
            index=False
        )

        event_audit.to_excel(
            writer,
            sheet_name="event_audit_sample",
            index=False
        )

        metadata.to_excel(
            writer,
            sheet_name="reproducibility",
            index=False
        )

    print(f"  Output workbook: {OUTPUT_FILE.name}")
    print(f"  Log file: {LOG_FILE.name}")

    # =========================================================================
    # FINAL AUDIT
    # =========================================================================

    print()
    print("=" * 78)
    print("TWO-STAGE DISCRETE-EVENT SIMULATION AUDIT")
    print("=" * 78)

    print(f"Master analytical procedures:          {MASTER_N}")
    print(
        f"Complete temporal decompositions:      "
        f"{stage_n} ({100 * stage_n / MASTER_N:.2f}%)"
    )
    print(
        f"Operational simulated entities:        "
        f"{OPERATIONAL_N:,} per scenario"
    )

    print()
    print("PROCESS ARCHITECTURE")
    print("-" * 78)
    print("NOTICE")
    print("  -> Query / integration stage")
    print("INTEGRATED_TERMS")
    print("  -> Evaluation / award stage")
    print("AWARD")

    print()
    print("PRIMARY DEPENDENCE REPRESENTATION")
    print("-" * 78)
    print("Joint empirical resampling of observed stage-duration pairs.")
    print(
        "Independent stage sampling is retained only as sensitivity analysis."
    )

    print()
    print("PRIMARY DES RESULTS")
    print("-" * 78)

    for _, row in simulation_summary.iterrows():
        print(
            f"{row['scenario']:<10} | "
            f"query median={row['query_median']:.2f} | "
            f"evaluation median={row['evaluation_median']:.2f} | "
            f"total median={row['total_median']:.2f} | "
            f"P95={row['total_p95']:.2f} | "
            f"rho={row['simulated_spearman_rho']:.4f}"
        )

    print()
    print("SCIENTIFIC ROLE")
    print("-" * 78)
    print(
        "Direct total-duration Monte Carlo: PRIMARY STOCHASTIC REFERENCE"
    )
    print(
        "Two-stage discrete-event model:    SECONDARY PROCESS-DECOMPOSITION MODEL"
    )

    print()
    print("SCIENTIFIC SCOPE")
    print("-" * 78)
    print(
        "- Script 16 implements the two-stage stochastic process authorized "
        "with caution by Script 15."
    )
    print(
        "- Each simulated tender is represented as an entity progressing "
        "through NOTICE -> INTEGRATED_TERMS -> AWARD."
    )
    print(
        "- Stage dependence is preserved through joint empirical pair "
        "resampling within each tercile scenario."
    )
    print(
        "- Independent stage sampling is not used as the primary model."
    )
    print(
        "- No queue, resource constraint, service discipline, or unobserved "
        "administrative mechanism is invented."
    )
    print(
        "- The DES uses the 109 observed complete stage decompositions."
    )
    print(
        "- The master analytical population remains n=137."
    )
    print(
        "- Missing temporal values are not imputed."
    )
    print(
        "- No observations are deleted from the master analytical population."
    )
    print(
        "- Scenario thresholds are not redefined."
    )
    print(
        "- No probability distribution is selected in this script."
    )
    print(
        "- The 50,000-entity budget is inherited for comparability and is "
        "audited for internal stability."
    )
    print(
        "- DES does not replace the direct Monte Carlo model automatically."
    )
    print(
        "- Scenario contrasts are stochastic/descriptive and do not establish "
        "causal effects."
    )
    print(
        "- Formal joint model validation remains a subsequent pipeline phase."
    )

    print()
    print("=" * 78)
    print(
        "PIPELINE STATUS: TWO_STAGE_DES_COMPLETE_READY_FOR_JOINT_VALIDATION"
    )
    print("=" * 78)

finally:
    sys.stdout = original_stdout
    log_handle.close()
