# Buscador MercadoLibre Argentina → CSV

Herramienta de escritorio que busca artículos en [MercadoLibre Argentina](https://www.mercadolibre.com.ar) y exporta los resultados a un archivo CSV listo para analizar en Excel, Python, etc.

---

## Requisitos

- Windows 10 / 11
- **Google Chrome instalado** (el programa lo usa internamente)
- Conexión a internet

No requiere Python ni ninguna otra dependencia — el `.exe` es autocontenido.

---

## Uso

### Opción A — Doble clic

Hacé doble clic en `BusquedaMercadoLibre.exe`. El programa te va a pedir:

1. **Frase de búsqueda** — lo mismo que escribirías en MercadoLibre (ej: `ssd`, `zapatillas nike`, `notebook gamer`)
2. **Cantidad de resultados** — entre 1 y 1000. Presioná Enter para traer el máximo (1000)

### Opción B — Desde terminal (con argumento)

```
BusquedaMercadoLibre.exe zapatillas nike
```

En este modo también te pregunta la cantidad de resultados.

---

## Qué hace el programa

1. Abre Chrome en segundo plano (ventana minimizada)
2. Navega por las páginas de resultados de MercadoLibre automáticamente
3. Extrae los datos de cada artículo
4. Cierra Chrome
5. Guarda un `.csv` en la misma carpeta que el `.exe`

El archivo se llama `ML_[busqueda]_[fecha_hora].csv`, por ejemplo:
```
ML_ssd_20260519_143022.csv
```

---

## Datos que exporta

| Columna | Descripción |
|---|---|
| `titulo` | Nombre del artículo |
| `precio` | Precio de venta |
| `moneda` | Moneda (ARS) |
| `precio_original` | Precio antes del descuento (si aplica) |
| `condicion` | Nuevo / Usado |
| `envio_gratis` | Si / No |
| `tipo_envio` | Tipo logístico |
| `cantidad_vendida` | Ventas totales del artículo |
| `disponibles` | Stock disponible |
| `vendedor_id` | ID del vendedor |
| `vendedor_nickname` | Nombre del vendedor |
| `cuotas` | Cantidad de cuotas disponibles |
| `valor_cuota` | Monto por cuota |
| `rating` | Calificación promedio (ej: 4.8) |
| `cantidad_reseñas` | Número total de reseñas |
| `link` | URL del artículo en MercadoLibre |
| `thumbnail` | URL de la imagen principal |

---

## Límites

- **Máximo 1000 resultados por búsqueda** — es el límite que impone MercadoLibre independientemente de cuántos resultados existan en total.
- El programa muestra el total real que encontró MercadoLibre antes de empezar a traer resultados.

---

## Ejemplo de salida en consola

```
==================================================
  Buscador MercadoLibre Argentina -> CSV
==================================================

Ingresa la frase de busqueda: ssd
Cuantos resultados queres traer? (1-1000, Enter para 1000): 200

Buscando: 'ssd'
--------------------------------------------------
Iniciando navegador...
MercadoLibre encontro: 5.517 resultados
Vamos a traer: 200

[####################] 200/200 (100%)

200 articulos guardados en:
  C:\Users\...\ML_ssd_20260519_143022.csv

Presiona Enter para salir...
```

---

## Compilar desde el código fuente

Si querés modificar el script y regenerar el `.exe`:

```bash
pip install selenium undetected-chromedriver pyinstaller
pyinstaller --onefile --console --name "BusquedaMercadoLibre" --hidden-import undetected_chromedriver busqueda_ml.py
```

El ejecutable queda en la carpeta `dist/`.
