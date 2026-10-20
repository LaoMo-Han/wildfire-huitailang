"""Ownership, transactions and resource restoration at the offline boundary."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent


class EmbeddedSourceTests(unittest.TestCase):
    def test_new_runtime_sources_do_not_require_unicode_literal_codecs(self):
        # The embedded Python lacks utf-32-be used by its non-ASCII literal
        # decoder. Desktop Python's compile() does not reproduce that failure.
        for name in ('offline_equipment.py', 'offline_buffs.py',
                     'offline_skillsets.py', 'offline_practice.py'):
            with self.subTest(name=name):
                (ROOT/'runtime'/name).read_bytes().decode('ascii')


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'runtime'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Item:
    BASETYPE_HERO_TRINKET = 3
    BASETYPE_HERO_CONSUMABLE = 4
    def __init__(self, item_id):
        self.id = item_id
        self.uuid = ''
    def getMaxDur(self):
        return 100


class Inventory:
    def __init__(self, kind):
        self.values = {}
    def setQuickVal(self, page, pos, item):
        self.values[page, pos] = item


class Container:
    def __init__(self):
        self.items = {}
    def add_item(self, item, uuid):
        self.items[uuid] = item
    def get_keys_by_filter(self, filters):
        return list(self.items)


class EquipmentTests(unittest.TestCase):
    def setUp(self):
        self.data = {100+q:{'type':1, 'stype':1, 'hero':3, 'quality':q} for q in range(5)}
        self.data.update({200:{'type':1, 'stype':1, 'hero':4, 'quality':3},
                         201:{'type':1, 'stype':1, 'hero':999, 'quality':3},
                         202:{'type':1, 'stype':1, 'hero':3, 'quality':5},
                         300:{'type':3, 'stype':1, 'hero':3, 'tlimit':2},
                         400:{'type':4, 'stype':3, 'hero':0}})
        self.player = NS(id=1, root_hero_type=3, items=object(), equs={'e_p_attack':1}, set_equs=Mock())
        self.const = NS(INV_TYPE_HERO_CONF=1, HERO_INV_PAGE_EQUIP=7,
                        HERO_INV_PAGE_TRINKET=3, HERO_INV_PAGE_CONSUMABLE=4,
                        HERO_INVPAGE_COUNT={7:8, 3:3, 4:2})
        modules = {'BigWorld':NS(player=lambda:self.player), 'const':self.const,
                   'Item':NS(Item=Item), 'Inventory':NS(Inventory=Inventory),
                   'common_data':NS(item_data=NS(data=self.data)),
                   'logic':NS(ClientEquipsContainer=NS(EquipsContainer=Container),
                              ClientItem=NS(get_hero_default_equip=lambda *args:None))}
        self.mods = patch.dict(sys.modules, modules)
        self.mods.start()
        self.addCleanup(self.mods.stop)
        self.runtime = NS(profile={}, hero_ids=[3,4], save=Mock(), practice=None)
        self.equipment = load('offline_equipment').Equipment(self.runtime)
        self.equipment.initialize()
        self.equipment.refresh = Mock()

    def test_all_five_qualities_are_owned_without_unavailable_items(self):
        self.assertEqual(set(self.equipment.catalog), {100,101,102,103,104,200,300,400})
        self.assertEqual([i.id for i in self.equipment.choices(3,7,0)], [104,103,102,101,100])
        self.assertEqual(len(self.player.new_equip_inv.items), 8)

    def test_wrong_hero_and_wrong_slot_leave_profile_and_equipment_unchanged(self):
        for hero,page,pos,item in [(3,7,0,200),(3,7,2,104),(3,3,0,300)]:
            with self.assertRaises(ValueError):
                self.equipment.equip(hero,page,pos,item)
        self.assertEqual(self.runtime.profile, {})
        self.runtime.save.assert_not_called()

    def test_saved_equipment_reloads_and_unequip_removes_only_one_slot(self):
        self.equipment.equip(3,7,0,104)
        self.equipment.equip(3,3,1,300)
        self.player.id = 2
        self.equipment.initialize()
        self.assertEqual(self.player.hero_equips[3].values[7,0].id, 104)
        self.equipment.unequip(3,7,0)
        self.assertEqual(self.runtime.profile['equipment']['3'], {'3:1':300})

    def test_calculation_restores_backpack_even_when_native_calculation_fails(self):
        backpack = self.player.items
        self.equipment.native_calc = Mock(side_effect=ValueError('invalid modifier'))
        with self.assertRaises(ValueError):
            self.equipment.apply()
        self.assertIs(self.player.items, backpack)


class BuffTransactions(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.player = NS(cash=1000, equs={}, hp=100, mhp=1000,
                         add_combat_state=Mock(), remove_combat_state=Mock(),
                         offline_add_state=Mock(), offline_remove_state=Mock(), set_equs=Mock(), set_hp=Mock(),
                         board=NS(initProps=Mock()))
        self.states = {(1454,1):{'combat_props':{'t_p_attack':85}},
                       (1455,1):{'combat_props':{'t_mv_speed':3334}, 'interval':1,
                                  'triggers':{'interval_effect':('recoverHp',)},'set_hp_num':5}}
        item = {'type':4,'hero':3,'use_cash':150,'state':((1454,),1),
                'duration':(15.0,), 'cooldown':60.0}
        self.catalog = {70310:item, 70311:dict(item, state=((1455,),1))}
        modules = {'common_data':NS(combat_state_data=NS(data=self.states),
                                   equip_evolution_data=NS(data={})),
                   'system':NS(MsgManager=NS(show=Mock()))}
        self.mods=patch.dict(sys.modules, modules)
        self.mods.start()
        self.addCleanup(self.mods.stop)
        tree=ast.parse((ROOT/'runtime/offline_practice.py').read_text(encoding='utf8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LocalPractice')
        methods={'purchase_buff','apply_native_buff','tick_buffs','clear_buffs','update_equipment_stats'}
        cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in methods]
        module=ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[]))
        self.bigworld=NS(player=lambda:self.player,time=lambda:self.now,cancelCallback=Mock())
        scope={'BigWorld':self.bigworld}
        exec(compile(module,'offline_practice.py','exec'),scope)
        self.practice=scope['LocalPractice']()
        p=self.practice
        p.runtime=NS(equipment=NS(catalog=self.catalog),
                     skillsets=NS(visual_hero=lambda:3,busy=False),write_status=Mock())
        p.active=True
        p.loading=False
        p.base_equipment_stats={'e_p_attack':100}
        p.evolutions={}
        p.buff_states={}
        p.buff_purchases={}
        p.monster_buffs=self.catalog
        p.set_cash=lambda amount:setattr(self.player,'cash',amount)

    def test_purchase_charges_once_and_cooldown_blocks_repeat(self):
        self.assertTrue(self.practice.purchase_buff(70310))
        self.assertEqual(self.player.cash,850)
        self.assertEqual(self.player.equs['e_p_attack'],100)
        self.player.offline_add_state.assert_called_once_with((1454,1),15.0)
        self.player.add_combat_state.assert_not_called()
        self.assertFalse(self.practice.purchase_buff(70310))
        self.assertEqual(self.player.cash,850)

    def test_expiry_restores_base_stats_and_does_not_refund(self):
        self.practice.purchase_buff(70310)
        self.now=25
        self.practice.tick_buffs()
        self.assertEqual(self.player.equs,{'e_p_attack':100})
        self.assertEqual(self.player.cash,850)
        self.assertEqual(self.practice.buff_states,{})

    def test_recovery_ticks_and_reset_remove_temporary_effects(self):
        self.practice.purchase_buff(70311)
        self.now=11
        self.practice.tick_buffs()
        self.assertEqual(self.player.hp,105)
        self.practice.clear_buffs()
        self.assertEqual(self.player.equs,{'e_p_attack':100})
        self.assertEqual(self.practice.buff_purchases,{})

    def test_insufficient_cash_invalid_hero_and_missing_state_do_not_charge(self):
        self.player.cash=149
        self.assertFalse(self.practice.purchase_buff(70310))
        with self.assertRaises(ValueError):self.practice.purchase_buff(70410)
        self.player.cash=1000
        del self.states[1454,1]
        with self.assertRaises(ValueError):self.practice.purchase_buff(70310)
        self.assertEqual(self.player.cash,1000)
        self.assertEqual(self.practice.buff_states,{})

    def test_failed_effect_rolls_back_and_does_not_charge(self):
        self.player.offline_add_state.side_effect=RuntimeError('missing effect')
        with self.assertRaises(RuntimeError):self.practice.purchase_buff(70310)
        self.assertEqual(self.player.cash,1000)
        self.assertEqual(self.practice.buff_states,{})

    def test_native_expiry_is_cancelled_and_reset_removes_native_property_keys(self):
        self.player.cb_remove_combat_state = 123
        self.practice.purchase_buff(70310)
        self.bigworld.cancelCallback.assert_called_once_with(123)
        self.assertIsNone(self.player.cb_remove_combat_state)
        self.player.offline_remove_state.reset_mock()
        self.practice.clear_buffs()
        self.player.offline_remove_state.assert_called_once_with(1454,1)

    def test_potion_catalog_does_not_grant_access_to_monster_buff_shop(self):
        self.practice.monster_buffs = {}
        with self.assertRaises(ValueError):
            self.practice.purchase_buff(70310)
        self.assertEqual(self.player.cash,1000)


class SkillResourceTests(unittest.TestCase):
    def setUp(self):
        self.player=NS(root_hero_type=3,hero_type=3,_bh_id=3,model_id=3)
        self.config={3:{'model_id':3,'bh_id':3,'controls':{'Q':6}},
                     4:{'model_id':4,'bh_id':4,'controls':{'Q':8}}}
        self.original=lambda entity,hid:self.config[hid]
        self.manager=NS(get_hero=self.original)
        modules={'BigWorld':NS(player=lambda:self.player),
                 'captain':NS(skillmanager=NS(ins=self.manager)),
                 'guis':NS(guiManager=Mock(),xnui=NS(XButton=Mock(return_value=Mock()))),
                 'rc':NS(COMMON_BTN_RECT_BIG='button')}
        self.mods=patch.dict(sys.modules,modules)
        self.mods.start()
        self.addCleanup(self.mods.stop)
        self.skills=load('offline_skillsets').Skillsets(NS())

    def test_donor_controls_and_behavior_keep_visual_model_and_restore_hooks(self):
        def change(source,*args):
            config=self.manager.get_hero(None,source)
            self.player.hero_type=source
            self.player.model_id=config['model_id']
            self.player.set_bh_id(config['bh_id'])
            self.assertEqual(config['controls'],{'Q':8})
        self.player.set_combat_type=change
        self.skills.rebuild(self.player,3,4)
        self.assertEqual((self.player.model_id,self.player._bh_id,self.player.hero_type),(3,4,4))
        self.assertEqual(self.config[4]['model_id'],4)
        self.assertIs(self.manager.get_hero,self.original)
        self.assertFalse(hasattr(self.player,'set_bh_id'))

    def test_native_failure_restores_existing_instance_override_and_global_lookup(self):
        override=Mock()
        self.player.set_bh_id=override
        self.player.set_combat_type=Mock(side_effect=RuntimeError('no behavior'))
        with self.assertRaises(RuntimeError):self.skills.rebuild(self.player,3,4)
        self.assertIs(self.player.set_bh_id,override)
        self.assertIs(self.manager.get_hero,self.original)

    def test_hall_picker_is_separate_and_reuses_the_native_hero_list(self):
        class Picker:
            def __init__(self):
                self.visible=False
                self.part_basic=NS(hero_list=NS(lock_mode=True))
            def setting(self, ids):
                self.ids=list(ids)
            def connect(self, target, hero, select_mode=0):
                self.visible=True
                self.source=hero
        original_picker=Picker()
        stage=NS(visible=False,selector=original_picker,restore_hall_control=Mock())
        self.skills.runtime=NS(practice=None,hero_ids=[3,4],
                               hall=NS(hero_page=stage),write_status=Mock())
        self.skills.toggle_selector()
        self.assertTrue(self.skills.selector_visible)
        self.assertFalse(original_picker.visible)
        self.assertIs(self.skills.selector.local_stage,self.skills)
        self.assertEqual(self.skills.selector.ids,[3,4])
        self.assertFalse(self.skills.selector.part_basic.hero_list.lock_mode)
        button_factory=sys.modules['guis'].xnui.XButton
        self.assertIs(button_factory.call_args.args[0],self.skills.selector.part_basic)
        self.skills.toggle_selector()
        self.assertFalse(self.skills.selector_visible)

    def test_loading_or_rebuilding_blocks_selector_without_creating_ui(self):
        self.skills.runtime=NS(practice=NS(loading=True))
        self.skills.toggle_selector()
        self.assertIsNone(self.skills.selector)

        self.skills.runtime.practice=None
        self.skills.busy=True
        self.skills.toggle_selector()
        self.assertIsNone(self.skills.selector)

    def test_reset_all_removes_every_mapping_and_preserves_other_profile_fields(self):
        profile={'skillsets':{'3':4,'4':3},'equipment':{'3':{'7:0':104}},'fashion':123}
        self.skills.runtime=NS(profile=profile,save=Mock())
        self.skills.save_selection(3,3,reset_all=True)
        self.assertNotIn('skillsets',profile)
        self.assertEqual(profile['equipment'],{'3':{'7:0':104}})
        self.assertEqual(profile['fashion'],123)
        self.skills.runtime.save.assert_called_once_with()

    def test_reset_all_save_failure_preserves_every_mapping(self):
        mappings={'3':4,'4':3}
        self.skills.runtime=NS(profile={'skillsets':mappings},
                               save=Mock(side_effect=IOError('disk full')))
        with self.assertRaises(IOError):
            self.skills.save_selection(3,3,reset_all=True)
        self.assertIs(self.skills.runtime.profile['skillsets'],mappings)

    def test_reset_all_rebuilds_current_hero_before_clearing_saved_mappings(self):
        self.player._offline_visual_hero=3
        self.player.hero_type=4
        self.skills.runtime=NS(practice=None)
        self.skills.select=Mock(return_value=True)
        self.assertTrue(self.skills.reset_all())
        self.skills.select.assert_called_once_with(3,save=False,reset_all=True)


if __name__=='__main__':
    unittest.main()
