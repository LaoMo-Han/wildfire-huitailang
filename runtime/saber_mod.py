# -*- coding: utf-8 -*-
"""Optional local Saber appearance for Arthur (22); combat assets stay original."""
import json
import os
import ResMgr
from helper import fashiontool

CONFIG = '../game/saber_mod.json'
MODEL = 'char/mods/saber/saber_v4.model'
DUMMY = 'char/hero/0022/dummy.model'


def install(log):
    if not os.path.isfile(CONFIG):
        return False
    config = json.load(open(CONFIG))
    if not config.get('enabled', False):
        return False
    if ResMgr.openSection(MODEL) is None:
        log('Saber appearance skipped: model file is missing.')
        return False
    original = getattr(fashiontool, '_saber_original_gen_model_pathes', fashiontool.gen_model_pathes)

    def model_paths(model_id, config_data):
        if int(model_id) == 22:
            return [MODEL, DUMMY]
        return original(model_id, config_data)

    fashiontool._saber_original_gen_model_pathes = original
    fashiontool.gen_model_pathes = model_paths
    log('Saber appearance enabled for Arthur (22).')
    return True
