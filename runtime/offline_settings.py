# -*- coding: utf-8 -*-
"""Extend the client's existing FPS step slider, retaining Apply/Cancel."""
import BigWorld
from guis import guiManager
from system import AppSetting

FPS_LIMITS = (60, 80, 120, 144, 165, 240, 0)


class LocalSettings(object):
    def __init__(self, runtime):
        self.runtime = runtime
        self.ui = guiManager.get_ui('sys_menu')
        self.original_set_visible = self.ui.set_visible
        self.ui.set_visible = self.set_visible
        self.setting = None
        value = runtime.profile.get('fps_limit', 80)
        self.limit = value if value in FPS_LIMITS else 80
        BigWorld.limitForegroundFPS(self.limit)
        # SysMenu initialises all native settings in its next-frame callback.
        BigWorld.callback(0.2, self.bind)

    def set_visible(self, value):
        position = BigWorld.getCursorPos() if not value else None
        result = self.original_set_visible(value)
        # Finish the native visibility/mode callbacks before restoring the
        # offline page's input policy. Keep native Apply and Cancel intact.
        BigWorld.callback(0.0, lambda: self.restore_page_input(position))
        return result

    def restore_page_input(self, position=None):
        stage = self.runtime.hall.hero_page
        if not stage.closed:
            stage.sync_input_mode()
            if position is not None and stage.cursor_shown:
                import C_ui
                C_ui.cursor_pos(*position)
                C_ui.set_cursor_pos(*position)

    def bind(self):
        setting = AppSetting.get_setting('LimitFpsSetting')
        if setting is None or self.ui.in_init:
            BigWorld.callback(0.2, self.bind)
            return
        self.setting = setting
        unlimited_label = setting.items[-1]
        setting.items = [str(x) + ' FPS' if x else unlimited_label for x in FPS_LIMITS]
        setting.default_value = 1
        owner = self

        def load(panel, order=None):
            panel.value = FPS_LIMITS.index(owner.limit)
            panel.value_changed = True

        def apply(panel):
            index = int(panel.value)
            if not 0 <= index < len(FPS_LIMITS):
                index = 1
            owner.limit = FPS_LIMITS[index]
            BigWorld.limitForegroundFPS(owner.limit)
            owner.runtime.write_status()

        def save(panel):
            # Save an actual rate, not an index tied to this extended list.
            owner.runtime.profile['fps_limit'] = owner.limit
            owner.runtime.save()

        def cancel(panel):
            saved = owner.runtime.profile.get('fps_limit', 80)
            owner.limit = saved if saved in FPS_LIMITS else 80
            load(panel)
            BigWorld.limitForegroundFPS(owner.limit)
            panel.value_changed = False

        for name, function in [('load', load), ('apply', apply), ('save', save), ('cancel', cancel)]:
            AppSetting.bound_instance_method(setting, name, function)
        load(setting)
        setting.present()
        apply(setting)
        self.runtime.log('Original video FPS selector ready: '+repr(FPS_LIMITS))

    def exercise(self):
        panel = self.setting
        if panel is None:
            raise RuntimeError('Native video settings are not ready')
        original = self.limit
        rates = []
        for index, rate in enumerate(FPS_LIMITS):
            panel.value = index
            panel.apply()
            rates.append(self.limit)
        panel.cancel()
        cancelled = self.limit
        panel.value = FPS_LIMITS.index(144)
        panel.apply()
        panel.save()
        panel.value = 0
        panel.load()
        reloaded = FPS_LIMITS[panel.value]
        panel.value = FPS_LIMITS.index(original)
        panel.apply()
        panel.save()
        panel.present()
        return {'rates':rates, 'cancelled':cancelled, 'reloaded':reloaded,
                'restored':self.limit, 'item_count':len(panel.items)}


def install(runtime):
    return LocalSettings(runtime)
