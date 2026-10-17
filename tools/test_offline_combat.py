"""Ownership, pickup lifetime and cooldown regressions, independent of engine assets."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


class Vector:
    def __init__(self, value):
        self.x, self.y, self.z = value

    def __sub__(self, other):
        return Vector((self.x-other.x, self.y-other.y, self.z-other.z))


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.player = NS(id=1, hero_type=28, spaceID=9, position=Vector((0,0,0)),
                         mana=NS(inform=Mock()), update_skill_cd=Mock())
        self.world = NS(player=lambda:self.player, entity=lambda eid:self.player if eid==1 else None,
                        time=lambda:10.0)
        self.cd = NS(instance=lambda:NS(dict_base_cd={7:12}),
                     update_next_extra_cd=Mock(), get_cd=lambda skill:(12,0))
        self.modules = patch.dict(sys.modules, {'BigWorld':self.world,
            'logic':NS(FsmGame=NS(state_is_offline=lambda:True)), 'captain':NS(cdmgr=self.cd),
            'utils':NS(get_skill_cd_by_scale=lambda p,s,e,r:e)})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec=importlib.util.spec_from_file_location('local_combat_test',
            Path(__file__).resolve().parent.parent/'runtime/offline_combat.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.combat=module.LocalCombat.__new__(module.LocalCombat)
        self.combat.practice=NS(active=True)
        self.combat.summons={}
        self.combat.souls=[]

    def soul(self, **changes):
        row=dict(model=NS(position=Vector((0,0,0)),visible=True),attacker=1,hero_type=28,
                 skill=11,space=9,ready=9,expires=30,
                 config={'trigger_event_id':39,'trap_range':1.5,'trap_height':1.7})
        row.update(changes)
        self.combat.souls=[row]
        return row

    def test_pickup_consumes_once_and_hides_model(self):
        row=self.soul()
        self.combat.tick()
        self.combat.tick()
        self.player.mana.inform.assert_called_once_with('target',11,39)
        self.assertFalse(row['model'].visible)

    def test_pickup_checks_horizontal_and_vertical_range(self):
        for pos in [(1.51,0,0),(0,1.71,0)]:
            with self.subTest(position=pos):
                self.player.position=Vector(pos)
                self.soul()
                self.combat.tick()
                self.player.mana.inform.assert_not_called()
                self.assertEqual(len(self.combat.souls),1)

    def test_pickup_waits_for_spawn_delay(self):
        self.soul(ready=10.1)
        self.combat.tick()
        self.player.mana.inform.assert_not_called()

    def test_expired_and_other_space_souls_cannot_refill(self):
        for changes in ({'expires':10},{'space':8}):
            self.soul(**changes)
            self.combat.tick()
            self.assertEqual(self.combat.souls,[])
        self.player.mana.inform.assert_not_called()

    def test_different_owner_and_changed_hero_cannot_pickup(self):
        for changes in ({'attacker':2},{'hero_type':25}):
            self.soul(**changes)
            self.combat.tick()
        self.player.mana.inform.assert_not_called()

    def test_sp_resets_requested_skill_even_without_extra_cd(self):
        self.combat.refresh_cooldown(self.player,3,{'reset_skill_use_time':7,'extra_cd':0})
        self.player.update_skill_cd.assert_called_once_with(28,7,0,12,True)
        self.cd.update_next_extra_cd.assert_not_called()

    def test_extra_cd_uses_native_refresh_without_resetting_other_skills(self):
        self.combat.refresh_cooldown(self.player,3,{'refresh_skill':7,'extra_cd':-4.8})
        self.cd.update_next_extra_cd.assert_called_once_with(7,-4.8)
        self.player.update_skill_cd.assert_called_once_with(28,7,-1,12,True)

    def test_absent_refresh_does_not_change_cooldowns(self):
        self.combat.refresh_cooldown(self.player,1,{'reset_skill_use_time':-1})
        self.player.update_skill_cd.assert_not_called()
        self.cd.update_next_extra_cd.assert_not_called()

    def test_stale_summon_ids_are_discarded(self):
        self.combat.summons={99:(1,13)}
        self.combat.tick()
        self.assertEqual(self.combat.summons,{})


if __name__=='__main__':
    unittest.main()
