"""Lógica de mapeo mando -> MIDI CC. No toca hardware, así que se puede testear."""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

STICK_AXES = ("LX", "LY", "RX", "RY")
TRIGGER_AXES = ("LT", "RT")
AXES = STICK_AXES + TRIGGER_AXES
BUTTONS = ("A", "B", "X", "Y", "LB", "RB", "BACK", "START", "LS", "RS",
           "UP", "DOWN", "LEFT", "RIGHT")
AXIS_MODES = ("absolute", "positive", "negative", "relative")
BUTTON_MODES = ("momentary", "toggle")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PadState:
    axes: dict           # nombre -> float (sticks -1..1, gatillos 0..1)
    buttons: frozenset   # nombres de botones pulsados


@dataclass
class AxisMap:
    input: str
    cc: int
    mode: str = "absolute"
    deadzone: float = 0.12
    curve: float = 1.0
    min: int = 0
    max: int = 127
    invert: bool = False
    smoothing: float = 0.0
    speed: float = 0.6
    start: float = 0.0
    label: str = ""


@dataclass
class ButtonMap:
    input: str
    cc: int
    mode: str = "momentary"
    on: int = 127
    off: int = 0
    label: str = ""


@dataclass
class Config:
    port: str = "loopMIDI"
    channel: int = 1
    rate_hz: float = 250.0
    controller: int | None = None
    bank_count: int = 1
    bank_next: str | None = None
    bank_prev: str | None = None
    rumble: bool = True
    axes: list = field(default_factory=list)
    buttons: list = field(default_factory=list)
    # banco (0-based) -> (ejes, botones) que sustituyen a los generales
    # para las entradas que mencionan; el resto se hereda.
    overrides: dict = field(default_factory=dict)

    def layout(self, bank: int) -> tuple[list, list]:
        ov = self.overrides.get(bank)
        if not ov:
            return self.axes, self.buttons
        ov_axes, ov_buttons = ov
        a_in = {m.input for m in ov_axes}
        b_in = {m.input for m in ov_buttons}
        return ([m for m in self.axes if m.input not in a_in] + ov_axes,
                [m for m in self.buttons if m.input not in b_in] + ov_buttons)


@dataclass(frozen=True)
class MidiEvent:
    channel: int
    cc: int
    value: int
    label: str


# ---------------------------------------------------------------- config

def _check_keys(table: dict, allowed: set, where: str) -> None:
    unknown = set(table) - allowed
    if unknown:
        raise ConfigError(f"{where}: clave(s) desconocida(s): {', '.join(sorted(unknown))}")


def _num(table, key, default, lo, hi, where, integer=False):
    v = table.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (integer and not isinstance(v, int)):
        raise ConfigError(f"{where}: '{key}' debe ser un número{' entero' if integer else ''}")
    if not lo <= v <= hi:
        raise ConfigError(f"{where}: '{key}' = {v} fuera de rango ({lo}..{hi})")
    return v if integer else float(v)


def _choice(table, key, default, options, where):
    v = table.get(key, default)
    if not isinstance(v, str) or v.upper() not in [o.upper() for o in options]:
        raise ConfigError(f"{where}: '{key}' = {v!r} no válido. Opciones: {', '.join(options)}")
    return next(o for o in options if o.upper() == v.upper())


def _bool(table, key, default, where):
    v = table.get(key, default)
    if not isinstance(v, bool):
        raise ConfigError(f"{where}: '{key}' debe ser true o false")
    return v


def _str(table, key, default, where):
    v = table.get(key, default)
    if not isinstance(v, str):
        raise ConfigError(f"{where}: '{key}' debe ser texto")
    return v


_AXIS_KEYS = set(AxisMap.__dataclass_fields__)
_BUTTON_KEYS = set(ButtonMap.__dataclass_fields__)


