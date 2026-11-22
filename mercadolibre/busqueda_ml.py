import csv
import sys
import os
import time
import json
import atexit
import re
import unicodedata
from datetime import datetime
from urllib.parse import quote

import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ITEMS_POR_PAGINA = 48
SELECTOR_TARJETAS = (
    "li.ui-search-layout__item, .ui-search-layout__item, "
    "article.poly-card, .poly-card"
)
SELECTOR_SIN_RESULTADOS = (
    ".ui-search-rescue, .ui-search-no-results, "
    "[class*='no-results'], [class*='search-rescue']"
)


def directorio_base() -> str:
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def ruta_perfil() -> str:
    return os.path.join(directorio_base(), ".perfil_chrome")


def detectar_version_principal_chrome() -> int | None:
    """Detecta la version instalada para descargar el ChromeDriver compatible."""
    try:
        ejecutable = uc.find_chrome_executable()
        carpeta = os.path.dirname(ejecutable)
        versiones = [
            int(nombre.split(".", 1)[0])
            for nombre in os.listdir(carpeta)
            if "." in nombre and nombre.split(".", 1)[0].isdigit()
        ]
        return max(versiones, default=None)
    except Exception:
        return None


def crear_driver() -> uc.Chrome:
    # Eliminar el binario cacheado para evitar el error "archivo ya existe"
    import glob
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
    opciones.add_argument("--no-first-run")
    opciones.add_argument("--no-default-browser-check")
    # Perfil propio y persistente: la sesion iniciada queda guardada entre
    # busquedas, asi solo hay que iniciar sesion manualmente la primera vez.
    opciones.add_argument(f"--user-data-dir={ruta_perfil()}")
    return uc.Chrome(
        options=opciones,
        use_subprocess=True,
        version_main=detectar_version_principal_chrome(),
    )


def esperar_login_manual(driver) -> None:
    """Abre MercadoLibre y espera a que el usuario confirme que esta logueado."""
    try:
        driver.maximize_window()
        driver.get("https://www.mercadolibre.com.ar/")
    except Exception:
        pass

    print("\n" + "=" * 55)
    print("  Se abrio MercadoLibre en el navegador.")
    print("  Revisa que estes logueado (inicia sesion si hace falta).")
    print("=" * 55)
    input("\n  Cuando estes listo, presiona Enter para continuar...")

    try:
        driver.minimize_window()
    except Exception:
        pass
    print()


def url_busqueda(frase: str, desde: int) -> str:
    termino = quote("-".join(frase.split()), safe="-")
    if desde == 0:
        return f"https://listado.mercadolibre.com.ar/{termino}"
    return f"https://listado.mercadolibre.com.ar/{termino}_Desde_{desde + 1}_NoIndex_True"


def _carpeta_captura(driver) -> str:
    """Crea una carpeta unica para diagnosticar la busqueda fuera de linea."""
    run_id = getattr(driver, "_debug_run_id", None)
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        driver._debug_run_id = run_id
    carpeta = os.path.join(directorio_base(), "debug_mercadolibre", run_id)
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def _leer_ldjson_crudo(driver) -> list:
    datos = []
    for script in driver.find_elements(By.CSS_SELECTOR, "script[type='application/ld+json']"):
        try:
            datos.append(json.loads(script.get_attribute("innerHTML")))
        except Exception:
            continue
    return datos


