import csv
import sys
import os
import time
import json
import atexit
from datetime import datetime

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ITEMS_POR_PAGINA = 48


def crear_driver() -> uc.Chrome:
    # Eliminar el binario cacheado para evitar el error "archivo ya existe"
    import glob, shutil
    patron = os.path.join(os.path.expanduser("~"), "appdata", "roaming",
                          "undetected_chromedriver", "undetected_chromedriver.exe")
    if os.path.exists(patron):
        try:
            os.remove(patron)
        except Exception:
            pass

    opciones = uc.ChromeOptions()
    opciones.add_argument("--window-size=1920,1080")
    opciones.add_argument("--start-minimized")
    return uc.Chrome(options=opciones, use_subprocess=True)


def url_busqueda(frase: str, desde: int) -> str:
    termino = frase.replace(" ", "-")
    if desde == 0:
        return f"https://listado.mercadolibre.com.ar/{termino}"
    return f"https://listado.mercadolibre.com.ar/{termino}_Desde_{desde + 1}_NoIndex_True"


def extraer_pagina(driver: webdriver.Chrome, url: str) -> list[dict]:
    driver.get(url)
    # Esperar a que la URL coincida (evita leer contenido de la página anterior)
    try:
        WebDriverWait(driver, 15).until(lambda d: url.split("?")[0] in d.current_url)
    except Exception:
        pass
    time.sleep(3)

    items_ldjson = _parsear_ldjson(driver)
    items_dom = _parsear_items_dom(driver)

    def normalizar(texto: str) -> str:
        import unicodedata
        texto = unicodedata.normalize("NFD", texto.lower())
        return "".join(c for c in texto if unicodedata.category(c) != "Mn")

    dom_por_titulo = {normalizar(i["titulo"]): i for i in items_dom}

    resultado = []
    for item in items_ldjson:
        clave = normalizar(item["titulo"])
        dom = dom_por_titulo.get(clave, {})
        if not dom:
            # Buscar por coincidencia parcial (primeras 30 chars)
            for k, v in dom_por_titulo.items():
                if clave[:30] in k or k[:30] in clave:
                    dom = v
                    break
        item["envio_gratis"] = dom.get("envio_gratis", "")
        item["condicion"] = dom.get("condicion", "")
        resultado.append(item)

    if not resultado:
        resultado = items_dom

    return resultado


def _parsear_ldjson(driver: webdriver.Chrome) -> list[dict]:
    resultado = []
    scripts = driver.find_elements(By.CSS_SELECTOR, "script[type='application/ld+json']")
    for script in scripts:
        try:
            datos = json.loads(script.get_attribute("innerHTML"))
            grafo = datos.get("@graph", [datos]) if isinstance(datos, dict) else []
            for nodo in grafo:
                if nodo.get("@type") != "Product":
                    continue
                oferta = nodo.get("offers", {})
                rating = nodo.get("aggregateRating", {})
                resultado.append({
                    "id": "",
                    "titulo": nodo.get("name", ""),
                    "precio": oferta.get("price", ""),
                    "moneda": oferta.get("priceCurrency", "ARS"),
                    "precio_original": "",
                    "condicion": oferta.get("itemCondition", "").replace("https://schema.org/", ""),
                    "envio_gratis": "",
                    "tipo_envio": "",
                    "cantidad_vendida": "",
                    "disponibles": "",
                    "vendedor_id": "",
                    "vendedor_nickname": "",
                    "cuotas": "",
                    "valor_cuota": "",
                    "rating": rating.get("ratingValue", ""),
                    "cantidad_reseñas": rating.get("ratingCount", ""),
                    "link": oferta.get("url", ""),
                    "thumbnail": nodo.get("image", ""),
                })
        except Exception:
            continue
    return resultado


def _parsear_items_json(items: list) -> list[dict]:
    resultado = []
    for item in items:
        precio_info = item.get("prices", {}).get("price", {}) or {}
        envio = item.get("shipping", {})
        vendedor = item.get("seller", {})
        cuotas = item.get("installments", {}) or {}

        resultado.append({
            "id": item.get("id", ""),
            "titulo": item.get("title", ""),
            "precio": precio_info.get("amount") or item.get("price", ""),
            "moneda": precio_info.get("currency_id") or item.get("currency_id", "ARS"),
            "precio_original": precio_info.get("original_amount", ""),
            "condicion": item.get("condition", ""),
            "envio_gratis": "Si" if envio.get("free_shipping") else "No",
            "tipo_envio": envio.get("logistic_type", ""),
            "cantidad_vendida": item.get("sold_quantity", ""),
            "disponibles": item.get("available_quantity", ""),
            "vendedor_id": vendedor.get("id", ""),
            "vendedor_nickname": vendedor.get("nickname", ""),
            "cuotas": cuotas.get("quantity", ""),
            "valor_cuota": cuotas.get("amount", ""),
            "link": item.get("permalink", ""),
            "thumbnail": item.get("thumbnail", ""),
        })
    return resultado


