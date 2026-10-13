# -*- coding: utf-8 -*-
"""Restore the original city hero page using its own UI and preview scene."""
import traceback
import types
import BigWorld
from guis import factory, guiManager
from guis.city import ActorField
from guis.city.hero_equip import HeroEquipsPanel as original
from common_data import hero_info_data
from helper import ClientUtils
from logic import FsmGame


class LocalHeroInfo(original.HeroInfoDlg):
    @property
    def hero_type(self):
        return getattr(self, '_local_hero_type', int(BigWorld.player().hero_type))

    def set_visible(self, value):
        factory.HeroBoardDlg.set_visible(self, value)
        self.hero_list.visible = value
        if value and hasattr(self, 'local_page'):
            self.hero_list.setting_hero(self.local_page.heroes.hero_ids)
            self.hero_list.select(int(BigWorld.player().hero_type))

    def on_hero_selected(self, hero_type):
        try:
            self.local_page.select(int(hero_type))
        except Exception:
            self.local_page.log(traceback.format_exc())

    def set_hero(self, hero_type):
        self._local_hero_type = hero_type
        self.hero_list.select(hero_type)
        info = hero_info_data.data.get(hero_type, {})
        self.label_name.text = ClientUtils.get_hero_name(hero_type)
        self.label_title.text = info.get('title', '')
        self.hero_des.text = info.get('desc', '')
        self.label_exp.text = ''
        self.label_lv.text = ''
        self.bar_exp.visible = False
        self.bar_bg.visible = False
        self.six_box.hero_type = hero_type
        self.six_box.update()
        # The original attribute refresh requires an online equipment inventory.
        # Keep the original widgets empty until that data is available locally.
        for key in ['p_attack', 'crit', 'mhp', 'hp_recover', 'p_armor', 'anti_crit', 'h_speed_forward']:
            getattr(self, 'bara_'+key).rate = 0
            getattr(self, 'barb_'+key).rate = 0
            getattr(self, 'txt_'+key).text = ''
        for grid in self.grids.values():
            grid.visible = False

    def on_btn_dress_click(self, sender):
        self.local_page.hall.notice(sender)

    def on_btn_skill_click(self, sender):
        # This existing skill page selects the local player in offline state.
        guiManager.get_ui('skill_desc_dlg').toggle()