def _parse_axis(t: dict, w: str) -> AxisMap:
    _check_keys(t, _AXIS_KEYS, w)
    m = AxisMap(
        input=_choice(t, "input", "", AXES, w),
        cc=_num(t, "cc", 0, 0, 127, w, integer=True),
        mode=_choice(t, "mode", "absolute", AXIS_MODES, w),
        deadzone=_num(t, "deadzone", 0.12, 0.0, 0.95, w),
        curve=_num(t, "curve", 1.0, 0.1, 5.0, w),
        min=_num(t, "min", 0, 0, 127, w, integer=True),
        max=_num(t, "max", 127, 0, 127, w, integer=True),
        invert=_bool(t, "invert", False, w),
        smoothing=_num(t, "smoothing", 0.0, 0.0, 2.0, w),
        speed=_num(t, "speed", 0.6, 0.01, 20.0, w),
        start=_num(t, "start", 0.0, 0.0, 1.0, w),
        label=_str(t, "label", "", w),
    )
    if m.input in TRIGGER_AXES and m.mode == "negative":
        raise ConfigError(f"{w}: los gatillos no tienen dirección negativa")
    return m


def _parse_button(t: dict, w: str, reserved: set) -> ButtonMap:
    _check_keys(t, _BUTTON_KEYS, w)
    m = ButtonMap(
        input=_choice(t, "input", "", BUTTONS, w),
        cc=_num(t, "cc", 0, 0, 127, w, integer=True),
        mode=_choice(t, "mode", "momentary", BUTTON_MODES, w),
        on=_num(t, "on", 127, 0, 127, w, integer=True),
        off=_num(t, "off", 0, 0, 127, w, integer=True),
        label=_str(t, "label", "", w),
    )
    if m.input in reserved:
        raise ConfigError(f"{w}: {m.input} está reservado para cambiar de banco")
    return m


def _check_unique_cc(axes: list, buttons: list, where: str) -> None:
    used: dict[int, str] = {}
    for m in axes + buttons:
        name = f"{m.input} ({m.label or m.mode})"
        if m.cc in used:
            raise ConfigError(f"{where}: CC {m.cc} lo usan a la vez {used[m.cc]} y {name}")
        used[m.cc] = name


def parse_config(data: dict) -> Config:
    _check_keys(data, {"midi", "general", "banks", "axis", "button", "bank"}, "config")
    cfg = Config()

    midi = data.get("midi", {})
    _check_keys(midi, {"port", "channel"}, "[midi]")
    cfg.port = _str(midi, "port", cfg.port, "[midi]")
    cfg.channel = _num(midi, "channel", 1, 1, 16, "[midi]", integer=True)

    gen = data.get("general", {})
    _check_keys(gen, {"rate_hz", "controller"}, "[general]")
    cfg.rate_hz = _num(gen, "rate_hz", 250, 30, 1000, "[general]")
    ctrl = gen.get("controller", "auto")
    if ctrl == "auto":
        cfg.controller = None
    else:
        cfg.controller = _num(gen, "controller", 0, 0, 3, "[general]", integer=True)

    banks = data.get("banks", {})
    _check_keys(banks, {"count", "next", "prev", "rumble"}, "[banks]")
    cfg.bank_count = _num(banks, "count", 1, 1, 16, "[banks]", integer=True)
    for attr in ("next", "prev"):
        v = banks.get(attr, "")
        val = None if v == "" else _choice(banks, attr, v, BUTTONS, "[banks]")
        setattr(cfg, f"bank_{attr}", val)
    cfg.rumble = _bool(banks, "rumble", True, "[banks]")
    if cfg.channel + cfg.bank_count - 1 > 16:
        raise ConfigError("[banks]: channel + count - 1 no puede pasar de 16 (cada banco usa un canal MIDI)")

    reserved = {cfg.bank_next, cfg.bank_prev} - {None}
    cfg.axes = [_parse_axis(t, f"[[axis]] #{n}") for n, t in enumerate(data.get("axis", []), 1)]
    cfg.buttons = [_parse_button(t, f"[[button]] #{n}", reserved)
                   for n, t in enumerate(data.get("button", []), 1)]
    _check_unique_cc(cfg.axes, cfg.buttons, "layout general")

    for n, bt in enumerate(data.get("bank", []), 1):
        w = f"[[bank]] #{n}"
        _check_keys(bt, {"number", "axis", "button"}, w)
        num = _num(bt, "number", 0, 1, cfg.bank_count, w, integer=True)
        if num - 1 in cfg.overrides:
            raise ConfigError(f"{w}: el banco {num} ya está definido en otro [[bank]]")
        wb = f"banco {num}"
        ov_axes = [_parse_axis(t, f"{wb} [[bank.axis]] #{i}") for i, t in enumerate(bt.get("axis", []), 1)]
        ov_buttons = [_parse_button(t, f"{wb} [[bank.button]] #{i}", reserved)
                      for i, t in enumerate(bt.get("button", []), 1)]
        cfg.overrides[num - 1] = (ov_axes, ov_buttons)
        _check_unique_cc(*cfg.layout(num - 1), wb)

    return cfg


