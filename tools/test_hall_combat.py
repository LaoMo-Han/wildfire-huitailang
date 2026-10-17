"""Hall Tab combat, chat hints and source-copy placement checks."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT/'runtime/hero_stage.py'
PRACTICE = ROOT/'runtime/offline_practice.py'


def functions(source, names):
    return [node for node in ast.parse(source.read_text(encoding='utf-8')).body
            if isinstance(node, ast.FunctionDef) and node.name in names]


def stage_class(methods):
    tree = ast.parse(STAGE.read_text(encoding='utf-8'))
    original = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == 'HeroStage')
    body = [node for node in original.body
            if isinstance(node, (ast.FunctionDef, ast.Assign))]
    body = [node for node in body
            if not isinstance(node, ast.FunctionDef) or node.name in methods]
    return ast.Module(body=[ast.ClassDef(name='Stage', bases=[], keywords=[], body=body,
                                         decorator_list=[])], type_ignores=[])


class CloneGeometryTests(unittest.TestCase):
    def setUp(self):
        subset = ast.Module(body=functions(STAGE, {'source_clone_offset'}), type_ignores=[])
        ast.fix_missing_locations(subset)
        namespace = {'math': __import__('math')}
        exec(compile(subset, str(STAGE), 'exec'), namespace)
        self.offset = namespace['source_clone_offset']

    def test_first_eight_copies_surround_the_character_without_overlap(self):
        points = [self.offset(0.0, index) for index in range(8)]
        radii = [round((x*x+z*z) ** .5, 6) for x, z in points]
        self.assertEqual(len(set(radii)), 1)
        self.assertAlmostEqual(radii[0], 1.15, places=6)
        for first in range(len(points)):
            for second in range(first+1, len(points)):
                gap = ((points[first][0]-points[second][0]) ** 2
                       +(points[first][1]-points[second][1]) ** 2) ** .5
                self.assertGreater(gap, .5)

    def test_ninth_copy_starts_an_outer_ring(self):
        inner = self.offset(0.0, 0)
        outer = self.offset(0.0, 8)
        self.assertIsNot(inner, outer)
        self.assertAlmostEqual((outer[0] ** 2+outer[1] ** 2) ** .5, 1.8, places=6)

    def test_ring_follows_character_facing(self):
        forward = self.offset(0.0, 0)
        turned = self.offset(1.5707963267948966, 0)
        self.assertAlmostEqual(forward[1], 1.15, places=6)
        self.assertAlmostEqual(turned[0], 1.15, places=6)


class HintTests(unittest.TestCase):
    def setUp(self):
        methods = {'hint_lines', 'hint_coord', 'set_hint_layout'}
        subset = stage_class(methods)
        ast.fix_missing_locations(subset)
        self.namespace = {'math': __import__('math')}
        exec(compile(subset, str(STAGE), 'exec'), self.namespace)
        self.stage = self.namespace['Stage']()
        self.stage.hall = NS(chat_open=False)
        self.stage.runtime = NS(practice=None)
        self.stage.source_clones = []
        self.stage.CLONE_LIMIT = 12
        self.stage.hall_combat = False

    def test_peacetime_hints_explain_the_hall_keys(self):
        lines = self.stage.hint_lines()
        self.assertIn(u'Tab', lines[0])
        self.assertIn(u'\u975e\u6218\u6597', lines[0])
        text = u''.join(lines)
        for key in (u'\u56de\u8f66', u'Z', u'X', u'C', u'V', u'B', u'H', u'Esc', u'\u6e90\u529b\u5851\u5f62'):
            self.assertIn(key, text)

    def test_hidden_ui_key_is_documented_as_h(self):
        self.assertIn(u'H \u9690\u85cf/\u663e\u793a\u5168\u90e8 UI', self.stage.hint_lines()[5])

    def test_combat_hints_switch_to_skill_help(self):
        self.stage.hall_combat = True
        lines = self.stage.hint_lines()
        self.assertIn(u'\u6218\u6597', lines[0])
        self.assertIn(u'\u6280\u80fd', u''.join(lines))
        self.assertIn(u'Tab', lines[0])

    def test_copy_counter_tracks_generated_bodies(self):
        self.stage.source_clones = [11, 12, 13]
        self.assertIn(u'3/12', self.stage.hint_lines()[-1])

    def test_chat_focus_replaces_the_counter_line(self):
        self.stage.hall.chat_open = True
        self.assertIn(u'\u804a\u5929', self.stage.hint_lines()[-1])

    def test_training_arena_owns_the_screen_so_hints_disappear(self):
        self.stage.runtime.practice = NS(active=True, loading=False)
        self.assertEqual(self.stage.hint_lines(), [])


class HintLayoutTests(unittest.TestCase):
    def setUp(self):
        source = ROOT/'runtime/offline_hall.py'
        original = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                        if isinstance(node, ast.ClassDef) and node.name == 'OfflineHall')
        body = [node for node in original.body
                if isinstance(node, ast.Assign)
                or isinstance(node, ast.FunctionDef)
                and node.name in ('hint_coord', 'set_hint_layout')]
        tree = ast.Module(body=[ast.ClassDef(name='Hall', bases=[], keywords=[], body=body,
                                             decorator_list=[])], type_ignores=[])
        ast.fix_missing_locations(tree)
        namespace = {}
        exec(compile(tree, str(source), 'exec'), namespace)
        self.hall = namespace['Hall']()
        self.hall.hint_labels = [NS(set_coord=Mock()) for _ in range(self.hall.HINT_ROWS)]

    def test_collapsed_hints_sit_above_the_chat_input(self):
        x, y = self.hall.hint_coord(0, False)
        self.assertEqual(x, self.hall.HINT_X)
        self.assertEqual(self.hall.hint_coord(self.hall.HINT_ROWS-1, False)[1], self.hall.HINT_BOTTOM)
        self.assertEqual(y, self.hall.HINT_BOTTOM-(self.hall.HINT_ROWS-1)*self.hall.HINT_STEP)

    def test_expanded_chat_moves_hints_right_of_the_native_log(self):
        self.hall.set_hint_layout(True)
        self.assertEqual(self.hall.hint_labels[0].set_coord.call_args.args[0], 540)
        self.assertEqual(self.hall.hint_labels[-1].set_coord.call_args.args[0], 540)
        collapsed = self.hall.hint_coord(0, False)
        self.hall.set_hint_layout(False)
        self.assertEqual(self.hall.hint_labels[0].set_coord.call_args.args, collapsed)


class SpawnTests(unittest.TestCase):
    def setUp(self):
        subset = ast.Module(body=functions(STAGE, {'source_clone_offset'})
                            + [stage_class({'spawn_source_clone', 'maintain_source_clones'}).body[0]],
                            type_ignores=[])
        ast.fix_missing_locations(subset)
        self.player = NS(hero_type=4, camp=1, position=NS(x=10., y=2., z=20.),
                         model=NS(yaw=0., bh=NS(bh_yaw=0.)))
        self.entity = NS(id=77, hp=10, mhp=100, camp=2,
                         model=NS(yaw=0., bh=NS(bh_yaw=0.)), set_hp=Mock())
        self.manager = NS(create_target=Mock(return_value=[self.entity]))
        self.bigworld = NS(player=lambda: self.player,
                           entity=lambda entity_id: self.entity if entity_id == 77 else None,
                           callback=lambda delay, fn: None)
        self.namespace = {'math': __import__('math'), 'BigWorld': self.bigworld}
        exec(compile(subset, str(STAGE), 'exec'), self.namespace)
        self.stage = self.namespace['Stage']()
        self.stage.source_clones = []
        self.stage.source_clone_serial = 0
        self.stage.CLONE_LIMIT = 12
        self.stage.errors = {}
        self.stage.log = Mock()
        self.stage.hall = NS(refresh_hints=Mock())
        self.stage.runtime = NS(fashions_for=lambda hero_type: [160204], write_status=Mock())
        modules = patch.dict(sys.modules, {'debug': NS(DebugManager=NS(instance=self.manager))})
        modules.start()
        self.addCleanup(modules.stop)

    def test_copy_uses_current_hero_fashion_and_stays_independent(self):
        entity_id = self.stage.spawn_source_clone()
        self.assertEqual(entity_id, 77)
        args = self.manager.create_target.call_args.args
        self.assertEqual(args[0], 1)
        self.assertEqual(args[1], 'PracticeAIHero')
        self.assertEqual(args[3], 4)
        self.assertEqual(args[5], [160204])
        self.assertEqual(args[4], (10.0, 2.02, 20.0+1.15))
        self.assertEqual(self.stage.source_clones, [77])
        self.assertEqual(self.entity.camp, 1)
        self.assertEqual(self.entity.model.yaw, self.player.model.yaw)
        self.stage.hall.refresh_hints.assert_called()
        self.stage.runtime.write_status.assert_called()

    def test_next_copy_gets_its_own_ring_slot(self):
        self.stage.spawn_source_clone()
        second = NS(id=78, hp=10, mhp=100, camp=2, model=NS(yaw=0., bh=NS(bh_yaw=0.)),
                    set_hp=Mock())
        self.bigworld.entity = lambda entity_id: (self.entity if entity_id == 77
                                                  else second if entity_id == 78 else None)
        self.manager.create_target.return_value = [second]
        self.stage.spawn_source_clone()
        first_pos = self.manager.create_target.call_args_list[0].args[4]
        second_pos = self.manager.create_target.call_args_list[1].args[4]
        self.assertNotEqual(first_pos, second_pos)
        self.assertEqual(self.stage.source_clones, [77, 78])

    def test_limit_blocks_new_copies(self):
        self.stage.source_clones = list(range(12))
        self.stage.maintain_source_clones = Mock()
        self.assertIsNone(self.stage.spawn_source_clone())
        self.manager.create_target.assert_not_called()

    def test_copies_survive_damage_and_prune_when_gone(self):
        self.stage.source_clones = [77]
        self.stage.maintain_source_clones()
        self.assertEqual(self.entity.hp, 100)
        self.entity.set_hp.assert_called_once_with(0)
        self.bigworld.entity = lambda entity_id: None
        self.stage.maintain_source_clones()
        self.assertEqual(self.stage.source_clones, [])


class UiHideTests(unittest.TestCase):
    def setUp(self):
        subset = stage_class({'set_hall_ui_hidden', 'toggle_hall_ui', 'confirm_exit',
                              'set_hall_crosshair'})
        ast.fix_missing_locations(subset)
        self.elements = {'a': NS(visible=True), 'b': NS(visible=False), 'c': NS(visible=True)}
        self.hall = NS(chat_open=False, parts={'navigation': NS(visible=True),
                                               'toolbar': NS(visible=True),
                                               'chat': NS(visible=True)})
        self.sysbox = NS(show_array=[], double_btn=Mock())
        self.ring = NS(visible=True)
        namespace = {'guiManager': NS(instance=lambda: NS(elements=self.elements)),
                     'BigWorld': NS(player=lambda: NS(aim=NS(ring=self.ring))),
                     'SysBox': NS(instance=lambda: self.sysbox, double_btn=self.sysbox.double_btn)}
        exec(compile(subset, str(STAGE), 'exec'), namespace)
        self.stage = namespace['Stage']()
        self.stage.hall = self.hall
        self.stage.runtime = NS(practice=None, write_status=Mock())
        self.stage.log = Mock()
        self.stage.visible = False
        self.stage.closed = False
        self.stage.hall_ui_hidden = False
        self.stage.ui_snapshot = {}
        self.stage.hall_combat = False

    def test_no_ui_hides_every_visible_element_and_restores_the_same_set(self):
        self.stage.hall_combat = True
        self.stage.set_hall_ui_hidden(True)
        self.assertTrue(self.stage.hall_ui_hidden)
        self.assertFalse(self.elements['a'].visible)
        self.assertFalse(self.elements['c'].visible)
        self.assertFalse(self.elements['b'].visible)
        self.assertFalse(self.hall.parts['chat'].visible)
        self.assertFalse(self.ring.visible)
        self.assertEqual(sorted(self.stage.ui_snapshot), ['a', 'c'])
        self.stage.set_hall_ui_hidden(False)
        self.assertFalse(self.stage.hall_ui_hidden)
        self.assertTrue(self.elements['a'].visible)
        self.assertTrue(self.elements['c'].visible)
        self.assertFalse(self.elements['b'].visible)
        self.assertTrue(self.hall.parts['chat'].visible)
        self.assertTrue(self.ring.visible)

    def test_no_ui_in_peacetime_leaves_the_hidden_crosshair_alone(self):
        self.stage.hall_combat = False
        self.ring.visible = False
        self.stage.set_hall_ui_hidden(True)
        self.stage.set_hall_ui_hidden(False)
        self.assertFalse(self.ring.visible)

    def test_repeated_hide_or_show_is_a_no_op(self):
        self.stage.set_hall_ui_hidden(True)
        self.stage.runtime.write_status.reset_mock()
        self.stage.set_hall_ui_hidden(True)
        self.stage.runtime.write_status.assert_not_called()

    def test_toggle_refuses_while_chat_or_training_is_open(self):
        self.hall.chat_open = True
        self.assertFalse(self.stage.toggle_hall_ui())
        self.assertFalse(self.stage.hall_ui_hidden)
        self.hall.chat_open = False
        self.stage.runtime.practice = NS(engaged=True)
        self.assertFalse(self.stage.toggle_hall_ui())
        self.stage.runtime.practice = None
        self.assertTrue(self.stage.toggle_hall_ui())
        self.assertTrue(self.stage.hall_ui_hidden)
        self.assertTrue(self.stage.toggle_hall_ui())
        self.assertFalse(self.stage.hall_ui_hidden)

    def test_escape_leaves_combat_before_opening_the_exit_box(self):
        self.stage.hall_combat = True
        self.stage.toggle_hall_combat = Mock()
        self.stage.confirm_exit()
        self.stage.toggle_hall_combat.assert_called_once_with(False)
        self.sysbox.double_btn.assert_not_called()


class CooldownButtonTests(unittest.TestCase):
    def test_no_cooldown_switch_sits_right_of_map_selector(self):
        subset = ast.Module(body=functions(PRACTICE, {'cooldown_button_position'}), type_ignores=[])
        ast.fix_missing_locations(subset)
        namespace = {}
        exec(compile(subset, str(PRACTICE), 'exec'), namespace)
        map_button = NS(coord=(120, 10), width=150)
        x, y = namespace['cooldown_button_position'](map_button)
        self.assertEqual(x, map_button.coord[0]+map_button.width+4)
        self.assertEqual(y, map_button.coord[1])


if __name__ == '__main__':
    unittest.main()
