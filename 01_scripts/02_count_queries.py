import time
import json
import re
import unicodedata
from pathlib import Path
import fitz
from google import genai
from google.genai import types
import pandas as pd

API_KEY = "TU_API_KEY_DE_GEMINI"
MODELO_GEMINI = "gemini-3.8-flash"

CARPETA_PDFS = Path(r"D:\00_THESIS_ALAN_BRUCE\CORRER CÓDIGO PARA CONSULTAS Y OBSERVACIONES\02_pdfs_descargados")
CARPETA_DESCARTADOS = CARPETA_PDFS / "descartados"
CARPETA_RESULTADOS = Path(r"D:\00_THESIS_ALAN_BRUCE\CORRER CÓDIGO PARA CONSULTAS Y OBSERVACIONES\03_resultados")

EXCEL_SALIDA = CARPETA_RESULTADOS / "conteos_consultas.xlsx"
EXCEL_ESTADISTICAS = CARPETA_RESULTADOS / "estadisticas_procesamiento.xlsx"

MAX_REINTENTOS_GEMINI = 4
ESPERA_BASE = 15
PAUSA_ENTRE_PDFS = 1

PROMPT_GEMINI = """
Eres un asistente experto en analizar documentos de licitaciones publicas del Peru.

En el PDF adjunto encontraras un documento de la etapa "Absolucion de Consultas y Observaciones" de un procedimiento de seleccion.

Necesito que analices el documento y me digas:

1. CUANTAS consultas y observaciones contiene en TOTAL. Cuenta el numero mas alto que aparezca numerado.
2. QUE TIPO de documento es:
   - "PLIEGO" si es un Pliego de Absolucion de Consultas y Observaciones.
   - "ACTA_NO_FORMULACION" si es un Acta que certifica que NO se formularon consultas ni observaciones.
   - "ACTA" si es otro tipo de acta.
   - "OTRO" si es un documento diferente.
3. Una NOTA breve (maximo 100 caracteres).

Responde UNICAMENTE con un objeto JSON valido, sin texto adicional:
{"total": <numero entero>, "tipo_documento": "<PLIEGO|ACTA_NO_FORMULACION|ACTA|OTRO>", "notas": "<breve descripcion>"}
"""

def normalizar(texto):
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto

def extraer_texto_pdf(ruta_pdf):
    doc = fitz.open(ruta_pdf)
    paginas = []
    for pagina in doc:
        paginas.append(pagina.get_text("text"))
    numero_paginas = len(doc)
    doc.close()
    return "\n".join(paginas), numero_paginas

def detectar_acta_sin_consultas(texto):
    t = normalizar(texto)
    frases = [
        "no se registraron formulacion de consultas y observaciones",
        "no se registraron consultas y observaciones",
        "no se formularon consultas ni observaciones",
        "no se formularon consultas y observaciones",
        "no se registraron consultas ni observaciones",
        "no se registraron formulacion de consultas",
        "no se formularon consultas",
    ]
    for frase in frases:
        if frase in t:
            return True
    if ("acta de no" in t and "consultas" in t and "observaciones" in t):
        return True
    return False

def detectar_registros_consultas(texto):
    patron = re.compile(
        r"""
        \bNro\.?
        \s*
        (\d+)
        \s*
        .{0,180}?
        \bConsulta
        \s*/\s*
        Observaci[oó]n
        \s*:
        """,
        re.IGNORECASE | re.DOTALL | re.VERBOSE
    )
    encontrados = patron.findall(texto)
    numeros = [int(n) for n in encontrados]
    return sorted(set(numeros))

