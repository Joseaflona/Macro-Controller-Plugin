"""PadMIDI: mando de Xbox -> MIDI CC para mapear en Ableton (Ctrl+M)."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .engine import ConfigError, Engine, load_config
from .midiout import MidiOut, high_res_timer, list_ports
from .xinput import XInputPad

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"


class Rumbler:
    """Pulsos de vibración no bloqueantes (para indicar el banco)."""

    def __init__(self, pad: XInputPad):
        self.pad = pad
        self.steps: list[tuple[float, float]] = []  # (instante, intensidad)

    def pulses(self, count: int, now: float, on=0.07, off=0.09, strength=0.5) -> None:
        self.steps = []
        t = now
        for _ in range(count):
            self.steps += [(t, strength), (t + on, 0.0)]
            t += on + off

    def tick(self, now: float) -> None:
        while self.steps and self.steps[0][0] <= now:
            _, s = self.steps.pop(0)
            self.pad.rumble(s, s)


def main() -> int:
    ap = argparse.ArgumentParser(prog="padmidi", description=__doc__)
    ap.add_argument("-c", "--config", default=str(DEFAULT_CONFIG), help="ruta a config.toml")
    ap.add_argument("-p", "--port", help="puerto MIDI (sustituye al de config.toml)")
    ap.add_argument("--list", action="store_true", help="lista los puertos MIDI de salida")
    ap.add_argument("-m", "--monitor", action="store_true", help="muestra cada mensaje enviado")
    ap.add_argument("-l", "--learn", action="store_true",
                    help="modo aprendizaje: solo envía el control que más se mueve (para Ctrl+M)")
    ap.add_argument("--dry-run", action="store_true", help="no abre MIDI, solo muestra los mensajes")
    args = ap.parse_args()

    if args.list:
        for i, name in enumerate(list_ports()):
            print(f"{i}: {name}")
        return 0

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"Error en la configuración: {e}", file=sys.stderr)
        return 1

    midi = None
    if not args.dry_run:
        try:
            midi = MidiOut(args.port or cfg.port)
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return 1

    verbose = args.monitor or args.learn or args.dry_run
    pad = XInputPad(cfg.controller)
    engine = Engine(cfg)
    rumbler = Rumbler(pad)
    period = 1.0 / cfg.rate_hz

    print(f"PadMIDI -> {midi.name if midi else '(dry-run, sin MIDI)'}")
    print(f"{len(cfg.axes)} ejes, {len(cfg.buttons)} botones, {cfg.bank_count} banco(s)"
          + (" | MODO APRENDIZAJE" if args.learn else ""))
    print("Ctrl+C para salir.\n")

    high_res_timer(True)
    connected = None
    last = time.perf_counter()
    try:
        while True:
            now = time.perf_counter()
            dt = min(now - last, 0.1)
            last = now

            state = pad.read()
            if state is None:
                if connected is not False:
                    print("Esperando mando... (conéctalo por USB)")
                    connected = False
                time.sleep(0.5)
                last = time.perf_counter()
                continue
            if connected is not True:
                print(f"Mando conectado (slot {pad.index}). Banco {engine.bank + 1}, canal MIDI {engine.channel}")
                connected = True

            for ev in engine.update(state, dt, learn=args.learn):
                if midi:
                    midi.cc(ev.channel, ev.cc, ev.value)
                if verbose:
                    print(f"  B{engine.bank + 1} ch{ev.channel:<2} CC{ev.cc:<3} = {ev.value:<3}  {ev.label}")

            if engine.bank_changed:
                print(f"Banco {engine.bank + 1} (canal MIDI {engine.channel})")
                if cfg.rumble:
                    rumbler.pulses(engine.bank + 1, now)
            rumbler.tick(now)

            remaining = period - (time.perf_counter() - now)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        print("\nSaliendo.")
    finally:
        pad.rumble(0, 0)
        if midi:
            midi.close()
        high_res_timer(False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
