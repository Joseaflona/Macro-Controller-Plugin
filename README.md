# PadMIDI

Convierte un mando de Xbox (USB, XInput) en un controlador MIDI para mapear macros o cualquier parámetro de Ableton (u otro DAW).
Solo necesita Python 3.11+ y no tiene dependencias externas.

## Puesta en marcha (una sola vez)

1. Instala **loopMIDI** (gratis, de Tobias Erichsen) y crea un puerto con el botón `+`. Por defecto se llama `loopMIDI Port`.
2. Conecta el mando por USB.
3. Ejecuta `run.bat --list` y comprueba que aparece el puerto de loopMIDI.

## En Ableton

1. Ve a *Preferences → Link, Tempo & MIDI*. En la fila **Input** de `loopMIDI Port`, activa **Remote**.
2. Ejecuta `run.bat --learn`. En modo aprendizaje solo se envía el control que más se mueve, para que no se mapee el eje equivocado.
3. En Ableton pulsa **Ctrl+M**, haz clic en un macro o parámetro y mueve el control del mando. Repite con el resto y pulsa Ctrl+M para salir.
4. Cierra y usa `run.bat` normal (o `run.bat -m` para ver los mensajes).

Para mapear varios bancos, cambia de banco con LB/RB antes de mapear. Cada banco envía por su propio canal MIDI, así que en Ableton cuentan como controles distintos.

## Layout por defecto (`config.toml`)

| Control | Modo | CC |
|---|---|---|
| Stick izq. ↑ ↓ → ← | throw: vuelve a 0 al soltar | 20, 21, 22, 23 |
| Stick der. X / Y | knob relativo: se queda donde lo dejes | 24, 25 |
| LT / RT | gatillo 0–127 | 26, 27 |
| A, B, cruceta | momentáneo | 102, 103, 106–109 |
| X, Y, clic de sticks | toggle | 104, 105, 110, 111 |
| LB / RB | banco anterior / siguiente (vibra N veces = banco N) | — |

Todo se edita en `config.toml`, donde cada opción viene explicada.

**Bancos personalizados**: un bloque `[[bank]]` con `number = N` y sus `[[bank.axis]]` / `[[bank.button]]` sustituye, solo en ese banco, los controles que menciona. El resto se hereda del layout general. Por defecto, en el **banco 2** los ejes horizontales LX (CC22) y RX (CC24) están en modo pan: el centro del stick envía 64.

## Consejos

- **Knobs relativos y el ratón**: si mueves con el ratón un parámetro mapeado a un knob relativo, el mando y Ableton se desincronizan. Pon *Takeover Mode = Value Scaling* en las preferencias MIDI de Ableton.
- **Throws** (modo `positive` o `negative`): mapéalos a macros de envío de reverb o delay, a un filtro o a un "dry/wet" de un efecto glitch. Al soltar el stick vuelven solos.
- Si mapeas un CC a un **macro de un Rack**, puedes ajustar el rango min/max de cada parámetro dentro del Rack.

## Opciones

```
run.bat [--list] [-m/--monitor] [-l/--learn] [--dry-run] [-p PUERTO] [-c CONFIG]
```

Tests: `py -m unittest discover -s tests`
