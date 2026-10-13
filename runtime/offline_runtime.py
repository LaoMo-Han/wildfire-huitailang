# -*- coding: utf-8 -*-
"""Single entry point for the original offline city and formal hero stage."""
import json
import os
import traceback
import BigWorld
import ResMgr
import rc
from helper import ClientUtils, PracticeRoomHelper
from logic import FsmGame
from guis import guiManager

PROFILE = '../game/offline_profile.json'
STATUS = '../game/offline_status.json'
COMMAND = '../game/offline_command.json'


class LocalRuntime(object):
    def __init__(self, log):
        self.log = log
        self.last_error = None
        self.exercise_result = None
        self.command_id = None
        self.command_completed_id = None
        self.hero_ids = sorted(int(h) for h in ClientUtils.get_hero_use(None, taste_included=False)
                               if 0 < int(h) < 1000 and hasattr(rc, 'ICON_HERO_LARGE_%04d' % int(h)))
        try:
            self.profile = json.load(open(PROFILE))
        except Exception:
            self.profile = {'hero_type':int(BigWorld.player().hero_type), 'fashion':{}, 'paint':{}, 'voice':{}, 'loadouts':[]}
        context = {}
        execfile('../res/editor/client/offline_hall.py', context)
        self.hall = context['install'](self, log)
        self.appearance_applied = None
        BigWorld.callback(0.5, self.apply_saved_appearance)
        BigWorld.callback(0.5, self.poll)

    def hide_map(self):
        minimap = guiManager.get_ui('miniMap')
        if minimap.minimap.visible:
            minimap.real_set_visible(False)

    def toggle(self):
        self.hall.hero_page.toggle()

    def apply_hero(self, hero_type):
        hero_type = int(hero_type)
        if hero_type not in self.hero_ids:
            raise ValueError('Hero is not present in this client')
        manager = PracticeRoomHelper.instance()
        manager.putting_ally = False
        manager.change_attacker(hero_type)
        from debug import EditorConf
        EditorConf.set('offline_hero_type', hero_type)
        self.profile['hero_type'] = hero_type
        self.save()
        self.hall.update_hero()
        BigWorld.callback(0.5, self.apply_saved_appearance)

    def apply_saved_appearance(self):
        player = BigWorld.player()
        if player is None or getattr(player, 'model', None) is None:
            BigWorld.callback(0.5, self.apply_saved_appearance)
            return
        hero_type = int(player.hero_type)
        if getattr(player, 'model_id', None) != hero_type:
            BigWorld.callback(0.5, self.apply_saved_appearance)
            return
        appearance = self.profile.get('appearance', {}).get(str(hero_type), {})
        fashion_id = int(appearance.get('fashion', self.profile.get('fashion', {}).get(str(hero_type), 0)) or 0)
        dye_id = int(appearance.get('dye') or 0)
        fashions = ([fashion_id] if fashion_id else []) + ([dye_id] if dye_id else []) + list(appearance.get('trinkets', []))
        marker = (player.id, hero_type, tuple(fashions))
        if marker == self.appearance_applied:
            return
        try:
            old = list(getattr(player, 'root_fashions', []) or [])
            player.fashions = fashions
            player.set_fashions(old)
            self.appearance_applied = marker
            self.log('Applied local hall appearance: '+repr(fashions))
            self.write_status()
        except Exception:
            self.last_error = traceback.format_exc()
            self.log(self.last_error)

    def save(self):
        with open(PROFILE, 'w') as stream:
            json.dump(self.profile, stream, indent=2)

    def write_status(self):
        try:
            result = {'state':FsmGame.state(), 'hero_type':int(BigWorld.player().hero_type),
                      'command_completed_id':self.command_completed_id,
                      'hero_count':len(self.hero_ids), 'hero_ids':self.hero_ids,
                      'last_error':self.last_error, 'hall_errors':self.hall.errors,
                      'exercise_result':self.exercise_result,
                      'stage':self.hall.hero_page.status() if hasattr(self.hall, 'hero_page') else None}
            with open(STATUS, 'w') as stream:
                json.dump(result, stream, indent=2)
        except Exception:
            self.log(traceback.format_exc())

    def poll(self):
        try:
            if os.path.isfile(COMMAND):
                command = json.load(open(COMMAND))
                if command.get('id') != self.command_id:
                    self.command_id = command.get('id')
                    action = command.get('action')
                    if action == 'show':
                        self.hall.hero_page.show()
                    elif action == 'hide':
                        self.hall.hero_page.hide()
                    elif action == 'tab':
                        self.hall.hero_page.set_tab(command['tab'])
                    elif action == 'preview':
                        self.hall.hero_page.select(int(command['hero_type']))
                    elif action == 'apply':
                        self.hall.hero_page.apply_clicked(self.hall.hero_page.exit.btn_change_shape)
                    elif action == 'exercise':
                        self.exercise_result = self.hall.hero_page.exercise(command['name'])
                    elif action == 'reload_stage':
                        context = {}
                        execfile('../res/editor/client/hero_stage.py', context)
                        self.hall.hero_page.destroy()
                        context['install'](self.hall, self, self.log)
                    self.command_completed_id = self.command_id
                    self.write_status()
        except Exception:
            self.last_error = traceback.format_exc()
            self.log(self.last_error)
        BigWorld.callback(0.5, self.poll)


def install(log):
    global controller
    controller = LocalRuntime(log)
    controller.write_status()
    return controller
