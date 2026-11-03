# Conditional Monte Carlo Simulation

This directory contains the computational simulation engines that model the award-time uncertainty of Peruvian road procurement procedures.

**Specific Objective 3**, as stated in the originally approved research project:

> *Model stochastically the procurement duration for each information asymmetry scenario using Monte Carlo simulation and Discrete Event Simulation (DES) in Python.*

---

## Workflow Overview

| Script | Title | Methodological Role |
|---|---|---|
| `06_convergence_analysis.py` | Monte Carlo Convergence Assessment | Evaluates Monte Carlo precision across M1/M2/M4 and low/medium/high Q scenarios, supporting scenario-specific sizes from 50,000 to 2,000,000 iterations |
| `07_conditional_monte_carlo_simulation.py` | Conditional Monte Carlo Simulation | Reuses the Script 06 core to generate verified continuous trajectories for nine empirical M1/M2/M4 and Q-scenario mixtures |

---

## 1. Script 06 — Monte Carlo Convergence Analysis

### Purpose
`06_convergence_analysis.py` evaluates numerical precision for conditional Monte Carlo simulation of published administrative schedule intervals. It provides an importable simulation core and scenario-specific iteration decisions for subsequent work in Script 07. It does not establish predictive validity or amend the officially approved thesis project.

### Key Methodological Features
- **Conditional architecture:** Three correlated intervals connect query close, absolution end, integration end and scheduled award end. Their sum is the simulated total. The sequence does not implement queues, resources or an independent DES engine.
- **Verified input:** Loads Script 05's `sixa-calibration-bundle/1.0`, its SHA-256 export manifest and linked 2,004 joint profiles. It consumes exported coefficients, transformations, institutional coding, variable ordering and model-specific Gaussian copulas. M2 is the reference, M1 the Q-only comparator and M4 the government/ln(procedure reference amount) alternative. No recalibration is performed.
- **Profile handling:** Empirical scenarios resample complete Q/government/nominal procedure-amount tuples using normalized subset weights. Primary boundaries are read from the bundle: low Q < 7, medium 7 <= Q <= 35, high Q > 35. FONAFE retains its special centered-contrast treatment. Empty conditional cells are rejected. Amount is a procedure reference amount, not an item amount or a monetary eligibility filter.
- **Temporal identity:** `T = D1 + D2 + D3`, without implicit rounding or minimum-day adjustments. The simulated sum and Script 05's independently calibrated TOTAL marginal are different distributions; they must not be substituted or forced to agree. Empirical validation of the sum belongs to Script 08.
- **Precision metrics:** Mean, sample standard deviation, P90, P95 and strict P(T > t) for t = 30, 45, 60, 75, 90, 120, 150 and 180 calendar days. Standard-deviation precision uses the fourth central moment; quantile intervals use order statistics/binomial ranks; exceedances use Wilson intervals, including nonzero uncertainty when no exceedance occurs.
- **Operational tolerances:** Pointwise 95% interval halfwidths must not exceed max(0.25 days, 0.5% of the mean), max(0.50 days, 1% of the standard deviation), max(0.50 days, 1% of P90), max(1 day, 2% of P95), and 0.005 probability units (0.5 percentage points) for each exceedance. These are numerical precision targets, not predictive-validity or engineering-equivalence criteria.
- **Acceptance:** At least 27 of 30 independent replicates must simultaneously meet all twelve metric tolerances. The smallest accepted evaluated N must also preserve acceptance at larger evaluated sizes and meet the implemented numerical-agreement check against those sizes. Agreement uses a Welch-style t margin between replicate averages; this is separate from single-run precision. Pointwise intervals and the 27/30 heuristic do not provide a simultaneous 95% coverage guarantee. If only the largest N qualifies, the absence of higher-size confirmation is explicit. Failure yields `PRECISION_NOT_REACHED`, without a forced recommendation.
- **Reproducible streams:** NumPy `SeedSequence` keys derive from the configuration identifier, N and replicate. Stream results do not depend on execution order. Initial and supplementary experiments use separate seeds and namespaces and never pool replicates.

