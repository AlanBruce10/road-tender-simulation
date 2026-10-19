"""Select and audit eligible vehicular-road works tenders, 2020-2025.

Run from any directory. Place in 01_scripts/01_sample_and_data/.
Dependencies: pandas, openpyxl. No external API is used.
The main workbook contains the final selection for this screening stage.
Documentary and temporal verification belong to subsequent pipeline stages.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import re
import shutil
import sys
import unicodedata

import pandas as pd

YEARS = tuple(range(2020, 2026))
KEYS = ["codigoconvocatoria", "n_item"]
SCHEMA_VERSION = "3.0-final-selection"
# Versioned, deterministic textual rules; no external language model is used.
# Positive expressions identify the contracted asset, not isolated location names.
ROAD_RULES = {
    "R01_road_network": r"\bCARRETERAS?\b|\bAUTOPISTAS?\b|\bCAMINOS?\s+(?:VECINAL(?:ES)?|RURAL(?:ES)?|DEPARTAMENTAL(?:ES)?|NACIONAL(?:ES)?)\b|\bTROCHAS?\s+CARROZABLES?\b|\bVIAS?\s+(?:VECINAL(?:ES)?|DEPARTAMENTAL(?:ES)?|NACIONAL(?:ES)?|URBANAS?|INTERURBANAS?)\b",
    "R02_transport_service": r"\b(?:SERVICIOS?\s+DE\s+)?TRANSITABILIDAD\b|\bMOVILIDAD\s+URBANA\b|\bINFRAESTRUCTURA\s+(?:VIAL|VEHICULAR)\b|\bACCESOS?\s+VEHICULAR(?:ES)?\b|\bINTERCAMBIOS?\s+VIALES?\b",
    "R03_road_surface": r"\bPAVIMENT(?:ACION|O|OS|AR)\b|\bASFALT(?:ADO|ADOS|ICA|ICO|ICAS|ICOS)\b|\bPISTAS?\b|\bCALZADAS?\b|\bCICLOVIAS?\b",
    "R05_vehicular_network": r"\bSISTEMA\s+VIAL\b|\bRED\s+VIAL\b|\bVIAS?\s+(?:DE\s+ACCESO|EXPRESAS?|CARROZABLES?)\b|\bPASOS?\s+A\s+DESNIVEL\b|\bCORREDOR(?:ES)?\s+VIAL(?:ES)?\b",
    "R06_street_intervention": r"\b(?:MEJORAMIENTO|REHABILITACION|RENOVACION|RECONSTRUCCION|CONSTRUCCION|PAVIMENTACION)\s+(?:DE(?:L| LA| LAS| LOS)?\s+)?(?:CALLES?|AVENIDAS?|JIRON(?:ES)?|JR\.?)\b",
    "R04_road_bridge": r"\bPUENTES?\s+(?:VEHICULAR(?:ES)?|CARROZABLES?)\b|\b(?:CONSTRUCCION|RENOVACION|REPOSICION|REHABILITACION|REPARACION|MEJORAMIENTO|AMPLIACION)\s+(?:DE(?:L| LOS)?\s+)?PUENTES?\b",
}
NONROAD_RULES = {
    "N01_education": r"\bSERVICIOS?\s+EDUCATIVOS?\b|\bINFRAESTRUCTURA\s+EDUCATIVA\b|\bINSTITUCION(?:ES)?\s+EDUCATIVA(?:S)?\b|\bLOCAL(?:ES)?\s+ESCOLAR(?:ES)?\b|\bAULAS?\b",
    "N02_water_sanitation": r"\bAGUA\s+POTABLE\b|\bALCANTARILLADO\b|\bSANEAMIENTO\b|\bDISPOSICION\s+(?:SANITARIA\s+)?DE\s+EXCRETAS\b|\bUNIDADES?\s+BASICAS?\s+DE\s+SANEAMIENTO\b",
    "N03_health": r"\bSERVICIOS?\s+DE\s+SALUD\b|\bESTABLECIMIENTOS?\s+DE\s+SALUD\b|\bCENTROS?\s+DE\s+SALUD\b|\bPUESTOS?\s+DE\s+SALUD\b|\bINFRAESTRUCTURA\s+HOSPITALARIA\b",
    "N04_irrigation": r"\bSISTEMAS?\s+DE\s+RIEGO\b|\bCANALES?\s+DE\s+RIEGO\b|\bIRRIGACION\b|\bAGUA\s+PARA\s+(?:USO\s+)?RIEGO\b",
    "N05_nonroad_facility": r"\bCOMISARIAS?\b|\bESTADIOS?\b|\bCOMPLEJOS?\s+DEPORTIVOS?\b|\bPALACIO\s+MUNICIPAL\b|\bMERCADOS?\s+DE\s+ABASTOS\b|\bCEMENTERIOS?\b",
}
NONROAD_RULES.update({
    "N06_education_services": r"\bEDUCACION\s+(?:INICIAL|PRIMARIA|SECUNDARIA|SUPERIOR|BASICA)\b|\bSERVICIOS?\s+(?:BASICOS?\s+)?(?:DE\s+)?EDUCACION\b|\bLABORATORIOS?\b|\b(?:I\s*\.\s*E\s*\.(?:\s*[IPSM]\s*\.)?|INSTITUTO\s+SUPERIOR|LOCAL\s+UNIVERSITARIO)\b",
    "N07_electricity": r"\bELECTRIFICACION\b|\bENERGIA\s+ELECTRICA\b|\bSERVICIO\s+ELECTRICO\b|\bSUMINISTRO\s+ELECTRICO\b|\bSUB\s*ESTACIONES?\s+ELECTRICAS?\b|\bREDES\s+PRIMARIAS\b",
    "N08_recreation_civic": r"\bSERVICIOS?\s+(?:DE\s+)?(?:RECREACION|ESPARCIMIENTO|DEPORTIVOS?|ADMINISTRACION\s+DE\s+JUSTICIA)\b|\bLOCAL(?:ES)?\s+(?:COMUNAL(?:ES)?|MULTIUSO|INSTITUCIONAL(?:ES)?)\b|\bCENTRO\s+(?:FERIAL|CULTURAL)\b|\bPARQUES?\b|\bPLAZA\s+DE\s+ARMAS\b|\bESPACIOS?\s+PUBLICOS?\b|\bAMBIENTE\s+DE\s+RECREACION\b",
    "N09_water_infrastructure": r"\b(?:SISTEMA|SERVICIO|CANAL|INFRAESTRUCTURA)\s+(?:PARA\s+|DE\s+)?RIEGO\b|\bAGUA\s+PARA\s+EL\s+RIEGO\b|\bDEFENSA\s+RIBEREN[AO]\b|\bPROTECCION\s+(?:EN\s+)?RIBERAS?\b|\bPROTECCION\s+(?:EN\s+)?RIVERAS?\b|\bDRENAJE\s+PLUVIAL\b",
    "N13_education_facilities": r"\bEDUCACION\b|\bEDUCATIV[AO]S?\b|(?<!\w)I\s*\.\s*E\s*\.(?:\s*[IPSM]\s*\.)?|\bUNIVERSIDAD(?:ES)?\b|\bCOLEGIOS?\b|\bINSTITUTOS?\b|\bESCUELAS?\b",
    "N14_water_agriculture": r"\bDESAGUE\b|\bAGUAS\s+RESIDUALES\b|\bINFRAESTRUCTURA\s+SANITARIA\b|\bAGUA\s+PARA\s+USO\s+AGRICOLA\b|\bSISTEMA\s+DE\s+AGUA\b|\bSERVICIOS?\s+DE\s+AGUA\b|\bRESERVORIOS?\b|\bREPRESAS?\b|\bAGUA\s+Y\s+SANEAMIENTO\b",
    "N15_flood_protection": r"\bPROTECCION\s+(?:FRENTE\s+A|Y\s+CONTROL\s+DE)\s+(?:INUNDACIONES|ALUVIONES)\b|\bDEFENSA\s+RIBERENA\b|\bENCAUZAMIENTO\b",
    "N16_other_buildings": r"\bSERVICIOS?\s+MIGRATORIOS?\b|\bSEDE\s+DE\b|\bARCHIVO\s+REGIONAL\b|\bCENTRO\s+PENITENCIARIO\b|\bSEGURIDAD\s+CIUDADANA\b|\bTERMINAL\s+PESQUERO\b|\bCAMAL\b|\bMATADERO\b|\bSERVICIOS?\s+FUNERARIOS?\b|\bSERVICIOS?\s+CULTURALES?\b",
    "N17_health_facilities": r"\b(?:CONSTRUCCION|MEJORAMIENTO|AMPLIACION|REHABILITACION)\s+(?:DE(?:L)?\s+)?HOSPITAL(?:ES)?\b|\bATENCION\s+DE\s+SALUD\b|\bATENCION\s+MEDICA\b",
    "N18_power_network": r"\bSISTEMA\s+ELECTRICO\b|\bREDES?\s+DE\s+DISTRIBUCION\b|\bLINEAS?\s+PRIMARIAS\b|\bALUMBRADO\s+PUBLICO\b",
    "N19_production_environment": r"\bCADENA\s+PRODUCTIVA\b|\bACTIVIDAD\s+ARTESANAL\b|\bRESIDUOS\s+SOLIDOS\b|\bMANEJO\s+DE\s+LIXIVIADOS\b|\bCELDAS\s+PARA\s+RESIDUOS\b|\bRELLENO\s+SANITARIO\b|\bINFRAESTRUCTURA\s+PRODUCTIVA\b",
    "N20_social_institutional": r"\bPRONOEI\b|\bHABITABILIDAD\s+INSTITUCIONAL\b|\bOFICINAS?\s+ADMINISTRATIVAS?\b|\bLOCAL\s+SOCIAL\b|\bCASA\s+DE\s+REPOSO\b|\bSERVICIOS?\s+SOCIO\s*CULTURALES?\b|\bINVESTIGACION\s+POLICIAL\b|\bEDIFICIO\b|\bPALACIO\b",
    "N21_flood_control": r"\bPROTECCION\s+CONTRA\s+INUNDACIONES\b|\bPROTECCION\s+FRENTE\s+A\s+INUNDACIONES\b|\bCONTROL\s+DE\s+INUNDACIONES\b|\bPROTECCION\s+EN\s+RIBERAS\b",
    "N10_facilities": r"\bHANGAR\b|\bALMACEN(?:ES)?\b|\bBA[NÑ]OS?\s+O\s+SERVICIOS\s+SANITARIOS\b|\bSEDES?\s+(?:ADMINISTRATIVAS?|INSTITUCIONALES?)\b",
})
# Explicit asset categories extend coverage without treating generic words as evidence.
ROAD_RULES["R07_road_circulation"] = r"\bCIRCULACION\s+VIAL\b|\bTRANSITO\s+VEHICULAR\b"
NONROAD_RULES.update({
    "N22_power_assets": r"\b(?:MEDIA|ALTA|BAJA)\s+TENSION\b|\bALIMENTADORES?\s+(?:ELECTRICOS?|DE\s+\d)|\b(?:REDES?|LINEAS?)\s+ELECTRICAS?\b",
    "N23_sports_assets": r"\bPISTAS?\s+(?:DE\s+)?ATLETISMO\b|\bCAMPOS?\s+DEPORTIVOS?\b|\bLOSAS?\s+(?:DEPORTIVAS?|MULTIDEPORTIVAS?)\b|\bTRIBUNAS?\b|\bSERVICIOS?\s+DE\s+PRACTICA\s+DEPORTIVA\b",
    "N24_other_services": r"\bSERVICIOS?\s+ACADEMICOS?\b|\bCENTROS?\s+DE\s+CONVENCIONES\b|\bMERCADOS?\s+(?:CENTRAL(?:ES)?(?:\s+DE\s+ABASTOS?)?|DE\s+ABASTO)\b",
    "N25_agricultural_drainage": r"\bDRENAJE\s+AGRICOLA\b|\bEVACUACION\s+DE\s+AGUAS\s+PLUVIALES\b|\bAREAS?\s+DEGRADADAS?\b",
    "N26_education_initials": r"(?<!\w)I\s*\.\s*E(?=\s|\.|$)",
})
ROAD_PATTERN = "|".join(f"(?:{p})" for p in ROAD_RULES.values())

# Independent scope dimensions prevent pedestrian text from excluding a road
# with sidewalks, and an airport street name from excluding a public avenue.
AIR_ASSET = r"\bPISTAS?\s+DE\s+ATERRIZAJE\b|\bAERODROMO\b|\bTERMINAL\s+AEROPORTUARIO\b"
PEDESTRIAN_ASSET = r"\bPEATONAL(?:ES)?\b|\bVEREDAS?\b|\bESCALINATAS?\b|\bESCALERAS?\b|\bCICLOVIAS?\b|\bMALECON(?:ES)?\b|\bALAMEDAS?\b"
MOTOR_EVIDENCE = r"\bVEHICULAR(?:ES)?\b|\bCARRETERAS?\b|\bAUTOPISTAS?\b|\bCAMINOS?\s+VECINAL(?:ES)?\b|\bVIAS?\s+(?:VECINAL(?:ES)?|DEPARTAMENTAL(?:ES)?|NACIONAL(?:ES)?)\b|\bTROCHAS?\s+CARROZABLES?\b|\bPISTAS?\b|\bCALZADAS?\b|\bPASOS?\s+A\s+DESNIVEL\b|\bTRANSITO\s+VEHICULAR\b"
ROAD_RULES["R08_explicit_road_service"] = r"\bSERVICIOS?\s+VIALES?\b|\bMEJORAMIENTO\s+VIAL\b|\b(?:CREACION|MEJORAMIENTO|CONSTRUCCION|REHABILITACION|RENOVACION|REPARACION)\s+(?:DE(?:L|\s+LA|\s+LAS|\s+LOS)?\s+)?(?:AV\.|JR\.|CA\.)"
NONROAD_RULES["N27_named_nonroad_services"] = r"\bRESIDENCIA\s+ESCOLAR\b|\bBOCATOMA\s+DE\s+RIEGO\b|\bCANALES?\s+DE\s+REGADIO\b|\bLIMPIEZA\s+PUBLICA\b|\bBOTADERO\b|\bDESEMBARCADERO\s+PESQUERO\b|\bINFRAESTRUCTURA\s+PESQUERA\b|\bESTABLECIMIENTO\s+PENITENCIARIO\b|\bSUBESTACION\s+DE\s+TRANSFORMACION\b|\bCOLISEO\b|\bSERVICIO\s+RECREATIVO\b|\bTERMINAL\s+TERRESTRE\b"
ROAD_PATTERN = "|".join(f"(?:{p})" for p in ROAD_RULES.values())
EXECUTION_REVIEW = r"\bCONCURSO OFERTA\b|\bLLAVE EN MANO\b|\bDISENO Y CONSTRUCCION\b|\bELABORACION.*EXPEDIENTE TECNICO"


def subject_text(value):
    """Remove explicit administrative-location tails, retaining original text elsewhere."""
    text = norm(value)
    return re.split(r"\b(?:EN (?:EL|LOS) DISTRITOS? DE|DEL DISTRITO DE|DISTRITO DE|PROVINCIA DE|DEPARTAMENTO DE)\b", text, maxsplit=1)[0]


def matches_by_rule(text, rules):
    return [(rule, m.group(0)) for rule, pattern in rules.items() for m in re.finditer(pattern, text)]


def classify_scope(procedure, item):
    """Classify descriptions independently; contradictory evidence is not guessed away.

    Clear nonroad objects are excluded even when their location includes PUENTE.
    Mixed road/nonroad objects remain unresolved. This is textual screening,
    not validated natural-language understanding.
    """
    proc, detail = subject_text(procedure), subject_text(item)
    def remove_explicit_place_names(text):
        # Mask only immediate place-name homonyms; do not erase facility objects.
        return re.sub(r"\b(AVENIDA|AV\.|JIRON|JR\.|CALLES?|CA\.|A\.\s*H\.?|AA\.\s*HH\.?)\s+(?:DEL\s+)?(?:CEMENTERIO|MERCADO CENTRAL|PARQUE)(?!\w)", r"\1 NAMED_LOCATION", text)
    proc, detail = remove_explicit_place_names(proc), remove_explicit_place_names(detail)
    def evidence(text):
        # Remove asset-specific homonyms only from the road evidence channel.
        road_text = re.sub(r"\bPISTAS?\s+(?:DE\s+)?ATLETISMO\b", "SPORTS_TRACK", text)
        # A road address explicitly following a building location is not its object.
        road_text = re.split(r"\b(?:UBICAD[AO]S?\s+EN|CON\s+DIRECCION\s+EN|CON\s+DOMICILIO\s+EN)\b", road_text, maxsplit=1)[0]
        # Do not interpret CALZADA as a road when introduced as a locality.
        road_text = re.sub(r"\bLOCALIDAD\s+DE\s+CALZADA\b", "NAMED_LOCALITY", road_text)
        nonroad_text = text
        if matches_by_rule(road_text, ROAD_RULES):
            nonroad_text = re.sub(r"\b(?:DRENAJE\s+PLUVIAL|EVACUACION\s+DE\s+AGUAS\s+PLUVIALES|ALCANTARILLADO\s+PLUVIAL)\b", "ROAD_DRAINAGE", nonroad_text)
        return matches_by_rule(road_text, ROAD_RULES), matches_by_rule(nonroad_text, NONROAD_RULES)
    rproc, nproc = evidence(proc)
    ritem, nitem = evidence(detail)
    road, other = rproc + ritem, nproc + nitem
    # Health/education destinations are not contracted assets when explicitly
    # introduced as road access destinations; retain that distinction conservatively.
    def destination_only(text, evidence):
        return bool(evidence) and all(re.search(r"(?:ACCESO|ACCESOS)\s+(?:(?:VEHICULAR|VEHICULARES)\s+)?(?:A|AL|A LA|A LAS|A LOS)\s*$", text[:text.find(phrase)]) for _, phrase in evidence)
    if rproc and destination_only(proc, nproc):
        nproc = []
    if ritem and destination_only(detail, nitem):
        nitem = []
    other = nproc + nitem
    # Remove facility-name matches explicitly used as street names.
    other = [(k, v) for k, v in other if not (k == "N17_health_facilities" and re.search(r"(?:JR\.?|JIRON|CALLE|AV\.?|AVENIDA)\s+" + re.escape(v), proc + " | " + detail))]
    joined = proc + " | " + detail
    # Drainage and civic landscaping may be complementary to an explicit road.
    if road:
        other = [(k, v) for k, v in other if v != "DRENAJE PLUVIAL" and not (k == "N08_recreation_civic" and re.search(r"\b(?:TRANSITABILIDAD|MOVILIDAD|INFRAESTRUCTURA VIAL)\b", joined) and v in {"PARQUE", "PARQUES", "PLAZA DE ARMAS"})]
    airport = re.search(AIR_ASSET, joined)
    pedestrian = re.search(PEDESTRIAN_ASSET, joined)
    motor = re.search(MOTOR_EVIDENCE, joined)
    explicit_road_asset = any(k in {"R01_road_network", "R05_vehicular_network"} for k, _ in road)
    if airport:
        # A contract with separate road-network evidence is mixed, not blindly excluded.
        decision = "unresolved" if explicit_road_asset else "excluded"
        reason = "Airport asset outside vehicular-road scope" if decision == "excluded" else "Airport and road-network assets coexist"
        other.append(("N11_airport_asset", airport.group(0)))
    elif pedestrian and not motor and not explicit_road_asset:
        decision, reason = "excluded", "Exclusively pedestrian or nonmotorized scope; no vehicular-road evidence"
        other.append(("N12_nonmotorized_only", pedestrian.group(0)))
    elif road and not other:
        decision, reason = "included", "Explicit road asset or transport-service scope"
    elif other and not road:
        decision, reason = "excluded", "Explicit nonroad contracted asset; place names do not establish road scope"
    elif road and other:
        decision, reason = "unresolved", "Road and nonroad scope evidence coexist; descriptions do not resolve contract scope"
    else:
        decision, reason = "unresolved", "Insufficient asset-specific evidence; absence of a keyword is not proof of ineligibility"
    return {"scope_decision": decision, "scope_reason": reason,
            "scope_rule_ids": " | ".join(sorted({r for r, _ in road + other})),
            "road_matches": " | ".join(sorted({v for _, v in road})),
            "nonroad_matches": " | ".join(sorted({v for _, v in other}))}


LOG = []


def log(text=""):
    print(text, flush=True)
    LOG.append(str(text))


def norm(value):
    if pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).upper().split())


def key_value(value):
    if pd.isna(value) or not str(value).strip():
        return pd.NA
    text = str(value).strip()
    return re.sub(r"^(\d+)\.0+$", r"\1", text)


def root_from_script():
    for parent in Path(__file__).resolve().parents:
        if (parent / "00_data").is_dir():
            return parent
    raise FileNotFoundError("Cannot locate repository root with 00_data; use --project-root PATH.")


def parse_dates(series):
    def parse(value):
        if pd.isna(value) or str(value).strip() == "":
            return pd.NaT
        if isinstance(value, (int, float)):
            # Plausible modern Excel serial dates only; never interpret as nanoseconds.
            return pd.Timestamp("1899-12-30") + pd.to_timedelta(value, unit="D") if 30000 <= value <= 80000 else pd.NaT
        return pd.to_datetime(value, errors="coerce", dayfirst=True)
    return pd.to_datetime(series.map(parse), errors="coerce")


def count(df):
    return len(df), len(df[KEYS].drop_duplicates()), df[KEYS[0]].nunique()


def read_sources(data_dir):
    frames, manifest, inventory = {}, [], []
    for family, prefix in [("notice", "CONOSCE_CONVOCATORIAS"), ("award", "CONOSCE_ADJUDICACIONES")]:
        parts = []
        for year in YEARS:
            matches = sorted(data_dir.glob(f"{prefix}{year}_*.xlsx"))
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one {prefix}{year}_*.xlsx in {data_dir}; found {len(matches)}")
            path = matches[0]
            df = pd.read_excel(path)
            if not df.columns.is_unique:
                raise ValueError(f"Repeated source column names: {path.name}")
            required = KEYS + (["objetocontractual", "tipoprocesoseleccion", "descripcion_proceso", "fecha_convocatoria"] if family == "notice" else [])
            missing = sorted(set(required) - set(df.columns))
            if missing:
                raise ValueError(f"{path.name}: missing {missing}")
            for col in df.columns:
                inventory.append({"family": family, "file": path.name, "column": col, "missing": int(df[col].isna().sum()), "rows": len(df)})
            for key in KEYS:
                df[f"raw_key__{key}"] = df[key]
                df[key] = df[key].map(key_value).astype("string")
            df["source_file"] = path.name
            df["source_year"] = year
            df["source_excel_row"] = range(2, len(df) + 2)
            parts.append(df)
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()
            manifest.append({"family": family, "year": year, "file": path.name, "records": len(df), "sha256": digest})
            log(f"  {family} {year}: {len(df):,} records")
        frames[family] = pd.concat(parts, ignore_index=True)
    return frames, pd.DataFrame(manifest), pd.DataFrame(inventory)


def consensus(group, col):
    if col not in group:
        return pd.NA
    values = group[col].dropna().drop_duplicates()
    return values.iloc[0] if len(values) == 1 else pd.NA


def safe_excel(df):
    # Escape spreadsheet formula prefixes in source text without altering trace CSVs.
    result = df.copy()
    for col in result.select_dtypes(include=["object", "string"]).columns:
        result[col] = result[col].map(lambda x: "'" + x if isinstance(x, str) and x.startswith(("=", "+", "-", "@")) else x)
    return result


def run(project_root):
    log(f"SAMPLE SELECTION AUDIT | {SCHEMA_VERSION}")
    log("Notice cohort: 2020-2025 | No monetary cutoff | Stage dates retained without exclusion")
    out = project_root / "02_results" / "01_sample_and_data"
    logs = project_root / "03_logs" / "01_sample_and_data"
    out.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    for name in ["00_1_sample_selection.xlsx", "00_2_sample_selection_flow.xlsx"]:
        path = out / name
        if path.exists():
            try:
                with path.open("r+b"):
                    pass
            except PermissionError as exc:
                raise PermissionError(f"Close the Excel file before running: {path}") from exc
    frames, manifest, inventory = read_sources(project_root / "00_data")
    notices, awards = frames["notice"], frames["award"]
    flow, decisions = [], []

    def record(stage, before, after, rule):
        b, a = count(before), count(after)
        flow.append(dict(stage=stage, rule=rule, records_before=b[0], records_after=a[0], keys_before=b[1], keys_after=a[1], procedures_before=b[2], procedures_after=a[2], procedures_removed=b[2]-a[2]))
        log(f"{stage}: {b[2]:,} -> {a[2]:,} unique procedures ({a[0]:,} rows)")

    def select(df, mask, stage, rule):
        mask = mask.fillna(False)
        removed = df.loc[~mask, KEYS + ["source_file", "source_excel_row"]].copy()
        removed["stage"], removed["decision"], removed["reason"] = stage, "excluded", rule
        if "scope_reason" in df:
            removed["reason"] = df.loc[~mask, "scope_reason"]
        decisions.append(removed)
        kept = df.loc[mask].copy()
        record(stage, df, kept, rule)
        return kept

    # No inner join before eligibility: unmatched notices remain visible.
    valid = notices[KEYS].notna().all(axis=1)
    invalid_keys = notices.loc[~valid].copy()
    current = select(notices, valid, "01_valid_keys", "Both procedure and item identifiers must be present; invalid identifiers retained in audit")
    current["normalized_object"] = current["objetocontractual"].map(norm)
    current = select(current, current.normalized_object.eq("OBRA"), "02_works", "Exact normalized contractual object = OBRA")
    current["normalized_procedure"] = current["tipoprocesoseleccion"].map(norm)
    category_audit = current.groupby(["source_year", "tipoprocesoseleccion"], dropna=False).agg(records=(KEYS[0], "size"), unique_procedures=(KEYS[0], "nunique")).reset_index()
    current = select(current, current.normalized_procedure.eq("LICITACION PUBLICA"), "03_public_tender", "Exact normalized selection procedure = LICITACION PUBLICA; abbreviated procedures excluded")
    notice_dates = parse_dates(current.fecha_convocatoria)
    outside = notice_dates.notna() & ~notice_dates.between("2020-01-01", "2025-12-31 23:59:59")
    current = select(current, ~outside, "04_notice_cohort", "Exclude only confirmed notice dates outside 2020-2025; missing or unparseable dates require review")
    current["notice_date_unverified"] = parse_dates(current.fecha_convocatoria).isna()
    classified = current.apply(lambda r: pd.Series(classify_scope(r["descripcion_proceso"], r.get("descripcion_item", ""))), axis=1)
    current = pd.concat([current, classified], axis=1)
    text = current["descripcion_proceso"].fillna("").map(norm) + " | " + current.get("descripcion_item", pd.Series("", index=current.index)).fillna("").map(norm)
    current["execution_scope_review"] = text.str.contains(EXECUTION_REVIEW, regex=True)
    current["scope_review_required"] = current.scope_decision.eq("unresolved") | current.notice_date_unverified
    # Classify every ordinary works tender: this also detects false negatives
    # that the previous keyword-retrieval stage silently discarded.
    all_scope_rows = current.copy()
    scope_excluded = current.loc[current.scope_decision.eq("excluded")].copy()
    current = select(current, ~current.scope_decision.eq("excluded"), "05_nonroad_exclusion", "Exclude explicit nonroad scope; preserve unresolved descriptions in a separate register")

    # Full original candidate columns are kept separately for both sources.
    codes = set(current.codigoconvocatoria.dropna())
    trace_notices = notices.loc[notices.codigoconvocatoria.isin(codes)].copy()
    trace_awards = awards.loc[awards.codigoconvocatoria.isin(codes)].copy()
    valid_awards = awards.loc[awards[KEYS].notna().all(axis=1)].copy()
    nk = notices.loc[valid, KEYS].drop_duplicates()
    ak = valid_awards[KEYS].drop_duplicates()
    linkage = nk.merge(ak, on=KEYS, how="outer", indicator=True, validate="one_to_one")

    date_columns = {"notice_date": "fecha_convocatoria", "integrated_terms_date": "fechaintegracionbases", "proposal_date": "fechapresentacionpropuesta"}
    metadata = {"reference_amount": "montoreferencial", "entity_code": "codigoentidad", "entity_name": "entidad", "entity_type": "tipoentidad", "contracting_system": "sistema_contratacion", "purchase_type": "tipocompra", "source_currency": "moneda", "government_level": "SECTOR / NIVEL DE GOBIERNO", "selection_procedure": "tipoprocesoseleccion", "contractual_object": "objetocontractual"}
    candidates = []
    for code, group in current.groupby("codigoconvocatoria", sort=True):
        award_group = trace_awards.loc[trace_awards.codigoconvocatoria.eq(code)]
        # Relevant item awards only, preventing amounts/dates from unrelated items.
        award_group = award_group.loc[award_group.n_item.isin(group.n_item)]
        row = {"procedure_code": code, "procedure_description": consensus(group, "descripcion_proceso"), "item_count": group.n_item.nunique(), "notice_record_count": len(group), "award_record_count": len(award_group), "award_link_available": not award_group.empty, "road_matches": " | ".join(sorted(set(group.road_matches))), "scope_review_required": bool(group.scope_review_required.any()), "execution_scope_review": bool(group.execution_scope_review.any()), "scope_decision": "unresolved" if group.scope_decision.eq("unresolved").any() else "included", "scope_reason": " | ".join(sorted(set(group.scope_reason))), "scope_rule_ids": " | ".join(sorted(set(group.scope_rule_ids))), "nonroad_matches": " | ".join(sorted(set(group.nonroad_matches)))}
        conflicts = []
        for target, source in metadata.items():
            row[target] = consensus(group, source)
            if source in group and group[source].dropna().nunique() > 1:
                conflicts.append(source)
        for target, source in date_columns.items():
            row[target] = consensus(group, source)
            if source in group and group[source].dropna().nunique() > 1:
                conflicts.append(source)
        for target, source in {"award_date": "fecha_buenapro", "consent_date": "fecha_consentimiento_bp", "awarded_amount_pen": "monto_adjudicado_item_soles"}.items():
            row[target] = consensus(award_group, source)
            if source in award_group and award_group[source].dropna().nunique() > 1:
                conflicts.append(source)
        row["conflicting_fields"] = " | ".join(conflicts)
        row["multiple_items_review"] = row["item_count"] > 1
        row["record_resolution_required"] = bool(conflicts) or row["multiple_items_review"]
        row["selection_status"] = "pending_review" if row["scope_review_required"] or row["record_resolution_required"] else "candidate"
        row["queries_observations_count"] = pd.NA
        candidates.append(row)
    
    # A procedure with retained and explicitly excluded items is a mixed package.
    mixed_codes = set(scope_excluded.codigoconvocatoria).intersection(set(current.codigoconvocatoria))
    for row in candidates:
        if row["procedure_code"] in mixed_codes:
            row["scope_decision"] = "unresolved"
            row["scope_review_required"] = True
            row["scope_reason"] += " | Road and nonroad items in the same procedure"
    master = pd.DataFrame(candidates)
    # Stable empty schema is an explicit failure, avoiding silently replacing outputs.
    if master.empty:
        raise ValueError("No road candidates found. Inspect category and source data before changing rules.")
    for col in list(date_columns) + ["award_date", "consent_date"]:
        master[col + "_raw"] = master[col]
        master[col] = parse_dates(master[col])
    for name, end, start in [("query_stage_duration_days", "integrated_terms_date", "notice_date"), ("evaluation_stage_duration_days", "award_date", "integrated_terms_date"), ("total_award_time_days", "award_date", "notice_date")]:
        master[name] = (master[end] - master[start]).dt.days
    master["total_time_available"] = master.total_award_time_days.notna() & master.total_award_time_days.ge(0)
    master["complete_stage_dates"] = master[["notice_date", "integrated_terms_date", "award_date"]].notna().all(axis=1)
    master["chronology_issue"] = (master.query_stage_duration_days.lt(0) | master.evaluation_stage_duration_days.lt(0) | ((master.consent_date < master.award_date) & master.consent_date.notna()))
    master["consent_date_available"] = master.consent_date.notna()
    master["temporal_verification_status"] = "pending_official_record_verification"
    for col in ["reference_amount", "awarded_amount_pen"]:
        master[col] = pd.to_numeric(master[col], errors="coerce")
    # Scope eligibility and data-quality alerts are separate: dates never change scope.
    master["selection_status"] = master.scope_decision
    master["quality_review_required"] = master.record_resolution_required | master.chronology_issue | master.notice_date.isna()
    master["execution_modality_status"] = master.execution_scope_review.map({True: "text_signal_present_not_excluded", False: "not_verified_from_source_fields"})
    included = master.loc[master.selection_status.eq("included")].copy()
    unresolved = master.loc[master.selection_status.eq("unresolved")].copy()
    stage = dict(stage="06_scope_output", rule="Main output contains textually included procedures only; unresolved scope is reported separately", records_before=len(master), records_after=len(included), keys_before=pd.NA, keys_after=pd.NA, procedures_before=len(master), procedures_after=len(included), procedures_removed=len(unresolved))
    flow.append(stage)
    log(f"06_scope_output: {len(master):,} -> {len(included):,} unique procedures; {len(unresolved):,} unresolved")
    scope_summary = all_scope_rows.groupby(["scope_decision", "scope_reason"], dropna=False).agg(
        records=(KEYS[0], "size"), procedures=(KEYS[0], "nunique")).reset_index()
    assert master.procedure_code.is_unique
    assert len(master) == current.codigoconvocatoria.nunique()

    audit_dir = out / "audit"
    audit_dir.mkdir(exist_ok=True)
    names = ["00_1_sample_selection.xlsx", "00_2_sample_selection_flow.xlsx", "audit/00_3_candidate_notices.csv.gz", "audit/00_4_candidate_awards.csv.gz", "audit/00_5_screening_decisions.csv.gz"]
    existing = [out / name for name in names if (out / name).exists()]
    if existing:
        backup = out / "previous_runs" / stamp
        backup.mkdir(parents=True)
        for path in existing:
            shutil.copy2(path, backup / path.name)
        log(f"Previous outputs backed up: {backup}")
    # Preserve all raw source values, including text dates and both original keys.
    trace_notices.to_csv(out / names[2], index=False, encoding="utf-8-sig", compression="gzip")
    trace_awards.to_csv(out / names[3], index=False, encoding="utf-8-sig", compression="gzip")
    pd.concat(decisions, ignore_index=True).to_csv(out / names[4], index=False, encoding="utf-8-sig", compression="gzip")
    safe_excel(included).to_excel(out / names[0], index=False, engine="openpyxl")
    settings = pd.DataFrame([
        {"parameter": "schema_version", "value": SCHEMA_VERSION},
        {"parameter": "scope_policy", "value": "Vehicular road works and complementary components. Standalone nonmotorized and airport assets excluded. Mixed or insufficient descriptions are not selected and remain documented in the audit."},
        {"parameter": "amount_cutoff", "value": "None"},
        {"parameter": "missing_dates", "value": "Retain; verify in next stage"},
        {"parameter": "contractual_scope", "value": "Exact OBRA and LICITACION PUBLICA; vehicular road assets; excludes exclusively nonmotorized/airport assets; regime and execution modality not inferred"},
        {"parameter": "unit", "value": "Procedure; conflicting item values unresolved, never first-row selection"},
        {"parameter": "interpretation", "value": "Versioned deterministic scope screening; validate included and excluded decisions independently before final inference"},
        {"parameter": "road_regex", "value": ROAD_PATTERN},
        {"parameter": "nonroad_regex", "value": str(NONROAD_RULES)},
        {"parameter": "classifier", "value": "Contextual deterministic rules; no external AI/API"},
    ])
    categories = []
    for field in ["sistema_contratacion", "tipocompra", "estadoitem"]:
        if field in current:
            t = current.groupby(["source_year", field], dropna=False).agg(records=(KEYS[0], "size"), procedures=(KEYS[0], "nunique")).reset_index().rename(columns={field: "value"})
            t["field"] = field
            categories.append(t)
    temporal_summary = pd.DataFrame([{"scope_status": label, "procedures": len(frame), "total_time_available": int(frame.total_time_available.sum()), "complete_stage_dates": int(frame.complete_stage_dates.sum()), "chronology_alerts": int(frame.chronology_issue.sum())} for label, frame in [("included", included), ("unresolved", unresolved)]])
    summary = pd.DataFrame([
        {"screening_outcome": "selected", "procedures": len(included)},
        {"screening_outcome": "not_selected_insufficient_or_mixed_scope", "procedures": len(unresolved)},
    ])
    # Row-level source records and procedure-level output have distinct units.
    # This compact procedure funnel is the authoritative table for reporting.
    funnel_labels = {
        "01_valid_keys": "Valid procedure and item identifiers",
        "02_works": "Contractual object: works",
        "03_public_tender": "Selection procedure: public tender",
        "04_notice_cohort": "Notice cohort: 2020-2025",
        "05_nonroad_exclusion": "After explicit nonroad exclusions",
        "06_scope_output": "Final selection: explicit eligible vehicular-road scope",
    }
    funnel_rows = [{"stage": "00_source", "criterion": "Source procurement notices", "unique_procedures": notices.codigoconvocatoria.nunique(), "procedures_not_retained": 0}]
    for step in flow:
        funnel_rows.append({"stage": step["stage"], "criterion": funnel_labels[step["stage"]], "unique_procedures": step["procedures_after"], "procedures_not_retained": step["procedures_removed"]})
    selection_funnel = pd.DataFrame(funnel_rows)
    scope_register = all_scope_rows[[*KEYS, "descripcion_proceso", "descripcion_item", "scope_decision", "scope_reason", "scope_rule_ids", "road_matches", "nonroad_matches", "source_file", "source_excel_row"]].copy()
    rulebook = pd.DataFrame([{"rule_id": k, "family": family, "regex": v} for family, rules in [("road", ROAD_RULES), ("nonroad", NONROAD_RULES), ("scope_boundary", {"N11_airport_asset": AIR_ASSET, "N12_nonmotorized_only": PEDESTRIAN_ASSET, "vehicular_evidence": MOTOR_EVIDENCE})] for k, v in rules.items()])
    log("Writing main selection and audit workbook...")
    with pd.ExcelWriter(out / names[1], engine="openpyxl") as writer:
        sheets = {"selection_funnel": selection_funnel, "methodological_funnel": pd.DataFrame(flow), "candidate_status": summary, "temporal_summary": temporal_summary, "procedure_categories": category_audit, "source_files": manifest, "column_inventory": inventory, "linkage_summary": linkage["_merge"].value_counts().rename_axis("linkage").reset_index(name="keys"), "notice_only_keys": linkage.loc[linkage._merge.eq("left_only"), KEYS], "award_only_keys": linkage.loc[linkage._merge.eq("right_only"), KEYS], "invalid_notice_keys": invalid_keys, "not_selected_scope": unresolved, "excluded_scope": scope_excluded, "scope_register": scope_register, "scope_reason_summary": scope_summary, "quality_alerts": master.loc[master.quality_review_required], "execution_scope_signals": master.loc[master.execution_scope_review], "classification_rules": rulebook, "settings": settings}
        if categories:
            sheets["candidate_categories"] = pd.concat(categories, ignore_index=True)
        for sheet, table in sheets.items():
            safe_excel(table).to_excel(writer, sheet_name=sheet, index=False)
    log(f"FINAL SELECTION: {len(included):,} unique procedures | Not selected (insufficient or mixed scope): {len(unresolved):,}")
    log(summary.to_string(index=False))
    for label, frame in [("Selected", included), ("Not selected: insufficient or mixed scope", unresolved)]:
        log(f"{label}: total-time unavailable/unresolved={(~frame.total_time_available).sum():,}; complete stage dates={frame.complete_stage_dates.sum():,}; chronology alerts={frame.chronology_issue.sum():,}")
    log("Completed. Final selection: 00_1_sample_selection.xlsx | Funnel and audit: 00_2_sample_selection_flow.xlsx")
    return logs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve() if args.project_root else root_from_script()
    logs = root / "03_logs" / "01_sample_and_data"
    logs.mkdir(parents=True, exist_ok=True)
    try:
        run(root)
    finally:
        (logs / "00_sample_selection.log").write_text("\n".join(LOG), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PIPELINE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
