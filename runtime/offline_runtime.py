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
        self.hero_ids = sorted(int(h) for h in ClientUtils.get_hero_use(None, taste_included=False)
                               if 0 < int(h) < 1000 and hasattr(rc, 'ICON_HERO_LARGE_%04d' % int(h)))
        try:
            self.profile = json.load(open(PROFILE))
        except Exception:
            self.profile = {'hero_type':int(BigWorld.player().hero_type), 'fashion':{}, 'paint':{}, 'voice':{}, 'loadouts':[]}
        context = {}
        execfile('../res/editor/client/offline_hall.py', context)
        self.hall = context['install'](self, log)
        BigWorld.callback(0.5, self.poll)

    def hide_map(self):
        guiManager.get_ui('miniMap').real_set_visible(False)

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

    def save(self):
        with open(PROFILE, 'w') as stream:
            json.dump(self.profile, stream, indent=2)

    def write_status(self):
        try:
            result = {'state':FsmGame.state(), 'hero_type':int(BigWorld.player().hero_type),
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