### Protocols and Approved Results
The `initial` protocol evaluates M2/M1/M4 and all three Q scenarios at N = 1,000, 5,000, 10,000, 50,000 and 100,000, with 30 independent replicates per size, root seed `20251025` and 44,820,000 realizations. The original unchunked path remains the default for this protocol. The three low-Q mixtures qualified at 50,000; the other six returned `PRECISION_NOT_REACHED` through 100,000.

The prospective `supplement` protocol uses root seed `2026110306`, stream namespace `supplement_v1:`, 30 independent replicates at every size below, and 544,500,000 realizations. Every predefined size is evaluated even if a smaller one qualifies.

| Configuration | Supplementary N evaluated |
|---|---|
| M1 medium | 150,000; 250,000; 500,000 |
| M2 medium | 250,000; 500,000; 750,000 |
| M4 medium | 250,000; 500,000; 750,000 |
| M1 high | 500,000; 750,000; 1,000,000 |
| M2 high | 1,000,000; 2,000,000; 3,000,000 |
| M4 high | 1,000,000; 2,000,000; 3,000,000 |

The supplement processes blocks of 100,000, retaining every simulated total and calculating exact quantiles. It preserves random draw order; BLAS blocking may introduce floating-point roundoff. Tests verify close numerical equivalence without changing the statistical definitions. The controlled supplemental run completed in 706.24 seconds with a peak working set of 190.05 MiB.

| Model | Low Q | Medium Q | High Q |
|---|---:|---:|---:|
| M1 | 50,000 | 150,000 | 500,000 |
| M2 — reference | 50,000 | 500,000 | 2,000,000 |
| M4 | 50,000 | 250,000 | 2,000,000 |

These are the **smallest accepted sizes among those evaluated**, not exact mathematical minima. All recommendations have confirmation at larger evaluated sizes within their respective experiment. No common N has been certified across all nine configurations. The initial and supplementary artifacts remain independent evidence; original decisions, tolerances and replicas are preserved.

### Execution
From the repository root, use the existing approved local bundle and a fresh independent output root:

```bash
python 01_scripts/03_stochastic_simulation/06_convergence_analysis.py --bundle-dir 02_results/reproducibility/script05_sixa_export_20261102_01/02_results/02_statistical_analysis --output-root 02_results/reproducibility/script06_initial_new --protocol initial --seed 20251025
```

The supplementary protocol is reproduced separately:

```bash
python 01_scripts/03_stochastic_simulation/06_convergence_analysis.py --bundle-dir 02_results/reproducibility/script05_sixa_export_20261102_01/02_results/02_statistical_analysis --output-root 02_results/reproducibility/script06_supplement_new --protocol supplement --seed 2026110306 --chunk-size 100000
```

Both output directories must be fresh. Running these commands performs complete studies; synthetic tests are separate:

```bash
python 01_scripts/03_stochastic_simulation/06_convergence_analysis.py --self-test
```

The **26 automated tests** cover marginals, copulas, temporal sums, transformations, fixed profiles versus mixtures, deterministic streams, exact quantiles, chunk equivalence, original and supplementary plans, precision decisions, 27/30 boundaries, missing/duplicate metrics, corrupted contracts, hashes, publication failures and protected results. They include 23 loader-corruption variants and use isolated synthetic directories.

### Main Outputs (`02_results/03_stochastic_simulation/`)
Paths are relative to the chosen output root.

- `06_1_convergence_metrics.csv`: Twelve estimates, precision halfwidths, tolerances and metric flags for each configuration/N/replicate.
- `06_2_convergence_decision.json`: Protocol, plan, seed, stream namespace, block size, per-size acceptance/stability, recommended N or explicit nonacceptance, scope and dependency versions.
- `06_run_manifest.json`: Script/input fingerprints and SHA-256 values for the metrics and decisions. Publication verifies artifacts in a staging directory before renaming the complete directory; existing results are rejected.

Controlled local evidence is preserved under:

- Initial: `02_results/reproducibility/script06_real_20261103T030931307613Z/`.
- Supplement: `02_results/reproducibility/script06_supplement_real_20261103T032752392276Z/`.

Each contains the analytical outputs in `02_results/03_stochastic_simulation/` and execution logs, pre-execution integrity fingerprints and an execution-verification record at its root. The supplement additionally retains `flow_identifiers.json` for all 540 independent streams. These local evidence files are excluded from Git; publishing source and documentation does not publish data or results.

