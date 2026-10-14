# -*- coding: utf-8 -*-
"""Single entry point for the original offline city and formal hero stage."""
import json
import os
import traceback
import time
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
        # A command left by the previous debug session must not run on launch.
        try:
            self.command_id = json.load(open(COMMAND)).get('id')
            self.command_mtime = os.path.getmtime(COMMAND)
        except Exception:
            self.command_id = None
            self.command_mtime = None
        self.command_completed_id = None
        self.appearance_applied = None
        self.appearance_updates = 0
        self.bag = None
        self.practice = None
        self.status_pending = False
        self.hero_ids = sorted(int(h) for h in ClientUtils.get_hero_use(None, taste_included=False)
                               if 0 < int(h) < 1000 and hasattr(rc, 'ICON_HERO_LARGE_%04d' % int(h)))
        try:
            self.profile = json.load(open(PROFILE))
        except Exception:
            self.profile = {'hero_type':int(BigWorld.player().hero_type), 'fashion':{}, 'paint':{}, 'voice':{}, 'loadouts':[]}
        context = {}
        execfile('../res/editor/client/offline_hall.py', context)
        self.hall = context['install'](self, log)
        context = {}
        execfile('../res/editor/client/offline_practice.py', context)
        self.practice = context['install'](self)
        BigWorld.enablePlayerFade(False)
        context = {}
        execfile('../res/editor/client/offline_settings.py', context)
        self.settings = context['install'](self)
        self.scene_preload = None
        BigWorld.callback(0.3, self.preload_hall)
        BigWorld.callback(0.5, lambda: self.apply_saved_appearance(True))
        BigWorld.callback(0.5, self.place_in_hall)
        BigWorld.callback(0.5, self.poll)

    def preload_hall(self):
        # Original SpaceManager uses this engine API to pre-load a whole space.
        # Only request our small city once, never the hero preview/battle spaces.
        player = BigWorld.player()
        if player is None:
            return
        space_id = player.spaceID
        spaces = dict(BigWorld.getAllSpaceInfo())
        if 'zc_new01' not in spaces.get(space_id, ''):
            return
        start = time.clock()
        BigWorld.loadSpaceChunks(space_id)
        self.scene_preload = {'space_id':space_id, 'request_ms':round((time.clock()-start)*1000, 1)}
        self.log('City chunk preload requested once: '+repr(self.scene_preload))
        self.write_status()

    def place_in_hall(self):
        player = BigWorld.player()
        if player is None or getattr(player, 'model', None) is None:
            BigWorld.callback(0.5, self.place_in_hall)
            return
        # The original zc_new01 minimap is centred at world X/Z (52, 178).
        player.physics.teleport((52.0, 229.0, 178.0), (0.0, 0.0, 0.0))
        self.hall.hero_page.hall_pitch = 0.0
        self.hall.hero_page.hall_yaw = 0.0
        self.hall.hero_page.restore_hall_control()
        self.log('Offline player placed at central hall: '+repr(tuple(player.position)))

    def hide_map(self):
        if self.practice is not None and self.practice.active:
            return
        minimap = guiManager.get_ui('miniMap')
        if not getattr(minimap, '_offline_disabled', False):
            minimap._offline_original_methods = (minimap.real_set_visible, minimap.set_map_to_center,
                                                  minimap.minimap_can_visible)
            minimap.real_set_visible(False)
            minimap.real_set_visible = lambda value: None
            minimap.set_map_to_center = lambda: None
            minimap.minimap_can_visible = lambda: False
            minimap._offline_disabled = True
        if minimap.minimap.visible:
            minimap.minimap.visible = False

    def toggle_bag(self):
        if self.bag is None:
            context = {}
            execfile('../res/editor/client/offline_bag.py', context)
            self.bag = context['LocalBag'](self)
        self.bag.visible = not self.bag.visible

    def close_bag(self):
        if self.bag is not None and self.bag.visible:
            self.bag.visible = False
            return True
        return False

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
        BigWorld.callback(0.5, lambda: self.apply_saved_appearance(True))

    def apply_saved_appearance(self, force=False):
        player = BigWorld.player()
        if player is None or getattr(player, 'model', None) is None:
            BigWorld.callback(0.5, lambda: self.apply_saved_appearance(force))
            return
        hero_type = int(player.hero_type)
        if getattr(player, 'model_id', None) != hero_type:
            BigWorld.callback(0.5, lambda: self.apply_saved_appearance(force))
            return
        appearance = self.profile.get('appearance', {}).get(str(hero_type), {})
        fashion_id = int(appearance.get('fashion', self.profile.get('fashion', {}).get(str(hero_type), 0)) or 0)
        dye_id = int(appearance.get('dye') or 0)
        fashions = ([fashion_id] if fashion_id else []) + ([dye_id] if dye_id else []) + list(appearance.get('trinkets', []))
        marker = (player.id, hero_type, id(player.model), tuple(fashions))
        if marker == self.appearance_applied:
            return
        try:
            old = list(getattr(player, 'root_fashions', []) or [])
            if not force and old == fashions:
                self.appearance_applied = marker
                return
            player.fashions = fashions
            player.set_fashions(old)
            self.appearance_updates += 1
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
        if not self.status_pending:
            self.status_pending = True
            BigWorld.callback(0.05, self._write_status)

    def _write_status(self):
        self.status_pending = False
        try:
            result = {'state':FsmGame.state(), 'hero_type':int(BigWorld.player().hero_type),
                      'command_completed_id':self.command_completed_id,
                      'hero_count':len(self.hero_ids), 'hero_ids':self.hero_ids,
                      'last_error':self.last_error, 'hall_errors':self.hall.errors,
                      'exercise_result':self.exercise_result,
                      'fps_limit':self.settings.limit,
                      'scene_preload':self.scene_preload,
                      'practice':self.practice.status() if self.practice is not None else None,
                      'bag':{'visible':bool(self.bag.visible),
                             'item_count':sum(len(x) for x in self.bag.items.values()),
                             'categories':dict((str(k), len(v)) for k, v in self.bag.items.items()),
                             'pages_created':len(self.bag.pages)} if self.bag is not None else None,
                      'stage':self.hall.hero_page.status() if hasattr(self.hall, 'hero_page') else None}
            with open(STATUS, 'w') as stream:
                json.dump(result, stream, indent=2)
        except Exception:
            self.log(traceback.format_exc())

    def poll(self):
        try:
            if os.path.isfile(COMMAND) and os.path.getmtime(COMMAND) != self.command_mtime:
                command = json.load(open(COMMAND))
                self.command_mtime = os.path.getmtime(COMMAND)
                if command.get('id') != self.command_id:
                    self.command_id = command.get('id')
                    self.last_error = None
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
                        if command['name'] == 'settings':
                            self.exercise_result = self.settings.exercise()
                        else:
                            self.exercise_result = self.hall.hero_page.exercise(command['name'])
                    elif action == 'bag':
                        self.toggle_bag()
                    elif action == 'practice':
                        self.practice.command(command)
                    elif action == 'key':
                        import keys
                        key = getattr(keys, 'KEY_'+command['key'])
                        self.hall.hero_page.handle_menu_key(True, key, 0, 0)
                        self.hall.hero_page.handle_menu_key(False, key, 0, 0)
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
            self.command_completed_id = self.command_id
            self.write_status()
        BigWorld.callback(0.5, self.poll)


def install(log):
    global controller
    controller = LocalRuntime(log)
    controller.write_status()
    return controller