def _parsear_items_dom(driver: webdriver.Chrome) -> list[dict]:
    resultado = []
    tarjetas = driver.find_elements(
        By.CSS_SELECTOR,
        "li.ui-search-layout__item, .poly-card"
    )

    for tarjeta in tarjetas:
        try:
            titulo = ""
            for sel in [".poly-component__title", ".ui-search-item__title", "h2", "h3"]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    titulo = elems[0].text.strip()
                    if titulo:
                        break

            precio = ""
            for sel in [".andes-money-amount__fraction", ".price-tag-fraction"]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    precio = elems[0].text.strip().replace(".", "")
                    if precio:
                        break

            precio_original = ""
            for sel in [".andes-money-amount--previous .andes-money-amount__fraction"]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    precio_original = elems[0].text.strip().replace(".", "")
                    break

            envio_gratis = "No"
            for sel in [".poly-component__shipping", ".ui-search-item__shipping"]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems and "gratis" in elems[0].text.lower():
                    envio_gratis = "Si"
                    break

            condicion = ""
            for sel in [".poly-component__highlight", ".ui-search-item__highlight-label"]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    condicion = elems[0].text.strip()
                    break

            link = ""
            for sel in [".poly-component__title a", ".ui-search-item__title-label-grid a", "h2 a", "h3 a", "a.ui-search-link"]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    href = elems[0].get_attribute("href") or ""
                    if "mercadolibre.com.ar/p/" in href or "mercadolibre.com.ar/" in href:
                        link = href.split("?")[0]
                        break

            thumbnail = ""
            elems = tarjeta.find_elements(By.CSS_SELECTOR, "img.poly-component__picture, img.ui-search-result-image__element")
            if elems:
                thumbnail = elems[0].get_attribute("src") or elems[0].get_attribute("data-src") or ""

            if not titulo:
                continue

            resultado.append({
                "id": "",
                "titulo": titulo,
                "precio": precio,
                "moneda": "ARS",
                "precio_original": precio_original,
                "condicion": condicion,
                "envio_gratis": envio_gratis,
                "tipo_envio": "",
                "cantidad_vendida": "",
                "disponibles": "",
                "vendedor_id": "",
                "vendedor_nickname": "",
                "cuotas": "",
                "valor_cuota": "",
                "link": link,
                "thumbnail": thumbnail,
            })
        except Exception:
            continue

    return resultado


def obtener_total_resultados(driver) -> int:
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, ".ui-search-search-result__quantity-results")
        if elems:
            texto = elems[0].text.strip()
            numero = "".join(c for c in texto if c.isdigit())
            return int(numero) if numero else 0
    except Exception:
        pass
    return 0


def buscar_articulos(frase: str, max_resultados: int) -> list[dict]:
    print(f"\nBuscando: '{frase}'")
    print("-" * 50)
    print("Iniciando navegador...")

    driver = crear_driver()
    articulos = []
    total_ml = 0

    try:
        for desde in range(0, max_resultados, ITEMS_POR_PAGINA):
            url = url_busqueda(frase, desde)
            items = extraer_pagina(driver, url)

            if desde == 0:
                total_ml = obtener_total_resultados(driver)
                a_traer = min(total_ml, max_resultados)
                if total_ml == 0:
                    print("No se encontraron resultados.")
                    break
                print(f"MercadoLibre encontro: {total_ml:,} resultados".replace(",", "."))
                print(f"Vamos a traer: {a_traer:,}".replace(",", "."))
                print()

            if not items:
                break

            articulos.extend(items)
            if len(articulos) >= max_resultados:
                articulos = articulos[:max_resultados]
                obtenidos = len(articulos)
                meta = min(total_ml, max_resultados) if total_ml else max_resultados
                barra = "#" * 20
                print(f"[{barra}] {obtenidos}/{meta} (100%)", end="\r")
                break

            obtenidos = len(articulos)
            meta = min(total_ml, max_resultados) if total_ml else max_resultados
            porcentaje = min(int(obtenidos / meta * 100), 100)
            barra = "#" * (porcentaje // 5) + "-" * (20 - porcentaje // 5)
            print(f"[{barra}] {obtenidos}/{meta} ({porcentaje}%)", end="\r")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    print()
    return articulos


def guardar_csv(articulos: list[dict], frase: str) -> str:
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_seguro = "".join(c if c.isalnum() or c in " _-" else "_" for c in frase)[:50].strip()
    nombre_archivo = f"ML_{nombre_seguro}_{timestamp}.csv"
    ruta = os.path.join(script_dir, nombre_archivo)

    campos = [
        "id", "titulo", "precio", "moneda", "precio_original",
        "condicion", "envio_gratis", "tipo_envio", "cantidad_vendida",
        "disponibles", "vendedor_id", "vendedor_nickname",
        "cuotas", "valor_cuota", "rating", "cantidad_reseñas", "link", "thumbnail",
    ]

    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(articulos)

    return ruta


def main():
    print("=" * 50)
    print("  Buscador MercadoLibre Argentina -> CSV")
    print("=" * 50)

    if len(sys.argv) > 1:
        frase = " ".join(sys.argv[1:])
    else:
        frase = input("\nIngresa la frase de busqueda: ").strip()

    if not frase:
        print("Error: la frase no puede estar vacia.")
        input("\nPresiona Enter para salir...")
        sys.exit(1)

    while True:
        raw = input("Cuantos resultados queres traer? (1-1000, Enter para 1000): ").strip()
        if raw == "":
            max_resultados = 1000
            break
        if raw.isdigit() and 1 <= int(raw) <= 1000:
            max_resultados = int(raw)
            break
        print("Ingresa un numero entre 1 y 1000.")

    try:
        articulos = buscar_articulos(frase, max_resultados)

        if not articulos:
            print("No se encontraron resultados.")
            input("\nPresiona Enter para salir...")
            sys.exit(0)

        ruta_csv = guardar_csv(articulos, frase)
        print(f"\n{len(articulos)} articulos guardados en:")
        print(f"  {ruta_csv}")

    except KeyboardInterrupt:
        print("\n\nCancelado por el usuario.")
    except Exception as e:
        print(f"\nError: {e}")

    input("\nPresiona Enter para salir...")


def _suprimir_errores_salida():
    devnull = open(os.devnull, "w")
    sys.stderr = devnull


atexit.register(_suprimir_errores_salida)

if __name__ == "__main__":
    main()
