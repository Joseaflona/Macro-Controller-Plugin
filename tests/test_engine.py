import unittest

from padmidi.engine import AxisMap, ButtonMap, Config, ConfigError, Engine, PadState, parse_config


def pad(buttons=(), **axes):
    return PadState(axes, frozenset(buttons))


def cfg(axes=(), buttons=(), **kw):
    return Config(axes=list(axes), buttons=list(buttons), **kw)


class EngineTests(unittest.TestCase):
    def test_first_value_is_primed_not_sent(self):
        e = Engine(cfg([AxisMap("LY", 20, mode="absolute", deadzone=0)]))
        self.assertEqual(e.update(pad(LY=0.0), 0.01), [])
        ev = e.update(pad(LY=1.0), 0.01)
        self.assertEqual([(x.cc, x.value) for x in ev], [(20, 127)])

    def test_positive_negative_split(self):
        e = Engine(cfg([AxisMap("LY", 20, mode="positive", deadzone=0),
                        AxisMap("LY", 21, mode="negative", deadzone=0)]))
        e.update(pad(LY=0.0), 0.01)
        ev = e.update(pad(LY=-1.0), 0.01)
        self.assertEqual([(x.cc, x.value) for x in ev], [(21, 127)])

    def test_deadzone_blocks_noise(self):
        e = Engine(cfg([AxisMap("LX", 20, mode="positive", deadzone=0.2)]))
        e.update(pad(LX=0.0), 0.01)
        self.assertEqual(e.update(pad(LX=0.15), 0.01), [])

    def test_relative_accumulates_and_holds(self):
        e = Engine(cfg([AxisMap("RX", 24, mode="relative", deadzone=0, speed=1.0)]))
        e.update(pad(RX=0.0), 0.01)
        for _ in range(50):
            e.update(pad(RX=1.0), 0.01)       # 0.5 s a tope -> ~mitad
        ev = e.update(pad(RX=0.0), 0.01)       # soltar: se queda
        self.assertEqual(ev, [])
        self.assertAlmostEqual(e._sent[(0, "a", 0)], 64, delta=1)

    def test_toggle_button(self):
        e = Engine(cfg(buttons=[ButtonMap("X", 104, mode="toggle")]))
        e.update(pad(), 0.01)
        self.assertEqual(e.update(pad(["X"]), 0.01)[0].value, 127)
        self.assertEqual(e.update(pad(), 0.01), [])
        self.assertEqual(e.update(pad(["X"]), 0.01)[0].value, 0)

    def test_bank_switch_changes_channel(self):
        e = Engine(cfg(buttons=[ButtonMap("A", 102)], bank_count=3, bank_next="RB", bank_prev="LB"))
        e.update(pad(), 0.01)
        e.update(pad(["RB"]), 0.01)
        self.assertTrue(e.bank_changed)
        e.update(pad(), 0.01)                  # registra banco 2
        ev = e.update(pad(["A"]), 0.01)
        self.assertEqual((ev[0].channel, ev[0].cc), (2, 102))
        e.update(pad(["LB"]), 0.01)
        e.update(pad(["LB"]), 0.01)
        self.assertEqual(e.bank, 0)

    def test_learn_sends_only_dominant(self):
        e = Engine(cfg([AxisMap("LX", 22, mode="positive", deadzone=0),
                        AxisMap("LY", 20, mode="positive", deadzone=0)]))
        e.update(pad(LX=0.0, LY=0.0), 0.01)
        ev = e.update(pad(LX=0.1, LY=0.9), 0.01, learn=True)
        self.assertEqual([x.cc for x in ev], [20])


class ConfigTests(unittest.TestCase):
    def test_duplicate_cc_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"axis": [{"input": "LX", "cc": 20}], "button": [{"input": "A", "cc": 20}]})

    def test_bank_button_reserved(self):
        with self.assertRaises(ConfigError):
            parse_config({"banks": {"count": 2, "next": "RB"}, "button": [{"input": "RB", "cc": 1}]})

    def test_typo_key_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"axis": [{"input": "LX", "cc": 20, "dedzone": 0.1}]})

    def test_shipped_config_loads(self):
        from pathlib import Path
        from padmidi.engine import load_config
        c = load_config(Path(__file__).resolve().parent.parent / "config.toml")
        self.assertEqual(c.bank_count, 4)


if __name__ == "__main__":
    unittest.main()
