# -*- coding: utf-8 -*-
"""Original city HUD templates with local actions, independent of CityManager."""
import traceback
import BigWorld
import ResMgr
import rc
from guis import factory, xnui, font, color, guiManager
from guis.city.MainMenuBar import MainMenuBar as OriginalMenuBar
from logic import FsmGame


def gb(text):
    return text.encode('gbk')


class LocalNavigation(OriginalMenuBar):
    def on_main_menu_click(self, key_info, is_on):
        if key_info == 'page_hero':
            self.local_hall.hero_clicked()
        else:
            self.local_hall.notice()

    def on_btn_battle_click(self, sender):
        self.local_hall.notice(sender)

    def on_btn_practice_click(self, sender):
        self.local_hall.heroes.practice.toggle_entry()

    def on_btn_observer_click(self, sender):
        self.local_hall.notice(sender)


class OfflineHall(object):
    def __init__(self, heroes, log):
        self.heroes = heroes
        self.log = log
        self.parts = {}
        self.errors = {}
        self.buttons = []
        self.chat_open = False
        for name, build in [('navigation', self.navigation), ('activities', self.activities),
                            ('toolbar', self.toolbar), ('chat', self.chat)]:
            try:
                build()
                self.log('Original hall HUD installed: '+name)
            except Exception:
                self.errors[name] = traceback.format_exc()
                self.log(self.errors[name])

    def visible(self, part):
        part.visible = True
        self.parts[part.__class__.__name__] = part
        return part

    def notice(self, sender=None):
        pass

    def hero_clicked(self, sender=None):
        self.heroes.toggle()

    def navigation(self):
        top = self.visible(LocalNavigation())
        top.local_hall = self
        for name in ['status_punish', 'status_matching', 'status_back', 'status_start', 'btn_back', 'btn_quit']:
            getattr(top, name).visible = False
        top.status_battle.visible = True
        top.cd_battle.visible = False
        top.btn_battle.text = ''
        top.btn_battle.event_click = self.notice
        top.btn_practice.event_click = top.on_btn_practice_click
        top.btn_observer.event_click = self.notice

    def activities(self):
        side = self.visible(factory.TrainingMainDlg())
        side.con_dlg.visible = False
        side.box_0.visible = False
        side.con_icon.visible = True
        side.con_icon.allow_default_ani = False
        side.con_icon.coord = (7, -46)
        side.con_icon_acti.visible = True
        side.con_icon_acti.allow_default_ani = False
        side.con_icon_acti.coord = (7, 31)
        side.con_dlg_acti.visible = True
        side.con_dlg_acti.coord = (-314, 85)
        side.con_dlg_acti.allow_default_ani = False
        for name in ['img_news_acti', 'ing_news_teamcup', 'img_new', 'ani_news', 'ani_news_acti', 'btn_teamcup']:
            getattr(side, name).visible = False
        for name in ['btn_icon', 'btn_icon_acti', 'sensor_task', 'sensor_acti',
                     'button_0', 'button_1', 'img_btn_banner']:
            getattr(side, name).event_click = self.notice
        side.btn_close_acti.event_click = lambda sender: setattr(side.con_dlg_acti, 'visible', False)
        side.btn_down.event_click = lambda sender: setattr(side.con_dlg_acti, 'visible', True)
        side.btn_up.event_click = lambda sender: setattr(side.con_dlg_acti, 'visible', False)
        side.label_2.text = gb(u'\u67e5\u770b\u6bcf\u65e5\u7684\u91ce\u706b\u8bad\u7ec3\u4efb\u52a1')
        side.btn_down.coord = (-32, 300)
        side.btn_up.coord = (-32, 300)
        side.btn_up.visible = False

    def toolbar(self):
        self.visible(factory.MainMenuRightBottomBg())
        bar = self.visible(factory.MainMenuRightBottom())
        for name in ['bub_bag', 'bub_friend', 'bub_mail', 'reconnect_btn', 'img_frame_light',
                     'levelexp_total', 'levelexp_now', 'diagonal', 'lv_num', 'lv_bg', 'lv_progress', 'lv_progress_bg']:
            getattr(bar, name).visible = False
        bar.tmp_label_friend.text = ''
        bar.tmp_label_avatar.text = gb(u'\u79bb\u7ebf')
        bar.tmp_label_avatar.coord = (-174, -25)
        bar.tmp_label_avatar.set_color_unpack(color.LIGHT_CYAN, 0)
        bar.img_set_frame.state = 'lv1'
        bar.friends_btn.event_click = self.notice
        bar.bag.event_click = lambda sender: self.heroes.toggle_bag()
        bar.mail_btn.event_click = self.notice
        bar.avatar_btn.event_click = self.hero_clicked
        self.bottom = bar
        self.update_hero()

    def update_hero(self):
        if hasattr(self, 'bottom'):
            hero = int(BigWorld.player().hero_type)
            name = 'ICON_ROLE_4_HERO_%04d' % hero
            if hasattr(rc, name) and ResMgr.fileExist(getattr(rc, name)):
                self.bottom.avatar_btn.image = getattr(rc, name)
            else:
                self.bottom.avatar_btn.image = getattr(rc, 'ICON_HERO_64_%04d' % hero)

    def chat(self):
        chat = self.visible(factory.ChatCityNewDlg())
        for name in ['show_content', 'con_list', 'tab_content', 'con_unable', 'con_timer', 'con_emote', 'img_bg']:
            getattr(chat, name).visible = False
        chat.btn_channel.text = gb(u'\u5206\u7ebf')
        self.chat_panel = chat
        chat.chat_edit.event_text_enter = lambda sender: self.close_chat()
        chat.chat_edit.event_text_escape = lambda sender: self.close_chat()
        chat.chat_edit.event_active_changed = self.chat_focus_changed
        chat.btn_send.event_click = self.notice
        chat.btn_channel.event_click = self.notice

    def open_chat(self):
        if self.chat_open:
            return
        self.hero_page.stop_hall_drag()
        self.hero_page.capture_hall_camera()
        self.heroes.close_bag()
        self.chat_open = True
        self.chat_return_visible = self.chat_panel.visible
        self.chat_panel.visible = True
        for name in ['show_content', 'con_list', 'img_bg']:
            getattr(self.chat_panel, name).visible = True
        FsmGame.set_hero_only_move(True)
        FsmGame.init().mode = FsmGame.MOD_NOML
        self.chat_panel.chat_edit.active = True
        self.hero_page.cursor_shown = True

    def close_chat(self):
        if not self.chat_open:
            return
        self.chat_open = False
        self.chat_panel.chat_edit.active = False
        for name in ['show_content', 'con_list', 'img_bg']:
            getattr(self.chat_panel, name).visible = False
        self.chat_panel.visible = getattr(self, 'chat_return_visible', True)
        self.hero_page.sync_input_mode()

    def chat_focus_changed(self, sender):
        if self.chat_panel.chat_edit.active and not self.chat_open:
            self.open_chat()
        elif not self.chat_panel.chat_edit.active and self.chat_open:
            self.close_chat()

    def team(self):
        panel = self.visible(factory.GroupMainDlg())
        panel.list_player.visible = False
        panel.con_apply.visible = False
        panel.img_bg.visible = False
        panel.bt_out.visible = False
        panel.bt_add.event_click = self.notice
        panel.btn_max.event_click = self.notice

    def destroy(self):
        if hasattr(self, 'hero_page'):
            self.hero_page.destroy()
        for part in self.parts.values():
            part.destroy()
        self.parts.clear()

    def layout_status(self):
        result = {}
        for key, part in self.parts.items():
            result[key] = {'coord': list(part.coord), 'visible': bool(part.visible)}
        return result

    def visible_gui(self):
        result = []
        for name, part in guiManager.instance().elements.items():
            try:
                if part.visible:
                    result.append(name)
            except Exception:
                pass
        return sorted(result)

def install(heroes, log):
    hall = OfflineHall(heroes, log)
    heroes.hall = hall
    heroes.hide_map()
    guiManager.get_ui('city_fps_bar')._set_container_visible(False)
    try:
        context = {}
        execfile('../res/editor/client/hero_stage.py', context)
        context['install'](hall, heroes, log)
    except Exception:
        hall.errors['hero_page'] = traceback.format_exc()
        log(hall.errors['hero_page'])
    FsmGame.init().mode = FsmGame.MOD_HERO
    return hall
