# -*- coding: utf-8 -*-
"""Original hero portrait UI attached to the client's local offline manager."""
import json
import os
import traceback
import BigWorld
import ResMgr
import tw2
import keys
from captain import skillmanager as SK
from guis import guiManager, xnui, font, color
from guis.HeroList import HeroPageList
from helper import ClientUtils, PracticeRoomHelper
from logic import FsmGame
from system import ShortcutManager
import rc

STATUS_PATH = '../game/offline_status.json'
COMMAND_PATH = '../game/offline_command.json'
PROFILE_PATH = '../game/offline_profile.json'


class OfflineHeroMenu(object):
    def __init__(self):
        self.panel = None
        self.caption = None
        self.close_button = None
        self.open_button = None
        self.menu_key_down = False
        self.last_error = None
        self.history = []
        self.last_command_id = None
        published = sorted(int(hid) for hid in ClientUtils.get_hero_use(None, taste_included=False) if 0 < int(hid) < 1000)
        portraits = [hid for hid in published if hasattr(rc, 'ICON_HERO_64_%04d' % hid)
                     and ResMgr.fileExist(getattr(rc, 'ICON_HERO_64_%04d' % hid))]
        self.hero_ids = portraits or published
        self.make_panel()
        self.open_button = xnui.XButton(xnui.get_anchor(), 40, 45, rc.COMMON_BTN_RECT_BIG,
                                       u'\u82f1\u96c4 (H)'.encode('gbk'))
        self.open_button.visible = True
        self.open_button.topmostEx = True
        self.open_button.event_click = self.open_clicked
        self.original_key_handler = tw2.handleKeyEvent
        tw2.handleKeyEvent = self.handle_key_event
        ShortcutManager.add_key_event(keys.KEY_H, self.toggle, mode=[FsmGame.MOD_NOML, FsmGame.MOD_HERO])
        ShortcutManager.add_key_event(keys.KEY_F6, self.toggle, mode=[FsmGame.MOD_NOML, FsmGame.MOD_HERO])
        BigWorld.callback(0.5, self.poll)
        try:
            self.show()
        except Exception:
            self.last_error = traceback.format_exc()
            _offline_log(self.last_error)
            self.write_status()

    def make_panel(self):
        self.panel = HeroPageList(xnui.get_anchor(), 40, 95, count_w=10, count_h=4)
        self.panel.event_select_hero = self.select
        self.panel.setting_hero(self.hero_ids, False)
        self.panel.content_time.visible = False
        self.caption = xnui.XLabel(self.panel, 20, 12, u'\u82f1\u96c4\u5217\u8868  |  H \u6253\u5f00/\u6536\u8d77'.encode('gbk'), font.TEXT_16, color.WHITE, 0)
        self.close_button = xnui.XButton(self.panel, 780, 8, rc.COMMON_BTN_ROUND_CLOSE, '')
        self.close_button.event_click = self.close_clicked
        self.panel.visible = False
        _offline_log('Original HeroPageList created: '+str(len(self.hero_ids))+' heroes.')

    def hide_map(self):
        guiManager.get_ui('miniMap').real_set_visible(False)

    def show(self):
        self.hide_map()
        self.panel.visible = True
        self.panel.topmostEx = True
        if FsmGame.mode() != FsmGame.MOD_NOML:
            FsmGame.operate_change()
        player = BigWorld.player()
        if player is not None:
            self.panel.select(int(player.hero_type))
        self.write_status()

    def hide(self):
        self.panel.visible = False
        if FsmGame.mode() != FsmGame.MOD_HERO:
            FsmGame.operate_change()
        self.write_status()

    def toggle(self):
        if self.panel.visible:
            self.hide()
        else:
            self.show()

    def close_clicked(self, sender):
        self.hide()

    def open_clicked(self, sender):
        self.toggle()

    def handle_key_event(self, down, key, vk, mods):
        # Route only these local menu keys before the original offline manager
        # consumes the event. Other keys go through the unmodified game handler.
        if key in (keys.KEY_H, keys.KEY_F6) and not mods and FsmGame.state_is_offline():
            if down and not self.menu_key_down:
                self.menu_key_down = True
                self.toggle()
            elif not down:
                self.menu_key_down = False
            return True
        return self.original_key_handler(down, key, vk, mods)

    def select(self, hero_type):
        try:
            hero_type = int(hero_type)
            if hero_type not in self.hero_ids:
                raise ValueError('Hero is absent from local client data')
            player = BigWorld.player()
            before = int(player.hero_type)
            manager = PracticeRoomHelper.instance()
            manager.putting_ally = False
            manager.change_attacker(hero_type)
            from debug import EditorConf
            EditorConf.set('offline_hero_type', hero_type)
            with open(PROFILE_PATH, 'w') as stream:
                json.dump({'hero_type':hero_type}, stream)
            self.history.append({'before':before, 'requested':hero_type, 'after':int(BigWorld.player().hero_type)})
            self.last_error = None
            _offline_log('Local hero switch: '+str(before)+' -> '+str(hero_type))
            self.hide()
            BigWorld.callback(0.5, self.write_status)
        except Exception:
            self.last_error = traceback.format_exc()
            _offline_log(self.last_error)
            self.write_status()

    def write_status(self):
        try:
            player = BigWorld.player()
            model = getattr(player, 'model', None)
            status = {
                'state': FsmGame.state(),
                'hero_type': int(player.hero_type) if player is not None else None,
                'player_class': player.__class__.__name__ if player is not None else None,
                'hero_count':len(self.hero_ids), 'hero_ids':self.hero_ids,
                'menu_visible': bool(self.panel.visible) if self.panel is not None else False,
                'model_present':model is not None,
                'panel_size':[int(self.panel.width), int(self.panel.height)] if self.panel is not None else None,
                'switch_history':self.history[-10:], 'last_error':self.last_error,
            }
            with open(STATUS_PATH, 'w') as stream:
                json.dump(status, stream, indent=2)
        except Exception:
            _offline_log(traceback.format_exc())

    def poll(self):
        try:
            if os.path.exists(COMMAND_PATH):
                with open(COMMAND_PATH, 'r') as stream:
                    command = json.load(stream)
                command_id = command.get('id')
                if command_id != self.last_command_id:
                    self.last_command_id = command_id
                    action = command.get('action')
                    if action == 'show':
                        self.show()
                    elif action == 'hide':
                        self.hide()
                    elif action == 'switch':
                        self.select(command['hero_type'])
                    elif action == 'inspect':
                        self.write_status()
        except Exception:
            self.last_error = traceback.format_exc()
            _offline_log(self.last_error)
        BigWorld.callback(0.5, self.poll)


def install():
    global controller
    controller = OfflineHeroMenu()
