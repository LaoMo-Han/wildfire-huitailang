# -*- coding: utf-8 -*-
"""The formal StageSelectPart/StageInfoPart hero screen, using original pages."""
import math
import traceback
import BigWorld
import Math
import keys
import Inventory
import Item
import const
import ClientConst
from guis import factory, guiManager, SysBox
from system import MsgManager, camera, ShortcutManager
from guis.city import ActorField, CityManager
from guis.city.stage import SelectPart, BasicPhase, HeroVoicePhase, StoryPhase, PaintPhase, SharePhase, StageMenu
from guis.city.fashion import FashionPhaseNew as FashionPhase
from logic import FsmGame, FashionMgr, ClientEquipsContainer


def source_clone_offset(yaw, index, ring_size=8, radius=1.15, spacing=0.65):
    """Place successive copies on rings around the character, never stacked."""
    ring = int(index)//ring_size
    angle = yaw+(2.0*math.pi/ring_size)*(int(index) % ring_size)
    distance = radius+spacing*ring
    return (math.sin(angle)*distance, math.cos(angle)*distance)



class LocalActorField(ActorField.ActorField):
    def enter(self, hero_type, show_eff=False, enter_load_fashions=False, show_default_eff=False):
        if self.isin:
            self.set_hero(hero_type)
            return
        # Retain the original scene/actors and the user's render configuration.
        # The online entry temporarily rebuilds HQ/shadow/cloth settings on
        # every visit, then rebuilds them again when the page closes.
        self.show_default_eff = show_default_eff
        self.enter_load_fashions = enter_load_fashions
        self.isin = True
        self._release_bh()
        self._init_check()
        getattr(camera, self.camera_name)()
        BigWorld.camera().spaceID = self.space_id
        camera.eqc2.bw_cam.spaceID = self.space_id
        if self.camera_name == 'eqc':
            matrix = Math.Matrix()
            matrix.setTranslate(self.pos_default)
            BigWorld.camera().target = matrix
        self.set_hero(hero_type)
        self.show_eff = show_eff
        BigWorld.setViewDirModelBlend(0)
        camera.eqc.set_enabled(True)
        if ActorField.SpaceManager.is_loading_optimizing_enable():
            BigWorld.setSpaceInUse(self.space_id, True)

    def _leave_clear(self):
        self.isin = False
        self._change_lock = False
        self.show_model_handler = None
        if self._default_change_timer:
            BigWorld.cancelCallback(self._default_change_timer)
            self._default_change_timer = None
        self._clear_eff_default()
        self._clear_eff_random()
        BigWorld.setViewDirModelBlend(1)
        for actor_id in self.actors:
            ActorField.CueEffMgr.stop_sounds_by_ent_id(actor_id)
            actor = BigWorld.entity(actor_id)
            if actor is not None and getattr(actor, 'model', None) is not None:
                actor.model.visible = False
        if self._change_bh_pos:
            BigWorld.cancelCallback(self._change_bh_pos)
            self._change_bh_pos = None
        self.on_stop_effect()

    def clear(self):
        return ActorField.ActorField.clear(self)


class LocalSelectPart(SelectPart.SelectPart):
    def _quest_hero_infos(self):
        pass

    def _stage_change_hero(self, hero_type):
        return True

    def on_hero_select(self, hero_type):
        if hasattr(self, 'local_stage'):
            self.hero_type = int(hero_type)
            self.local_stage.select(int(hero_type))

    def connect(self, target_part, hero_type=None, enter_load_fashions=False,
                select_mode=0, check_callback=None, show_default_eff=False):
        self.connect_part = target_part
        if hero_type is not None:
            self.hero_type = int(hero_type)
        self.visible = True
        self._SelectPart__mode = -1
        self.select_mode = select_mode
        self._update()
        self.part_basic.hero_list.visible = select_mode == 0


class LocalInfoPart(BasicPhase.InfoPart):
    def on_btn_bag_click(self, sender):
        self.mgr.open_equipment()

    def on_btn_skill_click(self, sender):
        self.mgr.open_skills()


class LocalStory(StoryPhase.StoryPhase):
    def __init__(self):
        StoryPhase.StoryPhase.__init__(self)
        for name in ['cell_readme_0', 'cell_readme_1', 'cell_readme_2']:
            previous = getattr(self, name)
            parent, coord = previous.parent, previous.coord
            previous.destroy()
            setattr(self, name, StoryPhase.StageHeroReadmeCell(parent, coord[0], coord[1]))

    def set_visible(self, value):
        factory.StageDataPart.set_visible(self, value)
        if not value:
            self.sound_check.stop()
            self._stop_readme_voice()

    def on_hero_select(self, hero_type):
        self.cur_hero_type = hero_type
        self._update_base_info(hero_type)
        self._update_story_info(hero_type)
        self._update_readme(hero_type)
        # Story assets can be read locally; historic account achievements are
        # not needed to browse the recovered chapter texts.
        for cell in self.title_cells:
            cell.container_unlock.visible = True
            cell.container_lock.visible = False
        self.on_chapterpage_set(self.chapter_page.page)


class LocalSuit(FashionMgr.SuitObj):
    @property
    def item(self):
        if not hasattr(self, '_local_item'):
            item = FashionMgr.instance().fashion_items.get(self.item_id)
            self._local_item = item if item is not None else FashionMgr.FashionItem(self.item_id, self.hero_type)
        return self._local_item

    @property
    def trinkets(self):
        return list(getattr(self, '_local_trinkets', []))

    def get_fashion_detail(self):
        return ([self.item_id] if self.item_id else []) + ([self.dye] if self.dye else []) + self.trinkets


class LocalCosmeticInventory(Inventory.Inventory):
    def __init__(self, cosmetic_ids):
        Inventory.Inventory.__init__(self, const.INV_TYPE_AVATAR)
        self.cosmetic_ids = set(cosmetic_ids)
        self.cosmetic_items = {}

    def countByID(self, page, item_id):
        if item_id in self.cosmetic_ids:
            return 999
        return Inventory.Inventory.countByID(self, page, item_id)

    def getFirstItemByID(self, item_id):
        if item_id in self.cosmetic_ids:
            if item_id not in self.cosmetic_items:
                self.cosmetic_items[item_id] = Item.Item(item_id)
            return self.cosmetic_items[item_id]
        return Inventory.Inventory.getFirstItemByID(self, item_id)


class LocalFashion(FashionPhase.FashionPhase):
    def init_ui(self):
        FashionPhase.FashionPhase.init_ui(self)
        self._catalog_built = False
        self._original_catalog_update = self.page_all.update
        self.page_all.update = self.update_catalog
        self.page_hero.btn_equip.event_click = self.equip_selected
        self.page_hero.btn_buy.event_click = lambda sender: self.local_stage.hall.notice()

    def update_catalog(self):
        if not self._catalog_built:
            self._original_catalog_update()
            self._catalog_built = True

    def focus_suit(self, suit):
        if suit is None:
            return
        self.local_stage.hero_type = suit.hero_type
        FashionPhase.FashionPhase.focus_suit(self, suit)

    def equip_selected(self, sender):
        stage = self.local_stage
        suit = self.page_hero.tgt_suit
        if suit is None:
            return
        stage.runtime.profile.setdefault('fashion', {})[str(suit.hero_type)] = suit.item_id
        suit.dye = int(self.page_hero.tgt_dye_id or 0)
        suit._local_trinkets = list(self.page_hero.tgt_trinket_ids)
        stage.runtime.profile.setdefault('appearance', {})[str(suit.hero_type)] = {
            'fashion':suit.item_id, 'dye':suit.dye, 'trinkets':suit.trinkets}
        stage.runtime.save()
        FashionMgr.instance().equip_suit[suit.hero_type] = suit.suit_no
        self.on_hero_select(suit.hero_type)


class PaintBucket(object):
    def __init__(self, stage):
        self.stage = stage
        self.allPaints = dict((item_id, 1) for item_id in stage.paint.all_paints)

    def getHeroPaint(self, hero_type):
        value = self.stage.runtime.profile.get('paint', {}).get(str(hero_type))
        return int(value) if value else min(self.allPaints)


class LocalPaint(PaintPhase.PaintPhase):
    def on_btn_set_click(self, sender):
        self.local_stage.runtime.profile.setdefault('paint', {})[str(self.hero_type)] = self.selected_paint_id
        self.local_stage.runtime.save()
        self.on_hero_select(self.hero_type)

    def on_btn_use_click(self, sender):
        self.on_btn_set_click(sender)


