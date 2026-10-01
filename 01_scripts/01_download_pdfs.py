import re
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"D:\00_THESIS_ALAN_BRUCE\CORRER CÓDIGO PARA CONSULTAS Y OBSERVACIONES")
PDFS_DIR = BASE_DIR / "02_pdfs_descargados"
RESULTADOS_DIR = BASE_DIR / "03_resultados"
LOGS_DIR = BASE_DIR / "04_logs"
DESCARTADOS_DIR = PDFS_DIR / "descartados"

PDFS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DESCARTADOS_DIR.mkdir(parents=True, exist_ok=True)

EXCEL_BASE = RESULTADOS_DIR / "BASE_FINAL_137_PROCESOS.xlsx"
EXCEL_SALIDA = RESULTADOS_DIR / "estado_descargas.xlsx"

URL_SEACE = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"

LOG_FILE = LOGS_DIR / "log_descarga_masiva_v7.txt"

PAUSA_ENTRE_PROCESOS = 3

MAX_PROCESOS = None

def log(mensaje):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{timestamp}] {mensaje}"
    print(linea)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linea + "\n")

def esperar_elemento(page, selector_texto, max_intentos=15, espera=1):
    for intento in range(max_intentos):
        try:
            elemento = page.get_by_text(selector_texto, exact=False)
            if elemento.count() > 0:
                return elemento
        except:
            pass
        time.sleep(espera)
    return None

def verificar_contenido_pdf(ruta_pdf):
    try:
        import fitz
        doc = fitz.open(str(ruta_pdf))
        if len(doc) == 0:
            doc.close()
            return False

        texto = ""
        for i in range(min(2, len(doc))):
            texto += doc[i].get_text()
        doc.close()

        texto_lower = texto.lower()

        if "pliego de absolución" in texto_lower or "pliego absolutorio" in texto_lower:
            return True
        if "absolución de consultas" in texto_lower and "consulta" in texto_lower:
            return True

        return False
    except Exception as e:
        log(f"      Error verificando PDF: {str(e)[:100]}")
        return False

