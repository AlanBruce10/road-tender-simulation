# SEACE PDF Documents

This directory stores the documents retrieved from public SEACE procedure records:

- **Query and observation response documents** (*Pliegos de absolución de consultas y observaciones*).
- **Statements confirming that no queries or observations were submitted** (*Actas de no formulación*).

PDFs are not included in this repository. Researchers can obtain them independently by running the acquisition script.

## Input

Script 01 reads the procedure identifiers selected by Script 00 from:

```text
02_results/01_sample_and_data/00_1_sample_selection.xlsx
```

The study's reference selection contains **2,018 unique procedures**. The script processes the identifiers in the local input workbook; it does not apply additional sample-selection criteria.

## Run the Script

Run these commands from the **repository root**, after installing the project dependencies and generating the Script 00 output.

### Process a batch

Attempt up to 50 pending procedures:

```bash
python 01_scripts/01_sample_and_data/01_download_pdfs.py --batch-size 50
```

Repeat the same command to continue. The batch size can be changed, for example to `--batch-size 100`.

### Process all pending procedures

Attempt all pending procedures in one execution:

```bash
python 01_scripts/01_sample_and_data/01_download_pdfs.py --all
```

This performs one pass over the pending procedures. Cases that fail may require another execution.

## Generated Files

PDFs are stored directly in this directory using the procedure code:

```text
05_pdfs/
├── <procedure_code>.pdf
└── <procedure_code>_ACTA.pdf
```

The `_ACTA` suffix identifies a statement of no formulation. Query and observation counts are extracted in a subsequent script; Script 01 does not assign them.

In addition to retrieving PDFs, Script 01 extracts the published schedule and document-publication dates from each procedure record.

| Output | Location |
|---|---|
| PDFs | `05_pdfs/` |
| Acquisition report | `02_results/01_sample_and_data/01_acquisition/01_1_acquisition_status.xlsx` |
| Resume checkpoints | `02_results/01_sample_and_data/01_acquisition/state/` |
| Captured records and supporting evidence | `02_results/01_sample_and_data/01_acquisition/runs/` |
| Execution logs | `03_logs/01_sample_and_data/` |

Schedule dates and document-publication dates are retained separately. Neither is automatically treated as a verified actual event date.

## Existing PDFs and Resumption

The script checks existing PDFs, including files in nested pilot directories, before downloading. Suitable files are reused and copied to the standard location when needed. The procedure record is still retrieved if its schedule or document-list information remains pending.

Progress is saved after each procedure. If execution is interrupted:

1. Keep the downloaded files and acquisition checkpoints.
2. Run the same command again.
3. The script skips completed procedures and attempts pending or failed cases.

The procedure being processed at the moment of interruption may need to be repeated.

Files with unrecognized names, codes outside the current selection, invalid contents, or identifiable nomenclature mismatches are recorded in the acquisition audit. Files whose identity cannot be established from their text are flagged for review rather than treated as identity-verified.

## Execution Recommendations

Full acquisition can take considerable time because each procedure is visited individually. Please allow sufficient time for execution.

Processing speed depends on internet connectivity, SEACE responsiveness, document availability, and existing reusable files. **No fixed completion time is guaranteed.**

During execution:

- Keep the computer awake and connected to the internet.
- Do not close or interact with browser windows opened by the script.
- Run only one acquisition instance for the same project.
- Keep the acquisition report closed in Excel so it can be updated.
- Preserve the generated checkpoint files.

To stop execution, press `Ctrl+C` in the terminal. Rerun the command when ready to continue.

## Check the Results

Monitor progress in the terminal and review the acquisition report.

A message such as `[152/2018]` identifies the procedure currently being attempted within that execution. It does **not** mean that 152 PDFs have been successfully downloaded.

`ACQUIRED` indicates that the script completed its technical acquisition checks. It does not establish that all dates are actual event dates or that every document's identity has been verified.

Selecting 2,018 procedures does not guarantee 2,018 successful PDF downloads. Use the report to distinguish completed acquisitions, identity alerts, and pending or failed cases.

Independent runs may differ if the source datasets or SEACE records change. Compare procedure identifiers and acquisition outcomes, rather than PDF counts alone.
