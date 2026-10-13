# -*- coding: utf-8 -*-
"""Paged client item catalogue in the original backpack template."""
import BigWorld
import Item
import const
from common_data import item_data
from guis import factory, xnui, InvPanel, tipsMgr
from logic import FsmGame


class CataloguePage(InvPanel.InvPage):
    def __init__(self, bag, parent, pid, item_ids):
        self.item_ids = item_ids
        self.local_items = {}
        self.local_tips = {}
        InvPanel.InvPage.__init__(self, bag, parent, 0, 0)
        self.pid = pid
        self.pos_count = len(item_ids)
        self.hero_list.visible = False
        self.btn_more.visible = False
        self.btn_arrange.visible = False
        for grid in self.grids:
            grid.changeable = False
            grid.takeable = False
            grid.discardable = False
            grid.event_grid_take = lambda sender: None
            grid.event_grid_put = lambda sender: None
            grid.event_grid_use = lambda sender: None
            grid.event_grid_split = lambda sender: None
        self.page_mgr.set_page_len(len(item_ids))
        self.on_page_select(0, len(self.grids)-1)

    def set_visible(self, value):
        # Native InvPage expects a live account inventory on every show.
        factory.CityCommonCell.set_visible(self, value)
        if hasattr(self, 'hero_list'):
            self.hero_list.visible = False

    def on_page_select(self, start_pos, end_pos):
        for index, grid in enumerate(self.grids):
            pos = int(start_pos)+index
            grid.clear_all()
            if pos < len(self.item_ids):
                item_id = self.item_ids[pos]
                if item_id not in self.local_items:
                    self.local_items[item_id] = Item.Item(item_id)
                item = self.local_items[item_id]
                grid.get_grid_obj = lambda item=item: item
                grid.get_tips_dict = lambda item=item: self.item_tips(item)
                grid.source = const.CONTAINER_INV
                grid.mapping_pos = (self.pid, pos)
                grid.enable_click_hint = False
                grid.enable_price_hint = False
                grid.visible = True
                grid.update_display()
                grid.set_sensor_avtive(True)
            else:
                grid.get_grid_obj = lambda: None
                grid.visible = False

    def item_tips(self, item):
        key = (item.id, tipsMgr.is_tips_ex)
        if key not in self.local_tips:
            self.local_tips[key] = tipsMgr.ItemTipDict.get_item_tip_dict(item.id, item, None)
        return self.local_tips[key]


class LocalBag(factory.CityBagDlg):
    def __init__(self, runtime):
        self.runtime = runtime
        self.pages = {}
        self.items = {}
        self.current_pid = None
        self.restoring = False
        self.classification_errors = []
        for item_id in sorted(item_data.data):
            try:
                pid = Item.Item.getProperPageByID(item_id)
            except Exception as error:
                if len(self.classification_errors) < 3:
                    self.classification_errors.append(repr(error))
                pid = const.INV_PAGE_EXTRA
            if pid not in (const.INV_PAGE_EQU, const.INV_PAGE_FASHION, const.INV_PAGE_APPEARANCE_CARD):
                pid = const.INV_PAGE_EXTRA
            self.items.setdefault(pid, []).append(item_id)
        runtime.log('Backpack catalogue classification: '+repr(self.classification_errors))
        factory.CityBagDlg.__init__(self)
        self.num_1.text = self.num_2.text = self.num_3.text = '0'
        for name in ['newbiebox', 'newbiebox_money', 'newbiebox_goldbrick', 'newbiebox_pvp',
                     'icon_new_1', 'icon_new_2', 'icon_new_3', 'icon_new_4']:
            getattr(self, name).visible = False
        self.btn_pieces.event_click = lambda sender: None
        for name, pid in [('btn_common', const.INV_PAGE_EXTRA), ('btn_equip', const.INV_PAGE_EQU),
                          ('btn_fashion', const.INV_PAGE_FASHION), ('btn_monster', const.INV_PAGE_APPEARANCE_CARD)]:
            getattr(self, name).event_click = self.handler(pid)
        self.btn_close.event_click = lambda sender: setattr(self, 'visible', False)
        self.select_category(const.INV_PAGE_EXTRA)
        self.visible = False

    def handler(self, pid):
        return lambda sender: self.select_category(pid)

    def select_category(self, pid):
        for page in self.pages.values():
            page.visible = False
        if pid not in self.pages:
            self.pages[pid] = CataloguePage(self, self.container_1, pid, self.items.get(pid, []))
        self.container_0.visible = False
        self.container_1.visible = True
        self.pages[pid].visible = True
        self.current_pid = pid

    def set_visible(self, value):
        factory.CityBagDlg.set_visible(self, value)
        if value:
            if not self.runtime.hall.hero_page.visible:
                self.runtime.hall.hero_page.capture_hall_camera()
            FsmGame.set_hero_only_move(True)
            self.topmostEx()
        elif hasattr(self.runtime.hall, 'hero_page') and not self.runtime.hall.hero_page.visible:
            self.runtime.hall.hero_page.restore_hall_control()

    def on_btn_close_click(self, sender):
        self.visible = False