def _guardar_captura_pagina(
    driver, pagina: int, url_solicitada: str, items_ldjson: list,
    items_embebidos: list, items_dom: list, resultado: list,
) -> None:
    """Guarda la respuesta y lo interpretado para investigar cambios del sitio."""
    try:
        carpeta = _carpeta_captura(driver)
        prefijo = f"pagina_{pagina:03d}"

        with open(os.path.join(carpeta, f"{prefijo}.html"), "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        captura_pantalla_guardada = False
        try:
            captura_pantalla_guardada = driver.save_screenshot(
                os.path.join(carpeta, f"{prefijo}.png")
            )
        except Exception:
            pass

        captura = {
            "capturado_en": datetime.now().isoformat(timespec="seconds"),
            "pagina": pagina,
            "url_solicitada": url_solicitada,
            "url_final": driver.current_url,
            "titulo_pagina": driver.title,
            "total_visible": obtener_total_resultados(driver),
            "cantidad_ldjson": len(items_ldjson),
            "cantidad_embebidos": len(items_embebidos),
            "cantidad_dom": len(items_dom),
            "cantidad_resultado": len(resultado),
            "captura_pantalla_guardada": captura_pantalla_guardada,
            "reintentos_carga": getattr(driver, "_debug_reintentos_carga", 0),
            "ldjson_crudo": _leer_ldjson_crudo(driver),
            "items_ldjson": items_ldjson,
            "items_embebidos": items_embebidos,
            "items_dom": items_dom,
            "resultado": resultado,
        }
        with open(os.path.join(carpeta, f"{prefijo}.json"), "w", encoding="utf-8") as f:
            json.dump(captura, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[DEBUG] No se pudo guardar la captura de la pagina {pagina}: {e}")


def _guardar_resumen_busqueda(
    driver, frase: str, max_resultados: int, articulos: list,
    total_ml: int, error: str = "",
) -> None:
    try:
        resumen = {
            "iniciada_en": getattr(driver, "_debug_iniciada_en", ""),
            "finalizada_en": datetime.now().isoformat(timespec="seconds"),
            "frase": frase,
            "max_resultados": max_resultados,
            "total_informado_por_mercadolibre": total_ml,
            "cantidad_extraida": len(articulos),
            "paginas_capturadas": getattr(driver, "_debug_paginas", 0),
            "reintentos_carga": getattr(driver, "_debug_reintentos_carga", 0),
            "error": error,
            "articulos": articulos,
        }
        ruta = os.path.join(_carpeta_captura(driver), "debug_busqueda.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(resumen, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[DEBUG] No se pudo guardar el resumen de la busqueda: {e}")


def _esperar_resultado_busqueda(driver, timeout: int = 30) -> str:
    """Espera tarjetas o una pantalla explícita de búsqueda vacía."""
    def estado(d):
        if d.find_elements(By.CSS_SELECTOR, SELECTOR_TARJETAS):
            return "items"
        for elemento in d.find_elements(By.CSS_SELECTOR, SELECTOR_SIN_RESULTADOS):
            if elemento.is_displayed() and elemento.text.strip():
                return "vacio"
        return ""

    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.5).until(estado)
    except Exception:
        return "timeout"


def extraer_pagina(driver: webdriver.Chrome, url: str) -> list[dict]:
    pagina = int(getattr(driver, "_debug_paginas", 0)) + 1
    driver._debug_paginas = pagina
    driver.get(url)
    # Esperar a que la URL coincida (evita leer contenido de la página anterior)
    try:
        WebDriverWait(driver, 15).until(lambda d: url.split("?")[0] in d.current_url)
    except Exception:
        pass

    # Nordic puede entregar todas las tarjetas serializadas antes de renderizar
    # la grilla. En ese caso no hace falta esperar al DOM ni al spinner.
    items_embebidos = _parsear_polycards_embebidas(driver)
    estado_carga = "embebidos" if items_embebidos else _esperar_resultado_busqueda(driver)
    if estado_carga == "timeout":
        # La interfaz puede quedar detenida en el spinner aunque el contador ya
        # esté disponible. Un refresh recupera ese estado intermitente.
        driver._debug_reintentos_carga = int(
            getattr(driver, "_debug_reintentos_carga", 0)
        ) + 1
        print("La pagina sigue cargando; reintentando una vez...")
        driver.refresh()
        estado_carga = _esperar_resultado_busqueda(driver)

    if estado_carga == "items":
        # Dar tiempo a que precio, envío y promociones completen su hidratación.
        time.sleep(1)

    items_ldjson = _parsear_ldjson(driver)
    if not items_embebidos:
        items_embebidos = _parsear_polycards_embebidas(driver)
    items_dom = _parsear_items_dom(driver)

    dom_por_titulo = {_normalizar(i["titulo"]): i for i in items_dom}

    resultado = []
    for item in (items_ldjson or items_embebidos):
        clave = _normalizar(item["titulo"])
        dom = dom_por_titulo.get(clave, {})
        if not dom:
            # Buscar por coincidencia parcial (primeras 30 chars)
            for k, v in dom_por_titulo.items():
                if clave[:30] in k or k[:30] in clave:
                    dom = v
                    break
        for campo in (
            "envio_gratis", "condicion", "vendedor_nickname", "cuotas",
            "valor_cuota", "full", "tiene_cupon", "cupones",
            "promociones", "beneficios",
        ):
            if dom.get(campo, "") not in ("", None):
                item[campo] = dom[campo]
        resultado.append(item)

    if not resultado:
        resultado = items_dom

    _guardar_captura_pagina(
        driver, pagina, url, items_ldjson, items_embebidos, items_dom, resultado,
    )
    return resultado


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _unicos(textos: list[str]) -> list[str]:
    resultado = []
    vistos = set()
    for texto in textos:
        texto = " ".join((texto or "").split()).strip(" |")
        clave = _normalizar(texto)
        if texto and clave not in vistos:
            vistos.add(clave)
            resultado.append(texto)

    # MercadoLibre suele repetir una misma etiqueta en nodos HTML anidados.
    # Si una variante corta esta contenida en otra, conservar la mas informativa.
    normalizados = [_normalizar(texto) for texto in resultado]
    return [
        texto for indice, texto in enumerate(resultado)
        if not any(
            indice != otro_indice
            and normalizados[indice] in otro
            and len(otro) > len(normalizados[indice])
            for otro_indice, otro in enumerate(normalizados)
        )
    ]


def _detectar_beneficios(textos: list[str]) -> dict:
    """Clasifica etiquetas comerciales visibles de una tarjeta de resultados."""
    textos = _unicos(textos)
    normalizados = [_normalizar(texto) for texto in textos]

    es_full = any(re.search(r"\bfull\b", texto) for texto in normalizados)
    envio_gratis = any(
        "envio gratis" in texto or "envio es gratis" in texto
        for texto in normalizados
    )
    cupones = [
        original for original, normalizado in zip(textos, normalizados)
        if "cupon" in normalizado
    ]
    promociones = [
        original for original, normalizado in zip(textos, normalizados)
        if (
            re.search(r"\b\d{1,3}\s*%\s*(off|de descuento)?\b", normalizado)
            or any(palabra in normalizado for palabra in (
                "oferta", "descuento", "promocion", "ahorra", "cashback",
            ))
        ) and "cupon" not in normalizado
    ]

    beneficios = []
    if es_full:
        beneficios.append("Full")
    if envio_gratis:
        beneficios.append("Envio gratis")
    beneficios.extend(cupones)
    beneficios.extend(promociones)

    return {
        "full": "Si" if es_full else "No",
        "envio_gratis": "Si" if envio_gratis else "No",
        "tiene_cupon": "Si" if cupones else "No",
        "cupones": " | ".join(_unicos(cupones)),
        "promociones": " | ".join(_unicos(promociones)),
        "beneficios": " | ".join(_unicos(beneficios)),
    }


def _deduplicar_items(items: list[dict]) -> list[dict]:
    resultado = []
    vistos = set()
    for item in items:
        clave = (
            item.get("id")
            or item.get("link")
            or "|".join((
                _normalizar(item.get("titulo", "")),
                str(item.get("precio", "")),
                _normalizar(item.get("vendedor_nickname", "")),
            ))
        )
        if clave and clave in vistos:
            continue
        if clave:
            vistos.add(clave)
        resultado.append(item)
    return resultado


def _textos_de_estructura(valor) -> list[str]:
    """Recorre una estructura JSON y devuelve sus valores de texto."""
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, dict):
        resultado = []
        for contenido in valor.values():
            resultado.extend(_textos_de_estructura(contenido))
        return resultado
    if isinstance(valor, list):
        resultado = []
        for contenido in valor:
            resultado.extend(_textos_de_estructura(contenido))
        return resultado
    return []


