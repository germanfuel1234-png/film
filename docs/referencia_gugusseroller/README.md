# referencia_gugusseroller/

Material de referencia sobre el **Gugusse Roller** (`github.com/meantux/GugusseRoller`), el escáner DIY que el cliente mencionó como ejemplo de cómo debería verse el resultado final.

## Contenido

- **`ANALISIS.md`** — análisis de la arquitectura y técnicas del Gugusse Roller, escrito con nuestras propias palabras. **Esto es lo que hay que leer** para entender qué aprendimos y qué conviene adoptar en nuestro propio código.
- **`GugusseRoller-source/`** — **copia textual, sin modificar, del código fuente original de terceros**, bajada el 2026-10-23 desde el zip que mandó el cliente (`~/Descargas/GugusseRoller-master.zip`).

## ⚠️ Licencia — por qué está separado así

El Gugusse Roller está licenciado bajo **GNU GPLv3** (ver `GugusseRoller-source/LICENSE`). Nuestro software (`proyecto_film/src/`) es del cliente y no está pensado para ser GPL.

Por eso:
- `GugusseRoller-source/` se mantiene **sin tocar y completamente separado** de `src/` — es lo que el GPL llama "agregación" (distribuir un programa GPL completo junto a otro software en el mismo repositorio, sin combinarlos), lo cual **no obliga a licenciar el resto del proyecto como GPL**.
- **Nunca copiar fragmentos de código de `GugusseRoller-source/` hacia `src/`.** Si algo de ahí resulta útil, hay que reimplementarlo de cero (entendiendo la idea, no el código) — es lo que ya se hizo en `ANALISIS.md`.
- Gran parte de `GugusseRoller-source/` depende de hardware específico de Raspberry Pi (`RPi.GPIO`, `picamera2`/libcamera) que no existe en una PC de escritorio normal — ver notas en `ANALISIS.md` §7 sobre qué tan realista es "hacerlo correr acá".
