# AGENTS.md

## Alcance del proyecto

DataMarket es una suite de buscadores de escritorio para Windows. Cada plataforma tiene un script Python, un archivo `.spec` de PyInstaller y un ejecutable autocontenido dentro de `dist/`.

- `aliexpress/busqueda_aliexpress.py`: AliExpress España, precios solicitados en USD.
- `amazon/busqueda_amazon.py`: Amazon Argentina.
- `mercadolibre/busqueda_ml.py`: MercadoLibre Argentina.
- `README.md`: documentación orientada al usuario.

Los scripts fuente son la implementación canónica. Los ejecutables de `dist/` son artefactos que deben recompilarse después de cambiar su script correspondiente.

## Reglas de trabajo

- Preservar cambios existentes del usuario. El repositorio puede estar sucio y los tres scripts o ejecutables pueden tener modificaciones deliberadas.
- No restaurar, borrar ni reemplazar cambios ajenos para resolver una tarea puntual.
- Usar `apply_patch` para cambios manuales de archivos.
- Escribir siempre en español los mensajes de commit, con una descripción clara y concreta del cambio.
- Validar como mínimo con `python -m py_compile` el script modificado.
- Si cambia el comportamiento que usa el usuario, recompilar el `.exe` correspondiente y comprobar que PyInstaller termina con `Build complete`.
- No versionar CSV, perfiles de Chrome, capturas de depuración ni datos de sesión.
- No editar directamente un `.exe`; siempre reconstruirlo desde el `.spec`.

## Entorno y compilación

Dependencias de desarrollo:

```powershell
pip install selenium undetected-chromedriver pyinstaller
```

Compilar AliExpress:

```powershell
cd aliexpress
pyinstaller --clean --noconfirm BusquedaAliExpress.spec
```

Compilar Amazon:

```powershell
cd amazon
pyinstaller --clean --noconfirm BusquedaAmazon.spec
```

Compilar MercadoLibre:

```powershell
cd mercadolibre
pyinstaller --clean --noconfirm BusquedaMercadoLibre.spec
```

Los ejecutables resultantes quedan en la carpeta `dist/` de cada plataforma. En este equipo PyInstaller puede estar en `C:\Users\matia\AppData\Local\Python\bin\pyinstaller.exe`.

## Navegación y perfiles

Los programas usan `undetected_chromedriver` con un perfil persistente `.perfil_chrome` ubicado junto al script o ejecutable. El usuario confirma manualmente el inicio de sesión antes de comenzar.

`detectar_version_principal_chrome()` determina la versión principal instalada. No volver a fijar un número de Chrome manualmente salvo que exista una razón comprobada.

## MercadoLibre: búsqueda y extracción

La ausencia del contador total no significa que una búsqueda esté vacía. MercadoLibre
puede cambiar u ocultar `.ui-search-search-result__quantity-results` aunque las
tarjetas se hayan cargado. La búsqueda sólo debe informar cero resultados cuando la
primera página no produce artículos. Si hay tarjetas y no hay contador, continuar
hasta el máximo solicitado o hasta encontrar una página vacía.

La presencia del contador tampoco garantiza que las tarjetas ya estén listas. En la
captura `mercadolibre/dist/debug_mercadolibre/20260905_124437/`, el contador mostraba
1.730 resultados pero la página seguía en el spinner: había cero productos LDJSON y
cero tarjetas DOM. `extraer_pagina()` debe esperar explícitamente tarjetas o una
pantalla vacía; si vence la espera, refrescar una vez y volver a esperar antes de
declarar que no hay resultados. Registrar el número de reintentos en las capturas.

La extracción combina los productos de `application/ld+json` con los datos visibles
del DOM. El DOM es también el fallback cuando no existe una lista LDJSON válida. Los
contenedores pueden representar varias veces la misma tarjeta; deduplicar por `id`,
`link` o, como último recurso, título, precio y vendedor.

Las páginas Nordic también serializan tarjetas completas como objetos escapados con
`{"id":"POLYCARD","state":"VISIBLE","polycard":...}`. Esta fuente debe
parsearse con `_parsear_polycards_embebidas()` y usarse cuando el LDJSON no existe,
incluso si la interfaz sigue mostrando el spinner y el DOM no contiene tarjetas. La
captura fallida `20260905_125019` permitió recuperar 57 publicaciones únicas de este
bloque: 14 Full, 27 con envío gratis y 6 con cupón.