def _componente(componentes: list[dict], tipo: str) -> dict:
    for componente in componentes:
        if componente.get("type") == tipo or componente.get("id") == tipo:
            return componente
    return {}


def _parsear_polycards_embebidas(driver: webdriver.Chrome) -> list[dict]:
    """Extrae las tarjetas serializadas aunque la interfaz quede en el spinner."""
    fuente = driver.page_source.replace('\\"', '"')
    patron = re.compile(r'\{"id":"POLYCARD","state":"VISIBLE","polycard":')
    decoder = json.JSONDecoder()
    resultado = []

    for coincidencia in patron.finditer(fuente):
        try:
            bloque, _ = decoder.raw_decode(fuente[coincidencia.start():])
            polycard = bloque.get("polycard", {})
            metadata = polycard.get("metadata", {}) or {}
            componentes = polycard.get("components", []) or []

            titulo_info = _componente(componentes, "title").get("title", {}) or {}
            titulo = titulo_info.get("text", "")
            if not titulo:
                continue

            precio_info = _componente(componentes, "price_v2").get("price", {}) or {}
            precio_actual = precio_info.get("current_price", {}) or {}
            precio_original = ""
            for etiqueta in precio_info.get("price_labels", []) or []:
                for valor in etiqueta.get("values", []) or []:
                    precio_anterior = valor.get("price", {}) or {}
                    if precio_anterior.get("previous"):
                        precio_original = precio_anterior.get("value", "")
                        break
                if precio_original != "":
                    break

            cuotas_info = precio_info.get("installments", {}) or {}
            cuotas_texto = cuotas_info.get("text", "")
            cantidad_cuotas = ""
            coincidencia_cuotas = re.search(r"(\d+)\s+cuotas?", cuotas_texto, re.IGNORECASE)
            if coincidencia_cuotas:
                cantidad_cuotas = coincidencia_cuotas.group(1)
            valor_cuota = ""
            for valor in cuotas_info.get("values", []) or []:
                if valor.get("type") == "price":
                    valor_cuota = (valor.get("price", {}) or {}).get("value", "")
                    break

            datos_comerciales = [
                polycard.get("ads_promotions", {}),
                polycard.get("float_highlight_generic", {}),
            ]
            datos_comerciales.extend(
                componente for componente in componentes
                if componente.get("type") != "title"
            )
            beneficios = _detectar_beneficios(
                _textos_de_estructura(datos_comerciales)
            )

            url = metadata.get("url", "")
            if url and not url.startswith(("http://", "https://")):
                url = "https://" + url.lstrip("/")

            foto_id = ""
            fotos = (polycard.get("pictures", {}) or {}).get("pictures", []) or []
            if fotos:
                foto_id = fotos[0].get("id", "")
            thumbnail = (
                f"https://http2.mlstatic.com/D_NQ_NP_{foto_id}-V.webp"
                if foto_id else ""
            )

            resultado.append({
                "id": metadata.get("id", ""),
                "titulo": titulo,
                "precio": precio_actual.get("value", ""),
                "moneda": precio_actual.get("currency", "ARS"),
                "precio_original": precio_original,
                "condicion": "",
                "envio_gratis": beneficios["envio_gratis"],
                "tipo_envio": "fulfillment" if beneficios["full"] == "Si" else "",
                "cantidad_vendida": "",
                "disponibles": "",
                "vendedor_id": "",
                "vendedor_nickname": "",
                "cuotas": cantidad_cuotas or cuotas_texto,
                "valor_cuota": valor_cuota,
                "full": beneficios["full"],
                "tiene_cupon": beneficios["tiene_cupon"],
                "cupones": beneficios["cupones"],
                "promociones": beneficios["promociones"],
                "beneficios": beneficios["beneficios"],
                "rating": "",
                "cantidad_reseñas": "",
                "link": url,
                "thumbnail": thumbnail,
            })
        except Exception:
            continue

    return _deduplicar_items(resultado)


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
                    "full": "",
                    "tiene_cupon": "",
                    "cupones": "",
                    "promociones": "",
                    "beneficios": "",
                    "rating": rating.get("ratingValue", ""),
                    "cantidad_reseñas": rating.get("ratingCount", ""),
                    "link": oferta.get("url", ""),
                    "thumbnail": nodo.get("image", ""),
                })
        except Exception:
            continue
    return _deduplicar_items(resultado)


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
            "full": "Si" if envio.get("logistic_type") == "fulfillment" else "No",
            "tiene_cupon": "",
            "cupones": "",
            "promociones": "",
            "beneficios": "Full" if envio.get("logistic_type") == "fulfillment" else "",
            "link": item.get("permalink", ""),
            "thumbnail": item.get("thumbnail", ""),
        })
    return _deduplicar_items(resultado)