def buscar_ficha_en_anio(page, codigo, anio):
    try:
        log(f"   [Intento] Codigo={codigo}, Anio={anio}")

        page.goto(URL_SEACE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        page.get_by_text("Buscador de Procedimientos de Selección", exact=True).click()
        page.wait_for_timeout(2500)

        page.wait_for_timeout(2000)
        page.evaluate("""
            () => {
                const legends = document.querySelectorAll('legend');
                for (let l of legends) {
                    if (l.textContent.includes('Búsqueda Avanzada')) {
                        l.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        page.wait_for_timeout(2500)

        try:
            etiqueta_anio = page.get_by_text("Año de la Convocatoria", exact=False).first
            fila_anio = etiqueta_anio.locator("xpath=ancestor::tr[1]")
            trigger_anio = fila_anio.locator(".ui-selectonemenu-trigger")
            trigger_anio.click()
            page.wait_for_timeout(700)

            opciones = page.locator("li.ui-selectonemenu-item:visible")
            opcion_anio = opciones.filter(has_text=str(anio))
            if opcion_anio.count() == 0:
                return ("ANIO_NO_DISPONIBLE", None, None)
            opcion_anio.first.click()
            page.wait_for_timeout(1200)
        except Exception as e:
            return ("ERROR_ANIO", None, None)

        try:
            campo_codigo = page.locator("#tbBuscador\\:idFormBuscarProceso\\:numeroConvocatoria")
            campo_codigo.fill(str(codigo))
            page.wait_for_timeout(500)
        except Exception as e:
            return ("ERROR_CODIGO", None, None)

        botones = page.get_by_text("Buscar", exact=True)
        boton_buscar = None
        for i in range(botones.count()):
            if botones.nth(i).is_visible():
                boton_buscar = botones.nth(i)
                break
        if boton_buscar is None:
            return ("ERROR_BOTON", None, None)
        boton_buscar.click()
        page.wait_for_timeout(8000)

        texto_pagina = page.locator("body").inner_text()
        if "No se encontraron Datos" in texto_pagina or "Mostrando de 0 a 0" in texto_pagina:
            return ("SIN_FICHA", None, None)

        log(f"      Hay resultados. Buscando fila...")

        filas = page.locator("tr")
        fila_resultado = None
        for i in range(filas.count()):
            try:
                contenido = filas.nth(i).inner_text().strip()
                if (any(nom in contenido for nom in ["LP-", "CP-", "AS-", "AM-", "AD-", "CD-"])
                    and len(contenido) > 50):
                    fila_resultado = filas.nth(i)
                    log(f"      Fila encontrada en indice {i}")
                    break
            except:
                pass

        if fila_resultado is None:
            return ("SIN_FICHA", None, None)

        candidatos = fila_resultado.locator("img, input[type='image']")
        control_ficha = None
        for i in range(candidatos.count()):
            try:
                src = (candidatos.nth(i).get_attribute("src") or "").lower()
                if "ficha" in src:
                    control_ficha = candidatos.nth(i)
                    break
            except:
                pass

        if control_ficha is None:
            return ("FICHA_ENCONTRADA_SIN_ICONO", None, None)

        paginas_antes = len(page.context.pages)
        control_ficha.click()
        page.wait_for_timeout(7000)
        paginas_despues = len(page.context.pages)
        if paginas_despues > paginas_antes:
            page = page.context.pages[-1]

        log(f"      Esperando que cargue la ficha...")
        boton_docs = esperar_elemento(page, "Ver documentos por Etapa", max_intentos=15, espera=1)

        if boton_docs is None:
            return ("FICHA_ENCONTRADA_SIN_DOCUMENTOS", None, None)

        try:
            boton_docs.first.click()
            page.wait_for_timeout(4000)
        except Exception as e:
            return ("FICHA_ENCONTRADA_SIN_DOCUMENTOS", None, None)

        log(f"      Buscando fila de Pliego de Absolucion...")

        filas_docs = page.locator("tr")
        fila_pliego = None
        tipo_doc = None

        for i in range(filas_docs.count()):
            try:
                fila = filas_docs.nth(i)
                celdas = fila.locator("td")

                if celdas.count() < 4:
                    continue

                etapa = celdas.nth(1).inner_text().strip()
                documento = celdas.nth(2).inner_text().strip()

                if ("Absolución de consultas" in etapa
                    and "Pliego de absolución" in documento):
                    fila_pliego = fila
                    tipo_doc = "PLIEGO"
                    log(f"      *** ENCONTRADO PLIEGO en fila {i} ***")
                    log(f"      Etapa: {etapa[:60]}")
                    log(f"      Documento: {documento[:80]}")
                    break
                elif ("Absolución de consultas" in etapa
                      and "Acta de no formulación" in documento):
                    fila_pliego = fila
                    tipo_doc = "ACTA_NO_FORMULACION"
                    log(f"      *** ENCONTRADO ACTA en fila {i} ***")
                    break

            except Exception as e:
                pass

        if fila_pliego is None:
            log(f"      *** NO se encontro fila de Pliego ***")
            return ("FICHA_SIN_PLIEGO", None, None)

        enlaces = fila_pliego.locator("a")
        enlace_descarga = None
        for i in range(enlaces.count()):
            try:
                elemento = enlaces.nth(i)
                onclick = elemento.get_attribute("onclick") or ""
                if "descargaDocGeneral" in onclick:
                    enlace_descarga = elemento
                    log(f"      Enlace de descarga encontrado")
                    break
            except:
                pass

        if enlace_descarga is None:
            return ("PLIEGO_SIN_ENLACE", None, tipo_doc)

        sufijo = "" if tipo_doc == "PLIEGO" else "_ACTA"
        nombre_archivo = f"{codigo}{sufijo}.pdf"
        ruta_pdf = PDFS_DIR / nombre_archivo
        id_enlace = enlace_descarga.get_attribute("id")

        try:
            with page.expect_download(timeout=30000) as download_info:
                page.evaluate("""
                    (id) => {
                        const el = document.getElementById(id);
                        if (el) { el.click(); }
                    }
                """, id_enlace)
            download = download_info.value

            nombre_descargado = download.suggested_filename.lower()
            log(f"      Nombre del archivo descargado: {nombre_descargado}")

            if nombre_descargado.endswith('.zip') or nombre_descargado.endswith('.rar'):
                log(f"      *** ERROR: Descargo un ZIP/RAR ***")
                ruta_descartado = DESCARTADOS_DIR / f"{codigo}_descargado_como.zip"
                download.save_as(str(ruta_descartado))
                return ("PDF_INCORRECTO_FORMATO", None, tipo_doc)

            download.save_as(str(ruta_pdf))
            log(f"      Archivo guardado: {nombre_archivo}")

            log(f"      Verificando contenido del PDF...")
            if not verificar_contenido_pdf(ruta_pdf):
                log(f"      *** ERROR: El PDF no es un Pliego ***")
                ruta_descartado = DESCARTADOS_DIR / nombre_archivo
                if ruta_descartado.exists():
                    ruta_descartado.unlink()
                ruta_pdf.rename(ruta_descartado)
                return ("PDF_INCORRECTO_CONTENIDO", None, tipo_doc)

            log(f"      OK - PDF verificado y guardado: {nombre_archivo} (tipo: {tipo_doc})")
            return ("OK", ruta_pdf, tipo_doc)

        except Exception as e:
            log(f"      Error descargando: {str(e)[:100]}")
            return ("ERROR_DESCARGA", None, tipo_doc)

    except Exception as e:
        log(f"      EXCEPCION: {type(e).__name__} - {str(e)[:150]}")
        return ("ERROR_GENERAL", None, None)

def descargar_con_reintentos(page, codigo, anio_original):
    anio_original = int(anio_original)
    anios_a_probar = [
        anio_original,
        anio_original + 1,
        anio_original - 1,
        anio_original + 2,
        anio_original - 2
    ]

    for anio in anios_a_probar:
        log(f"   >>> Probando anio {anio}")
        estado, ruta, tipo_doc = buscar_ficha_en_anio(page, codigo, anio)
        log(f"   <<< Resultado anio {anio}: {estado}")

        if estado == "OK":
            return (estado, ruta, anio, tipo_doc)

        if estado.startswith("FICHA_") and estado != "FICHA_ENCONTRADA_SIN_DOCUMENTOS":
            return (estado, None, anio, tipo_doc)

        if estado == "FICHA_ENCONTRADA_SIN_DOCUMENTOS":
            log(f"   *** Reintentando anio {anio} ***")
            time.sleep(5)
            estado2, ruta2, tipo_doc2 = buscar_ficha_en_anio(page, codigo, anio)
            log(f"   <<< Reintento anio {anio}: {estado2}")
            if estado2 == "OK":
                return (estado2, ruta2, anio, tipo_doc2)
            return (estado2, None, anio, tipo_doc2)

        if estado == "ANIO_NO_DISPONIBLE":
            continue

        if estado == "SIN_FICHA":
            continue

        continue

    return ("SIN_FICHA_EN_NINGUN_ANIO", None, None, None)

def main():
    log("=" * 60)
    log(" DESCARGA MASIVA DE PLIEGOS - VERSION v7 (CORREGIDA)")
    log("=" * 60)

    log(f"Leyendo Excel: {EXCEL_BASE}")
    df = pd.read_excel(EXCEL_BASE)
    log(f"Total de procesos: {len(df)}")

    df["fecha_convocatoria"] = pd.to_datetime(df["fecha_convocatoria"], errors="coerce")
    df["anio"] = df["fecha_convocatoria"].dt.year

    if MAX_PROCESOS:
        df = df.head(MAX_PROCESOS)
        log(f"*** MODO PRUEBA: procesando solo {MAX_PROCESOS} casos ***")

    pendientes = []
    for _, fila in df.iterrows():
        pendientes.append({
            "codigo": str(fila["codigoconvocatoria"]),
            "anio": int(fila["anio"])
        })

    log(f"Procesos a procesar: {len(pendientes)}")

    resultados = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1600, "height": 950},
            accept_downloads=True
        )
        page = context.new_page()

        for i, item in enumerate(pendientes):
            codigo = item["codigo"]
            anio = item["anio"]

            log(f"\n[{i+1}/{len(pendientes)}] Codigo: {codigo} (anio base {anio})")

            try:
                estado, ruta, anio_usado, tipo_doc = descargar_con_reintentos(page, codigo, anio)
            except Exception as e:
                log(f"EXCEPCION: {type(e).__name__}: {str(e)[:200]}")
                estado = "EXCEPCION"
                anio_usado = None
                tipo_doc = None

            resultados.append({
                "codigoconvocatoria": codigo,
                "anio_base": anio,
                "anio_encontrado": anio_usado if anio_usado else "",
                "tipo_documento": tipo_doc if tipo_doc else "",
                "estado_descarga": estado
            })

            if i < len(pendientes) - 1:
                time.sleep(PAUSA_ENTRE_PROCESOS)

        browser.close()

    df_resultados = pd.DataFrame(resultados)
    df_resultados.to_excel(EXCEL_SALIDA, index=False)
    log(f"\nEstado guardado en: {EXCEL_SALIDA}")

    log("\n" + "=" * 60)
    log(" RESUMEN")
    log("=" * 60)
    conteo_estado = df_resultados["estado_descarga"].value_counts()
    for estado, cantidad in conteo_estado.items():
        log(f"  {estado}: {cantidad}")

    log(f"\nTotal PDFs en carpeta: {len(list(PDFS_DIR.glob('*.pdf')))}")
    log(f"Total descartados: {len(list(DESCARTADOS_DIR.glob('*')))}")
    log("FIN")

if __name__ == "__main__":
    main()