class LocalShare(SharePhase.SharePhase):
    def init_ui(self):
        SharePhase.SharePhase.init_ui(self)
        groups = [('equip_cells', SharePhase.ShareBattleEquipCell),
                  ('talent_cells', SharePhase.ShareBattleTalentCell),
                  ('city_equip_cells', SharePhase.ShareCityEquipCell),
                  ('trinket_cells', SharePhase.ShareCityEquipCell),
                  ('consume_cells', SharePhase.ShareCityEquipCell)]
        for name, cell_class in groups:
            replacements = []
            for previous in getattr(self, name):
                parent, coord = previous.parent, previous.coord
                cell = cell_class(parent, coord[0], coord[1])
                for attr in ['equip_key', 'talent_key', 'event_equip_cell_click', 'event_item_click']:
                    if hasattr(previous, attr):
                        setattr(cell, attr, getattr(previous, attr))
                previous.destroy()
                replacements.append(cell)
            setattr(self, name, replacements)
        self._edit_cells = self.equip_cells+self.talent_cells+self.city_equip_cells+self.trinket_cells+self.consume_cells
        previous = self.part_left
        parent, coord = previous.parent, previous.coord
        self.part_left = SharePhase.EquipSelectPart(parent, coord[0], coord[1])
        previous.destroy()
        self.part_left.visible = False
        for name in ['my_share_loading', 'billboard_loading']:
            previous = getattr(self, name)
            parent, coord = previous.parent, previous.coord
            replacement = SharePhase.ShareLoadingPart(parent, coord[0], coord[1])
            previous.destroy()
            setattr(self, name, replacement)
    def request_token(self):
        pass

    def _show_billboard(self, need_query=True, need_loading=True):
        pass

    def _show_my_share(self, value, need_query=True, need_loading=True):
        self.con_noshare.visible = True

    def _show_equip_share(self, hero_type, need_update=True):
        self.cur_select_hero_type = hero_type
        SharePhase.mgr().update_select_hero(hero_type)
        self.reset_edit(hero_type)

    def on_btn_upload_click(self, sender):
        stage = self.local_stage
        loadout = {'hero_type':self.cur_select_hero_type,
                   'equipment':[getattr(c, 'evo_id', None) for c in self.equip_cells],
                   'talents':[getattr(c, 'evo_id', None) for c in self.talent_cells],
                   'items':self._get_selected_city_equip_ids()}
        stage.runtime.profile.setdefault('loadouts', []).append(loadout)
        stage.runtime.save()
        MsgManager.show(text=u'\u51fa\u88c5\u5df2\u4fdd\u5b58\u5230\u79bb\u7ebf\u6863\u6848'.encode('gbk'))

    def on_hero_select(self, hero_type):
        self._show_equip_share(hero_type)


