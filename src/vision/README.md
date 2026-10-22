# vision/

Visión por computadora del pipeline: detecta las perforaciones del film y calcula la corrección necesaria para que cada fotograma quede alineado con el anterior.

## Submódulos

- [`perforation_detection.py`](perforation_detection.py) — localiza las perforaciones dentro de las zonas de búsqueda configuradas.
- [`stabilization.py`](stabilization.py) — calcula offset X/Y y rotación (θ) respecto a una referencia fija, y aplica el crop & match.

## Flujo

`perforation_detection` recibe un frame + zonas de búsqueda (izquierda/derecha, definidas en la pestaña "Configuración" del prototipo) → devuelve posición de perforaciones → `stabilization` compara contra la referencia (fotograma de calibración) → devuelve transformación (offset XY, ángulo, residuo de confianza, tal como se ve en la pestaña "Resultados": `desplazamiento X/Y +0.09/-12.07 px · giro +0.012° · residuo 0.49 px`).