### Scope and Downstream Responsibilities
Precision applies only to the nine empirical model/scenario mixtures evaluated with fixed calibrated parameters. It is not a certificate for arbitrary fixed profiles, amount bands, sparsely represented government levels or future populations. In particular, national/FONAFE support limitations from Script 05 persist. Monte Carlo error, inherent interval variability, profile heterogeneity, parameter uncertainty and model-selection uncertainty are distinct.

The approved Script 07 reuses the importable core and both convergence decision directories. Script 08 separates internal phase-sum diagnostics from marginal out-of-fold evaluation. Joint out-of-fold validation of the phase sum remains unavailable. Script 09 evaluates descriptive and structural sensitivity.

---

## 2. Script 07 — Conditional Monte Carlo Simulation

### Purpose
`07_conditional_monte_carlo_simulation.py` orchestrates conditional Monte Carlo simulation of three correlated administrative schedule intervals. It imports the approved Script 06 core without invoking its main routine, avoiding duplicated distributions, transformations, copulas or calibration. The definitive filename replaces `07_discrete_event_simulation.py`; the rename does not change program contents or historical evidence.

The chronological milestones are query close, absolution end, integration end and scheduled award end. The model does not implement queues, resources or an independent DES engine. All intervals refer to published schedules, not verified actual durations or causal effects.

### Inputs and Convergence Decisions
- Loads Script 05's verified `sixa-calibration-bundle/1.0` and linked 2,004 empirical joint profiles through Script 06's loader.
- M2 is the scientific reference; M1 is the Q-only comparator and M4 adds government and ln(nominal procedure reference amount). Exported transformations, institutional coding and model-specific copulas are used directly. FONAFE remains a special centered-contrast case, not an independently estimated effect.
- Hash-verifies the initial and supplementary Script 06 publications, recomputes decisions through the approved verifier, checks their calibration inputs and records the source of each N. Missing, incompatible, ambiguous or unverified decisions stop execution; there is no fallback iteration count.

| Model | Low Q | Medium Q | High Q |
|---|---:|---:|---:|
| M1 | 50,000 | 150,000 | 500,000 |
| M2 — reference | 50,000 | 500,000 | 2,000,000 |
| M4 | 50,000 | 250,000 | 2,000,000 |

The primary scenarios are Q < 7, 7 <= Q <= 35 and Q > 35, as exported by Script 05. These N are the smallest accepted evaluated sizes for the nine empirical mixtures, not exact minima, a certified common size or a guarantee for fixed profiles.

### Simulation and Reproducibility
- Resamples complete Q/government/procedure-amount rows with normalized empirical subset weights, retaining code, entity, project and dependency-component identifiers. Q is never sampled independently of its covariates.
- Generates absolution, integration and post-integration intervals using the imported core and approved zero/positive integration mixture. Cumulative milestones are checked against the phase durations.
- `total_duration_days` is the continuous sum of the three phases, without rounding or an artificial minimum. Script 05's separately calibrated TOTAL marginal is not sampled or added. Validation of the phase-sum distribution remains pending in Script 08.
- Uses root seed `2026110307` and stable independent configuration streams `script07_v1:<model>:scenario:<scenario>`, N and replicate identifier 0. Execution order does not change a configuration's stream. Profile indices are selected before correlated duration draws.
- Processes one configuration at a time in blocks; the controlled run used 50,000. Retains one total vector for exact quantiles while writing compressed trajectory blocks, rather than accumulating all configurations and duplicated DataFrames.
- Computes mean, median, sample standard deviation, P90/P95 and strict exceedances at 30, 45, 60, 75, 90, 120, 150 and 180 days. Imported precision diagnostics apply to the individual production run. An accepted N under 27/30 convergence does not guarantee every future replicate passes.
- Omits pooled global statistics, tertiles, KDE and uncertified sensitivities. Future global summaries must use empirical scenario weights, never iteration counts, and must keep models separate. No SIXA interface or fixed-profile precision certification is implemented.

### Execution
From the repository root, use a fresh independent output root:

