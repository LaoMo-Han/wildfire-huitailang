"""Exercise the cooldown policy through the native clock adapter."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parent.parent/'runtime/offline_practice.py'
tree = ast.parse(SOURCE.read_text(encoding='utf8'))
original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'LocalPractice')
methods = {'cooldowns_disabled', 'enable_cooldowns', 'toggle_no_cooldown',
           'update_cooldown_button', 'install_skill_hook'}
subset = ast.Module(body=[ast.ClassDef(name='Practice', bases=[], keywords=[],
    body=[node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in methods],
    decorator_list=[])], type_ignores=[])
ast.fix_missing_locations(subset)


class CooldownTests(unittest.TestCase):
    def setUp(self):
        self.offline = True
        self.player = NS(test_do_cd_check=True)
        self.manager = NS(init_hero=Mock(), dict_base_cd={31:10}, dict_now_cd={31:(42,10)})
        self.clock = Mock()
        self.cd = NS(instance=lambda:self.manager, update=self.clock, reset=Mock())
        self.hud = NS(update_cd=Mock())
        self.modules = patch.dict(sys.modules, {'captain':NS(cdmgr=self.cd),
            'guis.battle.PracticeSpPart':NS(SpaceBox=type('Box', (), {'on_sensor_click':Mock()}))})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        namespace = {'BigWorld':NS(player=lambda:self.player),
            'FsmGame':NS(state_is_offline=lambda:self.offline),
            'guiManager':NS(get_ui=lambda name:self.hud)}
        exec(compile(subset, str(SOURCE), 'exec'), namespace)
        self.practice = namespace['Practice']()
        self.practice.active = False
        self.practice.loading = False
        self.practice.no_cooldown = False
        self.practice.cooldown_button = NS(text=None)
        self.practice.runtime = NS(write_status=Mock())
        self.practice.install_skill_hook()

    def test_hall_skills_record_ready_time_in_native_clock(self):
        self.cd.update(31, 10, -1)
        self.clock.assert_called_once_with(31, 10, 0)

    def test_normal_practice_preserves_native_cooldown(self):
        self.practice.active = True
        self.cd.update(31, 10, -1)
        self.clock.assert_called_once_with(31, 10, -1)

    def test_toggle_clears_current_cooldowns_and_keeps_hud_and_policy_together(self):
        self.practice.active = True
        self.practice.toggle_no_cooldown()
        self.assertTrue(self.practice.no_cooldown)
        self.assertFalse(self.player.test_do_cd_check)
        self.cd.reset.assert_called_once()
        self.hud.update_cd.assert_called_once()
        self.cd.update(31, 10, -1)
        self.clock.assert_called_once_with(31, 10, 0)
        self.assertEqual(self.practice.cooldown_button.text.decode('gbk'), '无CD：开 F7')
        self.practice.toggle_no_cooldown()
        self.assertTrue(self.player.test_do_cd_check)
        self.assertEqual(self.practice.cooldown_button.text.decode('gbk'), '无CD：关 F7')

    def test_policy_survives_reinitialization_for_hero_or_map_change(self):
        self.practice.active = True
        self.practice.no_cooldown = True
        self.practice.enable_cooldowns()
        self.assertFalse(self.player.test_do_cd_check)
        self.practice.active = False
        self.practice.no_cooldown = False
        self.practice.enable_cooldowns()
        self.assertFalse(self.player.test_do_cd_check)

    def test_no_cooldown_never_changes_online_clock(self):
        self.offline = False
        self.practice.no_cooldown = True
        self.cd.update(31, 10, -1)
        self.clock.assert_called_once_with(31, 10, -1)

    def test_toggle_is_ignored_in_hall_or_during_map_loading(self):
        self.practice.toggle_no_cooldown()
        self.practice.active = True
        self.practice.loading = True
        self.practice.toggle_no_cooldown()
        self.assertFalse(self.practice.no_cooldown)
        self.cd.reset.assert_not_called()


if __name__ == '__main__':
    unittest.main()
