# Anotación de noticias

Desde la raíz del repositorio (Python 3.10 o posterior, sin dependencias adicionales):

```sh
python3 news-calibration/server.py
```

Abre `http://127.0.0.1:8765/`. La pantalla carga directamente las noticias.

Todo lo necesario está en esta carpeta:

```text
news-calibration/
  samples/calibration_sample_40.csv            # Original
  annotations/calibration_sample_40_javi.csv   # Respuestas de Javi
  annotations/calibration_sample_40_hugo.csv   # Respuestas de Hugo
  annotations/calibration_sample_40_higinio.csv # Respuestas de Higinio
  server.py                                  # Arrancar la app
```

Los archivos de cada revisor se crean al guardar por primera vez.

## Archivos y revisores

- Coloca el CSV original en `news-calibration/samples/`, o usa **Archivo → Cargar otro CSV**.
  En **Archivo** también puedes seleccionar otra muestra.
  La muestra compartida debe tener las noticias pendientes y sin respuestas.
- Selecciona **Javi**, **Hugo** o **Higinio**. Cada perfil tiene sus propias
  respuestas y progreso. El CSV original permanece intacto.
- **Guardar y siguiente** confirma una decisión y guarda en disco.
  **Guardar borrador** guarda los campos actuales como pendientes sin avanzar.
  **Dejar pendiente** conserva una duda sin marcarla como revisada.
  Cambiar de noticia, muestra o revisor también guarda el borrador actual.
- **Descargar CSV** exporta todas las filas del revisor seleccionado, incluidas
  las pendientes, conservando columnas, orden e información original.

Las respuestas se guardan en
`news-calibration/annotations/<nombre-original>_<revisor>.csv`.
Por ejemplo, `calibration_sample_40.csv` se guarda para Javi como
`calibration_sample_40_javi.csv`; las siguientes veces se actualiza ese mismo
archivo. La descarga usa también ese nombre.
El navegador conserva además borradores sin guardar. Si otra pestaña modifica
el mismo perfil, la app evita sobrescribir sus cambios: descarga tu borrador
antes de pulsar **Descartar borrador y recargar guardado**.

El formato de referencia es `calibration_sample_40.csv`: 40 filas y 18 columnas.
La aplicación conserva todas las columnas de procedencia y solo modifica
`review_status`, `relevant_risk_news`, `company_relevance`, `event_status`,
`confirmed_risk_families`, `noise_type`, `reviewer` y `notes`.
La relación con la empresa se edita explícitamente, incluso en los borradores.
Una decisión positiva requiere relación empresarial confirmada, familia, estado y nota; una negativa requiere
relación con la empresa, motivo y nota. Las dudas quedan pendientes.
La noticia se muestra en un iframe junto al formulario. Yahoo bloquea su página
original en iframes, por lo que se muestra una vista de lectura del texto público
disponible, sin scripts ni anuncios interactivos. Puede ser parcial; no se accede
a contenido restringido. Otros medios se incrustan directamente; si lo bloquean,
se conserva **Abrir noticia original**. Un error de lectura no impide anotar.

Los perfiles son locales, sin cuentas ni autenticación. El servidor escucha
solo en este ordenador; cada compañero puede ejecutar su propia copia con la
misma muestra y entregar su CSV. La muestra original se incluye en el repositorio;
los archivos de cada revisor se generan localmente al guardar.
Para usar otra carpeta o puerto: `--data-dir RUTA --port 8766`.

Este flujo carga la muestra ya seleccionada por Higinio. No necesita
`risk_news_candidates.csv`, acceso a EODHD ni volver a generar las 40 noticias.
