# SEACE Procedure Documents

This directory is used locally to store procedure-level PDF documents retrieved from the **SEACE public procurement platform (Peru)** during the reconstruction of consultation and observation counts.

> **Important:** The PDF files used during the study are intentionally not distributed through this repository. This directory is documented so that the procedure-level evidence can be independently reconstructed from the original public source.

---

## Purpose

The study uses the **number of consultations and observations registered during the tender process** as the primary empirical proxy for pre-award information asymmetry / informational friction.

This information is not obtained exclusively from the annual OECE-SEACE Open Data Excel datasets.

For each procedure in the analytical sample, the computational workflow retrieves and evaluates the relevant SEACE documentation associated with consultations and observations.

The resulting procedure-level counts are subsequently integrated into the analytical dataset used by the statistical and stochastic-modeling pipeline.

---

## Local Directory

During local execution, downloaded procedure documents are stored under:

```text
05_pdfs/
```

The PDF files themselves are excluded from version control.

Therefore, a local working copy may contain substantially more files than the public GitHub directory.

This is intentional.

---

## Document Retrieval

The procedure-document retrieval workflow uses the SEACE procedure identifier associated with each tender in the analytical sample.

For each procedure, the pipeline attempts to locate the documentation containing the consultation and observation record.

Depending on the SEACE record, the relevant evidence may consist of:

- a consultation and observation document containing individual entries; or
- official procedure documentation indicating that no consultations or observations were submitted.

The workflow therefore distinguishes between:

```text
Document with consultations/observations
        │
        ▼
Extract and count valid entries
        │
        ▼
Procedure-level count
```

and:

```text
Official evidence of no consultations/observations
        │
        ▼
Procedure-level count = 0
```

A value of zero is therefore not automatically interpreted as a missing document or failed extraction.

---

## Role in the Computational Pipeline

The general data flow is:

```text
OECE-SEACE annual open data
          │
          ▼
Sample selection
          │
          ▼
137 eligible procedures
          │
          ▼
SEACE procedure-level document retrieval
          │
          ▼
Consultation / observation extraction
          │
          ▼
Procedure-level quality control
          │
          ▼
Integrated analytical dataset
```

The PDF documents are an **evidence layer**, not the final analytical dataset.

Downstream statistical analyses operate on the structured variables produced by the data-processing pipeline rather than directly on the PDF collection.

---

## Reproducibility

The public repository preserves the computational workflow required to reconstruct the analytical variables without redistributing the complete local PDF archive.

Reproduction therefore requires:

1. reconstructing the analytical sample from the official OECE-SEACE source data;
2. retrieving the corresponding public SEACE procedure documents;
3. processing the documents using the repository scripts;
4. reviewing the generated extraction and quality-control outputs; and
5. continuing with the integrated analytical dataset only after the corresponding processing stage has been completed.

The scripts, structured results, execution logs, and documented processing rules provide the reproducibility trail for this stage.

---

## Why the PDFs Are Not Included

The complete local PDF collection is intentionally excluded from the GitHub repository.

This design keeps the repository focused on:

- reproducible source acquisition;
- computational methods;
- structured analytical outputs;
- execution logs;
- methodological decisions;
- and scientific results.

It also avoids turning the repository into a static archive of source documents that can instead be retrieved from the original public procurement system.

The authoritative source remains **SEACE**.

---

## Analytical Interpretation

The extracted consultation and observation count is used as an empirical indicator in the study.

The repository does **not** assume that all consultations or observations are substantively identical.

The primary analysis uses their observed volume as the quantitative proxy defined by the study design.

Accordingly, the pipeline supports conclusions about the statistical association between this quantitative indicator and procurement award-time behavior.

It does not interpret the semantic content of individual consultations and observations, and it does not establish a causal effect of information asymmetry on procurement duration.

---

## Downstream Use

After document processing and integration, the analytical workflow evaluates:

- the continuous relationship between consultation/observation volume and award time;
- Low, Medium, and High information-asymmetry scenarios;
- scenario-specific stochastic representations;
- Monte Carlo simulation;
- a secondary two-stage discrete-event representation;
- temporal model validation; and
- robustness and sensitivity analyses.

For the complete computational sequence, see:

```text
../README.md
../01_scripts/README.md
../02_results/README.md
```
