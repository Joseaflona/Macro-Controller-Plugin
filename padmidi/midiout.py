"""Salida MIDI usando la API winmm de Windows (sin dependencias)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

_winmm = ctypes.WinDLL("winmm")


class MIDIOUTCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * 32),
        ("wTechnology", wintypes.WORD),
        ("wVoices", wintypes.WORD),
        ("wNotes", wintypes.WORD),
        ("wChannelMask", wintypes.WORD),
        ("dwSupport", wintypes.DWORD),
    ]


_winmm.midiOutGetNumDevs.restype = wintypes.UINT
_winmm.midiOutGetDevCapsW.argtypes = [ctypes.c_size_t, ctypes.POINTER(MIDIOUTCAPSW), wintypes.UINT]
_winmm.midiOutGetDevCapsW.restype = wintypes.UINT
_winmm.midiOutOpen.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.UINT,
                               ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
_winmm.midiOutOpen.restype = wintypes.UINT
_winmm.midiOutShortMsg.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_winmm.midiOutShortMsg.restype = wintypes.UINT
_winmm.midiOutReset.argtypes = [wintypes.HANDLE]
_winmm.midiOutClose.argtypes = [wintypes.HANDLE]
_winmm.midiOutGetErrorTextW.argtypes = [wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
_winmm.timeBeginPeriod.argtypes = [wintypes.UINT]
_winmm.timeEndPeriod.argtypes = [wintypes.UINT]


def _err(code: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _winmm.midiOutGetErrorTextW(code, buf, 256)
    return buf.value or f"error {code}"


def list_ports() -> list[str]:
    names = []
    for i in range(_winmm.midiOutGetNumDevs()):
        caps = MIDIOUTCAPSW()
        if _winmm.midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            names.append(caps.szPname)
    return names


def high_res_timer(enable: bool) -> None:
    """Sube la resolución del temporizador de Windows a 1 ms (para sleep preciso)."""
    (_winmm.timeBeginPeriod if enable else _winmm.timeEndPeriod)(1)


class MidiOut:
    def __init__(self, port_query: str):
        ports = list_ports()
        matches = [i for i, n in enumerate(ports) if port_query.lower() in n.lower()]
        if not matches:
            listing = "\n".join(f"  - {n}" for n in ports) or "  (ninguno)"
            raise RuntimeError(
                f"No hay ningún puerto MIDI que contenga '{port_query}'.\n"
                f"Puertos disponibles:\n{listing}\n"
                "Crea un puerto virtual con loopMIDI y pon su nombre en config.toml."
            )
        self.index = matches[0]
        self.name = ports[self.index]
        self._h = wintypes.HANDLE()
        rc = _winmm.midiOutOpen(ctypes.byref(self._h), self.index, 0, 0, 0)
        if rc != 0:
            raise RuntimeError(f"No se pudo abrir '{self.name}': {_err(rc)}")

    def cc(self, channel: int, cc: int, value: int) -> None:
        status = 0xB0 | ((channel - 1) & 0x0F)
        _winmm.midiOutShortMsg(self._h, status | (cc & 0x7F) << 8 | (value & 0x7F) << 16)

    def close(self) -> None:
        if self._h:
            _winmm.midiOutReset(self._h)
            _winmm.midiOutClose(self._h)
            self._h = wintypes.HANDLE()
