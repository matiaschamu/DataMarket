# DataMarket

Suite de herramientas de escritorio para buscar artículos en múltiples plataformas de e-commerce y exportar los resultados a CSV, listos para analizar en Excel, Python, etc.

---

## Plataformas disponibles

| Herramienta | Plataforma | Ejecutable |
|---|---|---|
| Buscador MercadoLibre | [MercadoLibre Argentina](https://www.mercadolibre.com.ar) | `Busqueda MercadoLibre.exe` |
| Buscador AliExpress | [AliExpress](https://es.aliexpress.com) | `Busqueda AliExpress.exe` |
| Buscador Amazon | [Amazon Argentina](https://www.amazon.com.ar) | `Busqueda Amazon.exe` |

---

## Requisitos

- Windows 10 / 11
- **Google Chrome instalado** (los programas lo usan internamente)
- Conexión a internet

No requiere Python ni ninguna otra dependencia — cada `.exe` es autocontenido.

---

## Uso

### Opción A — Doble clic

Hacé doble clic en el `.exe` correspondiente. El programa te va a pedir:

1. **Frase de búsqueda** — lo mismo que escribirías en la plataforma (ej: `ssd`, `zapatillas nike`, `canilla acero`)
2. **Cantidad de resultados** — entre 1 y 1000. Presioná Enter para traer el máximo (1000)

### Opción B — Desde terminal (con argumento)

```
"Busqueda MercadoLibre.exe" zapatillas nike
"Busqueda AliExpress.exe" canilla acero
"Busqueda Amazon.exe" auriculares bluetooth
```

En este modo también te pregunta la cantidad de resultados.

---

## Qué hace cada programa

1. Abre Chrome en segundo plano (ventana minimizada)
2. Navega por las páginas de resultados automáticamente
3. Extrae los datos de cada artículo
4. Cierra Chrome
5. Guarda un `.csv` en la misma carpeta que el `.exe`

---

## Archivos de salida

Los archivos CSV se nombran con prefijo de plataforma, búsqueda y fecha/hora:

```
ML_zapatillas_nike_20260522_143022.csv   ← MercadoLibre
AE_canilla_acero_20260522_151927.csv     ← AliExpress
AZ_auriculares_bluetooth_20260522_160500.csv  ← Amazon
```

---

## Datos que exporta — MercadoLibre

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
| `link` | URL del artículo |
| `thumbnail` | URL de la imagen principal |

---

## Datos que exporta — AliExpress

| Columna | Descripción |
|---|---|
| `titulo` | Nombre del artículo |
| `badge` | Etiqueta destacada (ej: "Top ventas", "Ahorra $X") |
| `precio_usd` | Precio de venta |
| `precio_original_usd` | Precio antes del descuento (si aplica) |
| `costo_envio` | Costo de envío (0 si es gratis) |
| `envio_gratis` | Si / No |
| `tiempo_envio` | Estimación de entrega |
| `pedidos` | Cantidad de ventas (ej: "4.000+ vendidos") |
| `rating` | Calificación promedio (ej: 4.8) |
| `cantidad_reseñas` | Número total de reseñas |
| `vendedor` | Nombre de la tienda |
| `link` | URL del artículo |
| `thumbnail` | URL de la imagen principal |

---

## Datos que exporta — Amazon

| Columna | Descripción |
|---|---|
| `titulo` | Nombre del artículo |
| `badge` | Etiqueta destacada (ej: "Más vendido", "Amazon's Choice") |
| `precio` | Precio de venta (ARS) |
| `precio_original` | Precio antes del descuento (si aplica) |
| `descuento` | Porcentaje de descuento (ej: -30%) |
| `envio_gratis` | Si / No |
| `prime` | Si / No (envío Prime) |
| `rating` | Calificación promedio (ej: 4.5) |
| `cantidad_reseñas` | Número total de reseñas |
| `vendedor` | Nombre del vendedor |
| `link` | URL del artículo |
| `thumbnail` | URL de la imagen principal |

---

## Límites

- **Máximo 1000 resultados por búsqueda** en todas las plataformas.
- El programa muestra el total real que encontró la plataforma antes de empezar.
- Amazon puede solicitar verificación CAPTCHA — el programa pausa y avisa para resolverla manualmente.

---

## Ejemplo de salida en consola

```
==================================================
  Buscador Amazon -> CSV
==================================================

Ingresa la frase de busqueda: auriculares bluetooth
Cuantos resultados queres traer? (1-1000, Enter para 1000): 50

Buscando: 'auriculares bluetooth'
--------------------------------------------------
Iniciando navegador...
Amazon encontro: 1.240 resultados
Vamos a traer: 50

[####################] 50/50 (100%)

50 articulos guardados en:
  C:\Users\...\AZ_auriculares_bluetooth_20260522_160500.csv

Presiona Enter para salir...
```

---

## Estructura del proyecto

```
DataMarket/
├── README.md
├── mercadolibre/
│   ├── busqueda_ml.py
│   ├── BusquedaMercadoLibre.spec
│   ├── icono/
│   │   └── Mercado.ico
│   └── dist/
│       └── Busqueda MercadoLibre.exe
├── aliexpress/
│   ├── busqueda_aliexpress.py
│   ├── BusquedaAliExpress.spec
│   ├── icono/
│   │   └── Aliexpress.ico
│   └── dist/
│       └── Busqueda AliExpress.exe
└── amazon/
    ├── busqueda_amazon.py
    ├── BusquedaAmazon.spec
    ├── Icono/
    │   └── Amazon.ico
    └── dist/
        └── Busqueda Amazon.exe
```

---

## Compilar desde el código fuente

Desde la carpeta de cada plataforma:

```bash
pip install selenium undetected-chromedriver pyinstaller

# MercadoLibre
cd mercadolibre
python -m PyInstaller BusquedaMercadoLibre.spec --noconfirm

# AliExpress
cd aliexpress
python -m PyInstaller BusquedaAliExpress.spec --noconfirm

# Amazon
cd amazon
python -m PyInstaller BusquedaAmazon.spec --noconfirm
```

El ejecutable queda en la carpeta `dist/` de cada módulo.
