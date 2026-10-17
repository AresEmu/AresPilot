import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from app.core.upgrade_menu import UpgradeRow
from app.core.upgrader import UpgradeAdvisor


def row(label='Army Camp x4', cost=10000000, resource='elixir'):
    return UpgradeRow(label, 'other', cost, resource, True, (580, 169), 169)


class UpgradeReadTests(unittest.TestCase):
    def setUp(self):
        self.advisor = UpgradeAdvisor(Mock(), Mock(), Mock(), Mock(), Mock())

    def test_resource_disagreement_is_not_corroboration(self):
        self.advisor._prev_scan_rows = [row(resource='gold')]
        self.assertEqual(self.advisor._corroborate_rows([row()]), [])

    def test_magic_button_does_not_beat_resource_upgrade(self):
        frame = np.zeros((731,1299,3), dtype=np.uint8)
        frame[550:630,655:750] = (255,150,0)
        normal = SimpleNamespace(text='Upgrade',left=565,top=606,width=66,height=14)
        magic = SimpleNamespace(text='Upgrade',left=669,top=610,width=66,height=14)
        self.advisor.vision.find_words_ocr.return_value = [normal,magic]
        self.assertEqual(self.advisor._find_upgrade_word(frame), (598,613))

    def test_bottom_bar_red_art_is_not_the_price(self):
        frame = np.zeros((731,1299,3),dtype=np.uint8)
        word = SimpleNamespace(text='Upgrade',left=565,top=606,width=66,height=14)
        self.advisor.vision.find_words_ocr.return_value=[word]
        frame[620:650,550:650]=(0,0,255)
        self.assertEqual(self.advisor._find_upgrade_word(frame),(598,613))
        frame[540:578,555:630]=(0,0,255)
        self.assertIsNone(self.advisor._find_upgrade_word(frame))

    def test_crafting_requires_exact_currency_and_price(self):
        frame=np.zeros((731,1299,3),dtype=np.uint8)
        frame[405:472,1007:1150]=(0,200,120)
        frame[436:458,1120:1146]=(200,0,200)
        footer=SimpleNamespace(text='Crafting')
        confirm=SimpleNamespace(text='Confirm',left=1040,top=414,width=76,height=18)
        price=SimpleNamespace(text='4000000')
        for cost,resource,expected in [(4000000,'elixir',(1078,423)),(3000000,'elixir',None),(4000000,'gold',None)]:
            self.advisor.vision.find_words_ocr.side_effect=[[footer],[confirm],[price]]
            self.assertEqual(self.advisor._find_crafting_confirm(frame,row(cost=cost,resource=resource)),expected)

    @patch('app.core.upgrader.parse_builder_menu')
    def test_nearby_same_price_other_building_is_not_confirmation(self, parse):
        parse.return_value = [row('Inferno Tower x3')]
        self.advisor.config.scale_scalar.return_value = 30
        point, _ = self.advisor._find_pick_row_once(row(), 'other', near_y=169)
        self.assertIsNone(point)

    # The old 16:9 builder-popup read (test_complete_cost_and_red_veto) is gone with
    # the October 2026 UI — the Build panel is covered by tests/test_build_panel_ui2026.py.


if __name__ == '__main__':
    unittest.main()