def load_config(path: str | Path) -> Config:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"No encuentro el archivo de configuración: {path}")
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Error de sintaxis en {path}: {e}")
    return parse_config(data)


# ---------------------------------------------------------------- engine

def apply_deadzone(x: float, dz: float) -> float:
    a = abs(x)
    if a <= dz:
        return 0.0
    return math.copysign(min((a - dz) / (1.0 - dz), 1.0), x)


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


class Engine:
    """Convierte estados del mando en eventos MIDI CC.

    - Cada banco usa su propio canal MIDI (channel + banco), así el mismo
      control mapea a cosas distintas en Ableton según el banco.
    - El primer valor de cada control se registra sin enviarse, para no
      mover parámetros de Ableton al arrancar o al cambiar de banco.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.bank = 0
        self.bank_changed = False
        self._prev_buttons: frozenset = frozenset()
        self._smooth: dict = {}
        self._accum: dict = {}
        self._toggle: dict = {}
        self._sent: dict = {}

    @property
    def channel(self) -> int:
        return self.cfg.channel + self.bank

    def _axis_value(self, key, m: AxisMap, raw: float, dt: float) -> float:
        x = apply_deadzone(raw, m.deadzone)
        x = math.copysign(abs(x) ** m.curve, x)

        if m.mode == "relative":
            rate = -x if m.invert else x
            acc = _clamp01(self._accum.get(key, m.start) + rate * m.speed * dt)
            self._accum[key] = acc
            return acc

        if m.mode == "absolute":
            v = x if m.input in TRIGGER_AXES else (x + 1.0) / 2.0
        elif m.mode == "positive":
            v = max(x, 0.0)
        else:  # negative
            v = max(-x, 0.0)
        if m.invert:
            v = 1.0 - v

        if m.smoothing > 0.0:
            s = self._smooth.get(key, v)
            s += (v - s) * (1.0 - math.exp(-dt / m.smoothing))
            self._smooth[key] = s
            v = s
        return v

    def update(self, pad: PadState, dt: float, learn: bool = False) -> list[MidiEvent]:
        cfg = self.cfg
        self.bank_changed = False
        pressed = pad.buttons - self._prev_buttons
        self._prev_buttons = pad.buttons

        if cfg.bank_count > 1:
            if cfg.bank_next in pressed:
                self.bank = (self.bank + 1) % cfg.bank_count
                self.bank_changed = True
            if cfg.bank_prev in pressed:
                self.bank = (self.bank - 1) % cfg.bank_count
                self.bank_changed = True

        b = self.bank
        ch = self.channel
        axes, buttons = cfg.layout(b)
        candidates = []  # (key, value, delta, event)

        for i, m in enumerate(axes):
            key = (b, "a", i)
            v = self._axis_value(key, m, pad.axes.get(m.input, 0.0), dt)
            val = round(m.min + v * (m.max - m.min))
            self._offer(candidates, key, val, MidiEvent(ch, m.cc, val, m.label or f"{m.input} {m.mode}"))

        for i, m in enumerate(buttons):
            key = (b, "b", i)
            if m.mode == "toggle":
                if m.input in pressed:
                    self._toggle[key] = not self._toggle.get(key, False)
                on = self._toggle.get(key, False)
            else:
                on = m.input in pad.buttons
            val = m.on if on else m.off
            self._offer(candidates, key, val, MidiEvent(ch, m.cc, val, m.label or f"{m.input} {m.mode}"))

        if learn and candidates:
            # Modo aprendizaje: solo el control que más se ha movido, para que
            # el MIDI Map de Ableton no pille el eje equivocado.
            candidates = [max(candidates, key=lambda c: c[2])]

        for key, val, _, _ in candidates:
            self._sent[key] = val
        return [c[3] for c in candidates]

    def _offer(self, candidates, key, val, event):
        prev = self._sent.get(key)
        if prev is None:
            self._sent[key] = val  # primer valor: registrar sin enviar
        elif prev != val:
            candidates.append((key, val, abs(val - prev), event))
