import csv
import sys
import os
import re
import time
import json
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
    """Abre AliExpress y espera a que el usuario confirme que esta logueado."""
    try:
        driver.maximize_window()
        driver.get("https://es.aliexpress.com/")
    except Exception:
        pass

    print("\n" + "=" * 55)
    print("  Se abrio AliExpress en el navegador.")
    print("  Revisa que estes logueado (inicia sesion si hace falta).")
    print("=" * 55)
    input("\n  Cuando estes listo, presiona Enter para continuar...")

    try:
        driver.minimize_window()
    except Exception:
        pass
    print()


def url_busqueda(frase: str, pagina: int) -> str:
    termino = frase.replace(" ", "-")
    return f"https://es.aliexpress.com/w/wholesale-{termino}.html?page={pagina}&sortType=total_tranpro_desc&currency=USD"


def extraer_pagina(driver: uc.Chrome, url: str) -> list[dict]:
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/item/']"))
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

    items = _parsear_runparams(driver)
    if not items:
        items = _parsear_items_dom(driver)

    return items


def _extraer_runparams(driver: uc.Chrome) -> dict | None:
    """Extrae window.runParams usando regex sobre el HTML (más confiable que execute_script)."""
    # Método 1: regex sobre el código fuente de la página
    fuente = driver.page_source
    decoder = json.JSONDecoder()

    # Método 1: regex preciso sobre el HTML — busca la asignación "window.X = {"
    patrones_html = [
        # _init_data_ usa JS object literal: { data: {...} } — capturamos el inner JSON válido
        r'window\._dida_config_\._init_data_\s*=\s*\{\s*data\s*:\s*(\{)',
        r'window\.runParams\s*=\s*(\{)',
        r'window\.__INIT_DATA__\s*=\s*(\{)',
        r'window\.pageData\s*=\s*(\{)',
    ]
    for patron in patrones_html:
        try:
            m = re.search(patron, fuente)
            if m:
                data, _ = decoder.raw_decode(fuente[m.start(1):])
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            continue

    # Método 2: tag <script type="application/json"> (Next.js / SSR)
    try:
        from selenium.webdriver.common.by import By as _By
        scripts = driver.find_elements(_By.CSS_SELECTOR,
            'script[type="application/json"], script#__NEXT_DATA__, script#__NUXT_DATA__')
        for s in scripts:
            try:
                contenido = s.get_attribute("innerHTML") or ""
                if len(contenido) > 100:
                    data = json.loads(contenido)
                    if isinstance(data, dict) and data:
                        return data
            except Exception:
                continue
    except Exception:
        pass

    # Método 3: execute_script con múltiples nombres de variable
    vars_js = [
        "window._dida_config_._init_data_.data",  # inner valid object (outer uses unquoted JS key)
        "window._dida_config_._init_data_",
        "window.runParams",
        "window._dida_config_",
        "window.__INIT_DATA__",
        "window.pageData",
        "window.__ssr_data__",
    ]
    for var in vars_js:
        try:
            data_str = driver.execute_script(f"""
                try {{ var d={var}; return d ? JSON.stringify(d) : null; }}
                catch(e) {{ return null; }}
            """)
            if data_str:
                data = json.loads(data_str)
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            continue

    # --- DIAGNÓSTICO: guardar el código fuente real de la página ---
    try:
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        # Guardar los primeros 200KB del source (suficiente para ver la estructura JS)
        source_path = os.path.join(script_dir, "debug_pagesource.html")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(fuente[:200000])
        print(f"\n[DEBUG] Source guardado en: {source_path}")
    except Exception as e:
        print(f"\n[DEBUG] Error guardando source: {e}")

    return None


def _buscar_en_rutas(item: dict, rutas: list) -> object:
    """Recorre una lista de rutas [key, key, ...] hasta encontrar un valor no-None."""
    for ruta in rutas:
        try:
            obj = item
            for key in ruta:
                if isinstance(obj, list):
                    obj = obj[key]
                else:
                    obj = obj[key]
            if obj is not None:
                return obj
        except (KeyError, IndexError, TypeError):
            continue
    return None


