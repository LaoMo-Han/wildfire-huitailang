# -*- coding: utf-8 -*-
# This file is executed by the game's embedded Python 2.7 interpreter.
import json
import os
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
        context = {'_offline_log': _offline_log}
        execfile('../res/editor/client/offline_ui.py', context)
        context['install']()
        try:
            hall_context = {}
            if os.path.exists('../res/editor/client/offline_hall.enabled'):
                execfile('../res/editor/client/offline_hall.py', hall_context)
                hall_context['install'](context['controller'], _offline_log)
        except Exception:
            import traceback
            _offline_log(traceback.format_exc())
    except Exception:
        import traceback
        error = traceback.format_exc()
        _offline_log(error)
        with open('../game/offline_status.json', 'w') as stream:
            json.dump({'startup_failed': True, 'last_error': error}, stream)


def _enter_offline_hall():
    try:
        from logic import FsmGame
        FsmGame.request(FsmGame.ST_OFFLINE)
        _offline_log('Entered offline state: ' + str(FsmGame.state()))
        BigWorld.callback(1.0, _install_menu)
    except Exception:
        import traceback
        _offline_log(traceback.format_exc())


_offline_log('Hero menu bootstrap loaded.')
BigWorld.callback(5.0, _enter_offline_hall)
