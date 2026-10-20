# -*- coding: utf-8 -*-
"""Use a donor's native skills and behavior with the selected hero's model."""
import BigWorld
from captain import skillmanager as SK
from guis import guiManager


class Skillsets(object):
    def __init__(self, runtime):
        self.runtime = runtime
        self.busy = False
        self.serial = 0
        self.error = None
        self.selector = None

    @property
    def selector_visible(self):
        return self.selector is not None and self.selector.visible

    def close_selector(self):
        if self.selector is not None:
            self.selector.visible = False
        self.runtime.hall.hero_page.restore_hall_control()

    def toggle_selector(self):
        practice = self.runtime.practice
        if self.busy or (practice is not None and practice.loading):
            return
        if self.selector_visible:
            self.close_selector()
            return
        stage = self.runtime.hall.hero_page
        if stage.visible:
            stage.hide()
        if practice is not None and practice.active:
            practice.toolbar.hero_list.visible = False
            for name in practice.MODALS:
                guiManager.get_ui(name).visible = False
            if hasattr(practice, 'map_dialog'):
                practice.map_dialog.visible = False
        if self.selector is None:
            # Reuse the native paginated hero list, with its own selection
            # callback. The practice attacker picker changes the whole hero.
            self.selector = stage.selector.__class__()
            self.selector.local_stage = self
            self.selector.setting(self.runtime.hero_ids)
            self.selector.part_basic.hero_list.lock_mode = False
            from guis import xnui
            import rc
            # Below the hero pager, clear of the selectable portraits.
            self.reset_button = xnui.XButton(self.selector.part_basic, 51, 635,
                rc.COMMON_BTN_RECT_BIG,
                u'\u8fd8\u539f\u6240\u6709\u6280\u80fd\u7ec4'.encode('gbk'))
            self.reset_button.set_size(200, 24)
            self.reset_button.event_click = lambda sender: self.reset_all()
        self.selector.connect(self, int(BigWorld.player().hero_type), select_mode=0)
        stage.restore_hall_control()
        self.runtime.write_status()

    def visual_hero(self):
        player = BigWorld.player()
        return int(getattr(player, '_offline_visual_hero', player.root_hero_type))

    def apply_saved(self):
        player = BigWorld.player()
        if player is None or getattr(player, 'model', None) is None:
            return
        visual = self.visual_hero()
        source = self.runtime.profile.get('skillsets', {}).get(str(visual), visual)
        if source not in self.runtime.hero_ids:
            source = visual
        if int(player.hero_type) != source or int(player.model_id) != visual:
            self.select(source, save=False)
        else:
            self.runtime.equipment.apply()

    def reset_all(self):
        practice = self.runtime.practice
        if self.busy or (practice is not None and practice.loading):
            return False
        return self.select(self.visual_hero(), save=False, reset_all=True)

    def save_selection(self, visual, source, reset_all=False):
        had_saved = 'skillsets' in self.runtime.profile
        previous = self.runtime.profile.get('skillsets')
        if reset_all:
            self.runtime.profile.pop('skillsets', None)
        else:
            mappings = dict(previous or {})
            mappings[str(visual)] = source
            self.runtime.profile['skillsets'] = mappings
        try:
            self.runtime.save()
        except Exception:
            if had_saved:
                self.runtime.profile['skillsets'] = previous
            else:
                self.runtime.profile.pop('skillsets', None)
            raise

    def select(self, source, save=True, reset_all=False):
        if self.busy:
            return False
        source = int(source)
        if source not in self.runtime.hero_ids:
            raise ValueError('Skill donor is not available in this client')
        if self.selector_visible:
            self.close_selector()
        player = BigWorld.player()
        visual = self.visual_hero()
        old_source = int(player.hero_type)
        self.busy = True
        self.error = None
        self.serial += 1
        serial = self.serial
        practice = self.runtime.practice
        if practice is not None:
            practice.combat.clear()
            practice.clear_buffs()
        try:
            self.rebuild(player, visual, source)
            if getattr(player, 'model', None) is not None:
                player.model.bh.active(True)
        except Exception:
            self.busy = False
            self.error = 'Skillset rebuild failed'
            # Rebuild the previous combination before propagating the failure.
            self.rebuild(player, visual, old_source)
            raise
        def finish(attempt=0):
            if serial != self.serial or BigWorld.player() is not player:
                return
            model = getattr(player, 'model', None)
            if model is None or not model.bh.isBehaviorReady():
                if attempt < 80:
                    BigWorld.callback(0.1, lambda: finish(attempt+1))
                    return
                self.busy = False
                self.error = 'Skillset behavior did not become ready'
                self.runtime.log(self.error)
                self.rebuild(player, visual, old_source)
                self.runtime.hall.hero_page.restore_hall_control()
                self.runtime.write_status()
                return
            self.busy = False
            if save or reset_all:
                self.save_selection(visual, source, reset_all=reset_all)
            self.runtime.equipment.apply()
            if practice is not None:
                practice.enable_cooldowns()
                if practice.active:
                    practice.refill_skill_resources()
            self.runtime.apply_saved_appearance(True)
            self.runtime.hall.update_hero()
            if practice is not None and hasattr(practice, 'skillset_button'):
                from helper import ClientUtils
                practice.skillset_button.text = (u'\u6280\u80fd\uff1a%s F8' %
                    ClientUtils.get_hero_name(source).decode('gbk')).encode('gbk')
            self.runtime.hall.hero_page.restore_hall_control()
            guiManager.get_ui('battle_skill').update_skill()
            self.runtime.write_status()
        BigWorld.callback(0.1, finish)
        return True

    def rebuild(self, player, visual, source):
        original = SK.ins.get_hero
        model_id = original(None, visual).get('model_id', visual)
        def mixed(entity, hero):
            info = original(entity, hero)
            if hero == source and info is not None:
                info = dict(info)
                info['model_id'] = model_id
            return info
        # Native set_bh_id restricts a mesh to its own behaviors. Both resources
        # are present locally; select the donor behavior explicitly for mixing.
        had_override = 'set_bh_id' in player.__dict__
        old_override = player.__dict__.get('set_bh_id')
        player.set_bh_id = lambda bhid: setattr(player, '_bh_id', bhid)
        player._offline_visual_hero = visual
        player.root_hero_type = visual
        SK.ins.get_hero = mixed
        try:
            if player.set_combat_type(source, None, False, False, True, False) is False:
                raise RuntimeError('Native combat initialization rejected skillset')
        finally:
            SK.ins.get_hero = original
            if had_override:
                player.set_bh_id = old_override
            else:
                del player.set_bh_id

    def status(self):
        return {'visual_hero':self.visual_hero(),
                'skill_hero':int(BigWorld.player().hero_type),
                'busy':self.busy, 'error':self.error,
                'selector_visible':self.selector_visible}