El CSV de MercadoLibre separa las señales comerciales en estas columnas:

- `full`: `Si` / `No` según la etiqueta Full visible o el tipo logístico conocido.
- `envio_gratis`: `Si` / `No` según el texto o atributo semántico visible.
- `tiene_cupon`: `Si` / `No`.
- `cupones`: texto completo de los cupones visibles.
- `promociones`: descuentos y promociones visibles que no sean cupones.
- `beneficios`: resumen combinado de las señales anteriores.

Para detectar beneficios, revisar elementos de envío, cupones, promociones, badges y
sus atributos `aria-label`, `title` y `alt`. Evitar inferir Full sólo porque la palabra
aparece dentro del título de un producto. Los nodos anidados pueden repetir una
etiqueta; conservar la variante más completa, por ejemplo `$ 5.000 OFF con Cupón` en
lugar de guardar además `OFF con Cupón`.

## Capturas offline de MercadoLibre

Cada búsqueda crea una carpeta fechada junto al script o ejecutable que se lanzó:

```text
debug_mercadolibre/YYYYMMDD_HHMMSS/
├── pagina_001.html
├── pagina_001.png
├── pagina_001.json
├── pagina_002.html
├── pagina_002.png
├── pagina_002.json
└── debug_busqueda.json
```

- Al ejecutar el `.exe`, la ruta queda bajo `mercadolibre/dist/debug_mercadolibre/`.
- Al ejecutar el fuente, queda bajo `mercadolibre/debug_mercadolibre/`.
- `pagina_NNN.html` conserva el DOM completo.
- `pagina_NNN.png` muestra lo que renderizó el navegador.
- `pagina_NNN.json` conserva URL solicitada y final, total visible, LDJSON crudo,
  artículos interpretados por LDJSON, artículos interpretados por DOM y resultado
  final combinado.
- `debug_busqueda.json` registra frase, fechas, máximo solicitado, total informado,
  páginas capturadas, artículos devueltos y cualquier error de ejecución.

Estas capturas pueden contener cookies indirectas, identificadores técnicos de
sesión, telemetría o información personalizada. Están ignoradas por Git, no deben
publicarse y deben preservarse localmente para futuras investigaciones salvo que el
usuario pida borrarlas.

Para investigar una búsqueda vacía o un beneficio incorrecto:

1. Elegir la captura más reciente y abrir `debug_busqueda.json`.
2. Revisar `url_final`, los contadores y `resultado` en `pagina_NNN.json`.
3. Comparar `items_ldjson` con `items_dom` para localizar dónde se perdió el dato.
4. Confirmar la etiqueta en `pagina_NNN.png` y su representación en el HTML.
5. Corregir con señales semánticas y validar casos positivos, negativos y ausentes.

## Auditoría de referencia: búsqueda `lanza pelotas`

Captura validada: `mercadolibre/debug_mercadolibre/20260905_124128/`.

- MercadoLibre informó 1.730 resultados.
- La primera página produjo 48 productos LDJSON, 49 tarjetas DOM deduplicadas y 48
  resultados finales.
- La captura PNG se guardó correctamente y no hubo error de ejecución.
- La prueba pidió un solo resultado, por eso `debug_busqueda.json` registra un
  artículo extraído aunque `pagina_001.json` contenga los 48 resultados de la página.
- La búsqueda confirmó ejemplos reales con Full, envío gratis y cupones.

Esta auditoría confirma el comportamiento observado el 5 de septiembre de 2026. Las
promociones pueden cambiar después; ante una diferencia, usar siempre la captura de
la ejecución reportada antes de modificar el parser.

## AliExpress: estrategia de extracción

La búsqueda carga la página, hace scroll para hidratar tarjetas y sigue este orden:

1. Extraer el objeto JSON de `window._dida_config_._init_data_.data`, `window.runParams` u otras variantes compatibles.
2. Localizar `itemList.content` en las rutas conocidas, incluida `data.root.fields.mods.itemList.content`.
3. Parsear cada tarjeta desde el JSON.
4. Usar el DOM únicamente como fallback si no existe una lista JSON válida.

Evitar selectores basados sólo en clases ofuscadas; AliExpress las cambia con frecuencia. Los campos semánticos del JSON son preferibles.

