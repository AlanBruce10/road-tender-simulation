"""Select and audit eligible vehicular-road works tenders, 2020-2025.

Run from any directory. Place in 01_scripts/01_sample_and_data/.
Dependencies: pandas, openpyxl. No external API is used.
The main workbook contains the final selection for this screening stage.
Documentary and temporal verification belong to subsequent pipeline stages.
Reproducibility changes (implementation 3.1): input contracts, complete decision
traces, code/environment metadata, validated five-file publication and no overwrite.
Official names, existing sheet/column contracts and substantive rules are retained.
Use --output-root NEW_ROOT for isolated reproduction; --self-test uses synthetic data.
The additional JSON manifest and unique logs are local execution provenance.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import numbers
import platform
import tempfile
import traceback
import uuid
from pathlib import Path
import re
import shutil
import sys
import unicodedata

import pandas as pd
import openpyxl

YEARS = tuple(range(2020, 2026))
KEYS = ["codigoconvocatoria", "n_item"]
SCHEMA_VERSION = "3.0-final-selection"
IMPLEMENTATION_VERSION = "3.1-reproducible-publication"
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


# Input contracts do not change substantive eligibility. Missing optional fields
# are audited and filled with NA; invalid dates remain subject to the original
# retain-and-review policy. Never repair a key or description by guessing.
REQUIRED_COLUMNS = {
    "notice": KEYS + ["objetocontractual", "tipoprocesoseleccion", "descripcion_proceso", "fecha_convocatoria"],
    "award": KEYS,
}
OPTIONAL_COLUMNS = {
    "notice": ["descripcion_item", "fechaintegracionbases", "fechapresentacionpropuesta",
               "montoreferencial", "codigoentidad", "entidad", "tipoentidad",
               "sistema_contratacion", "tipocompra", "moneda", "SECTOR / NIVEL DE GOBIERNO", "estadoitem"],
    "award": ["fecha_buenapro", "fecha_consentimiento_bp", "monto_adjudicado_item_soles"],
}
DATE_COLUMNS = {"fecha_convocatoria", "fechaintegracionbases", "fechapresentacionpropuesta",
                "fecha_buenapro", "fecha_consentimiento_bp"}
AMOUNT_COLUMNS = {"montoreferencial", "monto_adjudicado_item_soles"}
SCHEMA_ISSUES = []
OUTPUT_NAMES = ["00_1_sample_selection.xlsx", "00_2_sample_selection_flow.xlsx",
                "audit/00_3_candidate_notices.csv.gz", "audit/00_4_candidate_awards.csv.gz",
                "audit/00_5_screening_decisions.csv.gz"]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_source(df, family, filename):
    """Validate structure/types before screening; preserve original cell values."""
    missing = sorted(set(REQUIRED_COLUMNS[family]) - set(df.columns))
    if missing:
        raise ValueError(f"{filename}: missing required columns {missing}")
    if not df.columns.is_unique:
        raise ValueError(f"{filename}: repeated source column names")
    for col in OPTIONAL_COLUMNS[family]:
        if col not in df:
            SCHEMA_ISSUES.append({"file": filename, "column": col, "issue": "optional_column_absent", "count": len(df)})
            df[col] = pd.NA
    for col in KEYS:
        for value in df[col].dropna():
            if isinstance(value, bool) or not isinstance(value, (str, numbers.Real)):
                raise ValueError(f"{filename}: unsupported identifier type in {col}: {type(value).__name__}")
            if isinstance(value, numbers.Real) and (not math.isfinite(value) or value != int(value) or abs(value) > 2**53):
                raise ValueError(f"{filename}: nonintegral, nonfinite or unsafe numeric identifier in {col}")
    for col in ["objetocontractual", "tipoprocesoseleccion", "descripcion_proceso", "descripcion_item"]:
        if col in df and any(not isinstance(v, str) for v in df[col].dropna()):
            raise ValueError(f"{filename}: {col} must contain text or missing values")
    for col in DATE_COLUMNS.intersection(df.columns):
        present = df[col].notna() & df[col].astype(str).str.strip().ne("")
        allowed = df.loc[present, col].map(lambda v: not isinstance(v, bool) and isinstance(v, (str, numbers.Real, date)))
        if not allowed.all():
            raise ValueError(f"{filename}: unsupported date cell type in {col}")
        bad = int((present & parse_dates(df[col]).isna()).sum())
        if bad:
            SCHEMA_ISSUES.append({"file": filename, "column": col, "issue": "unparseable_date_retained", "count": bad})
    for col in AMOUNT_COLUMNS.intersection(df.columns):
        bad = int((df[col].notna() & pd.to_numeric(df[col], errors="coerce").isna()).sum())
        if bad:
            SCHEMA_ISSUES.append({"file": filename, "column": col, "issue": "nonnumeric_optional_amount", "count": bad})
    return df


def read_sources(data_dir):
    frames, manifest, inventory = {}, [], []
    for family, prefix in [("notice", "CONOSCE_CONVOCATORIAS"), ("award", "CONOSCE_ADJUDICACIONES")]:
        parts = []
        for year in YEARS:
            matches = sorted(data_dir.glob(f"{prefix}{year}_*.xlsx"))
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one {prefix}{year}_*.xlsx in {data_dir}; found {len(matches)}")
            path = matches[0]
            digest = sha256(path)
            # Check raw headers before pandas can mangle duplicate names.
            book = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                header_rows = list(book.worksheets[0].iter_rows(min_row=1, max_row=1, values_only=True))
                headers = header_rows[0] if header_rows else ()
                named = [h for h in headers if h is not None]
                if len(named) != len(set(named)):
                    raise ValueError(f"Repeated source column names: {path.name}")
            finally:
                book.close()
            with pd.ExcelFile(path, engine="openpyxl") as source_book:
                df = pd.read_excel(source_book)
            for col in df.columns:
                inventory.append({"family": family, "file": path.name, "column": col, "missing": int(df[col].isna().sum()), "rows": len(df)})
            validate_source(df, family, path.name)
            if sha256(path) != digest:
                raise ValueError(f"Input changed while being read: {path}")
            for key in KEYS:
                df[f"raw_key__{key}"] = df[key]
                df[key] = df[key].map(key_value).astype("string")
            df["source_file"] = path.name
            df["source_year"] = year
            df["source_excel_row"] = range(2, len(df) + 2)
            parts.append(df)
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


def build_outputs(project_root, out, metadata):
    """Build in private staging only; publication belongs to run()."""
    log(f"SAMPLE SELECTION AUDIT | {SCHEMA_VERSION} | {metadata['run_id']}")
    log("Notice cohort: 2020-2025 | No monetary cutoff | Stage dates retained without exclusion")
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
    if current.empty:
        raise ValueError("No ordinary works tenders remain before scope classification")
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
    metadata_columns = {"reference_amount": "montoreferencial", "entity_code": "codigoentidad", "entity_name": "entidad", "entity_type": "tipoentidad", "contracting_system": "sistema_contratacion", "purchase_type": "tipocompra", "source_currency": "moneda", "government_level": "SECTOR / NIVEL DE GOBIERNO", "selection_procedure": "tipoprocesoseleccion", "contractual_object": "objetocontractual"}
    candidates = []
    for code, group in current.groupby("codigoconvocatoria", sort=True):
        award_group = trace_awards.loc[trace_awards.codigoconvocatoria.eq(code)]
        # Relevant item awards only, preventing amounts/dates from unrelated items.
        award_group = award_group.loc[award_group.n_item.isin(group.n_item)]
        row = {"procedure_code": code, "procedure_description": consensus(group, "descripcion_proceso"), "item_count": group.n_item.nunique(), "notice_record_count": len(group), "award_record_count": len(award_group), "award_link_available": not award_group.empty, "road_matches": " | ".join(sorted(set(group.road_matches))), "scope_review_required": bool(group.scope_review_required.any()), "execution_scope_review": bool(group.execution_scope_review.any()), "scope_decision": "unresolved" if group.scope_decision.eq("unresolved").any() else "included", "scope_reason": " | ".join(sorted(set(group.scope_reason))), "scope_rule_ids": " | ".join(sorted(set(group.scope_rule_ids))), "nonroad_matches": " | ".join(sorted(set(group.nonroad_matches)))}
        conflicts = []
        for target, source in metadata_columns.items():
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
    if master.procedure_code.isna().any() or not master.procedure_code.is_unique:
        raise ValueError("Consolidation produced missing or duplicate procedure_code")
    if len(master) != current.codigoconvocatoria.nunique():
        raise ValueError("Consolidation count differs from retained unique procedure identifiers")
    # Keep the existing CSV columns and first-exclusion rows. Add explicit final
    # scope decisions for every retained source row, including unresolved codes.
    final_rows = current[KEYS + ["source_file", "source_excel_row"]].copy()
    final_map = master.set_index("procedure_code")
    final_rows["stage"] = "06_scope_output"
    final_rows["decision"] = final_rows.codigoconvocatoria.map(final_map.scope_decision).replace({"unresolved": "pending_review"})
    final_rows["reason"] = final_rows.codigoconvocatoria.map(final_map.scope_reason)
    decisions.append(final_rows)
    review = master.record_resolution_required | master.scope_review_required | master.quality_review_required | master.execution_scope_review
    review_codes = set(master.loc[review, "procedure_code"])
    review_rows = final_rows.loc[final_rows.codigoconvocatoria.isin(review_codes)].copy()
    review_rows["stage"] = "07_quality_review"
    review_rows["decision"] = "pending_review"
    review_rows["reason"] = "Scope, record, chronology, missing-date or execution-modality review; does not alter scope inclusion"
    decisions.append(review_rows)

    audit_dir = out / "audit"
    audit_dir.mkdir(exist_ok=True)
    names = OUTPUT_NAMES
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
    metadata["input_files"] = manifest.to_dict(orient="records")
    metadata["schema_issues"] = list(SCHEMA_ISSUES)
    settings = pd.concat([settings, pd.DataFrame([
        {"parameter": "execution_" + key, "value": json.dumps(value, ensure_ascii=False, default=str)}
        for key, value in metadata.items()
    ])], ignore_index=True)
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
    log("BUILT | Staging only; validation and publication still pending")
    return {
        "inputs": manifest.to_dict(orient="records"),
        "frames": [safe_excel(included), None, trace_notices, trace_awards, pd.concat(decisions, ignore_index=True)],
        "sheets": {name: safe_excel(frame) for name, frame in sheets.items()},
    }


def validate_outputs(out, expected):
    """Reopen all five outputs and compare logical content with in-memory tables."""
    inventory = []
    for index, name in enumerate(OUTPUT_NAMES):
        path = out / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing or empty output: {name}")
        if index == 1:
            with pd.ExcelFile(path, engine="openpyxl") as book:
                if book.sheet_names != list(expected["sheets"]):
                    raise ValueError("Audit workbook sheets differ from expected contract")
                pairs = [(sheet, frame, pd.read_excel(book, sheet_name=sheet, dtype=object, keep_default_na=False))
                         for sheet, frame in expected["sheets"].items()]
        elif index == 0:
            pairs = [(name, expected["frames"][index], pd.read_excel(path, dtype=object, engine="openpyxl", keep_default_na=False))]
        else:
            pairs = [(name, expected["frames"][index], pd.read_csv(path, dtype=object, keep_default_na=False, encoding="utf-8-sig"))]
        for label, original, reopened in pairs:
            # Match the original writer's serialization, including empty cells,
            # Excel date objects and pandas CSV numeric formatting.
            if list(original.columns) != list(reopened.columns) or len(original) != len(reopened):
                raise ValueError(f"Output structure mismatch: {label}")
            if index in (0, 1):
                for col in original:
                    left = original[col]
                    right = reopened[col]
                    if pd.api.types.is_datetime64_any_dtype(left):
                        equal = pd.to_datetime(left).fillna(pd.Timestamp.min).reset_index(drop=True).eq(pd.to_datetime(right).fillna(pd.Timestamp.min).reset_index(drop=True)).all()
                    else:
                        def cell_equal(a, b):
                            empty_a = pd.isna(a) or a == ""
                            empty_b = pd.isna(b) or b == ""
                            if empty_a or empty_b:
                                return empty_a and empty_b
                            if isinstance(a, bool) or isinstance(b, bool):
                                return type(a) is type(b) and a == b
                            if isinstance(a, numbers.Real) and isinstance(b, numbers.Real):
                                # Excel stores about 15 significant digits; tolerate
                                # serialization roundoff, never coerce text keys.
                                return math.isclose(a, b, rel_tol=1e-14, abs_tol=1e-12)
                            return str(a) == str(b)
                        equal = all(cell_equal(a, b) for a, b in zip(left, right))
                    if not equal:
                        raise ValueError(f"Output value mismatch: {label}/{col}")
            else:
                # Serialize expected CSV in memory with identical pandas rules.
                import io
                reference = pd.read_csv(io.StringIO(original.to_csv(index=False)), dtype=object, keep_default_na=False)
                pd.testing.assert_frame_equal(reference, reopened, check_dtype=False)
        inventory.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return inventory


def run(project_root, output_root=None):
    """Publish a complete new output directory, never replace existing results.

    --output-root is a separate project-shaped root. Both default and isolated
    execution refuse an existing 02_results/01_sample_and_data directory.
    Sibling staging and one rename prevent partially published definitive sets.
    A crash before publication can leave a clearly temporary staging directory.
    """
    project_root = Path(project_root).resolve()
    output_root = Path(output_root).resolve() if output_root is not None else project_root
    out = output_root / "02_results" / "01_sample_and_data"
    if out.exists() or out.is_symlink():
        raise FileExistsError(f"Refusing to replace existing results: {out}. Use a fresh --output-root.")
    if (project_root / "00_data") == output_root or (project_root / "00_data") in output_root.parents:
        raise ValueError("Output root must not be inside original 00_data")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex
    logs = output_root / "03_logs" / "01_sample_and_data"
    logs.mkdir(parents=True, exist_ok=True)
    logfile = logs / f"00_sample_selection_{run_id}.log"
    LOG.clear()
    SCHEMA_ISSUES.clear()
    metadata = {
        "run_id": run_id, "started_utc": datetime.now(timezone.utc).isoformat(),
        "implementation_version": IMPLEMENTATION_VERSION,
        "script_path": str(Path(__file__).resolve()), "script_sha256": sha256(__file__),
        "python": platform.python_version(),
        "dependencies": {name: importlib.metadata.version(name) for name in ("pandas", "numpy", "openpyxl")},
        "project_root": str(project_root), "input_root": str(project_root / "00_data"),
        "output_root": str(output_root), "years": list(YEARS),
        "parameters": {"schema_version": SCHEMA_VERSION, "amount_cutoff": None,
                       "contractual_object": "OBRA", "selection_procedure": "LICITACION PUBLICA",
                       "missing_dates": "retain_and_review", "scope_classifier": "unchanged_deterministic_rules"},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".00_{run_id}_", suffix=".tmp", dir=out.parent))
    try:
        expected = build_outputs(project_root, staging, metadata)
        metadata["outputs"] = validate_outputs(staging, expected)
        for entry in expected["inputs"]:
            if sha256(project_root / "00_data" / entry["file"]) != entry["sha256"]:
                raise ValueError(f"Input changed during execution: {entry['file']}")
        if sha256(__file__) != metadata["script_sha256"]:
            raise ValueError("Script changed during execution; refusing publication")
        metadata["completed_utc"] = datetime.now(timezone.utc).isoformat()
        metadata["status"] = "COMPLETE"
        (staging / "00_run_manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        if out.exists() or out.is_symlink():
            raise FileExistsError(f"Output appeared during execution; refusing publication: {out}")
        staging.rename(out)
        log(f"COMPLETE | Published five validated outputs: {out}")
        return out
    except Exception:
        metadata["status"] = "FAILED"
        log("FAILED | No definitive outputs published\n" + traceback.format_exc())
        if staging.exists():
            if staging.is_symlink() or staging.resolve().parent != out.parent.resolve() or not staging.name.startswith(f".00_{run_id}_"):
                raise RuntimeError("Unsafe staging cleanup path; temporary directory retained")
            shutil.rmtree(staging)
        raise
    finally:
        with logfile.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps({k: v for k, v in metadata.items() if k not in ("input_files", "schema_issues")}, ensure_ascii=False) + "\n")
            stream.write("\n".join(LOG) + "\n")



def run_self_tests():
    """Synthetic regression and fault-injection tests; never read research data."""
    import contextlib
    import io
    import unittest
    from unittest import mock

    class SyntheticTests(unittest.TestCase):
        def setUp(self):
            self.temp = tempfile.TemporaryDirectory(prefix="thesis_script00_test_")
            self.addCleanup(self.temp.cleanup)
            self.root = Path(self.temp.name) / "input"
            self.data = self.root / "00_data"
            self.data.mkdir(parents=True)
            self.output = Path(self.temp.name) / "isolated"
            self.input_hashes = {}
            for year in YEARS:
                def notice(code, item=1, description="MEJORAMIENTO DE CARRETERA", **overrides):
                    row = {col: pd.NA for col in REQUIRED_COLUMNS["notice"] + OPTIONAL_COLUMNS["notice"]}
                    row.update(codigoconvocatoria=code, n_item=item, objetocontractual="OBRA",
                               tipoprocesoseleccion="LICITACION PUBLICA", descripcion_proceso=description,
                               descripcion_item=description, fecha_convocatoria=f"01/02/{year}",
                               fechaintegracionbases=f"10/02/{year}", fechapresentacionpropuesta=f"15/02/{year}",
                               montoreferencial=100, moneda="PEN", codigoentidad="E01")
                    row.update(overrides)
                    return row
                code = str(year) + "01"
                rows = [notice(code)]
                if year == 2020:
                    rows += [notice(code, 2, montoreferencial=200),
                             notice("202002", description="CONSTRUCCION DE INSTITUCION EDUCATIVA"),
                             notice("202003", description="INTERVENCION GENERAL"),
                             notice("202004", description="MEJORAMIENTO DE CARRETERA"),
                             notice("202004", 2, description="CONSTRUCCION DE INSTITUCION EDUCATIVA"),
                             notice("202005", objetocontractual="SERVICIO"),
                             notice("202006", fecha_convocatoria="01/01/2019"),
                             notice(None), notice("202007", fecha_convocatoria=None, montoreferencial=1)]
                path = self.data / f"CONOSCE_CONVOCATORIAS{year}_test.xlsx"
                pd.DataFrame(rows).to_excel(path, index=False, engine="openpyxl")
                awards = pd.DataFrame([{"codigoconvocatoria": code, "n_item": 1,
                                       "fecha_buenapro": f"20/02/{year}",
                                       "fecha_consentimiento_bp": f"25/02/{year}",
                                       "monto_adjudicado_item_soles": 100}])
                award_path = self.data / f"CONOSCE_ADJUDICACIONES{year}_test.xlsx"
                awards.to_excel(award_path, index=False, engine="openpyxl")
            self.input_hashes = {p.name: sha256(p) for p in self.data.glob("*.xlsx")}

        def execute(self, output=None):
            with contextlib.redirect_stdout(io.StringIO()):
                return run(self.root, output or self.output)

        def assert_inputs_unchanged(self):
            self.assertEqual(self.input_hashes, {p.name: sha256(p) for p in self.data.glob("*.xlsx")})

        def test_classification_boundaries(self):
            cases = [("REHABILITACION DE CARRETERA", "included"),
                     ("CONSTRUCCION DE PUENTE VEHICULAR", "included"),
                     ("MEJORAMIENTO DE CALLE DEL CEMENTERIO", "included"),
                     ("CONSTRUCCION DE PISTAS Y VEREDAS", "included"),
                     ("CONSTRUCCION DE VEREDAS PEATONALES", "excluded"),
                     ("CONSTRUCCION DE PISTA DE ATERRIZAJE", "excluded"),
                     ("CONSTRUCCION DE INSTITUCION EDUCATIVA", "excluded"),
                     ("MEJORAMIENTO DE CARRETERA Y AGUA POTABLE", "unresolved"),
                     ("INTERVENCION GENERAL", "unresolved")]
            for description, expected in cases:
                with self.subTest(description=description):
                    self.assertEqual(classify_scope(description, "")["scope_decision"], expected)

        def test_identifiers(self):
            self.assertEqual(key_value(123.0), "123")
            self.assertEqual(key_value("00123"), "00123")
            self.assertEqual(key_value(" 123.00 "), "123")
            self.assertTrue(pd.isna(key_value(None)))
            self.assertTrue(pd.isna(key_value(" ")))

        def test_consensus(self):
            self.assertEqual(consensus(pd.DataFrame({"x": ["A", "A", None]}), "x"), "A")
            self.assertTrue(pd.isna(consensus(pd.DataFrame({"x": ["A", "B"]}), "x")))
            self.assertTrue(pd.isna(consensus(pd.DataFrame({"x": [None]}), "x")))

        def test_dates(self):
            values = parse_dates(pd.Series([43831, "31/12/2025", "invalid", None, 20]))
            self.assertEqual(values.iloc[0], pd.Timestamp("2020-01-01"))
            self.assertEqual(values.iloc[1], pd.Timestamp("2025-12-31"))
            self.assertTrue(values.iloc[2:].isna().all())

        def test_required_columns(self):
            with self.assertRaisesRegex(ValueError, "missing required"):
                validate_source(pd.DataFrame({"codigoconvocatoria": [1]}), "notice", "synthetic")

        def test_optional_fields_and_invalid_date_are_audited(self):
            frame = pd.DataFrame({"codigoconvocatoria": [1], "n_item": [1],
                                  "objetocontractual": ["OBRA"], "tipoprocesoseleccion": ["LICITACION PUBLICA"],
                                  "descripcion_proceso": ["CARRETERA"], "fecha_convocatoria": ["invalid"]})
            SCHEMA_ISSUES.clear()
            validate_source(frame, "notice", "synthetic")
            self.assertIn("descripcion_item", frame)
            self.assertTrue(any(x["issue"] == "unparseable_date_retained" for x in SCHEMA_ISSUES))
            self.assertTrue(any(x["issue"] == "optional_column_absent" for x in SCHEMA_ISSUES))

        def test_invalid_identifier_type(self):
            for value in [True, 1.5, float("inf"), 2**54]:
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "identifier"):
                    validate_source(pd.DataFrame({"codigoconvocatoria": [value], "n_item": [1]}), "award", "synthetic")

        def test_invalid_description_type(self):
            frame = pd.DataFrame({col: [1] for col in REQUIRED_COLUMNS["notice"]})
            with self.assertRaisesRegex(ValueError, "text"):
                validate_source(frame, "notice", "synthetic")

        def test_duplicate_raw_headers(self):
            path = self.data / "CONOSCE_CONVOCATORIAS2020_test.xlsx"
            book = openpyxl.Workbook()
            book.active.append(["codigoconvocatoria", "codigoconvocatoria", "n_item"])
            book.save(path)
            book.close()
            with self.assertRaisesRegex(ValueError, "Repeated source column"):
                self.execute()
            self.assertFalse((self.output / "02_results/01_sample_and_data").exists())

        def test_missing_or_multiple_source_files(self):
            path = self.data / "CONOSCE_CONVOCATORIAS2020_test.xlsx"
            shutil.copy2(path, self.data / "CONOSCE_CONVOCATORIAS2020_extra.xlsx")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                self.execute()

        def test_end_to_end_contract_integrity_and_decisions(self):
            out = self.execute()
            self.assertTrue(all((out / n).is_file() for n in OUTPUT_NAMES))
            selection = pd.read_excel(out / OUTPUT_NAMES[0], dtype={"procedure_code": str})
            self.assertEqual(set(selection.procedure_code), {str(y) + "01" for y in YEARS} | {"202007"})
            row = selection.set_index("procedure_code").loc["202001"]
            self.assertEqual(row.item_count, 2)
            self.assertTrue(row.record_resolution_required)
            self.assertTrue(pd.isna(row.reference_amount))
            self.assertTrue(pd.isna(selection.set_index("procedure_code").loc["202007", "notice_date"]))
            decisions = pd.read_csv(out / OUTPUT_NAMES[4], dtype=str)
            self.assertTrue({"included", "excluded", "pending_review"}.issubset(set(decisions.decision)))
            mixed = decisions.loc[decisions.codigoconvocatoria.eq("202004") & decisions.stage.eq("06_scope_output")]
            self.assertEqual(set(mixed.decision), {"pending_review"})
            # One terminal screening outcome for every original notice row;
            # additional quality-review events do not replace scope decisions.
            terminal = decisions.loc[decisions.stage.ne("07_quality_review")]
            self.assertFalse(terminal.duplicated(["source_file", "source_excel_row"]).any())
            original_rows = sum(len(pd.read_excel(p)) for p in self.data.glob("CONOSCE_CONVOCATORIAS*.xlsx"))
            self.assertEqual(len(terminal), original_rows)
            manifest = json.loads((out / "00_run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "COMPLETE")
            self.assertEqual(manifest["script_sha256"], sha256(__file__))
            self.assertEqual(len(manifest["input_files"]), 12)
            self.assertEqual(len(manifest["outputs"]), 5)
            for entry in manifest["outputs"]:
                self.assertEqual(entry["sha256"], sha256(out / entry["path"]))
            self.assert_inputs_unchanged()

        def test_existing_results_never_replaced(self):
            out = self.output / "02_results/01_sample_and_data"
            out.mkdir(parents=True)
            sentinel = out / "00_1_sample_selection.xlsx"
            sentinel.write_bytes(b"preserve-current-result")
            with self.assertRaisesRegex(FileExistsError, "Refusing"):
                self.execute()
            self.assertEqual(sentinel.read_bytes(), b"preserve-current-result")
            self.assert_inputs_unchanged()

        def check_failed_publication(self, patcher, error):
            with patcher, self.assertRaises(error):
                self.execute()
            self.assertFalse((self.output / "02_results/01_sample_and_data").exists())
            self.assertEqual(list((self.output / "02_results").glob(".00_*.tmp")), [])
            logs = list((self.output / "03_logs/01_sample_and_data").glob("*.log"))
            self.assertEqual(len(logs), 1)
            self.assertIn("FAILED", logs[0].read_text(encoding="utf-8"))
            self.assert_inputs_unchanged()

        def test_csv_write_failure(self):
            self.check_failed_publication(mock.patch.object(pd.DataFrame, "to_csv", side_effect=OSError("synthetic disk error")), OSError)

        def test_excel_write_failure(self):
            self.check_failed_publication(mock.patch.object(pd.DataFrame, "to_excel", side_effect=PermissionError("synthetic locked workbook")), PermissionError)

        def test_publication_rename_failure(self):
            self.check_failed_publication(mock.patch.object(Path, "rename", side_effect=PermissionError("synthetic rename denied")), PermissionError)

        def test_corrupt_output_blocks_publication(self):
            original = validate_outputs
            def corrupt(out, expected):
                (out / OUTPUT_NAMES[2]).write_bytes(b"not-a-gzip-file")
                return original(out, expected)
            self.check_failed_publication(mock.patch.dict(globals(), {"validate_outputs": corrupt}), OSError)

        def test_missing_source_file(self):
            # Only synthetic files in this test's own TemporaryDirectory.
            (self.data / "CONOSCE_CONVOCATORIAS2020_test.xlsx").unlink()
            with self.assertRaisesRegex(ValueError, "exactly one"):
                self.execute()
            self.assertFalse((self.output / "02_results/01_sample_and_data").exists())

        def test_source_mutation_blocks_publication(self):
            original = validate_outputs
            def mutate(out, expected):
                verified = original(out, expected)
                source = self.data / "CONOSCE_CONVOCATORIAS2020_test.xlsx"
                with source.open("ab") as stream:
                    stream.write(b"synthetic concurrent mutation")
                return verified
            with mock.patch.dict(globals(), {"validate_outputs": mutate}), self.assertRaisesRegex(ValueError, "Input changed"):
                self.execute()
            self.assertFalse((self.output / "02_results/01_sample_and_data").exists())

        def test_output_value_corruption_blocks_publication(self):
            original = validate_outputs
            def corrupt(out, expected):
                path = out / OUTPUT_NAMES[0]
                book = openpyxl.load_workbook(path)
                try:
                    book.active.cell(2, 1, "unexpected-procedure")
                    book.save(path)
                finally:
                    book.close()
                return original(out, expected)
            self.check_failed_publication(mock.patch.dict(globals(), {"validate_outputs": corrupt}), ValueError)

        def test_formula_text_escape(self):
            frame = pd.DataFrame({"text": ["=1+1", "@name", "plain"]})
            escaped = safe_excel(frame)
            self.assertEqual(escaped.text.tolist(), ["'=1+1", "'@name", "plain"])
            self.assertEqual(frame.text.iloc[0], "=1+1")

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SyntheticTests))
    if not result.wasSuccessful():
        raise RuntimeError("Synthetic self-tests failed; no real-data execution is permitted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--output-root", type=Path, help="Fresh project-shaped output root; existing result directories are never replaced")
    parser.add_argument("--self-test", action="store_true", help="Run synthetic automated tests in temporary directories only")
    args = parser.parse_args()
    if args.self_test:
        return run_self_tests()
    root = args.project_root.resolve() if args.project_root else root_from_script()
    run(root, args.output_root)



if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PIPELINE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