class OriginalHeroPage(object):
    def __init__(self, hall, heroes, log):
        self.hall, self.heroes, self.log = hall, heroes, log
        self.visible = False
        self.field = None
        self.hidden_ui = {}
        self.closed = False
        self.info = LocalHeroInfo()
        self.info.local_page = self
        self.info.visible = False
        self.tabs = factory.StageChangeMenu()
        self.tabs.visible = False
        self.exit = factory.HeroEquipMenu()
        self.exit.visible = False
        for name in ['container_unlock_s', 'container_unlock', 'container_use', 'container_shape', 'btn_refresh_scene', 'lbl_tips']:
            getattr(self.exit, name).visible = False
        self.exit.btn_quit.event_click = self.exit_clicked
        self.exit.btn_quit.coord = (25, 45)
        for name in ['equip', 'fashion', 'story', 'voice', 'paint', 'strategy', 'share']:
            getattr(self.tabs, 'btn_'+name+'_sel').visible = name == 'equip'
            getattr(self.tabs, 'btn_'+name).visible = name != 'equip'
            getattr(self.tabs, 'btn_'+name).event_click = hall.notice
        self.tabs.btn_equip_sel.event_click = lambda sender: None
        BigWorld.callback(0.5, self.tick)

    def show(self):
        if self.visible:
            return
        try:
            if self.field is None:
                self.field = ActorField.ActorField('HeroEquips')
            BigWorld.player().is_hero_type_changed = lambda: False
            self.field.enter(int(BigWorld.player().hero_type), show_eff=False,
                             enter_load_fashions=False, show_default_eff=False)
            self.load_preview_behavior(int(BigWorld.player().hero_type))
            for part in self.hall.parts.values():
                part.visible = False
            self.info.visible = True
            self.info.set_hero(int(BigWorld.player().hero_type))
            self.tabs.visible = True
            self.exit.visible = True
            self.visible = True
            if FsmGame.mode() != FsmGame.MOD_NOML:
                FsmGame.operate_change()
            self.heroes.write_status()
            self.log('Original HeroInfoDlg / HeroList / ActorField opened.')
        except Exception:
            self.heroes.last_error = traceback.format_exc()
            self.log(self.heroes.last_error)
            self.hide()
            self.heroes.write_status()

    def hide(self):
        self.info.visible = False
        self.tabs.visible = False
        self.exit.visible = False
        if self.field is not None and self.field.isin:
            try:
                BigWorld.player().is_hero_type_changed = lambda: False
                self.field.leave()
            except Exception:
                self.log(traceback.format_exc())
        for part in self.hall.parts.values():
            part.visible = True
        self.visible = False
        for part in self.hidden_ui.values():
            part.visible = True
        self.hidden_ui.clear()
        if FsmGame.mode() != FsmGame.MOD_NOML:
            FsmGame.operate_change()
        self.heroes.write_status()

    def toggle(self):
        if self.visible:
            self.hide()
        else:
            self.show()

    def select(self, hero_type):
        self.heroes.select(hero_type, close_menu=False)
        if int(BigWorld.player().hero_type) != hero_type:
            return
        self.field.set_hero(hero_type)
        BigWorld.callback(0.8, lambda: self.load_preview_behavior(hero_type))
        self.info.set_hero(hero_type)
        self.heroes.write_status()

    def exit_clicked(self, sender):
        self.hide()

    def destroy(self):
        self.closed = True
        if self.visible:
            self.hide()
        self.info.hero_list.destroy()
        self.info.item_list.destroy()
        self.info.tips_box.destroy()
        self.info.destroy()
        self.tabs.destroy()
        self.exit.destroy()

    def load_preview_behavior(self, hero_type):
        try:
            actor = self.field._get_curactor()
            if actor is not None and actor.hero_type == hero_type:
                # The online path finishes this initial empty behavior later.
                # Complete it locally using the original model/behavior loader.
                actor.init_all(False)
                self.log('Original preview behavior loaded: '+str(hero_type))
        except Exception:
            self.log(traceback.format_exc())

    def tick(self):
        if self.closed:
            return
        if self.visible:
            for name, part in guiManager.instance().elements.items():
                if name in ['battle_hp', 'battle_skill', 'cstate_panel', 'cstate_debuff_panel',
                            'cstate_special_panel', 'playerInfo', 'tipkey_panel', 'city_board_dlg',
                            'freshman_side_bar', 'welcome'] and part.visible:
                    self.hidden_ui[name] = part
                    part.visible = False
        BigWorld.callback(0.5, self.tick)

    def status(self):
        result = {'visible': self.visible}
        if self.field is not None:
            actor = self.field._get_curactor()
            result.update({'space_id': self.field.space_id, 'hero_type': self.field.hero_type,
                           'actor_ids': self.field.actors, 'actor_present': actor is not None})
            if actor is not None:
                model = getattr(actor, 'model', None)
                result.update({'actor_class':actor.__class__.__name__, 'actor_hero_type':actor.hero_type,
                               'model_present':model is not None})
                if model is not None:
                    result.update({'model_visible':bool(model.visible), 'position':list(model.position),
                                   'behavior_ready':bool(model.bh.isBehaviorReady())})
        return result


def install(hall, heroes, log):
    methods = {'_offline_log': log}
    execfile('../res/editor/client/offline_ui.py', methods)
    for name in ['select', 'write_status']:
        setattr(heroes, name, types.MethodType(getattr(methods['OfflineHeroMenu'], name).im_func, heroes))
    page = OriginalHeroPage(hall, heroes, log)
    hall.hero_page = page
    heroes.original_hero_page = page
    heroes.show = page.show
    heroes.hide = page.hide
    heroes.toggle = page.toggle
    return page
