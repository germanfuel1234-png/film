/*
 * FILMS - Firmware de control del motor paso a paso
 *
 * Implementa el protocolo serie consumido por
 * src/hardware/motor/stepper_motor.py (ver proyecto_film/ARQUITECTURA.md §4).
 * Un comando por linea, terminado en '\n':
 *
 *   MOVE <pasos> <dir:1|-1>   -> ACK <pasos_reales_movidos>  |  ERR <motivo>
 *   STOP                      -> ACK
 *   STATUS                    -> POS <pasos_acumulados>
 *   RESET_COUNTER             -> ACK
 *
 * Pulsos/microstepping, pines y driver exactos (A4988/TMC2209/etc.) quedan
 * pendientes de confirmar con el cliente (ver ESPECIFICACIONES_PROYECTO.md
 * seccion 6, pregunta 2). Este sketch asume un driver tipo STEP/DIR
 * generico, que es el caso comun para A4988/DRV8825/TMC2209.
 */

const int PIN_STEP = 3;
const int PIN_DIR = 4;
const int PIN_ENABLE = 5; // activo en bajo en la mayoria de los drivers STEP/DIR

const unsigned long STEP_PULSE_WIDTH_US = 8;     // ancho de pulso minimo del driver
const unsigned long STEP_INTERVAL_US = 800;      // velocidad de avance (a calibrar)

long positionSteps = 0;
volatile bool stopRequested = false;

void setup() {
  pinMode(PIN_STEP, OUTPUT);
  pinMode(PIN_DIR, OUTPUT);
  pinMode(PIN_ENABLE, OUTPUT);
  digitalWrite(PIN_ENABLE, LOW); // motor habilitado

  Serial.begin(115200);
  Serial.setTimeout(50);
}

void loop() {
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      handleCommand(line);
    }
  }
}

void handleCommand(const String &line) {
  if (line.startsWith("MOVE")) {
    handleMove(line);
  } else if (line == "STOP") {
    stopRequested = true;
    Serial.println("ACK");
  } else if (line == "STATUS") {
    Serial.print("POS ");
    Serial.println(positionSteps);
  } else if (line == "RESET_COUNTER") {
    // Reinicia el contador logico SIN mover el motor: conserva la
    // posicion fisica real, tal como describe la UI de calibracion.
    positionSteps = 0;
    Serial.println("ACK");
  } else {
    Serial.print("ERR comando desconocido: ");
    Serial.println(line);
  }
}

void handleMove(const String &line) {
  int firstSpace = line.indexOf(' ');
  int secondSpace = line.indexOf(' ', firstSpace + 1);
  if (firstSpace < 0 || secondSpace < 0) {
    Serial.println("ERR formato esperado: MOVE <pasos> <dir>");
    return;
  }

  long steps = line.substring(firstSpace + 1, secondSpace).toInt();
  int direction = line.substring(secondSpace + 1).toInt();
  if (direction != 1 && direction != -1) {
    Serial.println("ERR direccion invalida, debe ser 1 o -1");
    return;
  }
  if (steps <= 0) {
    Serial.println("ERR cantidad de pasos invalida");
    return;
  }

  digitalWrite(PIN_DIR, direction > 0 ? HIGH : LOW);

  stopRequested = false;
  long movedSteps = 0;
  for (long i = 0; i < steps; i++) {
    if (stopRequested) {
      break;
    }
    digitalWrite(PIN_STEP, HIGH);
    delayMicroseconds(STEP_PULSE_WIDTH_US);
    digitalWrite(PIN_STEP, LOW);
    delayMicroseconds(STEP_INTERVAL_US);
    movedSteps++;
  }

  positionSteps += movedSteps * direction;

  Serial.print("ACK ");
  Serial.println(movedSteps * direction);
}
