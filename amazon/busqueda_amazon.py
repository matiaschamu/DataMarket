import csv
import sys
import os
import re
import time
import atexit
from datetime import datetime

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def directorio_base() -> str:
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def ruta_perfil() -> str:
    return os.path.join(directorio_base(), ".perfil_chrome")


def crear_driver() -> uc.Chrome:
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
    opciones.add_argument("--lang=es-AR,es")
    opciones.add_argument("--no-first-run")
    opciones.add_argument("--no-default-browser-check")
    # Perfil propio y persistente: la sesion iniciada queda guardada entre
    # busquedas, asi solo hay que iniciar sesion manualmente la primera vez.
    opciones.add_argument(f"--user-data-dir={ruta_perfil()}")
    return uc.Chrome(options=opciones, use_subprocess=True, version_main=148)


def esperar_login_manual(driver) -> None:
    """Abre Amazon y espera a que el usuario confirme que esta logueado."""
    try:
        driver.maximize_window()
        driver.get("https://www.amazon.com.ar/")
    except Exception:
        pass

    print("\n" + "=" * 55)
    print("  Se abrio Amazon en el navegador.")
    print("  Revisa que estes logueado (inicia sesion si hace falta).")
    print("=" * 55)
    input("\n  Cuando estes listo, presiona Enter para continuar...")

    try:
        driver.minimize_window()
    except Exception:
        pass
    print()


def url_busqueda(frase: str, pagina: int) -> str:
    termino = frase.replace(" ", "+")
    return f"https://www.amazon.com.ar/s?k={termino}&page={pagina}"


def extraer_pagina(driver: uc.Chrome, url: str) -> list[dict]:
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div[data-component-type='s-search-result']")
            )
        )
    except Exception:
        pass

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.4);")
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.8);")
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

    # Detectar CAPTCHA / página de verificación
    if _hay_captcha(driver):
        print("\n[!] Amazon pidió verificación. Resolvela en el navegador y presioná Enter...")
        input()

    return _parsear_items_dom(driver)


def _hay_captcha(driver: uc.Chrome) -> bool:
    try:
        titulo = driver.title.lower()
        return "robot" in titulo or "captcha" in titulo or "verificar" in titulo
    except Exception:
        return False


def _texto_oculto(elem) -> str:
    """Obtiene el texto de un elemento aunque esté oculto con display:none (a-offscreen)."""
    try:
        return elem.get_attribute("textContent") or elem.get_attribute("innerHTML") or ""
    except Exception:
        return ""


def _extraer_precio(texto: str) -> str:
    """Limpia un string de precio: '$ 15.000,99' → '15000.99'."""
    # Eliminar símbolo de moneda y espacios
    texto = re.sub(r'[^\d.,]', '', texto.strip())
    if not texto:
        return ""
    # Formato argentino: punto como separador de miles, coma como decimal
    # Ej: "15.000,99" → "15000.99"
    if re.search(r'\d\.\d{3}', texto):
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    return texto


