"""Integrate Script 00 selection, Script 01 published schedules and Script 02 Q.

No network access, imputation, monetary cutoff, outlier cutoff or new covariates.
The eligible output supports a common complete-case, calendar-day schedule model.
Published schedule dates are NOT independently verified actual event timestamps.
Run: python 03_integrate_results.py
Dependencies: pandas, numpy, openpyxl.
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = '2.0-fiche-Q-quality-control'
DATE_NATURE = 'published_schedule_not_verified_actual_events'
LOG = []
STAGES = ['query', 'absolution', 'integration', 'offers', 'evaluation', 'award']
BOUNDARIES = [f'{stage}_{edge}' for stage in STAGES for edge in ('start', 'end')]
# Every adjacent interval is retained, including inter-stage waiting periods.
INTERVALS = [(f'{a}_to_{b}_calendar_days', a, b) for a, b in zip(BOUNDARIES, BOUNDARIES[1:])]
GATES = [
 ('valid_Q', 'Q must have status OK, a nonnegative integer and consistent document type'),
 ('verified_document', 'Script 01 identity, Script 02 fingerprint and current local PDF must agree'),
 ('verified_fiche', 'Extracted schedule with source-search/detail identity chain'),
 ('complete_dates', 'All start/end boundaries from query formulation through award are unambiguous'),
 ('consistent_sources', 'Fiche stage rows agree with available Script 01 summary dates'),
 ('chronological_dates', 'Calendar dates are nondecreasing from query start through award end'),
 ('additive_durations', 'Adjacent intervals exactly sum to the common modeled horizon'),
]


def log(text=''):
    print(text, flush=True)
    LOG.append(str(text))


def norm(value):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower()) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', text).strip()


def code(value):
    text = str(value).strip()
    if re.fullmatch(r'\d+\.0', text):
        text = text[:-2]
    if not re.fullmatch(r'\d+', text):
        raise ValueError(f'Invalid procedure_code: {value!r}')
    return text


def fingerprint(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_table(path, sheet=0):
    if path.suffix == '.csv':
        frame = pd.read_csv(path, dtype={'procedure_code': str}, keep_default_na=False)
    else:
        frame = pd.read_excel(path, sheet_name=sheet, dtype={'procedure_code': str}, keep_default_na=False)
    if 'procedure_code' not in frame:
        raise ValueError(f'procedure_code missing in {path.name} / {sheet}')
    frame['procedure_code'] = frame.procedure_code.map(code)
    return frame


def unique(frame, label):
    if frame.procedure_code.duplicated().any():
        raise ValueError(f'{label}: duplicate procedure_code; integration stopped to avoid many-to-many linkage')


def date(value):
    if value is None or pd.isna(value) or str(value).strip().lower() in ('', 'none', 'nan', 'nat'):
        return pd.NaT
    # Reject numbers: an Excel serial must not accidentally become a Unix timestamp.
    if isinstance(value, (int, float, np.number)):
        return pd.NaT
    try:
        if isinstance(value, (datetime, pd.Timestamp)):
            stamp = pd.Timestamp(value)
        elif re.match(r'^\d{4}-\d{2}-\d{2}', str(value).strip()):
            stamp = pd.Timestamp(str(value).strip())
        else:
            stamp = pd.to_datetime(str(value).strip(), dayfirst=True, errors='raise')
        # The study uses local calendar dates; time-of-day is not a duration unit.
        if stamp.tzinfo is not None:
            stamp = stamp.tz_localize(None)
        return stamp.normalize()
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def stage_key(label):
    t = norm(label)
    if t.startswith('formulacion de consultas'):
        return 'query'
    if t.startswith('absolucion de consultas'):
        return 'absolution'
    if t.startswith('integracion de') and 'bases' in t:
        return 'integration'
    if t.startswith(('presentacion de ofertas', 'presentacion de propuestas')):
        return 'offers'
    if t.startswith(('evaluacion', 'calificacion')):
        return 'evaluation'
    if t.startswith('otorgamiento de la buena pro'):
        return 'award'
    if t.startswith('convocatoria'):
        return 'notice'
    if t.startswith('registro de participantes'):
        return 'registration'
    return ''


def evidence_path(root, raw):
    text = str(raw or '').replace('\\', '/')
    direct = Path(text) / 'schedule_raw.json'
    if direct.is_file():
        return direct
    # Resolve moved Windows checkouts without hardcoded user paths.
    marker = '02_results/'
    if marker in text:
        candidate = root / marker / text.split(marker, 1)[1] / 'schedule_raw.json'
        if candidate.is_file():
            return candidate
    return None


def read_acquisition(root, selected):
    folder = root/'02_results'/'01_sample_and_data'/'01_acquisition'
    workbook = folder/'01_1_acquisition_status.xlsx'
    csv = folder/'01_1_acquisition_status.csv'
    stage_frame = pd.DataFrame()
    if workbook.exists():
        # CSV is written by Script 01 before Excel; it can be newer if Excel was locked.
        if csv.exists():
            status = read_table(csv)
        else:
            status = read_table(workbook, 'procedure_status')
        if 'schedule_stages' in pd.ExcelFile(workbook).sheet_names:
            stage_frame = read_table(workbook, 'schedule_stages')
    elif csv.exists():
        status = read_table(csv)
    else:
        status = pd.DataFrame(columns=['procedure_code'])
    unique(status, 'Script 01')
    if status.empty and not (folder/'state').is_dir():
        raise FileNotFoundError(f'Script 01 outputs missing: {folder}')
    records = {r['procedure_code']: r for r in status.to_dict('records')}
    by_stage = {k: v.to_dict('records') for k, v in stage_frame.groupby('procedure_code')} if not stage_frame.empty else {}
    gathered, audit, issues = {}, [], []
    for c in selected:
        a = records.get(c, {}).copy()
        state_file = folder/'state'/f'{c}.json'
        state = {}
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text(encoding='utf-8'))
                if code(state.get('procedure_code', c)) != c:
                    raise ValueError('State procedure code mismatch')
                a.update({k: state[k] for k in ('acquisition_status', 'evidence_directory', 'updated_at_utc') if k in state})
                a.update(state.get('schedule') or {})
                a.update({'document_'+k: v for k, v in (state.get('document') or {}).items()})
            except (ValueError, TypeError) as exc:
                issues.append({'procedure_code': c, 'issue': f'Invalid Script 01 state: {exc}'})
                a = {'state_error': str(exc)}
        rows = by_stage.get(c, [])
        origin = 'script01_workbook_schedule_stages'
        rawpath = evidence_path(root, a.get('evidence_directory'))
        if rawpath:
            try:
                raw = json.loads(rawpath.read_text(encoding='utf-8'))
                if code(raw.get('procedure_code', c)) != c:
                    raise ValueError('Raw schedule procedure code mismatch')
                rows = [{'stage': r.get('stage_label', ''),
                         'start_raw': (r.get('date_tokens') or ['', ''])[0],
                         'end_raw': (r.get('date_tokens') or ['', ''])[-1],
                         'raw_text': r.get('raw_text', '')} for r in raw.get('schedule_rows', [])]
                origin = 'script01_schedule_raw_json'
            except (ValueError, IndexError, TypeError) as exc:
                rows = []
                issues.append({'procedure_code': c, 'issue': f'Invalid raw schedule: {exc}'})
        for r in rows:
            audit.append({'procedure_code': c, 'origin': origin, **{k: r.get(k, '') for k in ('stage', 'start_raw', 'end_raw', 'raw_text')}})
        gathered[c] = (a, rows, origin)
    return gathered, audit, issues, status


def boundaries(rows):
    groups = {}
    for r in rows:
        key = stage_key(r.get('stage', ''))
        if key:
            groups.setdefault(key, []).append(r)
    out, problems = {}, []
    for key in ['notice', 'registration'] + STAGES:
        group = groups.get(key, [])
        for edge in ('start', 'end'):
            values = [date(r.get(edge+'_raw', r.get(edge+'_date'))) for r in group]
            good = sorted(set(v for v in values if pd.notna(v)))
            field = f'schedule_{key}_{edge}_date'
            out[field] = good[0] if len(good) == 1 and all(pd.notna(v) for v in values) else pd.NaT
            out[field.replace('_date', '_raw')] = ' || '.join(dict.fromkeys(str(r.get(edge+'_raw', r.get(edge+'_date', ''))) for r in group))
            if key in STAGES and (len(good) != 1 or not all(pd.notna(v) for v in values)):
                problems.append(f'{key}_{edge}:missing_invalid_or_conflicting')
    return out, problems


def evaluate(c, count, acquisition, rows, root):
    a = acquisition
    d, problems = boundaries(rows)
    q = pd.to_numeric(count.get('queries_observations_count'), errors='coerce')
    qvalid = bool(pd.notna(q) and np.isfinite(q) and q >= 0 and q == np.floor(q)
                  and count.get('count_status') == 'OK')
    kind = count.get('document_type', '')
    qvalid = qvalid and ((q == 0 and kind == 'ACTA_NO_FORMULACION') or (q > 0 and kind == 'PLIEGO'))
    d.update(queries_observations_count=int(q) if qvalid else None, Q_valid=qvalid)
    filename = str(count.get('file_name', ''))
    accepted = filename in {f'{c}.pdf', f'{c}_ACTA.pdf'}
    pdf = root/'05_pdfs'/filename if accepted else None
    local_hash = fingerprint(pdf) if pdf and pdf.is_file() else ''
    docvalid = bool(a.get('document_status') == 'OK'
                    and a.get('document_identity_validation') == 'NOMENCLATURE_MATCH'
                    and local_hash and local_hash == count.get('document_sha256') == a.get('document_sha256'))
    fichevalid = (a.get('schedule_status') == 'EXTRACTED'
                  and a.get('identity_status') == 'source_search_and_detail_matched'
                  and a.get('date_nature') == DATE_NATURE and not a.get('state_error'))
    d.update(date_nature=DATE_NATURE, duration_unit='calendar_days', modeled_origin='query_formulation_start',
             observed_actual_event_dates_verified=False, date_problems=';'.join(problems),
             local_document_sha256=local_hash)
    complete = not problems
    conflicts = []
    # Cross-check the stage table against Script 01 summary; never fill from Script 00.
    mapping = {'query_open_raw':'query_start', 'query_close_raw':'query_end',
               'absolution_raw':'absolution_end', 'integration_raw':'integration_end', 'award_raw':'award_end'}
    for rawkey, boundary in mapping.items():
        raw = a.get(rawkey)
        if raw is not None and str(raw).strip().lower() not in ('', 'none', 'nan', 'nat'):
            first, second = date(raw), d['schedule_'+boundary+'_date']
            if pd.isna(first) or (pd.notna(second) and first != second):
                conflicts.append(rawkey)
    d['source_date_conflicts'] = ';'.join(conflicts)
    values = [d['schedule_'+b+'_date'] for b in BOUNDARIES]
    chronological = complete and all(x <= y for x, y in zip(values, values[1:]))
    for name, start, end in INTERVALS:
        x, y = d['schedule_'+start+'_date'], d['schedule_'+end+'_date']
        d[name] = (y-x).days if pd.notna(x) and pd.notna(y) else None
    def days(start, end):
        x, y = d['schedule_'+start+'_date'], d['schedule_'+end+'_date']
        return (y-x).days if pd.notna(x) and pd.notna(y) else None
    d['query_to_award_calendar_days'] = days('query_start', 'award_end')
    d['query_close_to_award_calendar_days'] = days('query_end', 'award_end')
    d['absolution_calendar_days'] = days('query_end', 'absolution_end')
    d['integration_calendar_days'] = days('absolution_end', 'integration_end')
    d['post_integration_calendar_days'] = days('integration_end', 'award_end')
    additive = complete and sum(d[name] for name, _, _ in INTERVALS) == d['query_to_award_calendar_days']
    flags = [qvalid, docvalid, fichevalid, complete, not conflicts, chronological, additive]
    for (gate, _), flag in zip(GATES, flags):
        d['qc_'+gate] = bool(flag)
    failed = [gate for (gate, _), flag in zip(GATES, flags) if not flag]
    d.update(eligible_common_model=not failed, first_exclusion_reason=failed[0] if failed else '',
             all_exclusion_reasons=';'.join(failed))
    return d


def atomic_csv(frame, path):
    temp = path.with_suffix('.tmp.csv')
    frame.to_csv(temp, index=False, encoding='utf-8-sig')
    temp.replace(path)


def workbook(path, sheets):
    temporary = path.with_suffix('.tmp.xlsx')
    with pd.ExcelWriter(temporary, engine='openpyxl') as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            ws.freeze_panes = 'B2'
            if len(frame.columns):
                ws.auto_filter.ref = ws.dimensions
    try:
        temporary.replace(path)
    except PermissionError as exc:
        raise PermissionError(f'Close {path.name} in Excel and rerun; CSV outputs have been updated') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve() if args.project_root else next((p for p in Path(__file__).resolve().parents if (p/'00_data').is_dir()), None)
    if root is None:
        parser.error('Project root not found; use --project-root PATH')
    results = root/'02_results'/'01_sample_and_data'
    logs = root/'03_logs'/'01_sample_and_data'
    logs.mkdir(parents=True, exist_ok=True)
    logfile = logs/f"03_integrate_results_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log"
    try:
        sample_path = results/'00_1_sample_selection.xlsx'
        # Script 02 explicitly writes CSV before Excel to survive Excel file locks.
        counts_path = results/'02_1_query_counts.csv'
        if not counts_path.exists():
            counts_path = results/'02_1_query_counts.xlsx'
        sample, counts = read_table(sample_path), read_table(counts_path)
        unique(sample, 'Script 00'); unique(counts, 'Script 02')
        if sample.empty:
            raise ValueError('Script 00 selection is empty')
        required = {'count_status', 'queries_observations_count', 'file_name', 'document_type', 'document_sha256'}
        if not required.issubset(counts.columns):
            raise ValueError(f'Script 02 missing columns: {sorted(required-set(counts.columns))}')
        codes = sample.procedure_code.tolist()
        acquisition, stages, source_issues, status = read_acquisition(root, codes)
        count_map = {r['procedure_code']: r for r in counts.to_dict('records')}
        log(f'FINAL INTEGRATION | {VERSION} | selected={len(sample)}')
        log('Horizon: query formulation START -> award END; local calendar-day differences')
        log('Date evidence: published schedules, not independently verified actual events')
        computed = []
        for c in codes:
            a, rows, origin = acquisition[c]
            result = evaluate(c, count_map.get(c, {}), a, rows, root)
            result.update(procedure_code=c, schedule_row_source=origin)
            computed.append(result)
        qc = pd.DataFrame(computed)
        qc['queries_observations_count'] = pd.array(qc.queries_observations_count, dtype='Int64')
        # Preserve all source fields under explicit namespaces; no silent suffix collision.
        source00 = sample.rename(columns={k:'source00_'+k for k in sample.columns if k!='procedure_code'})
        source02 = counts.rename(columns={k:'source02_'+k for k in counts.columns if k!='procedure_code'})
        all_rows = source00.merge(source02, how='left', on='procedure_code', validate='one_to_one').merge(qc, on='procedure_code', validate='one_to_one')
        # Also preserve every available Script 01 summary field.
        acq_rows = [{'procedure_code': c, **{'source01_'+k: v for k,v in acquisition[c][0].items() if k!='procedure_code'}} for c in codes]
        all_rows = all_rows.merge(pd.DataFrame(acq_rows), on='procedure_code', validate='one_to_one')
        eligible = all_rows.loc[all_rows.eligible_common_model].copy()
        funnel = [{'stage':'00_selected_procedures', 'before':len(all_rows), 'excluded':0, 'remaining':len(all_rows), 'criterion':'Fixed Script 00 selection'}]
        retained = pd.Series(True, index=all_rows.index)
        for gate, explanation in GATES:
            before = int(retained.sum())
            retained &= all_rows['qc_'+gate]
            after = int(retained.sum())
            funnel.append({'stage':gate, 'before':before, 'excluded':before-after, 'remaining':after, 'criterion':explanation})
            log(f'{gate}: {before:,} -> {after:,} | excluded={before-after:,}')
        if int(retained.sum()) != len(eligible):
            raise RuntimeError('Funnel and eligible output disagree')
        exclusions = all_rows.loc[~all_rows.eligible_common_model].copy()
        first = exclusions.first_exclusion_reason.value_counts().rename_axis('reason').reset_index(name='procedures')
        overlaps = pd.DataFrame([{'reason':gate,'procedures':int((~all_rows['qc_'+gate]).sum())} for gate,_ in GATES])
        # Reconcile code sets without deleting selected procedures or failing for missing Q.
        selected_set = set(codes)
        linkage = []
        for label, frame in [('Script02', counts), ('Script01_summary', status)]:
            other = set(frame.procedure_code)
            for c in sorted(selected_set-other):
                linkage.append({'source':label,'procedure_code':c,'issue':'selected_code_missing_from_summary'})
            for c in sorted(other-selected_set):
                linkage.append({'source':label,'procedure_code':c,'issue':'extra_code_not_used'})
        metadata = pd.DataFrame([
            {'parameter':'version','value':VERSION},
            {'parameter':'date_nature','value':DATE_NATURE},
            {'parameter':'main_horizon','value':'query formulation start -> award end'},
            {'parameter':'secondary_horizon','value':'query formulation end -> award end'},
            {'parameter':'duration_unit','value':'calendar-day differences; no inclusive +1; equal dates give zero'},
            {'parameter':'boundary_requirement','value':';'.join(BOUNDARIES)},
            {'parameter':'QC_policy','value':'No imputation, date substitution, amount or outlier cutoff'},
            {'parameter':'scope','value':'Common eligible cohort for schedule-based DES and Monte Carlo; no causal validation implied'},
            {'parameter':'excluded_reason_counts','value':'first_reason is mutually exclusive; all_reason_counts overlap'},
            {'parameter':'run_utc','value':datetime.now(timezone.utc).isoformat()},
        ])
        dictionary = pd.DataFrame([{'variable': name,'start':start,'end':end,'unit':'calendar_days'} for name,start,end in INTERVALS])
        input_paths = [sample_path, counts_path]
        for name in ('01_1_acquisition_status.csv', '01_1_acquisition_status.xlsx'):
            candidate = results/'01_acquisition'/name
            if candidate.exists():
                input_paths.append(candidate)
        input_rows = [{'file':str(p.relative_to(root)), 'sha256':fingerprint(p)} for p in input_paths]
        # Fingerprint the actual per-case snapshot used, including state overrides.
        snapshot = json.dumps(acquisition, sort_keys=True, ensure_ascii=False, default=str)
        input_rows.append({'file':'Script01_selected_schedule_and_document_snapshot',
                           'sha256':hashlib.sha256(snapshot.encode('utf-8')).hexdigest()})
        input_rows.append({'file':'03_integrate_results.py', 'sha256':fingerprint(Path(__file__))})
        inputs = pd.DataFrame(input_rows)
        for stem, frame in [('03_1_integrated_dataset',all_rows), ('03_2_model_ready_dataset',eligible)]:
            atomic_csv(frame, results/(stem+'.csv'))
            workbook(results/(stem+'.xlsx'), {'data':frame})
        workbook(results/'03_3_quality_control.xlsx', {
            'funnel':pd.DataFrame(funnel), 'first_reason':first, 'all_reason_counts':overlaps,
            'excluded_procedures':exclusions, 'schedule_stages':pd.DataFrame(stages),
            'linkage_issues':pd.DataFrame(linkage,columns=['source','procedure_code','issue']),
            'source_read_issues':pd.DataFrame(source_issues,columns=['procedure_code','issue']),
            'definitions':metadata, 'duration_dictionary':dictionary, 'input_fingerprints':inputs})
        log(f'COMPLETE | selected={len(all_rows)} | common model eligible={len(eligible)} | excluded={len(exclusions)}')
        log(f'Eligible verified Q=0: {int(eligible.queries_observations_count.eq(0).sum())}')
        log(f'Outputs: {results}')
        if eligible.empty:
            log('No eligible records: inspect the quality workbook; no analytical model can be fitted to this empty output.')
    finally:
        logfile.write_text('\n'.join(LOG)+'\n', encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'PIPELINE FAILED: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
