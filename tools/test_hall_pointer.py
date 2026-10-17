"""Regression checks for widget/world input routing using the production methods."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parent.parent/'runtime/hero_stage.py'
METHODS = {'handle_menu_key_impl', 'handle_hall_mouse_key', 'stop_hall_drag',
           'poll_hall_drag', 'update_hall_drag', 'rotate_hall_view', 'handle_world_mouse',
           'sync_input_mode'}
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'HeroStage')
subset = ast.Module(body=[ast.ClassDef(name='Pointer', bases=[], keywords=[],
    body=[node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in METHODS],
    decorator_list=[])], type_ignores=[])
ast.fix_missing_locations(subset)


class PointerTests(unittest.TestCase):
    def setUp(self):
        self.position = [500, 400]
        self.callbacks = []
        self.cursor = NS(yaw=0., pitch=0., minPitch=-1.5, maxPitch=1.5,
                         mouseSensitivity=.003, invertVerticalMovement=False)
        self.player = NS(model=NS(yaw=.4, bh=NS(bh_yaw=.4, yaw_enable=True)))
        self.keys = NS(KEY_LEFTMOUSE=256, KEY_RIGHTMOUSE=257)
        self.bw = NS(getCursorPos=lambda: tuple(self.position),
                     callback=lambda delay, fn: self.callbacks.append(fn),
                     player=lambda: self.player, dcursor=lambda: self.cursor,
                     sendMouseMovementToScript=Mock())
        self.fsm = NS(active=True, _offline_original_world_mouse=Mock(return_value=False))
        namespace = {'BigWorld': self.bw, 'keys': self.keys,
                     'FsmGame': NS(init=lambda: self.fsm)}
        exec(compile(subset, str(SOURCE), 'exec'), namespace)
        self.stage = namespace['Pointer']()
        self.stage.menu_keys_down = set()
        self.stage.hall_mouse_buttons = set()
        self.stage.hall_drag_moved = False
        self.stage.hall_drag_position = None
        self.stage.hall_drag_generation = 0
        self.stage.hall_body_yaw = None
        self.stage.hall_world_input = lambda: True
        self.stage.runtime = NS(practice=None, settings=None)
        self.ui = NS(handleKeyEvent=Mock(return_value=False))
        self.gui = NS(handleKeyEvent=Mock(return_value=False))
        self.modules = patch.dict(sys.modules, {'C_ui': self.ui, 'GUI': self.gui})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def key(self, down, key=256):
        return self.stage.handle_menu_key_impl(down, key, int(down), 0)

    def test_widgets_receive_both_edges_and_never_start_world_drag(self):
        self.ui.handleKeyEvent.return_value = True
        self.assertTrue(self.key(True))
        self.position[0] += 2
        self.assertTrue(self.key(False))
        self.assertEqual([call.args[0] for call in self.ui.handleKeyEvent.call_args_list], [True, False])
        self.assertFalse(self.stage.hall_mouse_buttons)
        self.assertFalse(self.callbacks)
        self.assertEqual(self.cursor.yaw, 0.)

    def test_release_after_world_drag_still_reaches_native_ui(self):
        self.key(True)
        self.position[0] += 100
        self.callbacks.pop(0)()
        self.assertTrue(self.stage.hall_drag_moved)
        self.assertTrue(self.key(False))
        self.assertEqual([call.args[0] for call in self.ui.handleKeyEvent.call_args_list], [True, False])
        self.assertFalse(self.stage.hall_mouse_buttons)
        self.assertAlmostEqual(self.cursor.yaw, .3)
        self.assertAlmostEqual(self.player.model.bh.bh_yaw, .4)
        self.assertFalse(self.player.model.bh.yaw_enable)
        self.bw.sendMouseMovementToScript.assert_not_called()

    def test_simple_click_has_no_camera_or_body_effect(self):
        self.key(True)
        self.key(False)
        self.assertEqual(self.cursor.yaw, 0.)
        self.assertEqual(self.player.model.bh.bh_yaw, .4)

    def test_short_drag_applies_final_position_even_before_first_callback(self):
        self.key(True)
        self.position[0] += 80
        self.key(False)
        self.assertAlmostEqual(self.cursor.yaw, .24)
        for callback in self.callbacks[:]:
            callback()
        self.assertAlmostEqual(self.cursor.yaw, .24)

    def test_right_drag_aligns_body_without_changing_cursor_capture(self):
        self.key(True, 257)
        self.position[0] += 120
        self.key(False, 257)
        self.assertAlmostEqual(self.cursor.yaw, self.player.model.bh.bh_yaw)
        self.bw.sendMouseMovementToScript.assert_not_called()

    def test_cancelled_drag_callback_cannot_restart_or_move_camera(self):
        self.key(True)
        self.stage.stop_hall_drag()
        self.position[0] += 100
        self.callbacks.pop(0)()
        self.assertEqual(self.cursor.yaw, 0.)
        self.assertFalse(self.callbacks)

    def test_widget_click_after_drag_is_not_swallowed(self):
        self.key(True)
        self.position[0] += 100
        self.key(False)
        self.ui.handleKeyEvent.reset_mock()
        self.ui.handleKeyEvent.return_value = True
        self.key(True)
        self.key(False)
        self.assertEqual(self.ui.handleKeyEvent.call_count, 2)
        self.assertFalse(self.stage.hall_mouse_buttons)

    def test_hero_page_remains_in_ui_mode_after_native_settings_close(self):
        self.stage.visible = True
        self.stage.hall = NS(chat_open=False)
        self.stage.runtime.bag = None
        fsm_module = self.stage.sync_input_mode.__globals__['FsmGame']
        fsm_module.MOD_NOML, fsm_module.MOD_CITY, fsm_module.MOD_HERO = 0, 2, 1
        fsm_module.set_hero_only_move = Mock()
        self.ui.get_cursor_pos = lambda: (-20000, -20000)
        self.ui.cursor_pos = Mock()
        self.fsm.mode = 1
        self.stage.sync_input_mode()
        self.assertEqual(self.fsm.mode, 0)
        self.assertTrue(self.stage.cursor_shown)
        self.ui.cursor_pos.assert_called_once_with(500, 400)


class SettingsPointerTests(unittest.TestCase):
    def setUp(self):
        source = SOURCE.with_name('offline_settings.py')
        original = next(node for node in ast.parse(source.read_text(encoding='utf8')).body
                        if isinstance(node, ast.ClassDef) and node.name == 'LocalSettings')
        methods = [node for node in original.body if isinstance(node, ast.FunctionDef)
                   and node.name in ('set_visible', 'restore_page_input')]
        tree = ast.Module(body=[ast.ClassDef(name='Settings', bases=[], keywords=[],
            body=methods, decorator_list=[])], type_ignores=[])
        ast.fix_missing_locations(tree)
        self.callbacks = []
        namespace = {'BigWorld': NS(getCursorPos=lambda: (1037, 824),
            callback=lambda delay, fn: self.callbacks.append(fn))}
        exec(compile(tree, str(source), 'exec'), namespace)
        self.owner = namespace['Settings']()
        self.stage = NS(closed=False, cursor_shown=True, sync_input_mode=Mock())
        self.owner.runtime = NS(hall=NS(hero_page=self.stage))
        self.owner.original_set_visible = Mock()
        self.ui = NS(cursor_pos=Mock(), set_cursor_pos=Mock())
        self.modules = patch.dict(sys.modules, {'C_ui': self.ui})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_close_restores_page_policy_after_native_handler_and_preserves_pointer(self):
        self.owner.set_visible(False)
        self.owner.original_set_visible.assert_called_once_with(False)
        self.stage.sync_input_mode.assert_not_called()
        self.callbacks.pop()()
        self.stage.sync_input_mode.assert_called_once()
        self.ui.cursor_pos.assert_called_once_with(1037, 824)
        self.ui.set_cursor_pos.assert_called_once_with(1037, 824)

    def test_close_in_training_keeps_cursor_hidden(self):
        self.stage.cursor_shown = False
        self.owner.set_visible(False)
        self.callbacks.pop()()
        self.stage.sync_input_mode.assert_called_once()
        self.ui.set_cursor_pos.assert_not_called()


if __name__ == '__main__':
    unittest.main()
