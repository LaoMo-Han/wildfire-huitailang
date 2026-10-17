# -*- coding: utf-8 -*-
"""Small 1.0.304 client fixes adapted to the 1.0.192 local runtime.

Keep the old engine, assets and offline state. Do not load newer bytecode or
install the online SDK, account checks, telemetry or network code.
"""


class LocalCompatibility(object):
    FIXES = ('player_cash_events', 'tutorial_input_result',
             'controlled_teleport', 'talent_revert_ui')

    def __init__(self, runtime):
        self.runtime = runtime
        self.install_hooks()

    def practicing(self):
        practice = self.runtime.practice
        return practice is not None and practice.active

    def install_hooks(self):
        import BigWorld
        from Hero import Hero, PlayerHero
        owner = self
        # Retain the native methods across a runtime reload; never stack wrappers.
        originals = ((Hero, 'set_cash'), (PlayerHero, 'handle_special_event'),
                     (PlayerHero, 'allow_tp'), (PlayerHero, 'revert_evolution_item'))
        for cls, name in originals:
            saved = '_offline_304_original_'+name
            if not hasattr(cls, saved):
                setattr(cls, saved, getattr(cls, name))
        original_cash = Hero._offline_304_original_set_cash
        original_special = PlayerHero._offline_304_original_handle_special_event
        original_tp = PlayerHero._offline_304_original_allow_tp
        original_revert = PlayerHero._offline_304_original_revert_evolution_item

        def set_cash(entity, old):
            # 1.0.304 Hero.set_cash gates this notification to BigWorld.player().
            if entity == BigWorld.player():
                return original_cash(entity, old)

        def handle_special_event(entity, down, key, mods):
            if not owner.practicing():
                return original_special(entity, down, key, mods)
            from tutorial import TutorialFlowPlayer
            hacker = TutorialFlowPlayer.key_hacker()
            if hacker.get_enable():
                hacker.handle_key_event(down, key, 0, mods)
            # Preserve the tutorial callback while using the newer return contract.
            return False

        def allow_tp(entity):
            allowed = original_tp(entity)
            if owner.practicing() and allowed:
                return allowed and entity.debuff.can_attack()
            return allowed

        def revert_evolution_item(entity, old_evol_id, new_evol_id, full_cash):
            if not owner.practicing():
                return original_revert(entity, old_evol_id, new_evol_id, full_cash)
            from common_data import equip_evolution_data
            from guis.battle.TalentEvolutionPanel import TALENT_KEYS
            info = equip_evolution_data.data.get(old_evol_id)
            if info is None or (info['typ'], info['stype']) not in TALENT_KEYS:
                return original_revert(entity, old_evol_id, new_evol_id, full_cash)
            # The old PlayerHero implementation always dispatches to equipment
            # views. The newer implementation separates talents after the base edit.
            result = Hero.revert_evolution_item(entity, old_evol_id, new_evol_id, full_cash)
            owner.refresh_talent_revert(old_evol_id)
            return result

        Hero.set_cash = set_cash
        PlayerHero.handle_special_event = handle_special_event
        PlayerHero.allow_tp = allow_tp
        PlayerHero.revert_evolution_item = revert_evolution_item

    def refresh_talent_revert(self, evo_id):
        import BigWorld
        from guis import guiManager
        talent = guiManager.get_ui('talent_evolution')
        # 1.0.192 has these fields but lacks the newer on_talent_reverted method.
        if any(evo_id in choices for choices in talent.talent_data.values()):
            if evo_id in talent.use_talent_list:
                talent.use_talent_list.remove(evo_id)
            talent._update_popup_ui()
            talent._update_tool_bar()
            bar = guiManager.get_ui('equip_evolution_v2')
            update_revertable = getattr(bar, 'update_revertable_id', None)
            if update_revertable is not None:
                update_revertable(-1)
            talent.last_revert_talent_time = BigWorld.time()
        full = guiManager.get_ui('equip_evolution')
        cell = full.talent_cell_map.get(evo_id)
        # Newer cells include a cancel timer; old cells need only a state refresh.
        reverted = getattr(cell, 'on_talent_reverted', None)
        if reverted is not None:
            reverted()
        full._update_talent()

    def status(self):
        return {'source_version':'1.0.304', 'target_version':'1.0.192',
                'fixes':list(self.FIXES)}


def install(runtime):
    controller = LocalCompatibility(runtime)
    runtime.log('Local client compatibility fixes ready: '+', '.join(controller.FIXES))
    return controller
