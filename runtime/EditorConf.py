# -*- coding: utf-8 -*-
# This file is executed by the game's embedded Python 2.7 interpreter.
import json
import BigWorld

data = {'offline_hero_type': 3, 'create_offline_enemy': False, 'allow_ui_preview': False}
try:
    profile = json.load(open('../game/offline_profile.json', 'r'))
    data['offline_hero_type'] = int(profile.get('hero_type', 3))
except Exception:
    pass


def _offline_log(message):
    try:
        with open('../game/offline_bootstrap.log', 'a') as stream:
            stream.write(message + '\n')
    except Exception:
        pass


def _install_menu():
    try:
        context = {}
        execfile('../res/editor/client/offline_runtime.py', context)
        context['install'](_offline_log)
    except Exception:
        import traceback
        error = traceback.format_exc()
        _offline_log(error)
        with open('../game/offline_status.json', 'w') as stream:
            json.dump({'startup_failed': True, 'last_error': error}, stream)


def _hall_ground_ready():
    try:
        spawn = {}
        execfile('../res/editor/client/offline_spawn.py', spawn)
        player = BigWorld.player()
        point = spawn['place'](player)
        if point is None:
            # Stay behind the native loading screen until collision is ready.
            BigWorld.callback(0.1, _hall_ground_ready)
            return
        _offline_log('Initial hall ground spawn: '+repr(point))
        _install_menu()
    except Exception:
        import traceback
        _offline_log(traceback.format_exc())


def _enter_offline_hall():
    try:
        from logic import FsmGame
        from debug import DebugManager
        FsmGame.init()
        manager = DebugManager.instance
        spawn = {}
        execfile('../res/editor/client/offline_spawn.py', spawn)
        original_teleport = manager.teleport
        def initial_teleport(scene, position, callback=None):
            # The archived DebugManager.enter still requests its old high seed.
            # Substitute before the first teleport, not after the player falls.
            if scene == spawn['SCENE']:
                position = spawn['POSITION']
                callback = _hall_ground_ready
            same_space = manager.cSpaceName == scene
            result = original_teleport(scene, position, callback)
            if same_space and callback is not None:
                BigWorld.callback(0.0, callback)
            return result
        manager.teleport = initial_teleport
        try:
            FsmGame.request(FsmGame.ST_OFFLINE)
        finally:
            manager.teleport = original_teleport
        _offline_log('Entered offline state: ' + str(FsmGame.state()))
    except Exception:
        import traceback
        _offline_log(traceback.format_exc())


_offline_log('Formal hero stage bootstrap loaded.')
BigWorld.callback(5.0, _enter_offline_hall)
