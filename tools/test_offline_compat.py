"""Headless regression cases for the legacy engine compatibility boundary.

These exercise entity ownership, input routing, control state and distinct
equipment/talent callbacks. They do not substitute for a real game smoke test.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parent.parent/'runtime/offline_compat.py'
spec = importlib.util.spec_from_file_location('offline_compat_under_test', SOURCE)
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        events = self.events = []

        class Hero:
            def set_cash(entity, old):
                events.append(('cash', entity, old))

            def revert_evolution_item(entity, old, new, cash):
                events.append(('base_revert', old, new, cash))
                return 'base-reverted'

        class PlayerHero(Hero):
            def handle_special_event(entity, down, key, mods):
                events.append(('original_input', down, key, mods))
                return 'original-input-result'

            def allow_tp(entity):
                events.append(('original_tp', entity))
                return entity.original_allowed

            def revert_evolution_item(entity, old, new, cash):
                events.append(('equipment_revert', old, new, cash))
                return 'equipment-reverted'

        self.Hero, self.PlayerHero = Hero, PlayerHero
        self.player = PlayerHero()
        self.player.original_allowed = True
        self.player.debuff = types.SimpleNamespace(can_attack=Mock(return_value=True))
        self.hacker = types.SimpleNamespace(get_enable=Mock(return_value=True),
                                           handle_key_event=Mock(return_value=False))
        self.talent = types.SimpleNamespace(talent_data={(1, 6):[1001, 1002]},
            use_talent_list=[1001], _update_popup_ui=Mock(), _update_tool_bar=Mock())
        self.full = types.SimpleNamespace(talent_cell_map={1001:object()}, _update_talent=Mock())
        self.bar = types.SimpleNamespace(update_revertable_id=Mock())
        panels={'talent_evolution':self.talent,'equip_evolution':self.full,'equip_evolution_v2':self.bar}
        self.gui=types.SimpleNamespace(get_ui=Mock(side_effect=panels.__getitem__))
        mods={
            'BigWorld':types.SimpleNamespace(player=lambda:self.player,time=lambda:123.5),
            'Hero':types.SimpleNamespace(Hero=Hero,PlayerHero=PlayerHero),
            'tutorial':types.SimpleNamespace(TutorialFlowPlayer=types.SimpleNamespace(key_hacker=lambda:self.hacker)),
            'common_data':types.SimpleNamespace(equip_evolution_data=types.SimpleNamespace(
                data={1001:{'typ':1,'stype':6},81005:{'typ':1,'stype':1}})),
            'guis':types.SimpleNamespace(guiManager=self.gui),
            'guis.battle.TalentEvolutionPanel':types.SimpleNamespace(TALENT_KEYS=((1,6),(1,11),(1,16))),
        }
        self.modules=patch.dict(sys.modules, mods)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.runtime=types.SimpleNamespace(practice=types.SimpleNamespace(active=True),log=Mock())
        self.controller=compat.install(self.runtime)

    def test_npc_cash_never_notifies_player_hud(self):
        self.Hero().set_cash(800)
        self.assertEqual(self.events, [])

    def test_player_cash_preserves_old_value_for_observers(self):
        self.player.set_cash(90000)
        self.assertEqual(self.events, [('cash',self.player,90000)])

    def test_reinstall_does_not_stack_cash_or_input_callbacks(self):
        compat.install(self.runtime)
        self.player.set_cash(123)
        self.player.handle_special_event(True,17,2)
        self.assertEqual(self.events, [('cash',self.player,123)])
        self.hacker.handle_key_event.assert_called_once_with(True,17,0,2)

    def test_tutorial_receives_key_and_modifiers_without_claiming_input(self):
        self.assertIs(self.player.handle_special_event(False,19,3),False)
        self.hacker.handle_key_event.assert_called_once_with(False,19,0,3)

    def test_disabled_tutorial_does_not_swallow_controls(self):
        self.hacker.get_enable.return_value=False
        self.assertIs(self.player.handle_special_event(True,19,0),False)
        self.hacker.handle_key_event.assert_not_called()

    def test_hall_keeps_original_input_contract(self):
        self.runtime.practice.active=False
        self.assertEqual(self.player.handle_special_event(True,19,0),'original-input-result')
        self.hacker.get_enable.assert_not_called()

    def test_stun_blocks_otherwise_allowed_teleport(self):
        self.player.debuff.can_attack.return_value=False
        self.assertIs(self.player.allow_tp(),False)

    def test_free_player_preserves_allowed_teleport(self):
        self.assertIs(self.player.allow_tp(),True)

    def test_original_teleport_rejection_and_none_are_preserved(self):
        for value in (False,None):
            self.player.original_allowed=value
            self.assertIs(self.player.allow_tp(),value)
        self.player.debuff.can_attack.assert_not_called()

    def test_hall_does_not_evaluate_combat_debuffs(self):
        self.runtime.practice.active=False
        self.player.debuff.can_attack.return_value=False
        self.assertIs(self.player.allow_tp(),True)
        self.player.debuff.can_attack.assert_not_called()

    def test_equipment_rollback_keeps_original_route(self):
        result=self.player.revert_evolution_item(81005,0,True)
        self.assertEqual(result,'equipment-reverted')
        self.assertEqual(self.events,[('equipment_revert',81005,0,True)])
        self.gui.get_ui.assert_not_called()

    def test_talent_rollback_updates_base_and_both_views(self):
        result=self.player.revert_evolution_item(1001,0,True)
        self.assertEqual(result,'base-reverted')
        self.assertEqual(self.events,[('base_revert',1001,0,True)])
        self.assertEqual(self.talent.use_talent_list,[])
        self.talent._update_popup_ui.assert_called_once_with()
        self.talent._update_tool_bar.assert_called_once_with()
        self.full._update_talent.assert_called_once_with()
        self.bar.update_revertable_id.assert_called_once_with(-1)
        self.assertEqual(self.talent.last_revert_talent_time,123.5)

    def test_repeated_talent_view_refresh_is_idempotent(self):
        self.controller.refresh_talent_revert(1001)
        self.controller.refresh_talent_revert(1001)
        self.assertEqual(self.talent.use_talent_list,[])

    def test_old_cells_and_old_toolbar_need_no_newer_api(self):
        del self.bar.update_revertable_id
        self.controller.refresh_talent_revert(1001)
        self.full._update_talent.assert_called_once_with()

    def test_newer_cancel_timer_is_refreshed_when_available(self):
        cell=types.SimpleNamespace(on_talent_reverted=Mock())
        self.full.talent_cell_map[1001]=cell
        self.controller.refresh_talent_revert(1001)
        cell.on_talent_reverted.assert_called_once_with()

    def test_no_talent_or_unknown_id_is_sent_to_talent_views(self):
        self.assertEqual(self.player.revert_evolution_item(-1,0,False),'equipment-reverted')
        self.gui.get_ui.assert_not_called()

    def test_hall_talent_events_keep_original_route(self):
        self.runtime.practice.active=False
        self.assertEqual(self.player.revert_evolution_item(1001,0,False),'equipment-reverted')
        self.gui.get_ui.assert_not_called()

    def test_startup_before_practice_exists_uses_original_routes(self):
        self.runtime.practice=None
        self.assertEqual(self.player.handle_special_event(True,1,0),'original-input-result')


if __name__=='__main__':
    unittest.main(verbosity=2)