def _parsear_items_dom(driver: uc.Chrome) -> list[dict]:
    resultado = []

    tarjetas = driver.find_elements(
        By.CSS_SELECTOR,
        "div[data-component-type='s-search-result']"
    )

    for tarjeta in tarjetas:
        try:
            asin = tarjeta.get_attribute("data-asin") or ""
            if not asin:
                continue

            # --- TITULO ---
            titulo = ""
            for sel in ["h2 span.a-text-normal", "h2 a span", "h2 span"]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    titulo = elems[0].text.strip()
                    if titulo:
                        break
            if not titulo:
                continue

            # --- BADGE ---
            badge = ""
            elems = tarjeta.find_elements(By.CSS_SELECTOR, "span.a-badge-text")
            if elems:
                badge = elems[0].text.strip()

            # --- PRECIO ---
            precio = ""
            elems = tarjeta.find_elements(By.CSS_SELECTOR, "span.a-price span.a-offscreen")
            if elems:
                precio = _extraer_precio(_texto_oculto(elems[0]))

            # --- PRECIO ORIGINAL ---
            precio_original = ""
            elems = tarjeta.find_elements(By.CSS_SELECTOR, "span.a-text-price span.a-offscreen")
            if elems:
                precio_original = _extraer_precio(_texto_oculto(elems[0]))

            # --- DESCUENTO ---
            descuento = ""
            for sel in [
                "span.a-size-base.a-color-secondary",
                "span[class*='savingsPercentage']",
            ]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                for elem in elems:
                    texto = elem.text.strip()
                    if re.search(r'-?\d+\s*%', texto):
                        descuento = texto
                        break
                if descuento:
                    break

            # --- RATING ---
            rating = ""
            elems = tarjeta.find_elements(By.CSS_SELECTOR, "span.a-icon-alt")
            for elem in elems:
                texto = _texto_oculto(elem)
                m = re.search(r'(\d[.,]\d)', texto)
                if m:
                    try:
                        val = float(m.group(1).replace(",", "."))
                        if 0 < val <= 5:
                            rating = m.group(1)
                            break
                    except ValueError:
                        pass

            # --- RESEÑAS ---
            reseñas = ""
            for sel in [
                "span.a-size-base.s-underline-text",
                "span[aria-label*='calificaciones']",
                "span[aria-label*='ratings']",
            ]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                for elem in elems:
                    texto = elem.text.strip() or _texto_oculto(elem).strip()
                    if texto and re.search(r'\d', texto):
                        reseñas = texto
                        break
                if reseñas:
                    break

            # --- PRIME ---
            prime = "No"
            if tarjeta.find_elements(
                By.CSS_SELECTOR,
                "i[aria-label*='Prime'], span[aria-label*='Prime'], i.a-icon-prime"
            ):
                prime = "Si"

            # --- ENVIO GRATIS ---
            envio_gratis = "Si" if prime == "Si" else "No"
            if envio_gratis == "No":
                for sel in [
                    "span[aria-label*='gratis']",
                    "span[aria-label*='FREE']",
                    "span[class*='delivery']",
                ]:
                    elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elems:
                        texto = (elem.get_attribute("aria-label") or elem.text or "").lower()
                        if "gratis" in texto or "free" in texto:
                            envio_gratis = "Si"
                            break
                    if envio_gratis == "Si":
                        break

            # --- VENDEDOR ---
            vendedor = ""
            for sel in [
                "span.a-size-small + span.a-size-small",
                "span[class*='a-color-secondary'] span.a-size-small",
            ]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                for elem in elems:
                    texto = elem.text.strip()
                    if texto and len(texto) > 1 and "$" not in texto:
                        vendedor = texto
                        break
                if vendedor:
                    break

            # --- LINK ---
            link = ""
            elems = tarjeta.find_elements(By.CSS_SELECTOR, "h2 a")
            if elems:
                href = elems[0].get_attribute("href") or ""
                link = href.split("?")[0] if href else ""
            if not link and asin:
                link = f"https://www.amazon.com.ar/dp/{asin}"

            # --- THUMBNAIL ---
            thumbnail = ""
            elems = tarjeta.find_elements(By.CSS_SELECTOR, "img.s-image")
            if elems:
                thumbnail = elems[0].get_attribute("src") or ""

            resultado.append({
                "titulo": titulo,
                "badge": badge,
                "precio": precio,
                "precio_original": precio_original,
                "descuento": descuento,
                "envio_gratis": envio_gratis,
                "prime": prime,
                "rating": rating,
                "cantidad_reseñas": reseñas,
                "vendedor": vendedor,
                "link": link,
                "thumbnail": thumbnail,
            })
        except Exception:
            continue

    return resultado


def obtener_total_resultados(driver: uc.Chrome) -> int:
    try:
        for sel in [
            "div[data-component-type='s-result-info-bar'] span",
            "span.rush-component",
        ]:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for elem in elems:
                texto = elem.text
                m = re.search(r'([\d.,]+)\s+resultados', texto, re.IGNORECASE)
                if m:
                    numero = re.sub(r'[.,]', '', m.group(1))
                    return int(numero)
    except Exception:
        pass
    return 0


def buscar_articulos(frase: str, max_resultados: int) -> list[dict]:
    print(f"\nBuscando: '{frase}'")
    print("-" * 50)
    print("Iniciando navegador...")

    driver = crear_driver()
    articulos = []
    total_az = 0

    try:
        esperar_login_manual(driver)

        pagina = 1
        while len(articulos) < max_resultados:
            url = url_busqueda(frase, pagina)
            items = extraer_pagina(driver, url)

            if pagina == 1:
                total_az = obtener_total_resultados(driver)
                if not items:
                    print("No se encontraron resultados.")
                    break
                a_traer = min(total_az, max_resultados) if total_az else max_resultados
                if total_az:
                    print(f"Amazon encontro: {total_az:,} resultados".replace(",", "."))
                print(f"Vamos a traer: {a_traer:,}".replace(",", "."))
                print()

            if not items:
                break

            articulos.extend(items)

            if len(articulos) >= max_resultados:
                articulos = articulos[:max_resultados]
                obtenidos = len(articulos)
                meta = min(total_az, max_resultados) if total_az else max_resultados
                barra = "#" * 20
                print(f"[{barra}] {obtenidos}/{meta} (100%)", end="\r")
                break

            obtenidos = len(articulos)
            meta = min(total_az, max_resultados) if total_az else max_resultados
            porcentaje = min(int(obtenidos / meta * 100), 100) if meta else 0
            barra = "#" * (porcentaje // 5) + "-" * (20 - porcentaje // 5)
            print(f"[{barra}] {obtenidos}/{meta} ({porcentaje}%)", end="\r")

            pagina += 1
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
    nombre_archivo = f"AZ_{nombre_seguro}_{timestamp}.csv"
    ruta = os.path.join(script_dir, nombre_archivo)

    campos = [
        "titulo", "badge", "precio", "precio_original", "descuento",
        "envio_gratis", "prime", "rating", "cantidad_reseñas",
        "vendedor", "link", "thumbnail",
    ]

    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        writer.writeheader()
        writer.writerows(articulos)

    return ruta


def main():
    print("=" * 50)
    print("  Buscador Amazon -> CSV")
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