def analizar_local(ruta_pdf):
    try:
        texto, paginas = extraer_texto_pdf(ruta_pdf)
    except Exception as e:
        return (None, None, "PyMuPDF", "BAJA", "REQUIERE_OCR", f"Error lectura: {str(e)[:80]}")

    if len(texto.strip()) < 50:
        return (None, None, "PyMuPDF", "BAJA", "REQUIERE_OCR", "PDF sin texto suficiente")

    if detectar_acta_sin_consultas(texto):
        return (0, "ACTA_NO_FORMULACION", "PyMuPDF", "ALTA", "OK", "Acta sin consultas")

    numeros = detectar_registros_consultas(texto)

    if not numeros:
        return (None, None, "PyMuPDF", "BAJA", "REVISAR", "No se encontraron registros")

    primero = min(numeros)
    ultimo = max(numeros)
    unicos = len(numeros)

    esperado = set(range(1, ultimo + 1))
    encontrado = set(numeros)
    faltantes = sorted(esperado - encontrado)

    if primero == 1 and unicos == ultimo and not faltantes:
        return (ultimo, "PLIEGO", "PyMuPDF", "ALTA", "OK", f"Secuencia 1-{ultimo} completa")
    else:
        return (ultimo, "PLIEGO", "PyMuPDF", "MEDIA", "REVISAR", f"Secuencia incompleta: faltan {len(faltantes)}")

def contar_con_gemini(client, ruta_pdf):
    archivo_remoto = None
    try:
        archivo_remoto = client.files.upload(file=str(ruta_pdf))

        intentos_espera = 0
        while archivo_remoto.state.name == "PROCESSING":
            time.sleep(2)
            archivo_remoto = client.files.get(name=archivo_remoto.name)
            intentos_espera += 1
            if intentos_espera > 30:
                return (None, None, "GEMINI", "BAJA", "TIMEOUT", "Timeout esperando procesamiento")

        if archivo_remoto.state.name == "FAILED":
            return (None, None, "GEMINI", "BAJA", "ERROR_UPLOAD", "Fallo en Gemini")

        respuesta = client.models.generate_content(
            model=MODELO_GEMINI,
            contents=[
                types.Part.from_uri(file_uri=archivo_remoto.uri, mime_type="application/pdf"),
                PROMPT_GEMINI
            ]
        )

        texto_respuesta = respuesta.text.strip()

        try:
            client.files.delete(name=archivo_remoto.name)
        except:
            pass

        if "```" in texto_respuesta:
            texto_respuesta = texto_respuesta.split("```")[1]
            if texto_respuesta.startswith("json"):
                texto_respuesta = texto_respuesta[4:]
            texto_respuesta = texto_respuesta.strip()

        datos = json.loads(texto_respuesta)
        total = int(datos.get("total", 0))
        tipo = datos.get("tipo_documento", "OTRO")
        notas = datos.get("notas", "")

        return (total, tipo, "GEMINI", "ALTA", "OK", notas)

    except Exception as e:
        if archivo_remoto:
            try:
                client.files.delete(name=archivo_remoto.name)
            except:
                pass

        error_str = str(e)

        if "503" in error_str or "UNAVAILABLE" in error_str:
            return (None, None, "GEMINI", "BAJA", "REINTENTAR_503", "Gemini saturado")
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            return (None, None, "GEMINI", "BAJA", "REINTENTAR_429", "Rate limit")
        if "500" in error_str or "INTERNAL" in error_str:
            return (None, None, "GEMINI", "BAJA", "REINTENTAR_500", "Error servidor")

        return (None, None, "GEMINI", "BAJA", "ERROR_PERMANENTE", error_str[:80])

def contar_con_gemini_reintentos(client, ruta_pdf):
    for intento in range(MAX_REINTENTOS_GEMINI):
        total, tipo, metodo, confianza, estado, notas = contar_con_gemini(client, ruta_pdf)

        if estado == "OK":
            return (total, tipo, metodo, confianza, estado, notas)

        if estado.startswith("REINTENTAR"):
            espera = ESPERA_BASE * (intento + 1)
            print(f"      [Reintento {intento+1}/{MAX_REINTENTOS_GEMINI}] {estado} -> Esperando {espera}s...")
            time.sleep(espera)
            continue

        return (total, tipo, metodo, confianza, estado, notas)

    return (None, None, "GEMINI", "BAJA", "ERROR_MAX_REINTENTOS", "Fallo tras todos los reintentos")