## AliExpress: badges

La columna `badge` puede contener varias insignias separadas por ` | `.

Señales observadas el 30 de agosto de 2026:

| Badge | Señal JSON | ID observado |
|---|---|---|
| Choice | `trace.utLogMap.isChoice=true` y `sellingPoints[].source=choice_atm` | `m0000094` |
| Brands+ | `common_brand_plus_atm` y `common_brand_plus_picture_atm` | `m0000612`, `m0000609` |
| SuperDeals | `card_real_super_deals_atm` | `m0000607` |
| Big Sale | `bigSale_warmup_atm` | `m0000027` |

Precedencia para Choice:

- `isChoice=false` debe suprimir Choice aunque aparezca una señal secundaria.
- `isChoice=true` debe producir Choice.
- Si `isChoice` no existe, `choice_atm` es el fallback semántico.
- No inferir Choice buscando palabras en el título o en todo el texto de la tarjeta.

Señales de logística como `platformFreeShipping_atm`, `Free_Shipping_atm`, `Shipping_Fee_atm`, `delivery`, `freight` o textos de envío no son badges de programa.

Promociones textuales como monedas, `Top ventas`, `Oferta única` o `El mejor precio en ofertas similares` pueden aparecer en `badge` cuando no existe una insignia de programa reconocida. Si se decide separar conceptos, hacerlo mediante una nueva columna o una decisión explícita de producto, no cambiando silenciosamente el significado actual.

## Capturas offline de AliExpress

Cada búsqueda de AliExpress crea una carpeta local:

```text
aliexpress/dist/debug_aliexpress/YYYYMMDD_HHMMSS/
├── pagina_001.html
├── pagina_001.json
├── pagina_002.html
├── pagina_002.json
└── debug_badges.json
```

- `pagina_NNN.html`: DOM completo después del scroll.
- `pagina_NNN.json`: objeto interno completo usado por el parser.
- `debug_badges.json`: resumen acumulado de todos los artículos, `productId`, título, badge calculado, `isChoice` y `sellingPoints` relevantes.

Estas capturas pueden contener identificadores técnicos de sesión, telemetría o información personalizada. Son locales, están ignoradas por Git y no deben publicarse.

Para investigar un badge incorrecto:

1. Elegir la carpeta de captura más reciente.
2. Buscar el `productId` o título en `debug_badges.json`.
3. Comparar `badge_extraido`, `isChoice`, `source`, `sellingPointTagId`, `tagText` y `tagImgUrl`.
4. Confirmar la misma tarjeta en `pagina_NNN.json`.
5. Verificar en `pagina_NNN.html` si la imagen/texto del badge fue renderizada realmente.
6. Corregir la regla usando señales semánticas; no usar coincidencias sobre el título completo.

El navegador integrado de Codex puede bloquear la navegación directa a AliExpress. En ese caso, usar estas capturas producidas por el ejecutable para el análisis offline; no intentar eludir el bloqueo cambiando de superficie de navegador.

## Auditoría de referencia: búsqueda `jlink v11`

Captura analizada: `aliexpress/dist/debug_aliexpress/20260830_155943/`.

- 9 páginas y 540 artículos únicos capturados.
- 366 artículos tenían `isChoice=true`; 174 tenían `isChoice=false`.
- El extractor coincidió con `isChoice` en los 540 casos: cero contradicciones internas.
- Los 366 Choice también tenían `source=choice_atm`.
- En una tarjeta inspeccionada (`productId=1005009911992437`), el HTML renderizado contenía la imagen de Choice `S1887a285b60743859ac7bdbfca5e0896Z/154x64.png` dentro del encabezado del producto.

Esto demuestra qué informó y renderizó la página de búsqueda; no garantiza que la ficha individual mantenga el mismo estado promocional más tarde. Si el usuario observa una diferencia entre la búsqueda y la ficha, registrar el `productId`, la hora y ambas superficies antes de cambiar el parser.

## Verificación antes de entregar

- Ejecutar `git diff --check`.
- Revisar `git status --short` y distinguir cambios propios de cambios previos del usuario.
- Validar funciones puras con casos positivos, negativos y valores ausentes.
- Recompilar sólo los ejecutables afectados.
- Informar cualquier limitación de prueba end-to-end, especialmente login, CAPTCHA o bloqueos del navegador.