def _parsear_items_dom(driver: webdriver.Chrome) -> list[dict]:
    resultado = []
    tarjetas = driver.find_elements(
        By.CSS_SELECTOR,
        SELECTOR_TARJETAS
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

            textos_comerciales = []
            for sel in [
                ".poly-component__shipping", ".ui-search-item__shipping",
                "[class*='shipping']", "[class*='coupon']", "[class*='cupon']",
                "[class*='promotion']", "[class*='discount']",
                "[class*='badge']", "[class*='pill']",
            ]:
                for elem in tarjeta.find_elements(By.CSS_SELECTOR, sel):
                    textos_comerciales.append(elem.text)

            for elem in tarjeta.find_elements(
                By.CSS_SELECTOR, "[aria-label], [title], img[alt]"
            ):
                for atributo in ("aria-label", "title", "alt"):
                    valor = elem.get_attribute(atributo) or ""
                    normalizado = _normalizar(valor)
                    if any(palabra in normalizado for palabra in (
                        "full", "envio", "cupon", "oferta", "descuento", "promocion",
                    )):
                        textos_comerciales.append(valor)

            # Algunas etiquetas se renderizan como texto plano dentro de la tarjeta.
            for linea in tarjeta.text.splitlines():
                normalizada = _normalizar(linea)
                menciona_full = (
                    normalizada == "full"
                    or "envio full" in normalizada
                    or "llega full" in normalizada
                )
                if menciona_full or any(palabra in normalizada for palabra in (
                    "envio gratis", "cupon", "oferta", "descuento", "promocion",
                )) or re.search(r"\b\d{1,3}\s*%\s*off\b", normalizada):
                    textos_comerciales.append(linea)

            beneficios = _detectar_beneficios(textos_comerciales)

            condicion = ""
            for sel in [".poly-component__highlight", ".ui-search-item__highlight-label"]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    condicion = elems[0].text.strip()
                    break

            vendedor = ""
            for sel in [
                ".poly-component__seller",
                ".ui-search-official-store-label",
                ".ui-search-item__brand-discoverability__title",
            ]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    vendedor = elems[0].text.strip()
                    if vendedor:
                        break

            cuotas_texto = ""
            valor_cuota_texto = ""
            for sel in [".poly-component__installments", ".ui-search-installments"]:
                elems = tarjeta.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    cuotas_texto = elems[0].text.strip()
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
                "envio_gratis": beneficios["envio_gratis"],
                "tipo_envio": "",
                "cantidad_vendida": "",
                "disponibles": "",
                "vendedor_id": "",
                "vendedor_nickname": vendedor,
                "cuotas": cuotas_texto,
                "valor_cuota": valor_cuota_texto,
                "full": beneficios["full"],
                "tiene_cupon": beneficios["tiene_cupon"],
                "cupones": beneficios["cupones"],
                "promociones": beneficios["promociones"],
                "beneficios": beneficios["beneficios"],
                "link": link,
                "thumbnail": thumbnail,
            })
        except Exception:
            continue

    return _deduplicar_items(resultado)


