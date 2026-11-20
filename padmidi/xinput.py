"""Lectura del mando de Xbox vía XInput (Windows) con ctypes."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from .engine import PadState


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


class XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", wintypes.WORD), ("wRightMotorSpeed", wintypes.WORD)]


BUTTON_MASKS = {
    "UP": 0x0001, "DOWN": 0x0002, "LEFT": 0x0004, "RIGHT": 0x0008,
    "START": 0x0010, "BACK": 0x0020, "LS": 0x0040, "RS": 0x0080,
    "LB": 0x0100, "RB": 0x0200,
    "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000,
}

ERROR_SUCCESS = 0


def _load_dll():
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return ctypes.WinDLL(name)
        except OSError:
            continue
    raise RuntimeError("No se pudo cargar XInput (xinput1_4.dll)")


_dll = _load_dll()
_dll.XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
_dll.XInputGetState.restype = wintypes.DWORD
_dll.XInputSetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_VIBRATION)]
_dll.XInputSetState.restype = wintypes.DWORD


def _thumb(v: int) -> float:
    return v / 32767.0 if v >= 0 else v / 32768.0


class XInputPad:
    def __init__(self, index: int | None = None):
        self.fixed_index = index
        self.index = index
        self._state = XINPUT_STATE()

    def _try(self, i: int) -> bool:
        return _dll.XInputGetState(i, ctypes.byref(self._state)) == ERROR_SUCCESS

    def read(self) -> PadState | None:
        """Devuelve el estado o None si no hay mando conectado."""
        if self.index is not None and self._try(self.index):
            return self._to_state()
        if self.fixed_index is None:
            for i in range(4):
                if self._try(i):
                    self.index = i
                    return self._to_state()
        return None

    def _to_state(self) -> PadState:
        g = self._state.Gamepad
        axes = {
            "LX": _thumb(g.sThumbLX), "LY": _thumb(g.sThumbLY),
            "RX": _thumb(g.sThumbRX), "RY": _thumb(g.sThumbRY),
            "LT": g.bLeftTrigger / 255.0, "RT": g.bRightTrigger / 255.0,
        }
        buttons = frozenset(n for n, mask in BUTTON_MASKS.items() if g.wButtons & mask)
        return PadState(axes, buttons)

    def rumble(self, low: float, high: float) -> None:
        if self.index is None:
            return
        vib = XINPUT_VIBRATION(int(max(0.0, min(low, 1.0)) * 65535),
                               int(max(0.0, min(high, 1.0)) * 65535))
        _dll.XInputSetState(self.index, ctypes.byref(vib))
