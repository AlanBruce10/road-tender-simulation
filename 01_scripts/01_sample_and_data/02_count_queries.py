"""Count a single combined Q from verified Script 01 PDFs.
Run from any directory. No SEACE visits, no imputation, no source changes.
Outputs retain every selected procedure, including unresolved/missing cases.
Dependencies: pandas openpyxl pymupdf. Optional OCR: local Tesseract languages.
Optional Gemini proposals require --allow-ai and environment configuration;
AI-only totals are retained as proposals, not silently accepted observations.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pymupdf

VERSION = '2.0-acquisition-linked-count'
RULES_VERSION = 'combined-Q-2.0.1'
AI_PROVIDER = 'none'
AI_MODEL = os.getenv('AI_MODEL', '').strip()
AI_API_KEY = os.getenv('AI_API_KEY', '').strip()
MAX_AI_RETRIES = 4
BASE_WAIT_SECONDS = 15
LOG_LINES = []
AI_PROMPT = '''Analyze this SEACE PDF. Count numbered consultation/observation records
as one combined Q, not sentences or mentions. Use zero only if the document
explicitly confirms neither queries nor observations were submitted. Missing or
uncertain is null. Return ONLY JSON with total (integer or null), tipo_documento
(PLIEGO, ACTA_NO_FORMULACION, ACTA, OTRO), notas (brief supporting explanation).
Do not infer a total from a final number if numbering is incomplete or resets.'''


def log(message=''):
    line = str(message)
    print(line, flush=True)
    LOG_LINES.append(line)


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize_text(text):
    return re.sub(r'\s+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', str(text).lower())
                                     if not unicodedata.combining(c))).strip()


def compact(text):
    return re.sub('[^a-z0-9]', '', normalize_text(text))


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def code_string(value):
    value = str(value).strip()
    if re.fullmatch(r'\d+\.0', value):
        value = value[:-2]
    if not re.fullmatch(r'\d+', value):
        raise ValueError(f'Invalid procedure code: {value!r}')
    return value


RECORD = re.compile(r'\b(?:consulta|observaci[oó]n)\s*:\s*(?:nro\.?|n[°ºo.]|n[uú]mero)\s*:?\s*(\d+)\b', re.I)
LEGACY_RECORD = re.compile(r'\bNro\.?\s*(\d+)\s*.{0,180}?\bConsulta\s*/\s*Observaci[oó]n\s*:', re.I | re.S)
ZERO_COMBINED = re.compile(
    r'\bno\s+se\s+(?:han\s+)?(?:formulado|formularon|registrado|registraron|presentado|presentaron|recibido|recibieron)'
    r'\s+(?:las\s+|ninguna\s+|ningunas\s+)?consultas?\s*(?:y\s*/\s*o|y/o|ni|y|u|o)\s*observaciones?\b')
ZERO_TITLE = re.compile(r'\bacta\s+de\s+no\s+formulacion\s+de\s+consultas?\s*(?:y/o|y|ni|o)\s*observaciones?\b')


def record_numbers(text):
    # Prefer the explicit record heading; fallback supports the older layout.
    matches = list(RECORD.finditer(text))
    if not matches:
        matches = list(LEGACY_RECORD.finditer(text))
    return [int(m.group(1)) for m in matches]


def analyze_text(pages):
    text = '\n'.join(pages)
    normalized = normalize_text(text)
    numbers = record_numbers(text)
    zero = bool(ZERO_COMBINED.search(normalized) or ZERO_TITLE.search(normalized))
    pliego = 'pliego de absolucion de consultas y observaciones' in normalized
    result = {'queries_observations_count': None, 'document_type': 'PLIEGO' if pliego else '',
              'count_status': 'NO_RECORDS_DETECTED', 'confidence': 'LOW',
              'record_heading_count': len(numbers), 'unique_record_numbers': len(set(numbers)),
              'max_record_number': max(numbers) if numbers else None,
              'missing_record_numbers': '', 'notes': '',
              'evidence_pages': ','.join(str(i+1) for i,p in enumerate(pages)
                                       if record_numbers(p) or ZERO_COMBINED.search(normalize_text(p)) or ZERO_TITLE.search(normalize_text(p)))}
    if zero and numbers:
        result.update(count_status='CONTRADICTORY_EVIDENCE', notes='Both absence statement and numbered records detected')
    elif zero and pliego:
        result.update(count_status='CONTRADICTORY_EVIDENCE', notes='Absence statement inside a pliego; not accepted as a verified zero')
    elif zero:
        result.update(queries_observations_count=0, document_type='ACTA_NO_FORMULACION',
                      count_status='OK', confidence='HIGH', notes='Explicit combined absence statement detected')
    elif len(text.strip()) < 50:
        result.update(count_status='INSUFFICIENT_TEXT', notes='Scanned or insufficient extractable text; optional OCR may help')
    elif numbers:
        unique = set(numbers)
        maximum = max(numbers)
        missing = sorted(set(range(1, maximum+1)) - unique) if maximum <= 100000 else []
        result['missing_record_numbers'] = ','.join(map(str, missing[:200]))
        if len(numbers) > 100000 or maximum > 100000:
            result.update(count_status='NUMBERING_UNRESOLVED', notes='Implausible record numbering; Q remains missing')
        elif not pliego:
            result.update(count_status='DOCUMENT_TYPE_UNCONFIRMED', notes='Numbered records without verified pliego title')
        elif numbers == list(range(1, len(numbers)+1)):
            result.update(queries_observations_count=len(numbers), count_status='OK', confidence='HIGH',
                          notes='Combined record headings form a complete ordered sequence 1..Q')
        else:
            result.update(count_status='NUMBERING_UNRESOLVED',
                          notes='Gaps, repeated headings, resets or out-of-order numbering; maximum is diagnostic only')
    else:
        result['notes'] = 'No reliable numbered records or combined absence statement'
    return result


def extract_and_analyze(path, ocr=False, language='spa'):
    with pymupdf.open(path) as document:
        pages = [p.get_text('text', sort=False) for p in document]
        method = 'PYMUPDF'
        ocr_note = ''
        if ocr:
            for i, page in enumerate(document):
                if len(pages[i].strip()) < 50:
                    try:
                        textpage = page.get_textpage_ocr(language=language, dpi=300, full=True)
                        pages[i] = page.get_text('text', textpage=textpage)
                        method = 'PYMUPDF_OCR'
                    except Exception as exc:
                        ocr_note += f' OCR page {i+1}: {type(exc).__name__}: {str(exc)[:160]}'
        result = analyze_text(pages)
        thin_pages = [i+1 for i, text in enumerate(pages) if len(text.strip()) < 50]
        if thin_pages:
            result.update(queries_observations_count=None, count_status='INSUFFICIENT_PAGE_TEXT',
                          confidence='LOW', notes='Insufficient text on pages ' + ','.join(map(str, thin_pages)) + '; complete document count cannot be verified')
        result.update(processing_method=method, pages=len(document))
        result['notes'] += ocr_note
        return result


# Existing optional provider adapter. Proposals are validated below before export.
def analyze_with_gemini(pdf_path):
    try:
        from google import genai
        from google.genai import types

    except ImportError:
        return {
            "total": None,
            "document_type": None,
            "method": "GEMINI",
            "confidence": "LOW",
            "status": "DEPENDENCY_MISSING",
            "notes": (
                "google-genai package is not installed"
            ),
        }

    if not AI_API_KEY:
        return {
            "total": None,
            "document_type": None,
            "method": "GEMINI",
            "confidence": "LOW",
            "status": "API_KEY_MISSING",
            "notes": "AI_API_KEY is not configured",
        }

    if not AI_MODEL:
        return {
            "total": None,
            "document_type": None,
            "method": "GEMINI",
            "confidence": "LOW",
            "status": "MODEL_MISSING",
            "notes": "AI_MODEL is not configured",
        }

    client = genai.Client(
        api_key=AI_API_KEY
    )

    remote_file = None

    try:
        remote_file = client.files.upload(
            file=str(pdf_path)
        )

        waiting_cycles = 0

        while (
            remote_file.state.name
            == "PROCESSING"
        ):
            time.sleep(2)

            remote_file = client.files.get(
                name=remote_file.name
            )

            waiting_cycles += 1

            if waiting_cycles > 30:
                return {
                    "total": None,
                    "document_type": None,
                    "method": "GEMINI",
                    "confidence": "LOW",
                    "status": "TIMEOUT",
                    "notes": (
                        "Timeout while processing PDF"
                    ),
                }

        if (
            remote_file.state.name
            == "FAILED"
        ):
            return {
                "total": None,
                "document_type": None,
                "method": "GEMINI",
                "confidence": "LOW",
                "status": "UPLOAD_FAILED",
                "notes": (
                    "AI provider could not process PDF"
                ),
            }

        response = (
            client.models.generate_content(
                model=AI_MODEL,
                contents=[
                    types.Part.from_uri(
                        file_uri=remote_file.uri,
                        mime_type="application/pdf",
                    ),
                    AI_PROMPT,
                ],
            )
        )

        response_text = (
            response.text.strip()
        )

        if "```" in response_text:
            parts = response_text.split("```")

            if len(parts) >= 2:
                response_text = parts[1]

                if response_text.startswith(
                    "json"
                ):
                    response_text = (
                        response_text[4:]
                    )

                response_text = (
                    response_text.strip()
                )

        data = json.loads(
            response_text
        )

        raw_total = data.get("total")

        if raw_total is None:
            total = None
        else:
            total = int(raw_total)

        document_type = str(
            data.get(
                "tipo_documento",
                "OTRO"
            )
        ).strip()

        notes = str(
            data.get(
                "notas",
                ""
            )
        ).strip()[:100]

        valid_types = {
            "PLIEGO",
            "ACTA_NO_FORMULACION",
            "ACTA",
            "OTRO",
        }

        if (
            document_type
            not in valid_types
        ):
            return {
                "total": None,
                "document_type":
                    document_type,
                "method": "GEMINI",
                "confidence": "LOW",
                "status":
                    "INVALID_RESPONSE",
                "notes": (
                    "Invalid document type "
                    "returned by AI"
                ),
            }

        if (
            total == 0
            and document_type
            != "ACTA_NO_FORMULACION"
        ):
            return {
                "total": None,
                "document_type":
                    document_type,
                "method": "GEMINI",
                "confidence": "LOW",
                "status":
                    "ZERO_NOT_VERIFIED",
                "notes": (
                    "Zero rejected because "
                    "absence was not documented"
                ),
            }

        if total is None:
            return {
                "total": None,
                "document_type":
                    document_type,
                "method": "GEMINI",
                "confidence": "LOW",
                "status":
                    "REVIEW_REQUIRED",
                "notes": (
                    notes
                    or
                    "AI could not determine "
                    "a reliable total"
                ),
            }

        if total < 0:
            return {
                "total": None,
                "document_type":
                    document_type,
                "method": "GEMINI",
                "confidence": "LOW",
                "status":
                    "INVALID_RESPONSE",
                "notes": (
                    "Negative total rejected"
                ),
            }

        return {
            "total": total,
            "document_type":
                document_type,
            "method": "GEMINI",
            "confidence": "HIGH",
            "status": "OK",
            "notes": notes,
        }

    except Exception as error:
        error_text = str(error)

        if (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):
            status = "RETRY_503"

        elif (
            "429" in error_text
            or "RESOURCE_EXHAUSTED"
            in error_text
        ):
            status = "RETRY_429"

        elif (
            "500" in error_text
            or "INTERNAL" in error_text
        ):
            status = "RETRY_500"

        else:
            status = "PERMANENT_ERROR"

        return {
            "total": None,
            "document_type": None,
            "method": "GEMINI",
            "confidence": "LOW",
            "status": status,
            "notes": error_text[:100],
        }

    finally:
        if remote_file is not None:
            try:
                client.files.delete(
                    name=remote_file.name
                )
            except Exception:
                pass

def analyze_with_ai(pdf_path):
    if AI_PROVIDER in (
        "",
        "none",
        "off",
        "disabled",
    ):
        return {
            "total": None,
            "document_type": None,
            "method": "AI_DISABLED",
            "confidence": "LOW",
            "status": "AI_DISABLED",
            "notes": (
                "No AI fallback configured"
            ),
        }

    if AI_PROVIDER == "gemini":
        return analyze_with_gemini(
            pdf_path
        )

    return {
        "total": None,
        "document_type": None,
        "method": (
            AI_PROVIDER.upper()
        ),
        "confidence": "LOW",
        "status":
            "UNSUPPORTED_PROVIDER",
        "notes": (
            f"AI provider '{AI_PROVIDER}' "
            "does not yet have an adapter"
        ),
    }

def analyze_with_ai_retries(
    pdf_path
):
    for attempt in range(
        MAX_AI_RETRIES
    ):
        result = analyze_with_ai(
            pdf_path
        )

        if (
            result["status"]
            == "OK"
        ):
            return result

        if (
            result["status"]
            .startswith("RETRY_")
        ):
            wait_seconds = (
                BASE_WAIT_SECONDS
                * (attempt + 1)
            )

            log(
                f"      AI retry "
                f"{attempt + 1}/"
                f"{MAX_AI_RETRIES}: "
                f"{result['status']} -> "
                f"waiting {wait_seconds}s"
            )

            time.sleep(
                wait_seconds
            )

            continue

        return result

    return {
        "total": None,
        "document_type": None,
        "method": (
            AI_PROVIDER.upper()
        ),
        "confidence": "LOW",
        "status":
            "MAX_RETRIES_EXCEEDED",
        "notes": (
            "AI failed after all retries"
        ),
    }

def load_acquisition(root, codes):
    folder = root / '02_results' / '01_sample_and_data' / '01_acquisition'
    csv_path = folder / '01_1_acquisition_status.csv'
    fallback = {}
    if csv_path.exists():
        frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        if 'procedure_code' not in frame or frame.procedure_code.duplicated().any():
            raise ValueError('Acquisition CSV must have unique procedure_code')
        fallback = {code_string(r['procedure_code']): r for r in frame.to_dict('records')}
    elif not (folder / 'state').is_dir():
        raise FileNotFoundError(f'Script 01 acquisition output missing: {folder}')
    records = {}
    for code in codes:
        state_path = folder / 'state' / f'{code}.json'
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding='utf-8'))
            if code_string(state.get('procedure_code', code)) != code:
                raise ValueError(f'State identity mismatch: {state_path}')
            records[code] = {'acquisition_status': state.get('acquisition_status', ''),
                'nomenclature': state.get('schedule', {}).get('nomenclature', ''),
                **{'document_'+k: v for k,v in (state.get('document') or {}).items()}}
        else:
            records[code] = fallback.get(code, {})
    return records


def resolve_pdf(root, code, record):
    # Only canonical PDFs in 05_pdfs; never consume failed run downloads.
    raw = str(record.get('document_path') or '').replace('\\', '/')
    filename = raw.rsplit('/', 1)[-1]
    if filename not in {f'{code}.pdf', f'{code}_ACTA.pdf'}:
        return None
    path = root / '05_pdfs' / filename
    return path if path.is_file() else None


def export(rows, output, summary, directory_audit):
    frame = pd.DataFrame(rows)
    frame['queries_observations_count'] = pd.array(frame['queries_observations_count'], dtype='Int64')
    # CSV and checkpoints remain usable if Excel is open.
    csv_tmp = output.with_suffix('.tmp.csv')
    frame.to_csv(csv_tmp, index=False, encoding='utf-8-sig')
    os.replace(csv_tmp, output.with_suffix('.csv'))
    temp = output.with_suffix('.tmp.xlsx')
    try:
        frame.to_excel(temp, index=False, engine='openpyxl')
        os.replace(temp, output)
    except PermissionError:
        log('Excel locked: close the counts workbook and rerun; CSV/checkpoints are current.')
    temp_summary = summary.with_suffix('.tmp.xlsx')
    try:
        with pd.ExcelWriter(temp_summary, engine='openpyxl') as writer:
            frame.groupby('count_status', dropna=False).size().reset_index(name='procedures').to_excel(writer, sheet_name='status', index=False)
            frame.groupby('processing_method', dropna=False).size().reset_index(name='procedures').to_excel(writer, sheet_name='methods', index=False)
            frame.loc[frame.count_status != 'OK'].to_excel(writer, sheet_name='unresolved', index=False)
            frame.loc[frame.count_status == 'OK', 'queries_observations_count'].astype(float).describe().to_frame('value').to_excel(writer, sheet_name='descriptive_stats')
            pd.DataFrame(directory_audit, columns=['file_name','issue']).to_excel(writer, sheet_name='directory_audit', index=False)
        os.replace(temp_summary, summary)
    except PermissionError:
        log('Summary Excel locked; checkpoints and counts CSV are current.')
    return frame


def main():
    global AI_PROVIDER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--procedure-code', help='Process only this case; export retains the complete selection')
    parser.add_argument('--batch-size', type=int, help='Maximum new/unresolved PDF attempts; default all')
    parser.add_argument('--force', action='store_true', help='Recount instead of reusing matching successful checkpoints')
    parser.add_argument('--ocr', action='store_true', help='Try local Tesseract OCR on pages with insufficient text')
    parser.add_argument('--ocr-language', default='spa')
    parser.add_argument('--allow-ai', action='store_true', help='Enable configured Gemini fallback; sends unresolved PDFs to provider, may incur charges')
    args = parser.parse_args()
    if args.batch_size is not None and args.batch_size < 1:
        parser.error('--batch-size must be positive')
    root = args.project_root.resolve() if args.project_root else next((p for p in Path(__file__).resolve().parents if (p/'00_data').is_dir()), None)
    if root is None:
        parser.error('Cannot locate project root; use --project-root PATH')
    AI_PROVIDER = os.getenv('AI_PROVIDER', 'none').strip().lower() if args.allow_ai else 'none'
    results = root/'02_results'/'01_sample_and_data'
    logs = root/'03_logs'/'01_sample_and_data'
    checkpoints = results/'02_query_counts'/'state'
    for folder in (results,logs,checkpoints):folder.mkdir(parents=True,exist_ok=True)
    logfile = logs/f"02_count_queries_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log"
    lock_stream = (checkpoints.parent/'count.lock').open('a+b')
    lock_stream.seek(0,2)
    if lock_stream.tell()==0:lock_stream.write(b'0');lock_stream.flush()
    lock_stream.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock_stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock_stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        lock_stream.close()
        raise RuntimeError('Another Script 02 instance is running')
    try:
        sample = pd.read_excel(results/'00_1_sample_selection.xlsx', dtype=str, keep_default_na=False)
        if 'procedure_code' not in sample:raise ValueError('Script 00 output lacks procedure_code')
        codes = [code_string(v) for v in sample.procedure_code]
        if not codes or len(codes)!=len(set(codes)):raise ValueError('Selection must contain unique nonmissing codes')
        requested = code_string(args.procedure_code) if args.procedure_code else None
        if requested and requested not in codes:raise ValueError('Requested code not selected by Script 00')
        acquisition = load_acquisition(root,codes)
        allowed_files = set()
        rows=[]; attempted=0;reused=0
        config = {'rules':RULES_VERSION,'ocr':args.ocr,'ocr_language':args.ocr_language,
                  'ai_provider':AI_PROVIDER,'ai_model':AI_MODEL if args.allow_ai else ''}
        signature = hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
        log(f'QUERY COUNT | {VERSION} | selected={len(codes)} | combined Q only')
        log(f'Local OCR={args.ocr} | AI fallback={AI_PROVIDER}')
        output=results/'02_1_query_counts.xlsx';summary=results/'02_2_processing_summary.xlsx'
        for code in codes:
            a=acquisition[code]
            base={'procedure_code':code,'queries_observations_count':None,'count_status':'NOT_PROCESSED',
                  'document_type':'','processing_method':'NOT_PROCESSED','confidence':'',
                  'acquisition_status':a.get('acquisition_status','NOT_ATTEMPTED'),
                  'acquisition_document_status':a.get('document_status',''),
                  'document_identity_validation':a.get('document_identity_validation',''),
                  'file_name':'','document_sha256':'','notes':'','updated_at_utc':now(),
                  'counter_signature':signature,'ai_proposed_total':None}
            if a.get('document_status') != 'OK':
                base.update(count_status='IDENTITY_UNRESOLVED' if a.get('document_status')=='PDF_IDENTITY_MISMATCH' else 'DOCUMENT_NOT_ACQUIRED',
                            notes='Script 01 did not accept the target document; Q remains missing')
            elif a.get('document_identity_validation')!='NOMENCLATURE_MATCH':
                base.update(count_status='IDENTITY_UNRESOLVED',notes='Automatic nomenclature match absent; Q remains missing')
            else:
                path=resolve_pdf(root,code,a)
                if path is None:
                    base.update(count_status='PDF_MISSING',notes='Accepted canonical document not present in 05_pdfs')
                else:
                    allowed_files.add(path.name)
                    filehash=sha256(path)
                    base.update(file_name=path.name,document_sha256=filehash)
                    if not a.get('document_sha256') or filehash!=a.get('document_sha256'):
                        base.update(count_status='PDF_HASH_MISMATCH',notes='PDF differs from Script 01 fingerprint or fingerprint absent')
                    else:
                        checkpoint=checkpoints/f'{code}.json'
                        prior=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {}
                        same=(prior.get('document_sha256')==filehash and prior.get('counter_signature')==signature)
                        selected=requested is None or code==requested
                        if same and prior.get('count_status')=='OK' and not (args.force and selected):
                            base.update(prior);reused+=1
                        elif not selected or (args.batch_size is not None and attempted>=args.batch_size):
                            if same:base.update(prior)
                            else:base.update(count_status='NOT_PROCESSED',notes='Outside requested case or batch limit')
                        else:
                            attempted+=1
                            try:
                                counted=extract_and_analyze(path,args.ocr,args.ocr_language)
                                base.update(counted)
                                if path.stem.upper().endswith('_ACTA') and not (base['count_status']=='OK' and base['queries_observations_count']==0):
                                    base.update(queries_observations_count=None,count_status='ACTA_NOT_VERIFIED',confidence='LOW')
                                if base['count_status']!='OK' and AI_PROVIDER not in {'','none','off','disabled'}:
                                    proposal=analyze_with_ai_retries(path)
                                    total=proposal.get('total')
                                    if type(total) is int and total>=0:
                                        base.update(ai_proposed_total=total,count_status='AI_PROPOSAL_UNVERIFIED',confidence='LOW')
                                    base['notes']+=f" | AI {proposal.get('status')}: {proposal.get('notes','')}"
                            except Exception as exc:
                                base.update(queries_observations_count=None,count_status='READ_ERROR',notes=f'{type(exc).__name__}: {str(exc)[:500]}')
                            base['updated_at_utc']=now()
                            # Save every processed case before exports or next PDF.
                            atomic_json(checkpoint,base)
                            log(f"[{attempted}] {code} | Q={base['queries_observations_count']} | {base['count_status']}")
            rows.append(base)
        audit=[]
        pdfdir=root/'05_pdfs'
        for p in sorted(pdfdir.glob('*')):
            if p.is_file() and p.suffix.lower()=='.pdf' and p.name not in allowed_files:
                audit.append({'file_name':p.name,'issue':'NOT_USED_BY_ACCEPTED_ACQUISITION'})
        frame=export(rows,output,summary,audit)
        log(f"Selected={len(codes)} | Valid Q={int((frame.count_status=='OK').sum())} | Missing/unresolved Q={int((frame.count_status!='OK').sum())}")
        log(f'PDF attempts this run={attempted} | Successful counts reused={reused}')
        log(f'Counts: {output}\nSummary: {summary}')
        log('All selected procedures retained. No imputation; final analytical filtering belongs to Script 03.')
    finally:
        logfile.write_text('\n'.join(LOG_LINES)+'\n',encoding='utf-8')
        lock_stream.close()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(f'PIPELINE FAILED: {type(exc).__name__}: {exc}',file=sys.stderr)
        sys.exit(1)