class HeroStage(object):
    CLONE_LIMIT = 12
    # The hall combat reticle is half the native training-arena size.
    CROSSHAIR_SCALE = 0.5

    def __init__(self, hall, runtime, log):
        self.hall, self.runtime, self.log = hall, runtime, log
        self.visible = False
        self.closed = False
        self.hero_type = int(BigWorld.player().hero_type)
        self.tab = 'equip'
        self.hall_combat = False
        self.hall_ui_hidden = False
        self.ui_snapshot = {}
        self.source_clones = []
        self.source_clone_serial = 0
        self.source_clone_pending = 0
        self.source_clone_attempts = 0
        self.combat_key_cache = None
        self.combat_buttons = set()
        self.combat_keys_down = set()
        self.errors = {}
        self.parts = {}
        self.hidden = {}
        self.preview_linked = None
        self.catalog_initialized = False
        self.menu_keys_down = set()
        self.cursor_shown = True
        self.previous_camera_mouse = camera.bc.handle_mouse_event
        self.camera_mouse_handler = self.handle_camera_mouse
        camera.bc.handle_mouse_event = self.camera_mouse_handler
        self.hall_camera_distance = camera.bc.bw_cam.pivotMaxDist
        self.hall_pitch = 0.0
        self.hall_yaw = 0.0
        self.control_restore_pending = False
        self.install_view_controls()
        self.field = LocalActorField('HeroEquips')
        self.city = CityManager.instance
        if self.city is None:
            raise RuntimeError('Original CityManager context is not initialized')
        self.city.stage_hero_field = self.field
        self.city.unlock_heros = set(runtime.hero_ids)
        self.city.equip_wear_fashion = lambda fashions, keep_acc_and_dyes=False: self.field.actor_wear_fashion(
            fashions, keep_acc_and_dyes=keep_acc_and_dyes)
        self.initialize_player()
        self.selector = LocalSelectPart()
        self.selector.local_stage = self
        self.selector.setting(runtime.hero_ids)
        self.selector.visible = False
        self.selector.part_basic.hero_list.lock_mode = False
        self.info = LocalInfoPart(self)
        self.info.hero_infos = dict((h, (1, 0)) for h in runtime.hero_ids)
        self.info.visible = False
        self.parts['equip'] = self.info
        self.tabs = factory.StageChangeMenu()
        self.tabs.visible = False
        self.exit = factory.HeroEquipMenu()
        self.exit.visible = False
        self.exit.btn_quit.visible = False
        self.back = factory.ReturnDlg()
        self.back.visible = False
        self.back.btn_exit.visible = False
        self.back.btn_return.visible = True
        self.back.btn_return.event_click = self.exit_clicked
        for name in ['container_unlock_s', 'container_unlock', 'container_use', 'lbl_tips', 'btn_refresh_scene']:
            getattr(self.exit, name).visible = False
        self.exit.container_shape.visible = True
        self.exit.btn_change_shape.event_click = self.apply_clicked
        self.exit.btn_cancel_shape.event_click = self.cancel_clicked
        for name in ['equip', 'fashion', 'voice', 'story', 'share', 'paint', 'strategy']:
            getattr(self.tabs, 'btn_'+name).event_click = self.tab_handler(name)
            getattr(self.tabs, 'btn_'+name+'_sel').event_click = self.tab_handler(name)
        guiManager.instance().elements['stage_select_part'] = self.selector
        self.previous_key_listener = FsmGame.init().exclusive_key_listener
        self.menu_key_listener = self.handle_menu_key
        FsmGame.init().exclusive_key_listener = self.menu_key_listener
        self.previous_active_handler = FsmGame.active
        self.active_handler = self.handle_app_active
        FsmGame.active = self.active_handler
        BigWorld.callback(0.5, self.tick)

    def initialize_player(self):
        player = BigWorld.player()
        practice = getattr(self.runtime, 'practice', None)
        player.move_only = bool(self.visible or self.hall.chat_open)
        if getattr(player, 'hero_equips', None) is None:
            player.hero_equips = {}
        if getattr(player, 'inv', None) is None:
            player.inv = Inventory.Inventory(const.INV_TYPE_AVATAR)
        if not isinstance(getattr(player, 'new_equip_inv', None), ClientEquipsContainer.EquipsContainer):
            player.new_equip_inv = ClientEquipsContainer.EquipsContainer()
        if getattr(player, 'heros', None) is None:
            player.heros = dict((h, {'exp':0}) for h in self.runtime.hero_ids)
        player.is_hero_type_changed = lambda: False
        if getattr(player, 'clothes_press_data', None) is None:
            player.clothes_press_data = {}
        manager = FashionMgr.instance()
        cosmetic_ids = set(manager.dye_items)
        cosmetic_ids.add(const.FASHION_DYE_CLEANER_ID)
        for items in manager.hero_trinkets.values():
            cosmetic_ids.update(items)
        if not isinstance(player.inv, LocalCosmeticInventory):
            player.inv = LocalCosmeticInventory(cosmetic_ids)
        if self.catalog_initialized:
            return
        for hero_type in self.runtime.hero_ids:
            items = list(manager.hero_fashions.get(hero_type, []))
            if ClientConst.DEFAULT_FASHION_ID not in items:
                items.insert(0, ClientConst.DEFAULT_FASHION_ID)
            saved = self.runtime.profile.get('fashion', {}).get(str(hero_type), ClientConst.DEFAULT_FASHION_ID)
            for index, item_id in enumerate(items):
                number = hero_type*1000+index
                suit = LocalSuit(FashionMgr.create_fashion_suit(hero_type, number, item_id, 0))
                appearance = self.runtime.profile.get('appearance', {}).get(str(hero_type), {})
                if appearance.get('fashion') == item_id:
                    suit.dye = int(appearance.get('dye') or 0)
                    suit._local_trinkets = list(appearance.get('trinkets', []))
                manager.suit_data[number] = suit
                if item_id == saved:
                    manager.equip_suit[hero_type] = number
        self.catalog_initialized = True

    def tab_handler(self, name):
        def clicked(sender):
            self.set_tab(name)
        return clicked

    def ensure_tab(self, name):
        if name in self.parts:
            return self.parts[name]
        if name == 'voice':
            part = HeroVoicePhase.HeroVoicePhase()
        elif name == 'story':
            part = LocalStory()
        elif name == 'paint':
            part = LocalPaint()
            self.paint = part
            part.local_stage = self
            part.paint_bucket = PaintBucket(self)
            part.inventory_paints = []
            part.init_paints = []
        elif name == 'fashion':
            part = LocalFashion()
            part.local_stage = self
        elif name == 'share':
            part = LocalShare()
            part.local_stage = self
            # Legacy community APIs have no offline service. Keep every request
            # in this module local; no credentials or network token is created.
            SharePhase.mgr().request = lambda url, data=None, callback=None: None
        elif name == 'strategy':
            return None
        else:
            raise ValueError('Unknown original stage page')
        self.parts[name] = part
        part.visible = False
        return part

    def set_tab(self, name):
        if name == self.tab and name in self.parts and self.parts[name].visible:
            return
        try:
            part = self.ensure_tab(name)
            if part is None:
                self.hall.notice()
                return
            for page in self.parts.values():
                page.visible = False
            self.tab = name
            for key in ['equip', 'fashion', 'voice', 'story', 'share', 'paint', 'strategy']:
                getattr(self.tabs, 'btn_'+key).visible = key != name
                getattr(self.tabs, 'btn_'+key+'_sel').visible = key == name
            self.update_part()
            part.visible = True
            camera.switch_equip_camera(StageMenu.CAMERA_CENTER if name == 'equip' else StageMenu.CAMERA_LEFT)
            self.errors.pop(name, None)
            self.log('Formal hero stage tab opened: '+name)
        except Exception:
            self.errors[name] = traceback.format_exc()
            self.log(self.errors[name])
        self.runtime.write_status()

    def update_part(self):
        self.selector.connect(self, self.hero_type, select_mode=0 if self.tab in ['equip', 'voice'] else 2)
        if self.tab == 'equip':
            self.info.update(self.hero_type)
        elif self.tab == 'fashion':
            self.parts[self.tab].enter(self.hero_type, {})
        else:
            self.parts[self.tab].on_hero_select(self.hero_type)

    def show(self, name=None):
        self.stop_hall_drag()
        if name is not None:
            self.tab = name
        if self.visible:
            if name is not None:
                self.set_tab(name)
            return
        try:
            self.capture_hall_camera()
            self.set_hall_ui_hidden(False)
            self.runtime.hide_map()
            self.runtime.close_bag()
            self.hall.close_chat()
            # Pages are cursor-driven UI; return to the peaceful hall state so
            # closing a page never drops the user back into combat.
            self.hall_combat = False
            self.sync_input_mode()
            self.initialize_player()
            self.field.enter(self.hero_type, show_eff=False, enter_load_fashions=False, show_default_eff=False)
            self.visible = True
            for part in self.hall.parts.values():
                part.visible = False
            self.tabs.visible = True
            self.exit.visible = True
            self.back.visible = True
            self.back.topmostEx()
            self.set_tab(self.tab)
            FsmGame.set_hero_only_move(False)
            FsmGame.init().mode = FsmGame.MOD_NOML
            self.runtime.last_error = None
            self.log('Formal StageSelectPart/StageInfoPart opened.')
        except Exception:
            self.runtime.last_error = traceback.format_exc()
            self.log(self.runtime.last_error)
        self.hall.refresh_hints()
        self.runtime.write_status()

    def hide(self):
        self.preview_drag = False
        BigWorld.sendMouseMovementToScript(False)
        self.selector.visible = False
        for part in self.parts.values():
            part.visible = False
        self.tabs.visible = False
        self.exit.visible = False
        self.back.visible = False
        if hasattr(self, 'all_bags'):
            self.all_bags.visible = False
        skill_ui = guiManager.instance().elements.get('skill_desc_dlg')
        if skill_ui is not None:
            skill_ui.visible = False
        if self.field.isin:
            self.initialize_player()
            self.field.leave()
        for part in self.hall.parts.values():
            part.visible = True
        for part in self.hidden.values():
            part.visible = True
        self.hidden.clear()
        self.visible = False
        self.restore_hall_control()
        self.runtime.apply_saved_appearance()
        self.runtime.hide_map()
        self.hall.refresh_hints()
        self.runtime.write_status()

    def sync_input_mode(self):
        settings = getattr(self.runtime, 'settings', None)
        practice = getattr(self.runtime, 'practice', None)
        in_battle = practice is not None and practice.active and not practice.loading
        # Hall Tab combat keeps the native city input mode and cursor, and only
        # unlocks hero casts; the training arena keeps its own battle path.
        hall_combat = bool(getattr(self, 'hall_combat', False)) and not in_battle
        fighting = in_battle or hall_combat
        modal = self.visible or self.hall.chat_open or bool(self.runtime.bag is not None and self.runtime.bag.visible)
        modal = modal or bool(settings is not None and settings.ui.visible)
        modal = modal or bool(practice is not None and practice.entry is not None and practice.entry.visible)
        if in_battle:
            modal = modal or practice.toolbar.hero_list.visible or any(
                getattr(guiManager.instance().elements.get(name), 'visible', False) for name in practice.MODALS)
            modal = modal or getattr(getattr(practice, 'map_dialog', None), 'visible', False)
        ui_cursor = not fighting or modal
        self.cursor_shown = bool(ui_cursor)
        FsmGame.init().mode = FsmGame.MOD_NOML if modal else (FsmGame.MOD_HERO if fighting else FsmGame.MOD_CITY)
        FsmGame.set_hero_only_move(ui_cursor)
        # The mode setter is a no-op when the mode did not change. Focus loss
        # disables script mouse input, so explicitly restore it on every resume.
        BigWorld.sendMouseMovementToScript(fighting and not modal)
        if ui_cursor:
            # Native settings can return to combat mode when closed, leaving
            # the UI cursor at its hidden sentinel even on the hero page.
            import C_ui
            if C_ui.get_cursor_pos() == (-20000, -20000):
                C_ui.cursor_pos(*BigWorld.getCursorPos())
            if not in_battle:
                aim = getattr(BigWorld.player(), 'aim', None)
                if aim is not None:
                    # Chat/bag/pages need the cursor, not the battle crosshair.
                    aim.enabled(False)
        BigWorld.player().move_only = bool(modal)
        if practice is not None:
            BigWorld.player().test_do_cd_check = not practice.cooldowns_disabled()
        player = BigWorld.player()
        if fighting and not modal and not getattr(self, 'hall_ui_hidden', False) \
                and getattr(player, 'model', None) is not None and hasattr(player, 'aim'):
            # Combat keeps the native aim/crosshair bound; closing chat or the
            # bag must not leave the hall without it.
            player.aim.active()
            if getattr(self, 'hall_combat', False):
                self.set_hall_crosshair(True)
        return fighting

    def restore_hall_control(self):
        # Restore camera ownership only at scene/page transitions, not clicks.
        self.control_restore_pending = True
        self.resume_hall_behavior()
        in_battle = self.sync_input_mode()
        camera.tryReleaseDC(FsmGame.init())
        if camera.inst.current is not camera.bc:
            camera.bc()
        camera.bc.setTarget()
        if not in_battle:
            camera.camera_bind_player(False)
            body_yaw = getattr(self, 'hall_body_yaw', None)
            BigWorld.player().model.bh.yaw_enable = body_yaw is None
            if body_yaw is not None:
                BigWorld.player().model.yaw = body_yaw
                BigWorld.player().model.bh.bh_yaw = body_yaw
        else:
            BigWorld.player().model.bh.yaw_enable = True
        camera.bc.bw_cam.pivotMaxDist = self.hall_camera_distance
        # Normalised pitch remaps the old narrow range when limits change,
        # which can push the camera upwards on every return/focus change.
        BigWorld.dcursor().keepNormalizedPitch = False
        BigWorld.dcursor().minPitch = -1.569
        BigWorld.dcursor().maxPitch = 1.569
        BigWorld.dcursor().lookSpring = False
        BigWorld.dcursor().lookSpringOnMove = False
        BigWorld.dcursor().pitch = self.hall_pitch
        BigWorld.dcursor().yaw = self.hall_yaw
        BigWorld.enablePlayerFade(False)
        FsmGame.init().reset_mouse_state()
        if in_battle and hasattr(BigWorld.player(), 'aim'):
            # Changing heroes can replace Aim without activating a new camera.
            # Rebind its native pitch/depth matrix even when bc stayed current.
            BigWorld.player().aim.active()
            if getattr(self, 'hall_combat', False):
                self.set_hall_crosshair(True)
        elif hasattr(BigWorld.player(), 'aim'):
            BigWorld.player().aim.enabled(False)

    def install_view_controls(self):
        from debug import DebugManager
        manager = DebugManager.instance
        if not hasattr(manager, '_offline_original_preview_mouse'):
            manager._offline_original_preview_mouse = manager.handle_mouse_event
        self.preview_drag = False
        self.hall_mouse_buttons = set()
        self.hall_drag_moved = False
        self.hall_drag_generation = getattr(self, 'hall_drag_generation', 0)+1
        self.hall_drag_position = None
        self.hall_body_yaw = getattr(self, 'hall_body_yaw', None)
        if not hasattr(manager, '_offline_original_hall_key'):
            manager._offline_original_hall_key = manager.handle_key_event
        self.hall_key_handler = self.handle_hall_mouse_key
        manager.handle_key_event = self.hall_key_handler
        fsm = FsmGame.init()
        if not hasattr(fsm, '_offline_original_world_mouse'):
            fsm._offline_original_world_mouse = fsm.handle_mouse_event
        self.world_mouse_handler = self.handle_world_mouse
        fsm.handle_mouse_event = self.world_mouse_handler
        if not hasattr(fsm, '_offline_original_world_key'):
            fsm._offline_original_world_key = fsm.handle_key_event
        self.world_key_handler = self.handle_world_key
        fsm.handle_key_event = self.world_key_handler
        self.offline_mouse_handler = self.handle_preview_mouse
        manager.handle_mouse_event = self.offline_mouse_handler

    def handle_preview_mouse(self, dx, dy, dz):
        if self.visible and self.field.isin and self.preview_drag:
            self.field.handle_mouse(dx, dy, 0)
            return not dz
        from debug import DebugManager
        return DebugManager.instance._offline_original_preview_mouse(dx, dy, dz)

    def hall_world_input(self):
        practice = getattr(self.runtime, 'practice', None)
        return (not self.visible and not self.hall.chat_open
            and not (practice is not None and practice.engaged)
            and not (self.runtime.bag is not None and self.runtime.bag.visible)
            and not getattr(getattr(getattr(self.runtime, 'settings', None), 'ui', None), 'visible', False)
            and not SysBox.instance().show_array)

    def handle_hall_mouse_key(self, down, key, vk, mods):
        # Only start a world drag after the native widgets decline the press.
        # With the combat cursor hidden the native battle path owns the mouse.
        if key in (keys.KEY_LEFTMOUSE, keys.KEY_RIGHTMOUSE) and self.hall_world_input() \
                and getattr(self, 'cursor_shown', True):
            if down:
                starting = not self.hall_mouse_buttons
                self.hall_mouse_buttons.add(key)
                if starting:
                    self.hall_drag_position = BigWorld.getCursorPos()
                    self.hall_drag_generation += 1
                    generation = self.hall_drag_generation
                    BigWorld.callback(0.0, lambda: self.poll_hall_drag(generation))
            else:
                self.hall_mouse_buttons.discard(key)
            if getattr(self, 'hall_combat', False):
                if down:
                    self.combat_buttons.add(key)
                    BigWorld.player().handle_key_event(True, key, mods)
                elif key in self.combat_buttons:
                    self.combat_buttons.discard(key)
                    BigWorld.player().handle_key_event(False, key, mods)
            return True
        from debug import DebugManager
        return DebugManager.instance._offline_original_hall_key(down, key, vk, mods)

    def stop_hall_drag(self):
        combat = bool(getattr(self, 'hall_combat', False))
        for key in self.hall_mouse_buttons:
            if combat:
                BigWorld.player().handle_key_event(False, key, 0)
        self.hall_mouse_buttons.clear()
        for key in getattr(self, 'combat_buttons', set()):
            BigWorld.player().handle_key_event(False, key, 0)
        self.combat_buttons = set()
        self.hall_drag_moved = False
        self.hall_drag_generation += 1
        self.hall_drag_position = None

    def poll_hall_drag(self, generation):
        if generation != self.hall_drag_generation or not self.hall_mouse_buttons:
            return
        if not self.hall_world_input() or not FsmGame.init().active:
            self.stop_hall_drag()
            return
        self.update_hall_drag()
        BigWorld.callback(1.0/60.0, lambda: self.poll_hall_drag(generation))

    def update_hall_drag(self):
        # With the visible native cursor the engine can withhold relative mouse
        # events. Read client coordinates instead, without moving the cursor or
        # changing its capture mode on button presses.
        position = BigWorld.getCursorPos()
        previous = self.hall_drag_position
        self.hall_drag_position = position
        if previous is not None:
            self.rotate_hall_view(position[0]-previous[0], position[1]-previous[1])

    def handle_world_mouse(self, dx, dy, dz):
        if getattr(self, 'focus_restore_pending', False) or not FsmGame.init().active:
            return True
        if self.hall_mouse_buttons and self.hall_world_input() and FsmGame.init().active:
            self.update_hall_drag()
            if dz:
                self.handle_camera_mouse(0, 0, dz)
            return True
        return FsmGame.init()._offline_original_world_mouse(dx, dy, dz)

    def handle_world_key(self, down, key, vk, mods):
        # The native FSM returns None when the exclusive listener consumes an
        # event. tw2 treats that as unhandled and lets Windows drag MOD_CITY.
        if not FsmGame.init().active or getattr(self, 'focus_restore_pending', False):
            return True
        self.menu_key_handled = False
        result = FsmGame.init()._offline_original_world_key(down, key, vk, mods)
        if self.menu_key_handled:
            import tw2
            tw2.enable_drag_area(False)
            return True
        return result

    def rotate_hall_view(self, dx, dy):
        if not (dx or dy):
            return
        player = BigWorld.player()
        turning = keys.KEY_RIGHTMOUSE in self.hall_mouse_buttons
        if turning:
            self.hall_body_yaw = None
            player.model.bh.yaw_enable = True
        else:
            if self.hall_body_yaw is None:
                self.hall_body_yaw = player.model.bh.bh_yaw
            player.model.bh.yaw_enable = False
        cursor = BigWorld.dcursor()
        speed = cursor.mouseSensitivity
        cursor.yaw += dx*speed
        sign = 1.0 if cursor.invertVerticalMovement else -1.0
        cursor.pitch = max(cursor.minPitch, min(cursor.maxPitch, cursor.pitch+dy*speed*sign))
        self.hall_yaw, self.hall_pitch = cursor.yaw, cursor.pitch
        if turning:
            player.model.yaw = cursor.yaw
            player.model.bh.bh_yaw = cursor.yaw
        else:
            player.model.yaw = self.hall_body_yaw
            player.model.bh.bh_yaw = self.hall_body_yaw
        self.hall_drag_moved = True

    def capture_hall_camera(self):
        if camera.inst.current is camera.bc and not self.hall.chat_open:
            self.hall_pitch = BigWorld.dcursor().pitch
            self.hall_yaw = BigWorld.dcursor().yaw

    def handle_camera_mouse(self, dx, dy, dz):
        practice = getattr(self.runtime, 'practice', None)
        if practice is not None and practice.engaged:
            return self.previous_camera_mouse(dx, dy, dz)
        # Hall combat uses the native battle camera and wheel handling, exactly
        # like the practice arena, so the hidden cursor keeps its raw input.
        if getattr(self, 'hall_combat', False) and not getattr(self, 'cursor_shown', True):
            return self.previous_camera_mouse(dx, dy, dz)
        if FsmGame.state_is_offline() and self.hall_world_input() and dz:
            self.hall_camera_distance = max(1.0, min(30.0,
                self.hall_camera_distance*(0.9 if dz > 0 else 1.0/0.9)))
            camera.bc.bw_cam.pivotMaxDist = self.hall_camera_distance
            camera.bc.bw_cam.maxDistHalfLife = 0.1
            return True
        return self.previous_camera_mouse(dx, dy, dz)

    def confirm_exit(self):
        if SysBox.instance().show_array:
            return
        # Esc leaves hall combat first; the confirmation box needs the cursor.
        if getattr(self, 'hall_combat', False):
            self.toggle_hall_combat(False)
            return
        self.capture_hall_camera()
        SysBox.double_btn(text=u'\u786e\u5b9a\u9000\u51fa\u6e38\u620f\u5417\uff1f'.encode('gbk'),
                          yes_callback=BigWorld.quit, no_callback=self.exit_cancelled, cancel_key='ESC')

    def exit_cancelled(self):
        BigWorld.callback(0.0, self.restore_hall_control)

    def resume_hall_behavior(self):
        player = BigWorld.player()
        if player is not None and getattr(player, 'model', None) is not None:
            model = player.model
            if hasattr(model, 'bh'):
                model.bh.active(True)
                model.visible = True
                if model.bh.isBehaviorReady():
                    self.control_restore_pending = False
                    return True
        return False

    def toggle(self):
        self.hide() if self.visible else self.show()

    def handle_menu_key(self, down, key, vk, mods):
        try:
            result = self.handle_menu_key_impl(down, key, vk, mods)
            self.menu_key_handled = bool(result)
            if result:
                self.runtime.write_status()
            return result
        except Exception:
            self.menu_key_handled = True
            self.runtime.last_error = traceback.format_exc()
            self.log(self.runtime.last_error)
            self.runtime.write_status()
            return True

    def handle_menu_key_impl(self, down, key, vk, mods):
        # The engine caches tw2's entry point. Use its existing FSM listener
        # for the requested menu/return keys; movement continues through the FSM.
        world_release = not down and key in getattr(self, 'hall_mouse_buttons', ())
        if not down:
            self.menu_keys_down.discard(key)
            if key in getattr(self, 'hall_mouse_buttons', ()):
                self.update_hall_drag()
                self.hall_mouse_buttons.discard(key)
                if not self.hall_mouse_buttons:
                    self.stop_hall_drag()
                # The native UI saw the press before the world drag started.
                # It must also see the release to clear its button/capture state.
                # Consuming it here leaves subsequent menu clicks stuck down.
        practice = getattr(self.runtime, 'practice', None)
        settings_open = bool(getattr(getattr(getattr(self.runtime, 'settings', None), 'ui', None), 'visible', False))
        if key in (keys.KEY_LEFTMOUSE, keys.KEY_RIGHTMOUSE) and self.hall_world_input() \
                and getattr(self, 'cursor_shown', True):
            # Widgets get first refusal; only blank space starts combat/drag.
            import C_ui, GUI
            ui_handled = C_ui.handleKeyEvent(down, key, vk, mods) or GUI.handleKeyEvent(down, key, mods)
            if world_release or not ui_handled:
                self.handle_hall_mouse_key(down, key, vk, mods)
            return True
        if world_release:
            if key in getattr(self, 'combat_buttons', set()):
                self.combat_buttons.discard(key)
                BigWorld.player().handle_key_event(False, key, mods)
            return True
        if down and key in (keys.KEY_W, keys.KEY_A, keys.KEY_S, keys.KEY_D) and self.hall_world_input():
            self.hall_body_yaw = None
            BigWorld.player().model.bh.yaw_enable = True
        if key in (keys.KEY_LCONTROL, getattr(keys, 'KEY_RCONTROL', keys.KEY_LCONTROL)):
            return not (self.hall.chat_open or settings_open or self.visible)
        if self.visible and key in (keys.KEY_LEFTMOUSE, keys.KEY_RIGHTMOUSE):
            self.preview_drag = bool(down)
            BigWorld.sendMouseMovementToScript(bool(down))
            # Let existing widgets receive their normal click/release events.
            return False
        if SysBox.instance().show_array:
            if key == keys.KEY_ESCAPE:
                if down:
                    SysBox.instance().hide('ESC')
                    self.exit_cancelled()
                return True
            return False
        settings = getattr(self.runtime, 'settings', None)
        if settings is not None and settings.ui.visible:
            if key == keys.KEY_ESCAPE:
                if down:
                    settings.ui.visible = False
                    self.restore_hall_control()
                return True
            return False
        if self.hall.chat_open:
            if key in (keys.KEY_RETURN, keys.KEY_ESCAPE):
                if down:
                    self.hall.close_chat()
                return True
            return False
        if key == keys.KEY_RETURN and not self.visible and not mods:
            if down and key not in self.menu_keys_down:
                self.menu_keys_down.add(key)
                self.hall.open_chat()
            return True
        if practice is not None and practice.engaged:
            return practice.handle_key(down, key, vk, mods)
        tab_key = getattr(keys, 'KEY_TAB', None)
        if tab_key is not None and key == tab_key and not mods and not self.visible \
                and FsmGame.state_is_offline():
            if down and key not in self.menu_keys_down:
                self.menu_keys_down.add(key)
                self.toggle_hall_combat()
            elif not down:
                self.menu_keys_down.discard(key)
            return True
        if not mods and getattr(self, 'hall_combat', False) and key in self.combat_keys():
            if down:
                if key not in self.combat_keys_down:
                    self.combat_keys_down.add(key)
                    BigWorld.player().handle_key_event(True, key, mods)
            elif key in self.combat_keys_down:
                self.combat_keys_down.discard(key)
                BigWorld.player().handle_key_event(False, key, mods)
            return True
        if FsmGame.state_is_offline() and not mods:
            if key == keys.KEY_RETURN and not self.visible:
                if down and key not in self.menu_keys_down:
                    self.menu_keys_down.add(key)
                    self.hall.open_chat()
                return True
            menu_tabs = {keys.KEY_Z:'equip', keys.KEY_X:'fashion', keys.KEY_C:'voice', keys.KEY_V:'story'}
            if key in menu_tabs:
                if down and key not in self.menu_keys_down:
                    self.menu_keys_down.add(key)
                    name = menu_tabs[key]
                    if self.visible and self.tab == name:
                        self.hide()
                    else:
                        self.show(name)
                elif not down:
                    self.menu_keys_down.discard(key)
                return True
            if key in (keys.KEY_B, keys.KEY_ESCAPE):
                if down and key not in self.menu_keys_down:
                    self.menu_keys_down.add(key)
                    if key == keys.KEY_B:
                        self.runtime.toggle_bag()
                        self.sync_input_mode()
                    elif self.runtime.close_bag():
                        self.sync_input_mode()
                    elif getattr(self, 'hall_ui_hidden', False):
                        self.set_hall_ui_hidden(False)
                    elif self.visible:
                        self.hide()
                    else:
                        self.confirm_exit()
                elif not down:
                    self.menu_keys_down.discard(key)
                return True
            hide_ui_key = getattr(keys, 'KEY_H', None)
            if hide_ui_key is not None and key == hide_ui_key and not self.visible:
                if down and key not in self.menu_keys_down:
                    self.menu_keys_down.add(key)
                    self.toggle_hall_ui()
                elif not down:
                    self.menu_keys_down.discard(key)
                return True
        if self.previous_key_listener is not None:
            return self.previous_key_listener(down, key, vk, mods)
        return False

    def handle_app_active(self, active):
        if not active:
            # Save before the native focus callback changes cursor/capture.
            self.capture_hall_camera()
            self.stop_hall_drag()
            self.preview_drag = False
            BigWorld.sendMouseMovementToScript(False)
            self.focus_generation = getattr(self, 'focus_generation', 0)+1
            self.focus_restore_pending = True
        self.previous_active_handler(active)
        if not active:
            self.menu_keys_down.clear()
            getattr(self, 'combat_keys_down', set()).clear()
            practice = getattr(self.runtime, 'practice', None)
            if practice is not None:
                practice.keys_down.clear()
        if active and not self.closed:
            generation = getattr(self, 'focus_generation', 0)
            self.focus_restore_pending = True
            self.sync_input_mode()
            # Fullscreen focus/cursor warps complete after the active callback.
            BigWorld.callback(0.1, lambda: self.finish_focus_restore(generation))

    def finish_focus_restore(self, generation):
        if self.closed or generation != getattr(self, 'focus_generation', 0) or not FsmGame.init().active:
            return
        if self.visible:
            self.sync_input_mode()
        else:
            self.restore_hall_control()
        if not self.cursor_shown:
            FsmGame.set_mouse_middle()
            BigWorld.sendMouseMovementToScript(True)
        self.focus_restore_pending = False

    def select(self, hero_type):
        if hero_type not in self.runtime.hero_ids:
            return
        self.hero_type = hero_type
        self.field.set_hero(hero_type)
        self.selector.set_hero_type(hero_type)
        self.update_part()
        self.runtime.write_status()

    def on_hero_select(self, hero_type):
        self.select(hero_type)

    def apply_clicked(self, sender):
        # On the fashion page "source shaping" also commits the focused suit, so
        # the hall body and the new copy use exactly the look on screen.
        fashion = self.parts.get('fashion')
        if self.tab == 'fashion' and fashion is not None:
            try:
                fashion.equip_selected(sender)
            except Exception:
                self.errors['fashion_shape'] = traceback.format_exc()
                self.log(self.errors['fashion_shape'])
        self.runtime.apply_hero(self.hero_type)
        self.initialize_player()
        self.request_source_clone()
        self.runtime.write_status()

    def cancel_clicked(self, sender):
        self.runtime.apply_hero(3)
        self.initialize_player()

    def toggle_hall_combat(self, value=None):
        practice = getattr(self.runtime, 'practice', None)
        if self.visible or self.hall.chat_open or self.closed:
            return False
        if practice is not None and practice.engaged:
            return False
        current = bool(getattr(self, 'hall_combat', False))
        self.hall_combat = (not current) if value is None else bool(value)
        # Reuse the training-arena input path: hidden cursor, raw mouse look and
        # the native battle camera while fighting, then the city cursor again.
        self.capture_hall_camera()
        self.restore_hall_control()
        if not self.hall_combat:
            self.center_hall_cursor()
        elif getattr(self, 'hall_ui_hidden', False):
            self.set_hall_crosshair(False)
        self.hall.refresh_hints()
        self.log('Hall combat mode: '+str(self.hall_combat))
        self.runtime.write_status()
        return True

    def set_hall_crosshair(self, visible):
        # Only the reticle image is touched: disabling Aim itself would unbind
        # the battle camera and spin the view while the cursor is captured.
        aim = getattr(BigWorld.player(), 'aim', None)
        ring = getattr(aim, 'ring', None) if aim is not None else None
        if ring is None:
            return False
        try:
            ring.scale = self.CROSSHAIR_SCALE
            ring.visible = bool(visible)
        except Exception:
            return False
        return True

    def enforce_hall_crosshair(self):
        if not bool(getattr(self, 'hall_combat', False)):
            return
        aim = getattr(BigWorld.player(), 'aim', None)
        ring = getattr(aim, 'ring', None) if aim is not None else None
        if ring is None or not getattr(ring, 'visible', False):
            return
        try:
            if abs(float(ring.scale)-self.CROSSHAIR_SCALE) > 0.01:
                ring.scale = self.CROSSHAIR_SCALE
        except Exception:
            pass

    def center_hall_cursor(self):
        """Leaving combat puts the UI cursor back at the middle of the screen."""
        try:
            width, height = BigWorld.getScreenSize()
            position = (width/2, height/2)
            import C_ui
            C_ui.cursor_pos(*position)
            C_ui.set_cursor_pos(*position)
            return position
        except Exception:
            return None

    def set_hall_ui_hidden(self, hidden):
        hidden = bool(hidden)
        if hidden == bool(getattr(self, 'hall_ui_hidden', False)):
            return
        if hidden:
            snapshot = {}
            for name, part in guiManager.instance().elements.items():
                try:
                    if part.visible:
                        snapshot[name] = True
                        part.visible = False
                except Exception:
                    pass
            self.ui_snapshot = snapshot
            for part in self.hall.parts.values():
                part.visible = False
            self.hall_ui_hidden = True
            if getattr(self, 'hall_combat', False):
                self.set_hall_crosshair(False)
            self.log('Hall UI hidden: '+str(len(snapshot))+' elements')
        else:
            for name in getattr(self, 'ui_snapshot', {}):
                part = guiManager.instance().elements.get(name)
                if part is not None:
                    try:
                        part.visible = True
                    except Exception:
                        pass
            self.ui_snapshot = {}
            for part in self.hall.parts.values():
                part.visible = True
            self.hall_ui_hidden = False
            if getattr(self, 'hall_combat', False):
                self.set_hall_crosshair(True)
            self.log('Hall UI restored')
        self.runtime.write_status()

    def toggle_hall_ui(self, value=None):
        practice = getattr(self.runtime, 'practice', None)
        if self.visible or self.hall.chat_open or self.closed:
            return False
        if practice is not None and practice.engaged:
            return False
        hidden = (not getattr(self, 'hall_ui_hidden', False)) if value is None else bool(value)
        self.set_hall_ui_hidden(hidden)
        return True

    def combat_keys(self):
        if self.combat_key_cache is None:
            mapping = getattr(getattr(BigWorld.player(), 'skill_controller', None), 'key_skill_map', None) or {}
            self.combat_key_cache = set(getattr(keys, name, None) for name in mapping)
            self.combat_key_cache.discard(None)
            # Movement stays on the native FSM path in both hall states.
            for name in ('KEY_W', 'KEY_A', 'KEY_S', 'KEY_D'):
                self.combat_key_cache.discard(getattr(keys, name, None))
        return self.combat_key_cache

    def request_source_clone(self):
        self.source_clone_pending = int(getattr(self, 'source_clone_pending', 0) or 0)+1
        self.source_clone_attempts = 0
        BigWorld.callback(0.2, self.try_source_clone)

    def try_source_clone(self):
        if self.closed or not getattr(self, 'source_clone_pending', 0):
            return
        hero_type = int(self.hero_type)
        player = BigWorld.player()
        model = getattr(player, 'model', None) if player is not None else None
        current = int(getattr(player, 'hero_type', 0) or 0) if player is not None else 0
        try:
            model_id = int(getattr(player, 'model_id', 0) or 0)
        except (TypeError, ValueError):
            model_id = 0
        if model is not None and current == hero_type and model_id == hero_type:
            self.source_clone_pending -= 1
            self.source_clone_attempts = 0
            self.spawn_source_clone()
            if self.source_clone_pending:
                BigWorld.callback(0.15, self.try_source_clone)
            return
        if self.source_clone_attempts >= 12:
            self.source_clone_pending = 0
            self.log('Source clone skipped: hall model stayed on another hero')
            return
        self.source_clone_attempts += 1
        BigWorld.callback(0.25, self.try_source_clone)

    def spawn_source_clone(self):
        self.maintain_source_clones()
        if len(self.source_clones) >= self.CLONE_LIMIT:
            self.log('Source clone limit reached: '+str(self.CLONE_LIMIT))
            self.hall.refresh_hints()
            return None
        player = BigWorld.player()
        hero_type = int(player.hero_type)
        offset = source_clone_offset(player.model.yaw, self.source_clone_serial)
        position = (player.position.x+offset[0], player.position.y+0.02, player.position.z+offset[1])
        try:
            from debug import DebugManager
            created = DebugManager.instance.create_target(1, 'PracticeAIHero', 60000, hero_type,
                position, self.runtime.fashions_for(hero_type))
            entity = created[0]
            model = getattr(entity, 'model', None)
            if model is not None:
                model.yaw = player.model.yaw
                if hasattr(model, 'bh'):
                    model.bh.bh_yaw = player.model.yaw
            try:
                entity.camp = int(player.camp)
            except Exception:
                pass
            self.source_clones.append(entity.id)
            self.source_clone_serial += 1
            self.log('Source clone created: '+repr({'id':entity.id, 'hero':hero_type,
                                                    'count':len(self.source_clones)}))
        except Exception:
            self.errors['clone'] = traceback.format_exc()
            self.log(self.errors['clone'])
            return None
        self.hall.refresh_hints()
        self.runtime.write_status()
        return entity.id

    def maintain_source_clones(self):
        clones = getattr(self, 'source_clones', None)
        if clones is None:
            return
        alive = []
        for entity_id in clones:
            entity = BigWorld.entity(entity_id)
            if entity is None:
                continue
            alive.append(entity_id)
            try:
                # Copies are decoration; combat cannot remove or damage them.
                if entity.hp < entity.mhp:
                    entity.hp = entity.mhp
                    entity.set_hp(0)
            except Exception:
                pass
        if len(alive) != len(clones):
            self.source_clones = alive
            self.hall.refresh_hints()

    def hint_lines(self):
        practice = getattr(self.runtime, 'practice', None)
        if practice is not None and (practice.active or practice.loading):
            return []
        combat = bool(getattr(self, 'hall_combat', False))
        if combat:
            lines = [u'\u5927\u5385\u00b7\u6218\u6597\u72b6\u6001\uff08Tab/Esc \u8fd4\u56de\u975e\u6218\u6597\uff09',
                     u'\u5de6\u952e\u7a7a\u767d\u5904\u666e\u653b\uff0cQ/E/R/F/C \u91ca\u653e\u6280\u80fd',
                     u'WASD \u79fb\u52a8\uff0c\u9f20\u6807\u79fb\u52a8\u8f6c\u52a8\u89c6\u89d2',
                     u'\u51c6\u5fc3\u3001\u5149\u6807\u4e0e\u8f93\u5165\u65b9\u5f0f\u4e0e\u7ec3\u4e60\u573a\u4e00\u81f4']
        else:
            lines = [u'\u5927\u5385\u00b7\u975e\u6218\u6597\u72b6\u6001\uff08Tab \u8fdb\u5165\u6218\u6597\uff09',
                     u'WASD \u79fb\u52a8\uff0c\u6eda\u8f6e\u62c9\u8fd1\u62c9\u8fdc',
                     u'\u5de6\u952e\u62d6\u52a8\u89c6\u89d2\uff0c\u53f3\u952e\u62d6\u52a8\u540c\u65f6\u8f6c\u5411',
                     u'\u754c\u9762\u6309\u94ae\u4f18\u5148\uff0c\u6b64\u65f6\u4e0d\u4f1a\u91ca\u653e\u6280\u80fd']
        lines.append(u'\u56de\u8f66 \u804a\u5929\uff0cZ \u82f1\u96c4\uff0cX \u65f6\u88c5\uff0cC \u8bed\u97f3\uff0cV \u6545\u4e8b')
        lines.append(u'B \u80cc\u5305\uff0cH \u9690\u85cf/\u663e\u793a\u5168\u90e8 UI\uff0cEsc \u9000\u51fa\u786e\u8ba4')
        lines.append(u'\u82f1\u96c4/\u65f6\u88c5\u9875\u70b9\u201c\u6e90\u529b\u5851\u5f62\u201d\u5728\u811a\u4e0b\u751f\u6210\u590d\u5236\u4f53')
        if self.hall.chat_open:
            lines.append(u'\u804a\u5929\u8f93\u5165\u4e2d\uff1a\u56de\u8f66\u6216 Esc \u6536\u8d77\uff08\u79bb\u7ebf\u4e0d\u53d1\u9001\uff09')
        else:
            lines.append(u'\u6e90\u529b\u590d\u5236\u4f53 %d/%d\uff0c\u53ef\u53cd\u590d\u751f\u6210\uff0c\u4e92\u4e0d\u5f71\u54cd' % (
                len(self.source_clones), self.CLONE_LIMIT))
        return lines

    def exit_clicked(self, sender):
        self.hide()

    def open_equipment(self):
        self.ensure_equipment().visible = True

    def ensure_equipment(self):
        if not hasattr(self, 'all_bags'):
            self.all_bags = BasicPhase.HeroAllEquipBag()
        return self.all_bags

    def open_skills(self):
        guiManager.get_ui('skill_desc_dlg').toggle()

    def tick(self):
        if self.closed:
            return
        self.runtime.hide_map()
        self.maintain_source_clones()
        practice = getattr(self.runtime, 'practice', None)
        hall_fighting = bool(getattr(self, 'hall_combat', False)) and not getattr(self, 'cursor_shown', True)
        if hall_fighting:
            # Aim re-activation can restore the native reticle size.
            self.enforce_hall_crosshair()
        if (practice is None or not practice.active) and not hall_fighting:
            aim = getattr(BigWorld.player(), 'aim', None)
            if aim is not None:
                aim.enabled(False)
        if not self.visible and self.control_restore_pending:
            if self.resume_hall_behavior():
                self.runtime.write_status()
        if self.visible:
            for name, part in guiManager.instance().elements.items():
                if name in ['battle_hp', 'battle_skill', 'cstate_panel', 'cstate_debuff_panel', 'cstate_special_panel',
                            'playerInfo', 'tipkey_panel', 'city_board_dlg', 'freshman_side_bar', 'welcome'] and part.visible:
                    self.hidden[name] = part
                    part.visible = False
            try:
                actor = self.field._get_curactor()
                if actor is not None and actor.hero_type == self.hero_type:
                    model = getattr(actor, 'model', None)
                    if model is not None:
                        if hasattr(model, 'bh'):
                            model.bh.active(True)
                        marker = (actor.id, actor.hero_type, id(model))
                        if marker != self.preview_linked:
                            if getattr(model, 'empty_bh', True):
                                actor.link_bh(False)
                            self.preview_linked = marker
                        if hasattr(model, 'bh') and model.bh.isBehaviorReady():
                            if not model.visible:
                                model.visible = True
                                actor.fade_to(1.0, duration=0.0)
            except Exception:
                self.errors['preview'] = traceback.format_exc()
                self.log(self.errors['preview'])
        BigWorld.callback(0.5, self.tick)

    def status(self):
        result = {'visible':self.visible, 'tab':self.tab, 'hero_type':self.hero_type,
                  'tabs_ready':sorted(self.parts), 'errors':self.errors}
        result['selector'] = {'visible':self.selector.visible, 'mode':self.selector.select_mode,
                              'basic_visible':bool(self.selector.part_basic.visible),
                              'list_visible':bool(self.selector.part_basic.hero_list.visible),
                              'coord':list(self.selector.part_basic.coord)}
        result['return_button_visible'] = bool(self.back.visible and self.back.btn_return.visible)
        result['map_visible'] = bool(guiManager.get_ui('miniMap').minimap.visible)
        result['input_mode'] = FsmGame.mode()
        result['hero_input_mode'] = FsmGame.MOD_HERO
        result['input_active'] = bool(FsmGame.init().active)
        result['input_locked'] = bool(FsmGame.init()._mode_lock)
        result['loading'] = bool(guiManager.in_loading())
        player = BigWorld.player()
        result['player_class'] = player.__class__.__name__
        result['player_position'] = list(player.position)
        result['hall_fashions'] = list(getattr(player, 'root_fashions', []) or [])
        result['player_input_enabled'] = bool(getattr(player, 'input_enabled', False))
        result['player_freeze_move'] = bool(getattr(player, 'freeze_move_flag', False))
        result['player_behavior_ready'] = bool(player.model.bh.isBehaviorReady()) if getattr(player, 'model', None) is not None and hasattr(player.model, 'bh') else False
        result['control_restore_pending'] = self.control_restore_pending
        result['camera_class'] = camera.inst.current.__class__.__name__
        result['cursor_mode'] = bool(FsmGame.HERO_ONLY_MOVE)
        result['camera_can_rotate'] = bool(BigWorld.dcursor().canRotate)
        result['hall_camera_distance'] = self.hall_camera_distance
        result['pitch_limits'] = [BigWorld.dcursor().minPitch, BigWorld.dcursor().maxPitch]
        result['cursor_toggle'] = self.cursor_shown
        result['camera_pitch'] = BigWorld.dcursor().pitch
        result['camera_yaw'] = BigWorld.dcursor().yaw
        result['appearance_updates'] = self.runtime.appearance_updates
        result['chat_open'] = self.hall.chat_open
        result['hall_combat'] = bool(getattr(self, 'hall_combat', False))
        result['hall_ui_hidden'] = bool(getattr(self, 'hall_ui_hidden', False))
        result['source_clones'] = len(getattr(self, 'source_clones', ()))
        result['hint_lines'] = [line.decode('gbk', 'replace') for line in getattr(self.hall, 'hints', ())][:9]
        result['visible_hero_count'] = len(self.selector.part_basic.hero_list.use_heros)
        result['content_counts'] = {}
        if 'fashion' in self.parts:
            result['content_counts']['fashion_suits'] = len(self.parts['fashion'].page_hero.suits)
            result['content_counts']['all_fashions'] = len(self.parts['fashion'].page_all.suits)
        if 'story' in self.parts:
            result['content_counts']['story_chapters'] = len(self.parts['story'].title_cells)
        if 'voice' in self.parts:
            result['content_counts']['voice_groups'] = len(self.parts['voice'].skill_cells)+len(self.parts['voice'].other_cells)
        if 'paint' in self.parts:
            result['content_counts']['paint_catalog'] = len(self.parts['paint'].all_paints)
        actor = self.field._get_curactor()
        if actor is not None:
            model = getattr(actor, 'model', None)
            result.update({'actor_class':actor.__class__.__name__, 'model_present':model is not None,
                           'model_visible':bool(model.visible) if model is not None else False,
                           'behavior_ready':bool(model.bh.isBehaviorReady()) if model is not None and hasattr(model, 'bh') else False})
        return result

    def exercise(self, action):
        if action == 'hall_repair':
            if self.visible:
                self.hide()
            self.runtime.close_bag()
            self.hall.close_chat()
            self.cursor_shown = False
            self.restore_hall_control()
            BigWorld.dcursor().pitch = 0.6
            BigWorld.dcursor().yaw = 0.8
            self.capture_hall_camera()
            self.show('equip')
            self.hide()
            result = {'pitch_after_menu':BigWorld.dcursor().pitch,
                      'yaw_after_menu':BigWorld.dcursor().yaw}
            self.handle_app_active(False)
            self.handle_app_active(True)
            result['pitch_after_focus'] = BigWorld.dcursor().pitch
            result['yaw_after_focus'] = BigWorld.dcursor().yaw
            self.confirm_exit()
            result['exit_opened'] = bool(SysBox.instance().show_array)
            self.handle_menu_key(True, keys.KEY_ESCAPE, 0, 0)
            self.handle_menu_key(False, keys.KEY_ESCAPE, 0, 0)
            result['exit_cancelled'] = not bool(SysBox.instance().show_array)
            self.hall.open_chat()
            result['chat_active'] = bool(self.hall.chat_panel.chat_edit.active)
            self.handle_menu_key(True, keys.KEY_Z, 0, 0)
            self.handle_menu_key(False, keys.KEY_Z, 0, 0)
            result['typing_z_stays_in_chat'] = self.hall.chat_open and not self.visible
            self.handle_menu_key(True, keys.KEY_RETURN, 0, 0)
            self.handle_menu_key(False, keys.KEY_RETURN, 0, 0)
            result['chat_closed'] = not self.hall.chat_open
            self.runtime.toggle_bag()
            page = self.runtime.bag.pages[self.runtime.bag.current_pid]
            tips = page.grids[0].get_tips_dict()
            result['item_tips_nonempty'] = bool(tips)
            result['item_tips_keys'] = sorted(tips.keys())
            self.runtime.close_bag()
            before = self.runtime.appearance_updates
            self.runtime.appearance_applied = None
            self.runtime.apply_saved_appearance()
            result['unchanged_appearance_updates'] = self.runtime.appearance_updates-before
            self.hall_pitch = self.hall_yaw = 0.0
            self.restore_hall_control()
            return result
        if action == 'exit_dialog':
            self.confirm_exit()
            result = {'confirmation_visible':bool(SysBox.instance().show_array)}
            SysBox.clear('ESC')
            self.restore_hall_control()
            return result
        if action == 'catalog':
            if self.runtime.bag is not None:
                self.runtime.bag.visible = False
                self.runtime.bag.destroy()
                self.runtime.bag = None
            self.runtime.toggle_bag()
            bag = self.runtime.bag
            counts = {}
            for pid in sorted(bag.items):
                bag.select_category(pid)
                counts[str(pid)] = len(bag.items[pid])
            return {'categories':counts, 'classification_errors':bag.classification_errors,
                    'total':sum(counts.values()), 'grids_per_page':len(bag.pages[bag.current_pid].grids)}
        if action == 'camera':
            self.handle_camera_mouse(0, 0, 120)
            close = self.hall_camera_distance
            self.handle_camera_mouse(0, 0, -120)
            return {'zoom_in':close, 'zoom_out':self.hall_camera_distance,
                    'pitch_limits':[BigWorld.dcursor().minPitch, BigWorld.dcursor().maxPitch]}
        if action == 'filter':
            basic = self.selector.part_basic
            basic.on_btn_a_click(basic.btn_a)
            result = {'warrior_count':len(basic.hero_list.use_heros)}
            basic.on_btn_all_click(basic.btn_all)
            result['all_count'] = len(basic.hero_list.use_heros)
            return result
        if action == 'page':
            page = self.selector.part_basic.hero_list.part_page
            page.page = min(2, page.max_page)
            result = {'page':page.page, 'max_page':page.max_page}
            page.page = 1
            return result
        if action == 'voice':
            self.set_tab('voice')
            part = self.parts['voice']
            for hero_type in [self.hero_type]+sorted(HeroVoicePhase.hero_voice_index_data.data):
                if hero_type not in self.runtime.hero_ids:
                    continue
                part.on_hero_select(hero_type)
                for group in part.skill_cells+part.other_cells:
                    for cell in group.cells:
                        if cell.visible and hasattr(cell, 'on_btn_play_click'):
                            cell.on_btn_play_click(cell.btn_play)
                            result = {'hero_type':hero_type, 'extend_id':cell.extend_id,
                                      'playing':cell.playing_timer is not None}
                            part.on_hero_select(self.hero_type)
                            return result
            return {'playing':False, 'indexed_heroes':sorted(HeroVoicePhase.hero_voice_index_data.data)}
        if action == 'fashion':
            self.set_tab('fashion')
            phase = self.parts['fashion']
            phase.tabpages.select_index = 1
            part = phase.page_all
            result = {'all_fashions':len(part.suits), 'pages':part.part_page.max_page,
                      'all_tab_visible':bool(part.visible)}
            for suit in phase.page_hero.suits:
                if suit.item_id and not suit.item.is_default:
                    phase.focus_suit(suit)
                    result['selected_skin'] = phase.page_hero.tgt_suit.item_id
                    return result
            return {'selected_skin':None}
        if action == 'equipment':
            self.open_equipment()
            return {'equipment_visible':bool(self.all_bags.visible)}
        raise ValueError('Unknown local validation action')

    def destroy(self):
        self.stop_hall_drag()
        self.preview_drag = False
        BigWorld.sendMouseMovementToScript(False)
        from debug import DebugManager
        manager = DebugManager.instance
        if manager.handle_mouse_event == self.offline_mouse_handler:
            manager.handle_mouse_event = manager._offline_original_preview_mouse
        if manager.handle_key_event == self.hall_key_handler:
            manager.handle_key_event = manager._offline_original_hall_key
        if FsmGame.init().handle_mouse_event == self.world_mouse_handler:
            FsmGame.init().handle_mouse_event = FsmGame.init()._offline_original_world_mouse
        if FsmGame.init().handle_key_event == self.world_key_handler:
            FsmGame.init().handle_key_event = FsmGame.init()._offline_original_world_key
        if self.visible:
            self.hide()
        self.closed = True
        # Release the preview scene after its GUI references are detached.
        # The game itself owns final process shutdown cleanup.
        BigWorld.callback(0.1, self.field.clear)
        if FsmGame.init().exclusive_key_listener == self.menu_key_listener:
            FsmGame.init().exclusive_key_listener = self.previous_key_listener
        if FsmGame.active == self.active_handler:
            FsmGame.active = self.previous_active_handler
        if camera.bc.handle_mouse_event == self.camera_mouse_handler:
            camera.bc.handle_mouse_event = self.previous_camera_mouse
        self.selector.part_basic.destroy()
        self.selector.part_collect.destroy()
        self.selector.part_btn.destroy()
        for part in self.parts.values():
            part.destroy()
        self.tabs.destroy()
        self.exit.destroy()
        self.back.destroy()


def install(hall, runtime, log):
    stage = HeroStage(hall, runtime, log)
    hall.hero_page = stage
    stage.restore_hall_control()
    return stage