def main():
    print("=" * 70)
    print(" CONTEO DE CONSULTAS Y OBSERVACIONES - VERSION DEFINITIVA v7")
    print(" Lee PDFs de carpeta principal Y de descartados")
    print("=" * 70)

    client = genai.Client(api_key=API_KEY)
    print("Cliente Gemini configurado.")

    pdfs_principales = sorted(CARPETA_PDFS.glob("*.pdf"))
    print(f"PDFs en carpeta principal: {len(pdfs_principales)}")

    pdfs_descartados = []
    if CARPETA_DESCARTADOS.exists():
        pdfs_descartados = sorted(CARPETA_DESCARTADOS.glob("*.pdf"))
        print(f"PDFs en carpeta descartados: {len(pdfs_descartados)}")

    todos_los_pdfs = [(p, "principal") for p in pdfs_principales] + [(p, "descartado") for p in pdfs_descartados]
    print(f"TOTAL de PDFs a procesar: {len(todos_los_pdfs)}")

    procesados_previos = {}
    if EXCEL_SALIDA.exists():
        try:
            df_prev = pd.read_excel(EXCEL_SALIDA)
            for _, fila in df_prev.iterrows():
                if fila.get("estado_conteo") == "OK":
                    procesados_previos[str(fila["nombre_archivo"])] = fila.to_dict()
            print(f"PDFs ya procesados OK: {len(procesados_previos)}")
        except Exception as e:
            print(f"Aviso: no se pudo leer Excel previo: {e}")

    resultados = []
    for i, (pdf, origen) in enumerate(todos_los_pdfs):
        nombre = pdf.stem
        codigo = nombre.split("_")[0]
        tipo_por_nombre = "ACTA" if "_ACTA" in nombre else ("OTRO" if "_OTRO" in nombre else "PLIEGO")

        print(f"\n[{i+1}/{len(todos_los_pdfs)}] Procesando: {nombre} (origen: {origen})")

        if nombre in procesados_previos:
            print(f"      Ya procesado OK. Saltando.")
            resultados.append(procesados_previos[nombre])
            continue

        print(f"      [Metodo LOCAL] Extrayendo texto...")
        total, tipo, metodo, confianza, estado, notas = analizar_local(pdf)
        print(f"      Local: total={total}, tipo={tipo}, confianza={confianza}, estado={estado}")

        if confianza != "ALTA" or estado != "OK":
            print(f"      [Metodo GEMINI] Usando IA...")
            total_g, tipo_g, metodo_g, confianza_g, estado_g, notas_g = contar_con_gemini_reintentos(client, pdf)

            if estado_g == "OK":
                total = total_g
                tipo = tipo_g
                metodo = "GEMINI"
                confianza = confianza_g
                estado = estado_g
                notas = notas_g
                print(f"      Gemini OK: total={total}, tipo={tipo}")
            else:
                if total is None:
                    total = 0
                metodo = "LOCAL+GEMINI_FALLIDO"
                estado = estado_g
                notas = notas_g
                print(f"      Gemini fallo: {estado}")

        resultados.append({
            "codigoconvocatoria": codigo,
            "nombre_archivo": nombre,
            "origen": origen,
            "tipo_por_nombre": tipo_por_nombre,
            "tipo_documento": tipo if tipo else "",
            "total_consultas_observaciones": total if total is not None else 0,
            "metodo": metodo,
            "confianza": confianza,
            "estado_conteo": estado,
            "notas": notas if notas else ""
        })

        if (i + 1) % 10 == 0:
            df_parcial = pd.DataFrame(resultados)
            df_parcial.to_excel(EXCEL_SALIDA, index=False)
            print(f"      *** Guardado parcial ***")

        time.sleep(PAUSA_ENTRE_PDFS)

    df = pd.DataFrame(resultados)
    df.to_excel(EXCEL_SALIDA, index=False)

    print("\n" + "=" * 70)
    print(" RESUMEN FINAL")
    print("=" * 70)
    print(f"Resultados guardados en: {EXCEL_SALIDA}")
    print(f"Total de PDFs procesados: {len(resultados)}")

    total_pdfs = len(df)
    ok = df[df["estado_conteo"] == "OK"]
    errores = df[df["estado_conteo"] != "OK"]

    print(f"\nConteo exitoso: {len(ok)} ({len(ok)/total_pdfs*100:.1f}%)")
    print(f"Con errores: {len(errores)} ({len(errores)/total_pdfs*100:.1f}%)")

    print("\nDistribucion por ORIGEN:")
    conteo_origen = df["origen"].value_counts()
    for origen, cantidad in conteo_origen.items():
        print(f"  {origen}: {cantidad}")

    print("\nDistribucion por METODO:")
    conteo_metodo = df["metodo"].value_counts()
    for metodo, cantidad in conteo_metodo.items():
        porcentaje = cantidad / total_pdfs * 100
        print(f"  {metodo}: {cantidad} ({porcentaje:.1f}%)")

    print("\nDistribucion por ESTADO:")
    conteo_estado = df["estado_conteo"].value_counts()
    for estado, cantidad in conteo_estado.items():
        porcentaje = cantidad / total_pdfs * 100
        print(f"  {estado}: {cantidad} ({porcentaje:.1f}%)")

    print("\nDistribucion por TIPO DE DOCUMENTO:")
    conteo_tipo = df["tipo_documento"].value_counts()
    for tipo, cantidad in conteo_tipo.items():
        if tipo:
            print(f"  {tipo}: {cantidad}")

    if len(errores) > 0:
        print("\n" + "=" * 70)
        print(" PDFs CON PROBLEMAS")
        print("=" * 70)
        print(errores[["codigoconvocatoria", "nombre_archivo", "origen", "metodo", "estado_conteo"]].to_string())

    print("\n" + "=" * 70)
    print(" ESTADISTICAS DE CONSULTAS Y OBSERVACIONES")
    print("=" * 70)

    con_conteo = df[df["estado_conteo"] == "OK"]
    if len(con_conteo) > 0:
        print(f"  Media: {con_conteo['total_consultas_observaciones'].mean():.2f}")
        print(f"  Mediana: {con_conteo['total_consultas_observaciones'].median()}")
        print(f"  Maximo: {con_conteo['total_consultas_observaciones'].max()}")
        print(f"  Minimo: {con_conteo['total_consultas_observaciones'].min()}")
        print(f"  Desv. estandar: {con_conteo['total_consultas_observaciones'].std():.2f}")

        print("\n  Percentiles:")
        for p in [25, 50, 75, 90, 95]:
            valor = con_conteo['total_consultas_observaciones'].quantile(p/100)
            print(f"    P{p}: {valor:.2f}")

    print("\n" + "=" * 70)
    print(" GUARDANDO EXCEL DE ESTADISTICAS")
    print("=" * 70)

    estadisticas = pd.DataFrame({
        "Metodo": conteo_metodo.index.tolist(),
        "Cantidad": conteo_metodo.values.tolist(),
        "Porcentaje": [f"{c/total_pdfs*100:.1f}%" for c in conteo_metodo.values]
    })
    estadisticas.to_excel(EXCEL_ESTADISTICAS, index=False)
    print(f"Estadisticas guardadas en: {EXCEL_ESTADISTICAS}")

    print("\n" + "=" * 70)
    print(" FIN DEL PROCESAMIENTO")
    print("=" * 70)

if __name__ == "__main__":
    main()