def _extraer_numero_de_formato(item: dict, rutas: list) -> str:
    """Busca un campo de precio formateado (ej: 'US $15.99') y devuelve solo el número."""
    for ruta in rutas:
        try:
            obj = item
            for key in ruta:
                obj = obj[key]
            if obj and isinstance(obj, str):
                nums = re.findall(r"\d+\.?\d*", obj.replace(",", "."))
                if nums:
                    return nums[0]
        except (KeyError, TypeError):
            continue
    return ""


def _parsear_runparams(driver: uc.Chrome) -> list[dict]:
    resultado = []
    data = _extraer_runparams(driver)
    if data is None:
        return []

    # AliExpress anida los items en distintas rutas dependiendo de la versión
    items_raw = []
    rutas = [
        # cuando _extraer_runparams devuelve _init_data_ directamente
        ["data", "data", "root", "fields", "itemList", "content"],
        ["data", "root", "fields", "itemList", "content"],
        ["data", "root", "fields", "mods", "itemList", "content"],
        # cuando _extraer_runparams devuelve _dida_config_ (que contiene _init_data_)
        ["_init_data_", "data", "data", "root", "fields", "itemList", "content"],
        ["_init_data_", "data", "root", "fields", "itemList", "content"],
        ["_init_data_", "data", "root", "fields", "mods", "itemList", "content"],
        # rutas legacy
        ["root", "fields", "itemList", "content"],
        ["root", "fields", "mods", "itemList", "content"],
        ["data", "itemList", "content"],
        ["itemList", "content"],
    ]
    for ruta in rutas:
        try:
            obj = data
            for key in ruta:
                obj = obj[key]
            if isinstance(obj, list) and obj:
                items_raw = obj
                break
        except (KeyError, TypeError):
            continue

    if not items_raw:
        return []

    # Guardar primer item como JSON de diagnóstico
    try:
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        debug_path = os.path.join(script_dir, "debug_item.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(items_raw[0], f, ensure_ascii=False, indent=2)
        print(f"[DEBUG] Item guardado en: {debug_path}")
    except Exception:
        pass

    for item in items_raw:
        try:
            # --- PRECIO ---
            precio = _buscar_en_rutas(item, [
                ["prices", "salePrice", "minPrice"],
                ["prices", "salePrice", "value"],
                ["prices", "price", "minPrice"],
                ["salePrice", "minPrice"],
                ["salePrice", "value"],
                ["salePrice"],
                ["price"],
                ["actPriceMoney", "value"],
                ["priceModule", "minAmount", "value"],
            ])
            if not precio:
                precio = _extraer_numero_de_formato(item, [
                    ["prices", "salePrice", "formattedPrice"],
                    ["prices", "price", "formattedPrice"],
                    ["salePrice", "formattedPrice"],
                ])

            # --- PRECIO ORIGINAL ---
            precio_original = _buscar_en_rutas(item, [
                ["prices", "originalPrice", "minPrice"],
                ["prices", "originalPrice", "value"],
                ["originalPrice", "minPrice"],
                ["originalPrice", "value"],
                ["originalPrice"],
                ["priceModule", "maxAmount", "value"],
            ])
            if not precio_original:
                precio_original = _extraer_numero_de_formato(item, [
                    ["prices", "originalPrice", "formattedPrice"],
                    ["originalPrice", "formattedPrice"],
                ])

            # --- RATING ---
            star = _buscar_en_rutas(item, [
                ["evaluation", "starRating"],
                ["evaluation", "score"],
                ["averageStarRate"],
                ["starRating"],
                ["rating"],
            ])
            rating = star if star is not None else ""

            # --- RESEÑAS ---
            rev = _buscar_en_rutas(item, [
                ["evaluation", "totalValidNum"],
                ["evaluation", "reviewCount"],
                ["totalFeedbackNum"],
                ["reviewCount"],
                ["feedbackCount"],
            ])
            reseñas = rev if rev is not None else ""

            # --- PEDIDOS ---
            pedidos = _buscar_en_rutas(item, [
                ["trade", "tradeDesc"],
                ["trade", "realTradedCount"],
                ["tradeCount"],
                ["orders"],
                ["soldCount"],
            ]) or ""

            # --- LOGÍSTICA ---
            logistics = item.get("logistics", {}) or {}
            shipping = item.get("shipping", {}) or {}

            # sellingPoints puede indicar "Free shipping"
            selling_points = item.get("sellingPoints") or []
            sp_texts = []
            for sp in selling_points:
                try:
                    t = (sp.get("tagContent", {}) or {}).get("tagText", "") or sp.get("tagText", "") or str(sp)
                    if t:
                        sp_texts.append(t)
                except Exception:
                    pass
            tiene_free = (logistics.get("hasFreeShipping") or
                          shipping.get("hasFreeShipping") or
                          logistics.get("isFreeShipping") or
                          any("free" in t.lower() or "gratis" in t.lower() for t in sp_texts))
            envio_gratis = "Si" if tiene_free else "No"

            tiempo_envio = (logistics.get("deliveryDayDesc") or
                            logistics.get("deliveryDesc") or
                            shipping.get("deliveryDayDesc") or "")

            costo_envio = (logistics.get("deliveryFeeDesc") or
                           logistics.get("freightFeeDesc") or
                           logistics.get("logisticsDesc") or
                           shipping.get("freightFeeDesc") or
                           shipping.get("deliveryFeeDesc") or "")
            if tiene_free and not costo_envio:
                costo_envio = "0"

            # --- BADGE ---
            badge = (_buscar_en_rutas(item, [
                ["evaluation", "tag"],
                ["badge"],
                ["labels", 0, "labelText"],
            ]) or "")
            if badge and str(badge).lower() in ("general", "normal", "default", "common"):
                badge = ""
            # Buscar badge en sellingPoints si todavía no hay uno
            if not badge:
                for sp in (item.get("sellingPoints") or []):
                    try:
                        t = (sp.get("tagContent", {}) or {}).get("tagText", "") or sp.get("tagText", "") or ""
                        t = t.strip()
                        if t and t.lower() not in ("free shipping", "envío gratis"):
                            badge = t
                            break
                    except Exception:
                        pass

            # --- TITULO ---
            titulo_obj = item.get("title") or {}
            if isinstance(titulo_obj, dict):
                titulo = titulo_obj.get("displayTitle", "")
            elif isinstance(titulo_obj, str):
                titulo = titulo_obj
            else:
                titulo = ""
            titulo = titulo or item.get("productTitle", "") or item.get("subject", "")

            # --- LINK ---
            link = (item.get("productDetailUrl") or item.get("detailUrl") or
                    item.get("productUrl") or "")
            if not link:
                product_id = item.get("productId") or item.get("itemId") or ""
                if product_id:
                    link = f"https://es.aliexpress.com/item/{product_id}.html"
            if link and not link.startswith("http"):
                link = "https:" + link
            link = link.split("?")[0] if link else ""

            # --- IMAGEN ---
            img_obj = item.get("image", {}) or {}
            thumbnail = (img_obj.get("imgUrl") or img_obj.get("src") or
                         item.get("imgUrl") or item.get("productImage") or "")
            if thumbnail and not thumbnail.startswith("http"):
                thumbnail = "https:" + thumbnail

            # --- VENDEDOR ---
            store = item.get("store", {}) or {}
            vendedor = (store.get("storeName") or store.get("name") or
                        item.get("sellerName") or item.get("storeName") or "")

            if not titulo:
                continue

            resultado.append({
                "titulo": titulo,
                "badge": badge,
                "precio_usd": precio,
                "precio_original_usd": precio_original,
                "costo_envio": costo_envio,
                "envio_gratis": envio_gratis,
                "tiempo_envio": tiempo_envio,
                "pedidos": pedidos,
                "rating": rating,
                "cantidad_reseñas": reseñas,
                "vendedor": vendedor,
                "link": link,
                "thumbnail": thumbnail,
            })
        except Exception:
            continue

    return resultado


def _parsear_items_dom(driver: uc.Chrome) -> list[dict]:
    """Fallback DOM cuando runParams no está disponible."""
    resultado = []

    # Buscar tarjetas de producto con múltiples selectores
    selectores_card = [
        "div[class*='search-item-card-wrapper-gallery']",
        "div[class*='search-card-item']",
        "div[class*='SearchCard']",
        "div[class*='manhattan--container']",
        "div[class*='list--card']",
        "div[class*='card--wishlist']",
    ]

    tarjetas = []
    for sel in selectores_card:
        found = driver.find_elements(By.CSS_SELECTOR, sel)
        if len(found) > len(tarjetas):
            tarjetas = found
        if len(tarjetas) >= 3:
            break

    # Fallback final: usar links directos de producto
    if not tarjetas:
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/item/']")
        vistos = set()
        for link in links:
            try:
                href = link.get_attribute("href") or ""
                href_limpio = href.split("?")[0]
                if not href_limpio or href_limpio in vistos:
                    continue
                vistos.add(href_limpio)
                # La tarjeta entera está dentro del <a>, usar h3 para el título
                titulo = ""
                try:
                    h3 = link.find_element(By.CSS_SELECTOR, "h3")
                    titulo = h3.text.strip()
                except Exception:
                    pass
                if not titulo:
                    lines = [l.strip() for l in link.text.split("\n") if l.strip() and not l.strip().startswith("$")]
                    titulo = lines[0] if lines else ""
                if not titulo or len(titulo) < 5:
                    continue
                resultado.append({
                    "titulo": titulo,
                    "badge": "",
                    "precio_usd": "",
                    "precio_original_usd": "",
                    "costo_envio": "",
                    "envio_gratis": "",
                    "tiempo_envio": "",
                    "pedidos": "",
                    "rating": "",
                    "cantidad_reseñas": "",
                    "vendedor": "",
                    "link": href_limpio,
                    "thumbnail": "",
                })
            except Exception:
                continue
        return resultado

    for tarjeta in tarjetas:
        try:
            # Título desde h3 (más específico que el texto completo de la tarjeta)
            titulo = ""
            try:
                h3 = tarjeta.find_element(By.CSS_SELECTOR, "h3")
                titulo = h3.text.strip()
            except Exception:
                pass
            if not titulo:
                for sel in ["h2", "h1", "[class*='title']", "[class*='Title']"]:
                    elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                    if elems:
                        titulo = elems[0].text.strip()
                        if titulo and len(titulo) > 5:
                            break
            if not titulo:
                continue

            # Parsear precio, rating y pedidos desde el texto de la tarjeta línea a línea
            # (AliExpress usa clases CSS ofuscadas que cambian frecuentemente)
            texto_tarjeta = tarjeta.text or ""
            lineas = [l.strip() for l in texto_tarjeta.split("\n")
                      if l.strip() and l.strip() != titulo]

            lineas_precio = []
            rating = ""
            pedidos = ""
            badge = ""
            envio_gratis = "No"

            # Líneas que son ruido de interfaz, no datos de producto
            _ruido = re.compile(
                r'^previsualizar$|^artículos similares$|^ver (más|more)|^add to|^agregar',
                re.IGNORECASE)
            # Líneas de descuento para nuevo comprador: "-$X · Nuevo comprador"
            _nuevo_comprador = re.compile(r'^-\$[\d.,]+', re.IGNORECASE)

            lineas_sin_clasificar = []
            for linea in lineas:
                # Precio: "$1.604" o "$24.843,33" — empieza con $ seguido solo de dígitos/puntos/comas
                if re.match(r'^\$\s*[\d.,]+$', linea):
                    lineas_precio.append(linea)
                # Rating: número decimal entre 1.0 y 5.0 solo en la línea
                elif re.match(r'^\d[.,]\d$', linea) and not rating:
                    try:
                        if 0 < float(linea.replace(",", ".")) <= 5.0:
                            rating = linea
                    except ValueError:
                        pass
                # Pedidos / vendidos
                elif re.search(r'vendidos|sold|\bpedidos\b', linea, re.IGNORECASE):
                    pedidos = linea
                # Envío gratis
                elif re.search(r'env[ií]o\s*gratis|free\s*ship', linea, re.IGNORECASE):
                    envio_gratis = "Si"
                # Descartar ruido de UI y líneas de descuento de nuevo comprador
                elif _ruido.search(linea) or _nuevo_comprador.match(linea):
                    pass
                # Precio por unidad como "($2.339,2/ud)" o "($X/unidad)"
                elif re.match(r'^\(\$|^\(\d', linea):
                    pass
                # Todo lo demás es candidato a badge (etiqueta del producto)
                elif 3 < len(linea) < 80:
                    lineas_sin_clasificar.append(linea)

            # Priorizar líneas con keywords conocidos de badge; si no, tomar la última línea corta
            for candidato in lineas_sin_clasificar:
                if re.search(r'aliexpress|choice|top venta|best seller|más vendido|mejor precio',
                             candidato, re.IGNORECASE):
                    badge = candidato
                    break
            if not badge and lineas_sin_clasificar:
                badge = lineas_sin_clasificar[-1]

            # El primer precio es el de venta, el segundo el original (tachado)
            precio = re.sub(r'[^\d.,]', '', lineas_precio[0]) if lineas_precio else ""
            precio_original = re.sub(r'[^\d.,]', '', lineas_precio[1]) if len(lineas_precio) >= 2 else ""

            link = ""
            link_elems = tarjeta.find_elements(By.CSS_SELECTOR, "a[href*='/item/']")
            if link_elems:
                link = (link_elems[0].get_attribute("href") or "").split("?")[0]

            thumbnail = ""
            img_elems = tarjeta.find_elements(By.CSS_SELECTOR, "img")
            if img_elems:
                thumbnail = (img_elems[0].get_attribute("src") or
                             img_elems[0].get_attribute("data-src") or "")

            resultado.append({
                "titulo": titulo,
                "badge": badge,
                "precio_usd": precio,
                "precio_original_usd": precio_original,
                "costo_envio": "",
                "envio_gratis": envio_gratis,
                "tiempo_envio": "",
                "pedidos": pedidos,
                "rating": rating,
                "cantidad_reseñas": "",
                "vendedor": "",
                "link": link,
                "thumbnail": thumbnail,
            })
        except Exception:
            continue

    return resultado


def obtener_total_resultados(driver: uc.Chrome) -> int:
    try:
        data = _extraer_runparams(driver)
        if data:
            for ruta in [
                ["data", "data", "root", "fields", "pageInfo", "totalResults"],
                ["data", "data", "root", "fields", "paginationResult", "totalResults"],
                ["_init_data_", "data", "data", "root", "fields", "pageInfo", "totalResults"],
                ["_init_data_", "data", "data", "root", "fields", "paginationResult", "totalResults"],
                ["data", "root", "fields", "mods", "paginationResult", "totalResults"],
                ["root", "fields", "mods", "paginationResult", "totalResults"],
            ]:
                try:
                    obj = data
                    for key in ruta:
                        obj = obj[key]
                    if obj:
                        return int(obj)
                except (KeyError, TypeError):
                    continue
    except Exception:
        pass

    try:
        for sel in ["[class*='result--count']", "[class*='total--count']", "[class*='totalResults']"]:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                numero = "".join(c for c in elems[0].text if c.isdigit())
                if numero:
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
    total_ae = 0

    try:
        esperar_login_manual(driver)

        pagina = 1
        while len(articulos) < max_resultados:
            url = url_busqueda(frase, pagina)
            items = extraer_pagina(driver, url)

            if pagina == 1:
                total_ae = obtener_total_resultados(driver)
                if not items:
                    print("No se encontraron resultados.")
                    break
                a_traer = min(total_ae, max_resultados) if total_ae else max_resultados
                if total_ae:
                    print(f"AliExpress encontro: {total_ae:,} resultados".replace(",", "."))
                print(f"Vamos a traer: {a_traer:,}".replace(",", "."))
                print()

            if not items:
                break

            articulos.extend(items)

            if len(articulos) >= max_resultados:
                articulos = articulos[:max_resultados]
                obtenidos = len(articulos)
                meta = min(total_ae, max_resultados) if total_ae else max_resultados
                barra = "#" * 20
                print(f"[{barra}] {obtenidos}/{meta} (100%)", end="\r")
                break

            obtenidos = len(articulos)
            meta = min(total_ae, max_resultados) if total_ae else max_resultados
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
    nombre_archivo = f"AE_{nombre_seguro}_{timestamp}.csv"
    ruta = os.path.join(script_dir, nombre_archivo)

    campos = [
        "titulo", "badge", "precio_usd", "precio_original_usd",
        "costo_envio", "envio_gratis", "tiempo_envio",
        "pedidos", "rating", "cantidad_reseñas",
        "vendedor", "link", "thumbnail",
    ]

    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(articulos)

    return ruta


def main():
    print("=" * 50)
    print("  Buscador AliExpress -> CSV")
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
