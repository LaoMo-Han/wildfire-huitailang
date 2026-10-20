# -*- coding: utf-8 -*-
"""Native monster-drop attack buff exposed by the practice F2 panel."""
from guis import xnui, guiManager
import rc


def install(practice):
    # sphere_501 Events[5017074]: (camp=1, state=506, level=1, time=30).
    # The fee is a local training option; the original buff drops from a mob.
    practice.monster_buffs = {506:{'state':((506,), 1), 'duration':(30.0,),
                                  'use_cash':300, 'cooldown':30.0},
                            # sphere_55 Events[557481]: native CD rune.
                            574:{'state':((574,), 1), 'duration':(60.0,),
                                 'use_cash':300, 'cooldown':60.0}}
    panel = guiManager.get_ui('equip_evolution')
    if not hasattr(practice, 'buff_button'):
        practice.buff_button = xnui.XButton(panel, 820, 105, rc.COMMON_BTN_RECT_BIG,
            u'\u7ea2Buff 300 / 30\u79d2'.encode('gbk'))
    practice.buff_button.text = u'\u7ea2Buff 300 / 30\u79d2'.encode('gbk')
    practice.buff_button.event_click = lambda sender: practice.guard(
        'buff_purchase', lambda: practice.purchase_buff(506))
    if not hasattr(practice, 'haste_button'):
        practice.haste_button = xnui.XButton(panel, 820, 158, rc.COMMON_BTN_RECT_BIG,
            u'\u653b\u901f\u7b26\u6587 300/60\u79d2'.encode('gbk'))
    practice.haste_button.event_click = lambda sender: practice.guard(
        'buff_purchase', lambda: practice.purchase_buff(574))
