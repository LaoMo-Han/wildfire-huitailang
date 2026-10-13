# -*- coding: utf-8 -*-
"""The formal StageSelectPart/StageInfoPart hero screen, using original pages."""
import traceback
import BigWorld
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


class LocalActorField(ActorField.ActorField):
    def enter(self, *args, **kwargs):
        self._reuse_scene = True
        try:
            return ActorField.ActorField.enter(self, *args, **kwargs)
        finally:
            self._reuse_scene = False

    def clear(self):
        if getattr(self, '_reuse_scene', False) and self.space_id is not None:
            return
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
    def __init__(self, hall, runtime, log):
        self.hall, self.runtime, self.log = hall, runtime, log
        self.visible = False
        self.closed = False
        self.hero_type = int(BigWorld.player().hero_type)
        self.tab = 'equip'
        self.errors = {}
        self.parts = {}
        self.hidden = {}
        self.preview_linked = None
        self.catalog_initialized = False
        self.menu_keys_down = set()
        self.cursor_shown = False
        self.previous_camera_mouse = camera.bc.handle_mouse_event
        self.camera_mouse_handler = self.handle_camera_mouse
        camera.bc.handle_mouse_event = self.camera_mouse_handler
        self.hall_camera_distance = camera.bc.bw_cam.pivotMaxDist
        self.control_restore_pending = False
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
        if name is not None:
            self.tab = name
        if self.visible:
            if name is not None:
                self.set_tab(name)
            return
        try:
            self.runtime.hide_map()
            self.runtime.close_bag()
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
        self.runtime.write_status()

    def hide(self):
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
        self.runtime.write_status()

    def restore_hall_control(self):
        # ActorField's original leave callback only resumes PlayerAvatar.
        # The built-in offline state uses PlayerHero and needs the same resume.
        self.control_restore_pending = True
        self.resume_hall_behavior()
        FsmGame.init().mode = FsmGame.MOD_HERO
        FsmGame.set_hero_only_move(self.cursor_shown)
        camera.tryReleaseDC(FsmGame.init())
        camera.bc()
        camera.bc.setTarget()
        camera.bc.bw_cam.pivotMaxDist = self.hall_camera_distance
        BigWorld.dcursor().minPitch = -1.569
        BigWorld.dcursor().maxPitch = 1.569
        FsmGame.init().reset_mouse_state()

    def handle_camera_mouse(self, dx, dy, dz):
        if FsmGame.state_is_offline() and not self.visible and not self.cursor_shown and dz:
            self.hall_camera_distance = max(1.0, min(30.0,
                self.hall_camera_distance*(0.9 if dz > 0 else 1.0/0.9)))
            camera.bc.bw_cam.pivotMaxDist = self.hall_camera_distance
            camera.bc.bw_cam.maxDistHalfLife = 0.1
            return True
        return self.previous_camera_mouse(dx, dy, dz)

    def confirm_exit(self):
        if SysBox.instance().show_array:
            return
        SysBox.double_btn(text=u'\u786e\u5b9a\u9000\u51fa\u6e38\u620f\u5417\uff1f'.encode('gbk'),
                          yes_callback=BigWorld.quit, cancel_key='offline_exit')

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
            if result:
                self.runtime.write_status()
            return result
        except Exception:
            self.runtime.last_error = traceback.format_exc()
            self.log(self.runtime.last_error)
            self.runtime.write_status()
            return True

    def handle_menu_key_impl(self, down, key, vk, mods):
        # The engine caches tw2's entry point. Use its existing FSM listener
        # for the requested menu/return keys; movement continues through the FSM.
        if not down:
            self.menu_keys_down.discard(key)
        if SysBox.instance().show_array:
            return False
        if FsmGame.state_is_offline() and not self.visible and key in (
                keys.KEY_LCONTROL, getattr(keys, 'KEY_RCONTROL', keys.KEY_LCONTROL)):
            if down and key not in self.menu_keys_down:
                self.menu_keys_down.add(key)
                self.cursor_shown = not self.cursor_shown
                ShortcutManager.instance().ob_show_cursor(self.cursor_shown)
            elif not down:
                self.menu_keys_down.discard(key)
            return True
        if FsmGame.state_is_offline() and not mods:
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
                    elif self.runtime.close_bag():
                        pass
                    elif self.visible:
                        self.hide()
                    else:
                        self.confirm_exit()
                elif not down:
                    self.menu_keys_down.discard(key)
                return True
        if self.previous_key_listener is not None:
            return self.previous_key_listener(down, key, vk, mods)
        return False

    def handle_app_active(self, active):
        self.previous_active_handler(active)
        if not active:
            self.menu_keys_down.clear()
        if active and not self.visible and not self.closed:
            self.restore_hall_control()

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
        self.runtime.apply_hero(self.hero_type)
        self.initialize_player()
        self.runtime.write_status()

    def cancel_clicked(self, sender):
        self.runtime.apply_hero(3)
        self.initialize_player()

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
        if action == 'exit_dialog':
            self.confirm_exit()
            result = {'confirmation_visible':bool(SysBox.instance().show_array)}
            SysBox.clear('offline_exit')
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
