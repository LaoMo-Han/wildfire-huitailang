# -*- coding: utf-8 -*-
"""Local ownership and saved loadouts for the original city equipment UI."""
import types
import BigWorld
import const
import Item
import Inventory
from common_data import item_data
from logic import ClientEquipsContainer, ClientItem


class Equipment(object):
    def __init__(self, runtime):
        self.runtime = runtime
        self.catalog = {}
        self.player_id = None
        self.generation = 0
        self.native_calc = None
        for item_id, info in item_data.data.items():
            if (info.get('type') in (1, 2, 3, 4)
                    and info.get('quality', 0) in (0, 1, 2, 3, 4)):
                hero = int(info.get('hero', 0))
                if hero == 0 or hero in runtime.hero_ids:
                    self.catalog[int(item_id)] = info

    def initialize(self):
        player = BigWorld.player()
        if self.player_id == player.id and getattr(player, '_offline_equipment', None) is self:
            return
        player.hero_equips = {}
        player.new_equip_inv = ClientEquipsContainer.EquipsContainer()
        self.items = {}
        for item_id in sorted(self.catalog):
            item = Item.Item(item_id)
            item.uuid = 'offline-equipment-%d' % item_id
            item.cdur = item.getMaxDur()
            item.is_new = False
            self.items[item_id] = item
            player.new_equip_inv.add_item(item, item.uuid)
        for hero in self.runtime.hero_ids:
            inv = Inventory.Inventory(const.INV_TYPE_HERO_CONF)
            player.hero_equips[hero] = inv
            saved = self.runtime.profile.get('equipment', {}).get(str(hero), {})
            for page, slots in const.HERO_INVPAGE_COUNT.items():
                for pos in range(slots):
                    item_id = saved.get('%d:%d' % (page, pos))
                    item = self.items.get(item_id)
                    if item is None or not self.accepts(hero, page, pos, item_id):
                        item = ClientItem.get_hero_default_equip(hero, page, pos)
                    if item is not None:
                        inv.setQuickVal(page, pos, item)
        player.client_get_item_keys = player.new_equip_inv.get_keys_by_filter
        player._offline_equipment = self
        self.player_id = player.id

    def accepts(self, hero, page, pos, item_id):
        info = self.catalog.get(item_id)
        if info is None or info.get('hero', 0) not in (0, hero):
            return False
        typ, stype = info.get('type'), info.get('stype')
        if page == const.HERO_INV_PAGE_EQUIP:
            return (typ, stype) == {0:(1, 1), 2:(2, 1), 4:(2, 3),
                                    5:(2, 4), 6:(2, 5), 7:(2, 6)}.get(pos)
        if page == const.HERO_INV_PAGE_TRINKET:
            return typ == Item.Item.BASETYPE_HERO_TRINKET and info.get('tlimit', stype)-1 == pos
        if page == const.HERO_INV_PAGE_CONSUMABLE:
            return typ == Item.Item.BASETYPE_HERO_CONSUMABLE and pos in (0, 1)
        return False

    def choices(self, hero, page, pos):
        return [self.items[item_id] for item_id in sorted(self.items,
                key=lambda k:(-self.catalog[k].get('quality', 0), k))
                if self.accepts(hero, page, pos, item_id)]

    def equip(self, hero, page, pos, item_id):
        self.initialize()
        if not self.accepts(hero, page, pos, item_id):
            raise ValueError('Equipment does not fit this hero or slot')
        inv = BigWorld.player().hero_equips[hero]
        inv.setQuickVal(page, pos, self.items[item_id])
        self.runtime.profile.setdefault('equipment', {}).setdefault(str(hero), {})[
            '%d:%d' % (page, pos)] = item_id
        self.runtime.save()
        self.refresh()

    def unequip(self, hero, page, pos):
        item = ClientItem.get_hero_default_equip(hero, page, pos)
        BigWorld.player().hero_equips[hero].setQuickVal(page, pos, item)
        self.runtime.profile.setdefault('equipment', {}).setdefault(str(hero), {}).pop(
            '%d:%d' % (page, pos), None)
        self.runtime.save()
        self.refresh()

    def refresh(self):
        stage = self.runtime.hall.hero_page
        if stage.info.hero_type:
            stage.info.update_equip()
            stage.info.update_info_panel()
        self.apply()
        self.runtime.write_status()

    def bind_stage(self, stage):
        """Retain native slot labels, scrolling list, item tips and bag filters."""
        equipment = self
        panel = stage.info.change_item_panel
        def show(panel, label, is_left=True, page_const=None):
            panel.page_const = page_const if page_const is not None else label.page
            panel.clear()
            panel.tgt_label = label
            panel.mgr.focus_item_label(label)
            panel._show(equipment.choices(stage.hero_type, label.page, label.pos))
            x, y = panel.mgr.container_item.abs_coord
            bottom = panel.parent.abs_coord[1]*2
            panel.abs_coord = (x-panel.width-5, max(8, min(y-15, bottom-panel.height-8)))
            panel.visible = True
            panel.topmostEx()
        def use(panel, sender):
            label = panel.tgt_label
            if label is not None and sender.item is not None:
                equipment.equip(stage.hero_type, label.page, label.pos, sender.item.id)
                panel.visible = False
        panel.show = types.MethodType(show, panel, panel.__class__)
        panel.on_label_use = types.MethodType(use, panel, panel.__class__)
        for group in (stage.info.page_equip, stage.info.page_trinket, stage.info.page_consumable):
            for label in group.labels:
                label.event_item_use = lambda sender: equipment.unequip(
                    stage.hero_type, sender.page, sender.pos)

    def bind_bag(self, stage, bag):
        from guis import tipsMgr
        equipment = self
        def show(manager, keys):
            manager.clear_grids()
            for index, grid in enumerate(manager.grids):
                item = BigWorld.player().new_equip_inv.get_item_by_keys(keys[index]) if index < len(keys) else None
                grid.get_grid_obj = lambda item=item: item
                grid.get_tips_dict = lambda item=item: tipsMgr.ItemTipDict.get_item_tip_dict(
                    item.id, item, None) if item is not None else {}
                grid.enable_click_hint = False
                grid.enable_price_hint = False
                if item is not None:
                    grid.source = const.CONTAINER_INV
                    grid.mapping_pos = keys[index]
                    grid.update_display()
                    grid.set_sensor_avtive(True)
        def use(grid):
            item = grid.get_grid_obj()
            if item is None:
                return
            for page, slots in const.HERO_INVPAGE_COUNT.items():
                for pos in range(slots):
                    if self.accepts(stage.hero_type, page, pos, item.id):
                        self.equip(stage.hero_type, page, pos, item.id)
                        return
        bag.grids_container.exclusive_grid_use_listener = use
        manager = bag.grids_container
        manager.show = types.MethodType(show, manager, manager.__class__)
        bag.set_wearing(False)

    def apply(self):
        """Run the native calculator with a private calculation-only context."""
        player = BigWorld.player()
        hero = int(getattr(player, '_offline_visual_hero', player.root_hero_type))
        if hero not in player.hero_equips:
            return
        if self.native_calc is None:
            from Hero import Hero
            original = Hero.calcAllEqus.im_func
            scope = dict(original.func_globals)
            original_state = scope['FsmGame']
            class CalculationState(object):
                def state_is_offline(self):
                    return False
                def __getattr__(self, name):
                    return getattr(original_state, name)
            scope['FsmGame'] = CalculationState()
            self.native_calc = types.FunctionType(original.func_code, scope,
                original.func_name, original.func_defaults, original.func_closure)
        # items normally points to the account backpack in ST_OFFLINE.
        previous_items = player.items
        old = dict(player.equs)
        try:
            player.items = player.hero_equips[hero]
            self.native_calc(player)
        finally:
            player.items = previous_items
        player.set_equs(old)
        practice = self.runtime.practice
        if practice is not None and practice.active:
            practice.base_equipment_stats = dict(player.equs)
            practice.update_equipment_stats()

    def status(self):
        counts = {}
        for info in self.catalog.values():
            quality = info.get('quality', 0)
            counts[quality] = counts.get(quality, 0)+1
        return {'count':len(self.catalog), 'qualities':counts,
                'loadouts':self.runtime.profile.get('equipment', {})}