def obtener_total_resultados(driver) -> int:
    try:
        for sel in [
            ".ui-search-search-result__quantity-results",
            "[class*='quantity-results']",
            ".ui-search-breadcrumb__title",
        ]:
            for elem in driver.find_elements(By.CSS_SELECTOR, sel):
                texto = elem.text.strip()
                coincidencia = re.search(r"([\d.]+)\s+resultados?", texto, re.IGNORECASE)
                if coincidencia:
                    return int(coincidencia.group(1).replace(".", ""))
    except Exception:
        pass
    return 0


def buscar_articulos(frase: str, max_resultados: int) -> list[dict]:
    print(f"\nBuscando: '{frase}'")
    print("-" * 50)
    print("Iniciando navegador...")

    driver = crear_driver()
    driver._debug_iniciada_en = datetime.now().isoformat(timespec="seconds")
    articulos = []
    total_ml = 0
    error_debug = ""

    try:
        esperar_login_manual(driver)
        print(f"Captura offline: {_carpeta_captura(driver)}")

        for desde in range(0, max_resultados, ITEMS_POR_PAGINA):
            url = url_busqueda(frase, desde)
            items = extraer_pagina(driver, url)

            if desde == 0:
                total_ml = obtener_total_resultados(driver)
                if not items:
                    print("No se encontraron resultados.")
                    break
                if total_ml:
                    a_traer = min(total_ml, max_resultados)
                    print(f"MercadoLibre encontro: {total_ml:,} resultados".replace(",", "."))
                    print(f"Vamos a traer: {a_traer:,}".replace(",", "."))
                else:
                    print("Se encontraron publicaciones (el total no esta visible).")
                    print(f"Vamos a traer hasta: {max_resultados:,}".replace(",", "."))
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
    except Exception as e:
        error_debug = repr(e)
        raise
    finally:
        _guardar_resumen_busqueda(
            driver, frase, max_resultados, articulos, total_ml, error_debug,
        )
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
    nombre_archivo = f"{timestamp}_ML_{nombre_seguro}.csv"
    ruta = os.path.join(script_dir, nombre_archivo)

    campos = [
        "id", "titulo", "precio", "moneda", "precio_original",
        "condicion", "envio_gratis", "tipo_envio", "cantidad_vendida",
        "disponibles", "vendedor_id", "vendedor_nickname",
        "cuotas", "valor_cuota", "full", "tiene_cupon", "cupones",
        "promociones", "beneficios", "rating", "cantidad_reseñas", "link", "thumbnail",
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
