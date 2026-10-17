# -*- coding: utf-8 -*-
"""Original practice entry and arena, running entirely in ST_OFFLINE."""
import traceback
import BigWorld
import keys
from guis import factory, guiManager, SysBox
from guis.city.PracticeEntry import PracticeEntry
from helper import ClientUtils, PracticeRoomHelper
from logic import FsmGame


class LocalEntry(PracticeEntry):
    def __init__(self, owner):
        self.owner = owner
        PracticeEntry.__init__(self)
        self.btn_moba.enabled = False
        self.btn_fps.enabled = False
        self.visible = False

    def set_visible(self, value):
        # The city implementation expects a connected PlayerAvatar account.
        factory.PracticeEntry.set_visible(self, value)

    def _on_btn_practice_click(self, sender):
        self.owner.enter()

    def _on_btn_moba_click(self, sender):
        pass

    def _on_btn_fps_click(self, sender):
        pass


class LocalPractice(object):
    SCENE = 'zd_gangtyztest'
    SPAWN = (-0.22, 0.07, -4.15)
    TARGET_SPAWN = (0.37, 0.07, 3.94)
    PANELS = ('practice_toolbar', 'practice_damage_dlg', 'practice_lvup_prompt',
              'battle_hp', 'battle_skill', 'battle_item_dlg', 'equip_evolution_v2', 'tipkey_panel', 'miniMap')
    MODALS = ('skill_desc_dlgb', 'equip_evolution',
              'practice_sp_part', 'combo_main_dlg', 'practice_dress_dlg')

    def __init__(self, runtime):
        self.runtime = runtime
        self.active = False
        self.no_cooldown = False
        self.loading = False
        self.entry = None
        self.target_id = None
        self.target_type = 3
        self.ai_difficulty = 'low'
        self.evolutions = {}
        self.purchase_history = []
        self.equipment_category = None
        self.ai = False
        self.keys_down = set()
        self.errors = {}
        self.return_scene = None
        self.saved_gui = {}
        self.last_safe_position = None
        self.toolbar = guiManager.get_ui('practice_toolbar')
        self.helper = PracticeRoomHelper.instance()
        # Startup already registers practice shortcuts even while hiding its UI.
        # Route them through the local menu listener, with no server calls.
        self.toolbar.unregister_shortcuts()
        self.toolbar.on_hero_select = self.select_hero
        self.toolbar.hero_list.on_hero_select = self.select_hero
        self.toolbar.btn_reset.event_click = lambda sender: self.reset()
        self.toolbar.btn_toggle_ai.event_click = lambda sender: self.toggle_ai()
        self.helper.change_target = self.change_target
        self.helper.get_target = self.get_target
        self.helper.toggle_target_ai = self.toggle_ai
        self.helper.reset = self.reset
        self.helper.reset_impl = self.reset
        self.install_damage_hook()
        self.install_skill_hook()
        self.install_local_combat()
        self.install_equipment_hooks()
        self.install_difficulty_buttons()
        self.install_toolbar_buttons()
        self.disable_debug_map_keys()
        self.enable_cooldowns()
        BigWorld.callback(0.25, self.tick)

    @property
    def engaged(self):
        return self.active or self.loading or bool(self.entry is not None and self.entry.visible)

    def guard(self, name, function):
        try:
            result = function()
            self.errors.pop(name, None)
            return result
        except Exception:
            self.errors[name] = traceback.format_exc()
            self.runtime.last_error = self.errors[name]
            self.runtime.log(self.errors[name])
            if name in ('enter', 'ready', 'leave', 'returned'):
                self.loading = False
            self.runtime.write_status()

    def toggle_entry(self):
        if self.active or self.loading:
            return
        if self.entry is None:
            self.entry = LocalEntry(self)
        if self.entry.visible:
            self.close_entry()
            return
        stage = self.runtime.hall.hero_page
        if stage.visible:
            stage.hide()
        self.runtime.close_bag()
        self.runtime.hall.close_chat()
        stage.capture_hall_camera()
        self.entry.enter_lock = False
        self.entry.visible = True
        self.entry.topmostEx()
        FsmGame.init().mode = FsmGame.MOD_NOML
        self.runtime.write_status()

    def close_entry(self):
        if self.entry is not None:
            self.entry.visible = False
        self.runtime.hall.hero_page.restore_hall_control()
        self.runtime.write_status()

    def enter(self):
        if self.active or self.loading:
            return
        self.guard('enter', self._enter)

    def _enter(self):
        from debug import DebugManager
        player = BigWorld.player()
        manager = DebugManager.instance
        self.return_scene = manager.cSpaceName
        self.return_position = tuple(player.position)
        self.errors.clear()
        self.return_level = int(player.lv)
        self.return_cash = int(player.cash)
        self.return_health = (player.mhp, player.hp)
        self.return_cd_check = getattr(player, 'test_do_cd_check', False)
        self.return_equs = dict(player.equs)
        self.evolutions = {}
        self.purchase_history = []
        self.arena_spawn = self.SPAWN
        self.target_spawn = self.TARGET_SPAWN
        self.base_equipment_stats = dict(player.equs)
        guiManager.get_ui('equip_evolution').clear()
        guiManager.get_ui('equip_evolution_v2').reset()
        self.runtime.hall.hero_page.capture_hall_camera()
        self.return_camera = (self.runtime.hall.hero_page.hall_pitch,
                              self.runtime.hall.hero_page.hall_yaw)
        if self.entry is not None:
            self.entry.visible = False
        self.runtime.close_bag()
        self.runtime.hall.close_chat()
        self.saved_gui = dict((name, bool(part.visible)) for name, part in guiManager.instance().elements.items()
                              if hasattr(part, 'visible'))
        for part in self.runtime.hall.parts.values():
            part.visible = False
        self.loading = True
        self.active = True
        self.teleport_scene(self.SCENE, self.SPAWN, self.ready)
        self.runtime.write_status()

    def ready(self):
        self.ready_attempts = 0
        BigWorld.loadSpaceChunks(BigWorld.player().spaceID)
        self.try_ready()

    def try_ready(self):
        if not self.active:
            return
        try:
            self.arena_spawn, self.target_spawn = self.grounded_spawns(self.SPAWN, self.TARGET_SPAWN)
        except ValueError:
            self.ready_attempts += 1
            if self.ready_attempts < 30:
                BigWorld.player().physics.teleport(self.SPAWN, (0.0, 0.0, 0.0))
                BigWorld.callback(0.5, self.try_ready)
                return
            self.guard('ready', self._ready)
            return
        self.guard('ready', self._ready)

    def teleport_scene(self, scene, position, callback):
        from debug import DebugManager
        manager = DebugManager.instance
        # DebugManager returns without invoking the callback for the same space.
        same_space = manager.cSpaceName == scene
        manager.teleport(scene, position, callback)
        if same_space:
            BigWorld.callback(0.0, callback)

    def _ready(self):
        player = BigWorld.player()
        self.loading = False
        self.helper.is_active = True
        self.helper.is_in_combo_teach_sphere = False
        self.toolbar.visible = True
        self.toolbar.player_use_heros = list(self.runtime.hero_ids)
        from common_data import practice_bot_config_data
        self.toolbar.bot_use_heros = sorted(set(self.runtime.hero_ids).intersection(practice_bot_config_data.data))
        self.toolbar.btn_toggle_ai.enabled = True
        player.physics.teleport(self.arena_spawn, (0.0, 0.0, 0.0))
        self.last_safe_position = self.arena_spawn
        self.helper.reset_damage_accumulation()
        self.enable_cooldowns()
        self.set_level(1)
        self.set_cash(90000)
        self.recover(player)
        self.change_target(self.target_type)
        for name in self.PANELS:
            if name != 'miniMap':
                guiManager.get_ui(name).visible = True
        self.set_map_enabled(True)
        for name in ('city_fps_bar', 'city_board_dlg', 'welcome'):
            part = guiManager.instance().elements.get(name)
            if part is not None and hasattr(part, 'visible'):
                part.visible = False
        self.toolbar.hero_list.visible = False
        self.runtime.hall.hero_page.cursor_shown = False
        self.restore_control()
        self.runtime.apply_saved_appearance(True)
        self.runtime.log('Local practice arena ready: '+self.SCENE)
        self.runtime.write_status()

    def set_map_enabled(self, enabled):
        minimap = guiManager.get_ui('miniMap')
        if enabled and getattr(minimap, '_offline_disabled', False):
            (minimap.real_set_visible, minimap.set_map_to_center,
             minimap.minimap_can_visible) = minimap._offline_original_methods
            minimap._offline_disabled = False
        if enabled:
            minimap.visible = True
            minimap.change_mode()
            minimap.real_set_visible(True)
        else:
            self.runtime.hide_map()

    def restore_control(self):
        stage = self.runtime.hall.hero_page
        stage.restore_hall_control()
        if self.active:
            stage.hall_pitch = 0.0
            stage.hall_yaw = 0.0
            BigWorld.dcursor().yaw = 0.0
            BigWorld.dcursor().pitch = 0.0

    def get_target(self):
        return BigWorld.entities.get(self.target_id) if self.target_id is not None else None

    def change_target(self, hero_type):
        from debug import DebugManager
        self.target_type = int(hero_type)
        target = self.get_target()
        if target is not None:
            BigWorld.destroyEntity(target.id)
        self.target_id = None
        self.ai = False
        self.toolbar.btn_toggle_ai.state = 'nml'
        target = DebugManager.instance.create_target(1, 'PracticeAIHero', 60000, self.target_type,
            getattr(self, 'target_spawn', self.TARGET_SPAWN))[0]
        self.target_id = target.id
        target.roleName = ClientUtils.get_hero_name(self.target_type)
        target.face_to_position(BigWorld.player().position)
        self.runtime.write_status()

    def install_difficulty_buttons(self):
        chooser = self.toolbar.difficulty_choose
        chooser.btn_easy.event_click = lambda sender: self.set_difficulty('low')
        chooser.btn_normal.event_click = lambda sender: self.set_difficulty('mid')
        chooser.btn_hard.event_click = lambda sender: self.set_difficulty('high')

    def set_difficulty(self, difficulty):
        self.ai_difficulty = difficulty
        chooser = self.toolbar.difficulty_choose
        for name, mode in [('btn_easy', 'low'), ('btn_normal', 'mid'), ('btn_hard', 'high')]:
            getattr(chooser, name).enabled = difficulty != mode
        if self.ai:
            self.toggle_ai()
            self.toggle_ai()
        self.runtime.write_status()

    def select_hero(self, hero_type):
        if not self.active or int(hero_type) not in self.runtime.hero_ids:
            return
        def select():
            if self.helper.is_selecting_attacker:
                self.runtime.apply_hero(int(hero_type))
                self.toolbar.set_selection(2)
            else:
                self.change_target(int(hero_type))
                self.toolbar.set_selection(3)
            self.reset(False)
            self.enable_cooldowns()
        self.guard('selection', select)

    def recover(self, entity):
        entity.hp = entity.mhp
        entity.set_hp(0)

    def set_cash(self, cash):
        player = BigWorld.player()
        player._cash_internal = int(cash)
        player.set_cash(0)

    def reset(self, clear_evo_and_lv=False):
        if not self.active or self.loading:
            return
        self.guard('reset', lambda: self._reset(clear_evo_and_lv))

    def _reset(self, clear_evo_and_lv):
        self.combat.clear()
        self.helper.clear_all()
        self.helper.force_update_mana()
        self.helper.reset_damage_accumulation()
        player = BigWorld.player()
        from captain import cdmgr
        player._skill_cd.clear()
        cdmgr.reset()
        guiManager.get_ui('battle_skill').update_cd()
        self.enable_cooldowns()
        self.refill_skill_resources()
        self.equipment_category = None
        guiManager.get_ui('equip_evolution_v2').hide_popup()
        player.physics.teleport(getattr(self, 'arena_spawn', self.SPAWN), (0.0, 0.0, 0.0))
        self.recover(player)
        ai = self.ai
        self.change_target(self.target_type)
        if ai:
            self.toggle_ai()
        if clear_evo_and_lv:
            self.set_level(1)
            guiManager.get_ui('equip_evolution').clear()
            guiManager.get_ui('equip_evolution_v2').reset()
            self.evolutions = {}
            self.purchase_history = []
            self.update_equipment_stats()
            self.set_cash(90000)
            self.recover(player)
        if self.toolbar.combo_mgr.is_combo_practice_on:
            self.toolbar.combo_mgr.combo_reset()
        from hook import hero_hooker
        hero_hooker(player.hero_type, 'on_practice_reset', player)
        self.restore_control()
        self.runtime.write_status()

    def refill_skill_resources(self):
        player = BigWorld.player()
        manager = getattr(player, 'mana', None)
        if manager is not None:
            manager.clear_pending_skill()
            for identity, resource in manager.mana.items():
                total = resource._mana_total_amount
                if total is not None:
                    resource._skill_timer_end()
                    manager.set_curr(identity, total)
                    resource.update()
        player.client_start_auto_skill()
        guiManager.get_ui('battle_skill').update_skill()

    def set_level(self, level):
        player = BigWorld.player()
        old = player.lv
        player.lv = max(1, min(16, int(level)))
        player.set_lv(old)

    def enable_cooldowns(self):
        # captain.cdmgr.check and the HUD consume the same cooldown clock.
        from captain import cdmgr
        manager = cdmgr.instance()
        manager.init_hero()
        # Missing entries fail the original readiness check. Offline startup
        # never receives the server's initial ready cooldown set.
        for skill_id, duration in manager.dict_base_cd.items():
            manager.dict_now_cd.setdefault(skill_id, (0, duration))
        BigWorld.player().test_do_cd_check = not self.cooldowns_disabled()

    def cooldowns_disabled(self):
        return FsmGame.state_is_offline() and (not self.active or getattr(self, 'no_cooldown', False))

    def toggle_no_cooldown(self):
        if not self.active or self.loading:
            return
        self.no_cooldown = not getattr(self, 'no_cooldown', False)
        from captain import cdmgr
        cdmgr.reset()
        self.enable_cooldowns()
        guiManager.get_ui('battle_skill').update_cd()
        self.update_cooldown_button()
        self.runtime.write_status()

    def update_cooldown_button(self):
        self.cooldown_button.text = (u'\u65e0CD\uff1a\u5f00 F7' if getattr(self, 'no_cooldown', False)
                                     else u'\u65e0CD\uff1a\u5173 F7').encode('gbk')

    def toolbar_action(self, action):
        if not self.active or self.loading:
            return
        def run():
            self.equipment_category = None
            guiManager.get_ui('equip_evolution_v2').hide_popup()
            if isinstance(action, int):
                keep = {0:'skill_desc_dlgb', 1:'equip_evolution', 4:'practice_sp_part'}.get(action)
                for name in self.MODALS:
                    if name != keep:
                        guiManager.get_ui(name).visible = False
                self.toolbar.set_selection(action)
                if keep is not None:
                    part = guiManager.get_ui(keep)
                    if part.visible:
                        part.topmostEx()
            elif action == 'combo':
                self.toolbar._toggle_combo()
            elif action == 'ai':
                self.toggle_ai()
            elif action == 'reset':
                self.reset()
            elif action == 'no_cooldown':
                self.toggle_no_cooldown()
            self.runtime.hall.hero_page.restore_hall_control()
        self.guard('toolbar', run)
        self.runtime.write_status()

    def install_toolbar_buttons(self):
        from guis import xnui
        import rc
        if not hasattr(self, 'toolbar_sensors'):
            self.toolbar_sensors = {}
        for name, action in [('btn_show_hint', 0), ('btn_equip', 1),
                             ('btn_select_attacker', 2), ('btn_select_target', 3),
                             ('btn_select_skill', 4), ('btn_combo', 'combo'),
                             ('btn_toggle_ai', 'ai'), ('btn_reset', 'reset')]:
            button = getattr(self.toolbar, name)
            button.event_click = lambda sender, action=action: self.toolbar_action(action)
            if isinstance(button, xnui.XPolymImage):
                if name not in self.toolbar_sensors:
                    self.toolbar_sensors[name] = xnui.XSelect(button.parent, button.coord[0], button.coord[1],
                        button.width, button.height, 0, 0)
                self.toolbar_sensors[name].event_click = button.event_click
        if not hasattr(self, 'map_button'):
            last = self.toolbar.btn_reset
            self.map_button = xnui.XButton(self.toolbar, last.coord[0]+last.width+4, last.coord[1],
                rc.COMMON_BTN_RECT_BIG, u'\u9009\u62e9\u5730\u56fe'.encode('gbk'))
        self.map_button.event_click = lambda sender: self.toggle_maps()
        if not hasattr(self, 'cooldown_button'):
            first = self.toolbar.btn_show_hint
            self.cooldown_button = xnui.XButton(self.toolbar, first.coord[0], first.coord[1]+first.height+4,
                rc.COMMON_BTN_RECT_BIG, '')
        self.cooldown_button.event_click = lambda sender: self.toolbar_action('no_cooldown')
        self.update_cooldown_button()

    def toggle_maps(self):
        if not self.active or self.loading:
            return
        if not hasattr(self, 'map_dialog'):
            from debug.UniverseSelectionDlg import SelectionDlg
            owner = self
            class LocalMaps(SelectionDlg):
                def load_universes(dialog):
                    from guis import xnui
                    import rc
                    rows = owner.map_catalog()
                    dialog.map_buttons = []
                    dialog.universe_panel = xnui.XScrollMaskPanel(dialog, 0, 44, 380,
                        dialog.height-98, 380, max(1, len(rows))*50)
                    guiManager.instance().on_ui_active(dialog.universe_panel)
                    for index, (scene, title) in enumerate(rows):
                        button = xnui.XButton(dialog.universe_panel, 60, index*50,
                            rc.COMMON_BTN_RECT_BIG, title)
                        button.scene_name = scene
                        dialog.map_buttons.append(button)
                        button.event_click = lambda sender, scene=scene: owner.change_map(scene)
                def on_btn_universe_clicked(dialog, sender):
                    owner.change_map(sender.text.rstrip())
                def on_btn_close_clicked(dialog, sender):
                    dialog.visible = False
                    guiManager.use_mouse(dialog, False)
                    owner.restore_control()
            self.map_dialog = LocalMaps()
            self.map_dialog.visible = False
        self.map_dialog.visible = not self.map_dialog.visible
        if self.map_dialog.visible:
            for name in self.MODALS:
                guiManager.get_ui(name).visible = False
            self.toolbar.hero_list.visible = False
        guiManager.use_mouse(self.map_dialog, self.map_dialog.visible)
        if self.map_dialog.visible:
            self.map_dialog.topmostEx()
        self.restore_control()

    def map_catalog(self):
        import MapConfig
        import ResMgr
        available = set(name[:-4] if name.endswith('.bag') else name
                        for name in ResMgr.openSection('universes')['eg'].keys())
        rows = {}
        for number in sorted(MapConfig.SpaceDict):
            config = MapConfig.SpaceDict[number]
            scene = config['map'].rsplit('/', 1)[-1]
            if scene in available and scene not in rows:
                rows[scene] = u'\u7ec3\u4e60\u573a'.encode('gbk') if scene == self.SCENE else config['name']
        return sorted(rows.items(), key=lambda row: row[1])

    def map_seed(self, scene):
        import MapConfig
        for number in sorted(MapConfig.SpaceDict):
            config = MapConfig.SpaceDict[number]
            if config['map'].rsplit('/', 1)[-1] != scene:
                continue
            try:
                module = __import__('cdata.spheres.sphere_'+str(number), fromlist=['data'])
            except ImportError:
                continue
            points = module.data.get('RelivePoints', {})
            point = points.get((1, 1))
            if point is not None:
                pos = tuple(point['position'])
                return (pos[0], pos[1]+0.1, pos[2])
            pos = module.data.get('start_pos')
            if pos is not None:
                return tuple(pos)
        return self.SPAWN if scene == self.SCENE else (0.0, 2.0, 0.0)

    def grounded_spawns(self, player_seed, target_seed):
        player = BigWorld.player()
        def ground(seed, extra):
            x, y, z = seed
            # Start above the recorded floor, avoiding ceilings far above it.
            hit = ClientUtils.get_collide_info(player.spaceID, (x, y+1.0, z),
                (x, y-30.0, z), comp_collide=False)
            if hit is None:
                raise ValueError('Map collision is not ready at its spawn')
            return (x, hit.position[1]+extra, z)
        player_spawn = ground(player_seed, 0.05)
        try:
            target_spawn = ground(target_seed, 0.05)
        except ValueError:
            x, y, z = player_spawn
            for dx, dz in ((0, -3), (3, 0), (-3, 0), (0, 0)):
                try:
                    target_spawn = ground((x+dx, y, z+dz), 0.05)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError('Map collision is not ready near its spawn')
        return player_spawn, target_spawn

    def change_map(self, scene):
        if not self.active or self.loading:
            return
        from debug import DebugManager
        if scene not in dict(self.map_catalog()):
            from system import MsgManager
            MsgManager.show(text=u'\u672c\u5730\u5ba2\u6237\u7aef\u7f3a\u5c11\u8fd9\u5f20\u5730\u56fe\u7684\u8d44\u6e90'.encode('gbk'))
            return
        if scene == DebugManager.instance.cSpaceName:
            return
        if hasattr(self, 'map_dialog'):
            self.map_dialog.visible = False
            guiManager.use_mouse(self.map_dialog, False)
        self.loading = True
        self.map_ai = self.ai
        player = BigWorld.player()
        self.map_player_state = (int(player.lv), int(player.cash), int(player.realSPSkill))
        self.map_previous_scene = DebugManager.instance.cSpaceName
        self.map_player_seed = self.map_seed(scene)
        x, y, z = self.map_player_seed
        self.map_target_seed = (x, y, z+5.0)
        self.combat.clear()
        self.helper.clear_all()
        self.target_id = None
        self.teleport_scene(scene, self.map_player_seed, self.map_ready)

    def map_ready(self):
        self.map_attempts = 0
        BigWorld.loadSpaceChunks(BigWorld.player().spaceID)
        BigWorld.callback(0.5, self.try_map_ready)

    def try_map_ready(self):
        if not self.active or not self.loading:
            return
        self.map_attempts += 1
        try:
            self._map_ready()
            self.errors.pop('map', None)
        except ValueError:
            if self.map_attempts < 30:
                BigWorld.player().physics.teleport(self.map_player_seed, (0.0, 0.0, 0.0))
                BigWorld.callback(0.5, self.try_map_ready)
                return
            self.loading = False
            from debug import DebugManager
            if DebugManager.instance.cSpaceName != self.SCENE:
                self.loading = True
                self.map_player_seed, self.map_target_seed = self.SPAWN, self.TARGET_SPAWN
                self.teleport_scene(self.SCENE, self.SPAWN, self.map_ready)
            else:
                self.arena_spawn, self.target_spawn = self.SPAWN, self.TARGET_SPAWN
                self.reset()
                self.restore_control()
        except Exception:
            self.loading = False
            self.errors['map'] = traceback.format_exc()
            self.runtime.last_error = self.errors['map']
            self.runtime.log(self.errors['map'])
            self.runtime.write_status()

    def _map_ready(self):
        player = BigWorld.player()
        self.arena_spawn, self.target_spawn = self.grounded_spawns(self.map_player_seed, self.map_target_seed)
        self.last_safe_position = self.arena_spawn
        player.physics.teleport(self.arena_spawn, (0.0, 0.0, 0.0))
        self.loading = False
        level, cash, sp_skill = self.map_player_state
        self.set_level(level)
        self.set_cash(cash)
        old_sp = player.realSPSkill
        player.realSPSkill = sp_skill
        player.set_realSPSkill(old_sp)
        self.enable_cooldowns()
        self.update_equipment_stats()
        self.recover(player)
        self.change_target(self.target_type)
        if self.map_ai:
            self.toggle_ai()
        for name in self.PANELS:
            if name != 'miniMap':
                guiManager.get_ui(name).visible = True
        self.set_map_enabled(True)
        self.restore_control()
        self.runtime.write_status()

    def disable_debug_map_keys(self):
        from debug import DebugManager
        from system import ShortcutManager
        manager = DebugManager.instance
        modes = [FsmGame.MOD_NOML, FsmGame.MOD_HERO]
        ShortcutManager.del_key_event(keys.KEY_1, manager.toggle_teleport_local, modes, FsmGame.ST_OFFLINE)
        ShortcutManager.del_key_event(keys.KEY_GRAVE, manager.toggle_teleport_space, modes, FsmGame.ST_OFFLINE)

    def equipment_number(self, index):
        bar = guiManager.get_ui('equip_evolution_v2')
        if guiManager.get_ui('equip_evolution').visible:
            return
        if self.toolbar.hero_list.visible:
            self.toolbar.hero_list.visible = False
        category = getattr(self, 'equipment_category', None)
        if category is None or not bar.popup_part.logic_visible:
            if index >= len(bar.toolbar_part.evo_btns):
                return
            bar.hide_popup()
            bar.select_category(index)
            self.equipment_category = index
            return
        button = bar.toolbar_part.evo_btns[category]
        bar.move_to_last()
        choices = list(bar.get_curr_evo_ids(button))
        if index >= len(choices):
            return
        before = dict(self.evolutions)
        self.purchase_equipment(choices[index])
        if self.evolutions != before:
            bar.hide_popup()
            self.equipment_category = None

    def toggle_ai(self):
        if self.active:
            self.ai = not self.ai
            self.toolbar.btn_toggle_ai.state = 'ovr' if self.ai else 'nml'
            target = self.get_target()
            if target is not None:
                if self.ai:
                    from common_data import practice_bot_config_data
                    config = practice_bot_config_data.data.get(self.target_type, {})
                    difficulty = getattr(self, 'ai_difficulty', 'low')
                    for trigger in list(target.triggerSystem._triggers):
                        target.triggerSystem.uninstall(trigger)
                    for trigger in config.get(difficulty+'_triggers', ()):
                        target.triggerSystem.install(target, trigger)
                    target.startOfflineAI(0, config[difficulty+'_btname'])
                    target.hateCtrlr.doDamage(target, BigWorld.player(), 1)
                else:
                    target.onControlled(False)
            self.runtime.write_status()
        return True

    def install_damage_hook(self):
        from Hero import Hero
        if not hasattr(Hero, '_offline_original_max_level'):
            Hero._offline_original_max_level = Hero.getMaxLevel
            Hero._offline_original_got_damage = Hero.got_damage
        original = Hero._offline_original_got_damage
        while getattr(original, 'func_code', None) is not None and original.func_code.co_filename.endswith('offline_practice.py'):
            closed = dict(zip(original.func_code.co_freevars, [cell.cell_contents for cell in original.func_closure or ()]))
            if 'original' not in closed:
                break
            original = closed['original']
        Hero._offline_original_got_damage = original
        Hero.got_damage = original
        max_level = Hero._offline_original_max_level
        owner = self
        def get_max_level(entity):
            return 16 if owner.active else max_level(entity)
        Hero.getMaxLevel = get_max_level

    def install_skill_hook(self):
        from captain import cdmgr
        owner = self
        if not hasattr(cdmgr, '_offline_original_update'):
            cdmgr._offline_original_update = cdmgr.update
        def update(skill_id, cd, use_time):
            # Keep the HUD and readiness clock in agreement, including skills
            # whose cooldown begins at the end of a channel or via hero hooks.
            if owner.cooldowns_disabled():
                use_time = 0
            return cdmgr._offline_original_update(skill_id, cd, use_time)
        cdmgr.update = update
        from guis.battle.PracticeSpPart import SpaceBox
        owner = self
        if not hasattr(SpaceBox, '_offline_original_click'):
            SpaceBox._offline_original_click = SpaceBox.on_sensor_click
        def clicked(box, sender):
            if not owner.active:
                return SpaceBox._offline_original_click(box, sender)
            def select():
                player = BigWorld.player()
                old = player.realSPSkill
                player.realSPSkill = int(box.skill_id)
                player.set_realSPSkill(old)
                owner.toolbar.set_selection(4)
                owner.reset()
            owner.guard('sp_skill', select)
        SpaceBox.on_sensor_click = clicked

    def install_local_combat(self):
        if hasattr(self, 'combat'):
            self.combat.clear()
        context = {}
        execfile('../res/editor/client/offline_combat.py', context)
        self.combat = context['LocalCombat'](self)

    def install_equipment_hooks(self):
        import types
        owner = self
        full = guiManager.get_ui('equip_evolution')
        bar = guiManager.get_ui('equip_evolution_v2')
        for panel, name in [(full, 'active_evo'), (bar, 'on_item_evolved')]:
            if not hasattr(panel, '_offline_original_evolve'):
                panel._offline_original_evolve = getattr(panel, name)
            def evolved(panel_self, evo_id):
                if not owner.active or getattr(owner, 'equipment_syncing', False):
                    return panel_self._offline_original_evolve(evo_id)
                owner.guard('equipment', lambda: owner.purchase_equipment(evo_id))
            setattr(panel, name, types.MethodType(evolved, panel, panel.__class__))
        if not hasattr(full, '_offline_original_revert'):
            full._offline_original_revert = full.revert_evo
        def reverted(panel_self, old_evo_id, new_evo_id):
            if not owner.active or getattr(owner, 'equipment_syncing', False):
                return panel_self._offline_original_revert(old_evo_id, new_evo_id)
            if panel_self.visible:
                owner.guard('sell', lambda: owner.sell_equipment(old_evo_id, new_evo_id))
        full.revert_evo = types.MethodType(reverted, full, full.__class__)
        for name in ('quick_revert', 'on_evo_revert'):
            original_name = '_offline_original_'+name
            if not hasattr(bar, original_name):
                setattr(bar, original_name, getattr(bar, name))
            def make_revert_handler(original):
                def reverted(*args, **kwargs):
                    if not owner.active:
                        return original(*args, **kwargs)
                    owner.undo_purchase()
                return reverted
            # Only the F2 view can sell in local practice.
            setattr(bar, name, make_revert_handler(getattr(bar, original_name)))
        bar.revert_panel.visible = False
        bar.revert_panel.logic_visible = False

    def sell_equipment(self, selected_id, parent_id):
        from common_data import equip_evolution_data
        info = equip_evolution_data.data.get(int(selected_id))
        if not info:
            return
        style = (info['typ'], info['stype'])
        current = self.evolutions.get(style)
        if current is None:
            return
        bar = guiManager.get_ui('equip_evolution_v2')
        full = guiManager.get_ui('equip_evolution')
        path = list(bar.get_full_path(current))
        parent_id = int(parent_id or 0)
        if int(selected_id) not in path or (parent_id and parent_id not in path):
            return
        cut = path.index(parent_id)+1 if parent_id else 0
        refund = 0
        for evo_id in path[cut:]:
            box = getattr(full, 'evo_units', getattr(full, 'evo_boxes', {})).get(evo_id)
            cost = box.get_cost(False) if box is not None else 0
            refund += sum(cost) if isinstance(cost, (list, tuple)) else cost
        if parent_id:
            self.evolutions[style] = parent_id
        else:
            self.evolutions.pop(style, None)
        # Selling invalidates undo history; it cannot refund an item twice.
        self.purchase_history = []
        self.set_cash(BigWorld.player().cash+int(refund))
        self.update_equipment_stats()
        self.equipment_syncing = True
        try:
            full._offline_original_revert(current, parent_id)
            bar.on_item_reverted(current, parent_id)
            bar.revert_panel.visible = False
            bar.revert_panel.logic_visible = False
        finally:
            self.equipment_syncing = False
        self.equipment_category = None
        bar.hide_popup()
        self.runtime.write_status()

    def purchase_equipment(self, evo_id):
        from common_data import equip_evolution_data
        info = equip_evolution_data.data.get(int(evo_id))
        if not info:
            return
        if not hasattr(self, 'evolutions'):
            self.evolutions = {}
            self.base_equipment_stats = dict(BigWorld.player().equs)
        style = (info['typ'], info['stype'])
        if self.evolutions.get(style) == int(evo_id):
            return
        bar = guiManager.get_ui('equip_evolution_v2')
        path = list(bar.get_full_path(int(evo_id)))
        current = self.evolutions.get(style)
        if current is not None and current not in path:
            return
        begin = path.index(current)+1 if current is not None else 0
        cost = sum(int(equip_evolution_data.data[node].get('cost_cash', 0)) for node in path[begin:])
        player = BigWorld.player()
        if cost > player.cash:
            return
        if not hasattr(self, 'purchase_history'):
            self.purchase_history = []
        self.purchase_history.append((style, current, int(evo_id), cost))
        self.evolutions[style] = int(evo_id)
        self.set_cash(player.cash-cost)
        self.update_equipment_stats()
        self.equipment_syncing = True
        try:
            guiManager.get_ui('equip_evolution')._offline_original_evolve(evo_id)
            guiManager.get_ui('equip_evolution_v2')._offline_original_evolve(evo_id)
            bar.revert_panel.visible = False
            bar.revert_panel.logic_visible = False
        finally:
            self.equipment_syncing = False
        self.runtime.write_status()

    def undo_purchase(self):
        history = getattr(self, 'purchase_history', [])
        if not history or not self.active or self.loading:
            return
        style, previous, current, cost = history[-1]
        if self.evolutions.get(style) != current:
            return
        history.pop()
        if previous is None:
            self.evolutions.pop(style, None)
        else:
            self.evolutions[style] = previous
        self.set_cash(BigWorld.player().cash+cost)
        self.update_equipment_stats()
        self.equipment_syncing = True
        try:
            guiManager.get_ui('equip_evolution')._offline_original_revert(current, previous or 0)
            bar = guiManager.get_ui('equip_evolution_v2')
            bar.on_item_reverted(current, previous or 0)
            bar.hide_popup()
            bar.revert_panel.visible = False
            bar.revert_panel.logic_visible = False
        finally:
            self.equipment_syncing = False
        self.equipment_category = None
        self.runtime.write_status()

    def update_equipment_stats(self):
        from common_data import equip_evolution_data
        player = BigWorld.player()
        old = dict(player.equs)
        values = dict(getattr(self, 'base_equipment_stats', old))
        for evo_id in getattr(self, 'evolutions', {}).values():
            for key, value in equip_evolution_data.data[evo_id].get('attribs', {}).items():
                if isinstance(value, (int, float)):
                    values[key] = values.get(key, 0)+value
        player.equs = values
        player.set_equs(old)
        player.board.initProps(player)

    def leave(self):
        if not self.active or self.loading:
            return
        self.guard('leave', self._leave)

    def _leave(self):
        self.combat.clear()
        from debug import DebugManager
        self.loading = True
        self.ai = False
        if hasattr(self, 'map_dialog'):
            self.map_dialog.visible = False
            guiManager.use_mouse(self.map_dialog, False)
        self.helper.clear_all()
        self.toolbar._combo_practice_exit()
        self.toolbar.hero_list.visible = False
        self.toolbar.difficulty_choose.visible = False
        guiManager.get_ui('hero_attr_panel').visible = False
        for name in self.PANELS + self.MODALS:
            part = guiManager.instance().elements.get(name)
            if part is not None:
                part.visible = False
        manager = DebugManager.instance
        if manager.cSpaceName == self.return_scene:
            manager.teleport(self.return_scene, self.return_position)
            self.returned()
        else:
            manager.teleport(self.return_scene, self.return_position, self.returned)

    def returned(self):
        self.guard('returned', self._returned)

    def _returned(self):
        self.target_id = None
        self.active = False
        self.loading = False
        for name, visible in self.saved_gui.items():
            part = guiManager.instance().elements.get(name)
            if part is not None:
                part.visible = visible
        for part in self.runtime.hall.parts.values():
            part.visible = True
        player = BigWorld.player()
        player.test_do_cd_check = getattr(self, 'return_cd_check', False)
        self.set_level(self.return_level)
        self.set_cash(self.return_cash)
        player.mhp, player.hp = self.return_health
        player.set_mhp(0)
        player.set_hp(0)
        old = dict(player.equs)
        player.equs = getattr(self, 'return_equs', getattr(self, 'base_equipment_stats', old))
        player.set_equs(old)
        player.board.initProps(player)
        self.set_map_enabled(False)
        self.runtime.hall.hero_page.hall_pitch, self.runtime.hall.hero_page.hall_yaw = self.return_camera
        self.runtime.hall.hero_page.restore_hall_control()
        self.runtime.apply_saved_appearance(True)
        self.runtime.write_status()

    def handle_key(self, down, key, vk, mods):
        if not down:
            self.keys_down.discard(key)
        if SysBox.instance().show_array:
            if down and key == keys.KEY_ESCAPE:
                SysBox.instance().hide('ESC')
            return key == keys.KEY_ESCAPE
        if key == keys.KEY_ESCAPE:
            if down and key not in self.keys_down:
                self.keys_down.add(key)
                if self.active:
                    if getattr(guiManager.instance().elements.get('hero_attr_panel'), 'visible', False):
                        guiManager.get_ui('hero_attr_panel').visible = False
                    elif getattr(getattr(self, 'map_dialog', None), 'visible', False):
                        self.toggle_maps()
                    elif getattr(self, 'equipment_category', None) is not None:
                        self.equipment_category = None
                        guiManager.get_ui('equip_evolution_v2').hide_popup()
                    elif self.toolbar.hero_list.visible:
                        self.toolbar.hero_list.visible = False
                        self.runtime.hall.hero_page.restore_hall_control()
                    elif any(getattr(guiManager.instance().elements.get(name), 'visible', False)
                             for name in ('skill_desc_dlgb', 'equip_evolution', 'practice_sp_part')):
                        for name in ('skill_desc_dlgb', 'equip_evolution', 'practice_sp_part'):
                            part = guiManager.instance().elements.get(name)
                            if part is not None:
                                part.visible = False
                        self.runtime.hall.hero_page.restore_hall_control()
                    else:
                        SysBox.double_btn(text=u'\u8fd4\u56de\u5927\u5385\uff1f'.encode('gbk'), yes_callback=self.leave,
                                          no_callback=self.runtime.hall.hero_page.restore_hall_control,
                                          cancel_key='ESC')
                else:
                    self.close_entry()
            return True
        if not self.active or self.loading:
            return False
        actions = {keys.KEY_F1:lambda: self.toolbar_action(0),
                   keys.KEY_F2:lambda: self.toolbar_action(1),
                   keys.KEY_F3:lambda: self.toolbar_action(2),
                   keys.KEY_F4:lambda: self.toolbar_action(3),
                   keys.KEY_F5:lambda: self.toolbar_action(4),
                   keys.KEY_F6:lambda: self.toolbar_action('combo'),
                   keys.KEY_F7:lambda: self.toolbar_action('no_cooldown'),
                   keys.KEY_B:lambda: self.reset(bool(mods & keys.MODIFIER_SHIFT)),
                   keys.KEY_Y:self.toggle_ai,
                   keys.KEY_P:self.toggle_attributes,
                   keys.KEY_GRAVE:self.undo_purchase,
                   keys.KEY_L:lambda: self.set_level(16 if mods & keys.MODIFIER_SHIFT else BigWorld.player().lv+1)}
        for index in range(5):
            actions[getattr(keys, 'KEY_'+str(index+1))] = lambda index=index: self.equipment_number(index)
        if key in actions:
            if down and key not in self.keys_down:
                self.keys_down.add(key)
                self.guard('key', actions[key])
            return True
        if key in (keys.KEY_LCONTROL, getattr(keys, 'KEY_RCONTROL', keys.KEY_LCONTROL)):
            return True
        # Do not route Z/X/C/V and B into the hall's pages/bag during combat.
        return False

    def toggle_attributes(self):
        panel = guiManager.get_ui('hero_attr_panel')
        panel.visible = not panel.visible
        if panel.visible:
            panel.topmostEx()
        self.runtime.write_status()

    def tick(self):
        if self.combat.enabled():
            self.guard('combat', self.combat.tick)
        if self.active and not self.loading:
            def update():
                player = BigWorld.player()
                safe = getattr(self, 'last_safe_position', None)
                if safe is not None and player.position[1] < safe[1]-60.0:
                    player.physics.teleport(safe, (0.0, 0.0, 0.0))
                target = self.get_target()
                if target is not None and target.hp <= 0:
                    self.recover(target)
            self.guard('tick', update)
        BigWorld.callback(0.5, self.tick)

    def cooldown_probe(self):
        from captain import cdmgr
        self.reset()
        self.toolbar.hero_list.visible = False
        for name in ('skill_desc_dlgb', 'equip_evolution', 'practice_sp_part'):
            guiManager.get_ui(name).visible = False
        self.runtime.hall.hero_page.cursor_shown = False
        self.runtime.hall.hero_page.restore_hall_control()
        player = BigWorld.player()
        result = {'enabled':bool(player.test_do_cd_check), 'before':int(player.skill_session_no), 'samples':[]}
        self.cooldown_probe_result = result
        self.runtime.exercise_result = result
        def press():
            player.handle_key_event(True, keys.KEY_Q, 0, False)
            player.handle_key_event(False, keys.KEY_Q, 0, False)
        press()
        result['first'] = int(player.skill_session_no)
        def repeat():
            info = player.skill_controller.key_skill_map['KEY_Q']
            result['skill_id'] = info.cd_id()
            result['allowed_during'] = bool(cdmgr.check(info.cd_id()))
            result['hud_during'] = cdmgr.get_cd(info.cd_id())
            result['repeat_before'] = int(player.skill_session_no)
            press()
            result['repeat_after'] = int(player.skill_session_no)
            remaining = max(0.0, result['hud_during'][1]-BigWorld.time()) if result['hud_during'] else 0.0
            BigWorld.callback(remaining+0.2, expired)
            self.runtime.write_status()
        def expired():
            info = player.skill_controller.key_skill_map['KEY_Q']
            result['allowed_after'] = bool(cdmgr.check(info.cd_id()))
            result['expiry_before'] = int(player.skill_session_no)
            press()
            result['expiry_after'] = int(player.skill_session_no)
            result['complete'] = True
            self.runtime.write_status()
        BigWorld.callback(2.0, lambda: self.guard('cooldown_probe', repeat))
        self.runtime.write_status()

    def command(self, command):
        action = command.get('operation', 'entry')
        if action == 'reload':
            context = {}
            execfile('../res/editor/client/offline_practice.py', context)
            self.__class__ = context['LocalPractice']
            self.install_damage_hook()
            self.install_skill_hook()
            self.install_local_combat()
            self.install_equipment_hooks()
            self.install_difficulty_buttons()
            self.install_toolbar_buttons()
            self.disable_debug_map_keys()
            stage_context = {}
            execfile('../res/editor/client/hero_stage.py', stage_context)
            stage = self.runtime.hall.hero_page
            stage.__class__ = stage_context['HeroStage']
            stage.install_view_controls()
            stage.menu_key_listener = stage.handle_menu_key
            FsmGame.init().exclusive_key_listener = stage.menu_key_listener
            stage.active_handler = stage.handle_app_active
            FsmGame.active = stage.active_handler
            from system import camera
            stage.camera_mouse_handler = stage.handle_camera_mouse
            camera.bc.handle_mouse_event = stage.camera_mouse_handler
            if stage.visible:
                stage.sync_input_mode()
            else:
                stage.restore_hall_control()
            if self.active:
                self.enable_cooldowns()
        elif action == 'inspect':
            from captain import cdmgr
            player = BigWorld.player()
            self.runtime.exercise_result = {'attributes':dict((name,repr(getattr(player,name)))
                for name in ('cash', 'lv', 'equs', 'p_attack', 'mhp', 'realSPSkill', 'test_do_cd_check', 'skill_session_no')),
                'cooldowns':repr(cdmgr.instance().dict_now_cd),
                'skill_keys':[(repr(key), repr(value)) for key, value in player.skill_controller.key_skill_map.items()],
                'equip_roots':[list(button.root_evo_ids) for button in guiManager.get_ui('equip_evolution_v2').toolbar_part.evo_btns],
                'visible_gui':self.runtime.hall.visible_gui()}
        elif action == 'inspect_ui':
            self.runtime.exercise_result = [(name, repr(type(getattr(self.toolbar, name))),
                repr(getattr(self.toolbar, name).parent), list(getattr(self.toolbar, name).coord),
                getattr(self.toolbar, name).width, getattr(self.toolbar, name).height)
                for name in ('btn_show_hint', 'btn_equip', 'btn_reset')]
        elif action == 'inspect_map':
            from debug import DebugManager
            p = BigWorld.player()
            self.runtime.exercise_result = {'space':p.spaceID, 'manager_space':DebugManager.instance.cSpaceId,
                'position':list(p.position), 'collision':repr(BigWorld.collide(p.spaceID,(0,1000,0),(0,-1000,0))),
                'units':list(getattr(guiManager.get_ui('equip_evolution'), 'evo_units', {}).keys())}
        elif action == 'input_probe':
            from system import camera
            stage = self.runtime.hall.hero_page
            self.toolbar.hero_list.visible = False
            for name in self.MODALS:
                guiManager.get_ui(name).visible = False
            stage.cursor_shown = False
            stage.restore_hall_control()
            p = BigWorld.player()
            result = {'battle':self.active, 'move_only':bool(p.move_only), 'before':int(p.skill_session_no),
                'camera_before':float(camera.bc.bw_cam.pivotMaxDist)}
            self.runtime.exercise_result = result
            if self.active:
                result['camera_handled'] = bool(stage.handle_camera_mouse(0, 0, -120))
                result['wheel_handled'] = bool(p.handle_mouse_event(0, 0, -120))
            else:
                p.handle_key_event(True, keys.KEY_Q, 0, False)
                p.handle_key_event(False, keys.KEY_Q, 0, False)
                p.handle_key_event(True, keys.KEY_LEFTMOUSE, 0, False)
                p.handle_key_event(False, keys.KEY_LEFTMOUSE, 0, False)
                result['camera_handled'] = bool(stage.handle_camera_mouse(0, 0, 120))
            def finish():
                result['after'] = int(p.skill_session_no)
                result['camera_after'] = float(camera.bc.bw_cam.pivotMaxDist)
                self.runtime.write_status()
            BigWorld.callback(0.5, finish)
        elif action == 'cash':
            self.set_cash(90000)
        elif action == 'cooldown_probe':
            self.cooldown_probe()
        elif action == 'buy':
            self.purchase_equipment(int(command['evo_id']))
        elif action == 'undo':
            self.undo_purchase()
        elif action == 'map':
            self.change_map(command['scene'])
        elif action == 'maps':
            self.toggle_maps()
        elif action == 'entry':
            self.toggle_entry()
        elif action == 'enter':
            self.enter()
        elif action == 'ready':
            self.ready()
        elif action == 'finish_return':
            self.returned()
        elif action == 'leave':
            self.leave()
        elif action == 'target':
            self.change_target(int(command['hero_type']))
        elif action == 'reset':
            self.reset(command.get('clear', False))
        elif action == 'restore_arena':
            from debug import DebugManager
            self.loading = True
            self.teleport_scene(self.SCENE, self.SPAWN, self.ready)
        elif action == 'sell':
            self.sell_equipment(int(command['evo_id']), int(command.get('parent_id', 0)))
        elif action == 'sell_selected':
            panel = guiManager.get_ui('equip_evolution')
            panel.visible = True
            panel.on_btn_sell_click(None)

    def status(self):
        target = self.get_target()
        return {'active':self.active, 'loading':self.loading,
                'no_cooldown':getattr(self, 'no_cooldown', False),
                'entry_visible':bool(self.entry is not None and self.entry.visible),
                'scene':ClientUtils.get_scene_name(), 'target_id':self.target_id,
                'target_type':self.target_type, 'damage':self.helper.damage_accumulation,
                'ai':self.ai, 'toolbar_visible':bool(self.toolbar.visible),
                'selector_visible':bool(self.toolbar.hero_list.visible),
                'target_hp':target.hp if target is not None else None,
                'target_class':target.__class__.__name__ if target is not None else None,
                'target_position':list(target.position) if target is not None else None,
                'ai_running':bool(getattr(target, 'is_client_ai', False)) if target is not None else False,
                'player_hp':BigWorld.player().hp,
                'move_only':bool(BigWorld.player().move_only),
                'input_mode':FsmGame.init().mode,
                'camera_distance':float(self.runtime.hall.hero_page.hall_camera_distance),
                'cooldown_probe':getattr(self, 'cooldown_probe_result', None),
                'equipment':list(getattr(self, 'evolutions', {}).values()),
                'equipment_category':getattr(self, 'equipment_category', None),
                'equipment_choices':list(guiManager.get_ui('equip_evolution_v2').get_curr_evo_ids(
                    guiManager.get_ui('equip_evolution_v2').toolbar_part.evo_btns[self.equipment_category]))
                    if getattr(self, 'equipment_category', None) is not None else [],
                'ai_difficulty':getattr(self, 'ai_difficulty', 'low'),
                'level':int(BigWorld.player().lv), 'cash':int(BigWorld.player().cash),
                'errors':self.errors}


def install(runtime):
    return LocalPractice(runtime)