```bash
python 01_scripts/03_stochastic_simulation/07_conditional_monte_carlo_simulation.py --bundle-dir 02_results/reproducibility/script05_sixa_export_20261102_01/02_results/02_statistical_analysis --initial-dir 02_results/reproducibility/script06_real_20261103T030931307613Z/02_results/03_stochastic_simulation --supplement-dir 02_results/reproducibility/script06_supplement_real_20261103T032752392276Z/02_results/03_stochastic_simulation --output-root 02_results/reproducibility/script07_new --models M1 M2 M4 --scenarios low medium high --seed 2026110307 --chunk-size 50000
```

`--models` defaults to M2 and `--scenarios` to all three primary scenarios; explicit model/scenario selections are validated. All four artifact/output directory arguments are required. The output directory must not exist. Do not rerun merely to replace an unfavorable precision diagnostic.

Run the **10 automated synthetic tests** separately:

```bash
python 01_scripts/03_stochastic_simulation/07_conditional_monte_carlo_simulation.py --self-test
```

Tests cover side-effect-free core import, core concordance, joint profiles/FONAFE, temporal identities, known summary statistics and strict exceedances, order-independent streams, all nine N and decision provenance, invalid contracts/hashes, existing outputs, deliberate publication failure and explicit unbounded precision diagnostics for small synthetic samples.

### Main Outputs (`02_results/03_stochastic_simulation/`)
Paths are relative to the selected output root.

- `07_1_<model>_<scenario>_trajectories.csv.gz`: One file per selected configuration, with 17 columns: source code/entity/project/component, Q/government/procedure amount, simulation ID, model/scenario, three continuous phases, three cumulative milestones and continuous total. A nine-configuration run produces nine files and 5,550,000 rows in total.
- `07_2_simulation_summary.json`: Per-configuration N, mean/median/standard deviation/P90/P95, eight exceedances, twelve individual precision diagnostics, seed/stream, block size, profile support, trajectory hash and convergence provenance. It identifies output-contract changes and scientific limitations.
- `07_run_manifest.json`: Script 07 and imported core fingerprints, input hashes, convergence sources, versions, configuration list and hashes/sizes of ten analytical outputs. Staged files and trajectories are verified before publication of the complete directory; overwrites are rejected.

This replaces the old pooled CSV and Excel summary contract. `total_duration_days` is now continuous. Script 08 must explicitly select model-specific trajectory files and use correct scenario weights; it must not treat models or numerical sampling allocations as one population.

### Controlled Reference Run and Limitations
The controlled run is preserved locally at `02_results/reproducibility/script07_real_20261103T035847496236Z/`, with analytical artifacts in `02_results/03_stochastic_simulation/`. Root-level execution records, protected-file hashes, post-run audit and artifact inventory retain additional provenance. These local results are excluded from Git and are not published with source/documentation.

The run completed 5,550,000 trajectories in 160.36 seconds, with a peak working set of 197.93 MiB. All nine files had the expected row counts; profile correspondence, finite nonnegative phases, cumulative milestones, continuous sums, recomputed indicators and hashes passed verification. The 26,222 preexisting protected files retained their hashes.

| M2 scenario | N | Mean | Median | Standard deviation | P90 | P95 |
|---|---:|---:|---:|---:|---:|---:|
| Low | 50,000 | 30.453 | 26.433 | 17.178 | 50.945 | 62.100 |
| Medium | 500,000 | 44.759 | 36.899 | 31.639 | 79.025 | 99.840 |
| High | 2,000,000 | 65.970 | 49.560 | 61.827 | 122.792 | 166.015 |

Values are continuous calendar days. **M1 high retains an individual standard-deviation precision failure:** estimated SD 48.193757 days, 95% halfwidth 0.543690 days, tolerance 0.500000 days. The other 107 individual metric checks passed. This realization was not repeated, N was not increased and its evidence remains unchanged.

Numerical precision is not empirical validation or total uncertainty. National/FONAFE support limitations and nominal-amount comparability persist; fixed profiles, amount bands and future populations are not certified. Parameter/model-selection uncertainty is not automatically included. Script 08 must validate the phase-sum distribution with appropriate treatment of dependence and calibration/evaluation separation; simulated trajectories do not increase the observational sample size. Script 09 retains responsibility for substantive sensitivities. Neither subsequent script was run or approved by this simulation.
