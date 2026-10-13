# -*- coding: utf-8 -*-
# Local configuration for this separate offline experiment. Python 2.7 syntax.
data = {
    'offline_hero_type': 3,
    'create_offline_enemy': False,
    'allow_ui_preview': False,
}

import BigWorld


def _offline_log(message):
    try:
        with open('../game/offline_bootstrap.log', 'a') as stream:
            stream.write(message + '\n')
    except Exception:
        pass


def _enter_offline_hall():
    try:
        from logic import FsmGame
        _offline_log('Requesting the existing local ST_OFFLINE state.')
        FsmGame.request(FsmGame.ST_OFFLINE)
        _offline_log('Request completed; resulting state: ' + str(FsmGame.state()))
    except Exception:
        import traceback
        _offline_log(traceback.format_exc())


_offline_log('Local EditorConf loaded; scheduling offline entry.')
BigWorld.callback(5.0, _enter_offline_hall)
