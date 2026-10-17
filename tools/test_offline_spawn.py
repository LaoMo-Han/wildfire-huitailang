"""Ground spawn waits for collision and never falls back to a high teleport."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('offline_spawn_test',Path(__file__).resolve().parent.parent/'runtime/offline_spawn.py')
spawn=importlib.util.module_from_spec(spec);spec.loader.exec_module(spawn)


class SpawnTests(unittest.TestCase):
    def test_no_teleport_until_collision_is_available(self):
        player=NS(spaceID=9,physics=NS(teleport=Mock()))
        with patch.dict(sys.modules,{'helper':NS(ClientUtils=NS(get_collide_info=lambda *a,**kw:None))}):
            self.assertIsNone(spawn.place(player))
        player.physics.teleport.assert_not_called()

    def test_uses_measured_floor_with_two_centimeters_clearance(self):
        player=NS(spaceID=9,physics=NS(teleport=Mock()))
        collide=Mock(return_value=NS(position=(52,219.025,178)))
        with patch.dict(sys.modules,{'helper':NS(ClientUtils=NS(get_collide_info=collide))}):
            point=spawn.place(player)
        self.assertAlmostEqual(point[1],219.045)
        player.physics.teleport.assert_called_once_with(point,(0,0,0))
        self.assertEqual(collide.call_args.args[0],9)

    def test_initial_seed_already_matches_ground_height(self):
        self.assertEqual(spawn.SCENE,'zc_new01')
        self.assertLess(abs(spawn.POSITION[1]-219.025),.05)


if __name__=='__main__':unittest.main()
