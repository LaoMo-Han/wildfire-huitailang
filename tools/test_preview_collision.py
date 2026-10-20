"""Preview actors must not leave a blocking Havok phantom at arena origin."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parent.parent/'runtime/hero_stage.py'


class PreviewCollisionTests(unittest.TestCase):
    def setUp(self):
        original = next(n for n in ast.parse(SOURCE.read_text(encoding='utf8')).body
                        if isinstance(n, ast.ClassDef) and n.name == 'LocalActorField')
        tree = ast.fix_missing_locations(ast.Module(body=[original], type_ignores=[]))
        self.base = type('Base', (), {'_init_check':Mock(), 'on_fashion_changed':Mock()})
        self.behavior = NS(isBehaviorReady=Mock(return_value=True),
                           setCollisionFilterInfo=Mock(), updateCollisionFilterOnPhantom=Mock())
        # Preview actors deliberately have no camp or gameplay collision API.
        self.actor = NS(model=NS(bh=self.behavior))
        self.entities = {10:self.actor, 20:NS(model=NS(bh=Mock()))}
        self.callbacks = []
        self.world = NS(entity=self.entities.get,
                        callback=lambda delay, cb:self.callbacks.append(cb))
        self.havok = NS(calcFilterInfo=Mock(return_value=12345))
        self.mods = patch.dict(sys.modules, {'Havok':self.havok})
        self.mods.start()
        self.addCleanup(self.mods.stop)
        namespace = {'BigWorld':self.world, 'ActorField':NS(ActorField=self.base),
                     'const':NS(LAYER_DONT_COLLIDE_EXCEPT_HIT_TEST=9)}
        exec(compile(tree, str(SOURCE), 'exec'), namespace)
        self.field = namespace['LocalActorField']()
        self.field.actors = [10]

    def test_only_owned_preview_phantoms_become_nonblocking(self):
        self.field.disable_actor_collision(10)
        self.havok.calcFilterInfo.assert_called_once_with(9,0,0,0)
        self.behavior.setCollisionFilterInfo.assert_called_once_with(12345)
        self.behavior.updateCollisionFilterOnPhantom.assert_called_once_with()
        self.field.disable_actor_collision(20)
        self.entities[20].model.bh.setCollisionFilterInfo.assert_not_called()

    def test_async_model_load_retries_and_applies_to_the_loaded_model(self):
        self.actor.model = None
        self.field.disable_actor_collision(10)
        self.actor.model = NS(bh=self.behavior)
        self.callbacks.pop()()
        self.behavior.updateCollisionFilterOnPhantom.assert_called_once_with()

    def test_callback_does_not_touch_released_preview_actors(self):
        self.behavior.isBehaviorReady.return_value = False
        self.field.disable_actor_collision(10)
        self.field.actors = []
        self.behavior.isBehaviorReady.return_value = True
        self.callbacks.pop()()
        self.behavior.setCollisionFilterInfo.assert_not_called()

    def test_fashion_rebuild_keeps_native_callback_and_reapplies_filter(self):
        self.field.on_fashion_changed(10)
        self.base.on_fashion_changed.assert_called_once_with(self.field,10)
        self.behavior.updateCollisionFilterOnPhantom.assert_called_once_with()

    def test_initialization_covers_both_preview_actors(self):
        other = NS(model=NS(bh=NS(isBehaviorReady=lambda:True,
                   setCollisionFilterInfo=Mock(),updateCollisionFilterOnPhantom=Mock())))
        self.entities[11] = other
        self.field.actors = [10,11]
        self.field._init_check()
        self.base._init_check.assert_called_once_with(self.field)
        other.model.bh.updateCollisionFilterOnPhantom.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
