# -*- coding: utf-8 -*-
"""Local counterparts for combat events normally completed by a room server."""
import BigWorld
from logic import FsmGame


class LocalCombat(object):
    SOUL_TRAPS = (16, 17, 23, 33)

    def __init__(self, practice):
        self.practice = practice
        self.souls = []
        self.summons = {}
        self.current_volume = None
        self.install()

    def enabled(self):
        return self.practice.active and FsmGame.state_is_offline()

    def install(self):
        from avolume.iAtkVolume import iAtkVolume
        from HeroSkillTrap import HeroSkillTrap
        from helper import ShadowCreatureManager
        owner = self
        for cls, name in ((iAtkVolume, 'apply_attack'), (iAtkVolume, '_skill_event_offline')):
            saved = '_offline_local_original_'+name
            if not hasattr(cls, saved):
                setattr(cls, saved, getattr(cls, name))
        if not hasattr(HeroSkillTrap, '_offline_local_original_get_model'):
            HeroSkillTrap._offline_local_original_get_model = staticmethod(HeroSkillTrap.get_model)
        manager = ShadowCreatureManager.inst
        if not hasattr(manager, '_offline_local_original_create'):
            manager._offline_local_original_create = manager.create

        def apply_attack(volume, avs, cur, maximum):
            previous = owner.current_volume
            owner.current_volume = volume if owner.enabled() else None
            try:
                return iAtkVolume._offline_local_original_apply_attack(volume, avs, cur, maximum)
            finally:
                owner.current_volume = previous

        def get_model(trap_id, attacker_id):
            model = HeroSkillTrap._offline_local_original_get_model(trap_id, attacker_id)
            volume = owner.current_volume
            if volume is not None and trap_id in owner.SOUL_TRAPS:
                from common_data import hero_trap_data
                config = hero_trap_data.data[trap_id]
                owner.souls.append({'model':model, 'attacker':attacker_id,
                    'hero_type':volume.hid, 'skill':volume.sid, 'config':config,
                    'space':BigWorld.player().spaceID, 'ready':BigWorld.time()+config.get('trap_delay', 0.1),
                    'expires':BigWorld.time()+config.get('trap_lifetime', 30.0)})
            return model

        def skill_event(volume, attacker, avs, cur, box):
            result = iAtkVolume._offline_local_original__skill_event_offline(volume, attacker, avs, cur, box)
            if owner.enabled() and attacker is BigWorld.player():
                owner.refresh_cooldown(attacker, volume.sid, avs)
            return result

        def create(attacker, identity, position):
            from common_data import skill_create_entity_data
            config = skill_create_entity_data.data.get(identity, {})
            if owner.enabled() and identity in (4, 8, 13, 26) and config.get('create_type') == 2:
                return owner.create_summon(attacker, identity, position, config)
            return manager._offline_local_original_create(attacker, identity, position)

        iAtkVolume.apply_attack = apply_attack
        iAtkVolume._skill_event_offline = skill_event
        HeroSkillTrap.get_model = staticmethod(get_model)
        manager.create = create

    def refresh_cooldown(self, player, skill, avs):
        from captain import cdmgr
        reset = avs.get('reset_skill_use_time', -1)
        if reset is not None and reset >= 0:
            player.update_skill_cd(player.hero_type, reset, 0,
                cdmgr.instance().dict_base_cd.get(reset, 0), True)
        # Same refresh rule as PlayerHero.start_skill_event in the online path.
        refresh = avs.get('refresh_skill')
        extra = avs.get('extra_cd', 0)
        if refresh is None or not extra:
            return
        import utils
        extra = utils.get_skill_cd_by_scale(player, refresh, extra, 0.0)
        cdmgr.update_next_extra_cd(refresh, extra)
        if refresh != skill:
            player.update_skill_cd(player.hero_type, refresh, -1, cdmgr.get_cd(refresh)[0], True)

    def create_summon(self, attacker, identity, position, config):
        from cdata.spheres import sphere_9
        from common_data import monster_prototype_data
        from helper import ShadowCreatureManager
        from hook import hero_hooker
        from functools import partial
        from helper import TimerManager
        model_id = config['model_id']
        sphere = sphere_9.data.get('Monster', {}).get(model_id)
        if sphere is None:
            self.practice.runtime.log('Local summon missing Monster configuration: '+str(model_id))
            return False
        prototype = monster_prototype_data.data.get(sphere['typ'])
        if prototype is None:
            return False
        detail = dict(prototype)
        detail.update(sphere)
        for prop in ('p_attack', 'm_attack', 'mhp', 'mcrit', 'pcrit', 'crit', 'p_armor', 'm_armor'):
            if hasattr(attacker, prop):
                scale = float(config.get('extra_3', 10000))/10000.0 if prop in ('p_attack', 'm_attack') else 1.0
                if prop == 'mhp':
                    scale = float(config.get('extra_4', 10000))/10000.0
                detail['h_'+prop] = getattr(attacker, prop)*scale
        detail.update(position=tuple(position), direction=(0.0, 0.0, attacker.model.yaw),
            hostID=attacker.id, masterID=attacker.id, master=attacker.base, masterSkill=0,
            camp=attacker.camp, lv=attacker.lv, shadow_creature_id=identity, typInSphere=model_id,
            lifeTime=max(0.0, config.get('duration', 10.0)))
        eid = BigWorld.createEntity('Monster', attacker.spaceID, 0, tuple(position),
            (0.0, 0.0, attacker.model.yaw), detail)
        target = BigWorld.entity(eid)
        self.summons[eid] = (attacker.id, identity)
        # Native shadow cleanup reads data/create_type; retain its bookkeeping.
        target.data = config
        target.model.position = position
        target.mhp = max(1, detail.get('h_mhp', detail.get('mhp', 1000)))
        target.hp = target.mhp if config.get('extra_5', 0) else min(target.mhp, attacker.hp)
        target.set_mhp(0)
        target.set_hp(0)
        target.modelscale = detail.get('model_scale', 1)
        target.set_modelscale(1)
        target.model.bh.bh_pos = position
        target.switch_filter('free')
        target.newPickUnitsNearBy = lambda *args: self.pick_units(target, target.position, *args)
        target.newPickUnitsNearPos = lambda pos, *args: self.pick_units(target, pos, *args)
        target.addState = lambda no, level, duration, source=0: self.add_state(target, no, level, duration)
        target.removeState = target.remove_combat_state
        manager = ShadowCreatureManager.inst
        sub_data = manager.data.setdefault(attacker.id, {})
        duration = max(0.1, config.get('duration', 10.0))
        timer = TimerManager.create_timer(duration,
            partial(manager._destroy_shadow_creature, sub_data, identity, attacker.id, eid), 1)
        sub_data.setdefault(identity, {})[eid] = [timer]
        timer.start()
        target.startOfflineAI(sphere.get('ai_mode', 0), sphere.get('btname', ''))
        target.enterWorld()
        hero_hooker(attacker.hero_type, 'shadow_creature_appear', attacker, target, position)
        return True

    def add_state(self, entity, no, level, duration):
        entity.add_combat_state(no, level, duration)
        entity.offline_add_state((no, level), duration)
        if duration > 0:
            eid = entity.id
            def expire():
                target = BigWorld.entity(eid)
                if target is not None:
                    target.remove_combat_state(no)
            BigWorld.callback(duration, expire)

    def pick_units(self, owner, position, distance, exclude_ally, exclude_enemy,
                   exclude_camp, exclude_subtype, keep_mode, unit_types):
        # The shared summon behavior trees use the server's newer picker API.
        # Apply the same filters to local entities; keep_mode 1/2 selects nearest/farthest.
        import Math
        import utils
        candidates = []
        center = Math.Vector3(position)
        for entity in BigWorld.entities.values():
            kind = getattr(entity, 'CU_TYPE', None)
            if entity is owner or kind is None or not hasattr(entity, 'isAlive'):
                continue
            if unit_types and kind not in unit_types:
                continue
            if not utils.isValidTarget(entity):
                continue
            if getattr(entity, 'hp', 1) <= 0 or getattr(entity, 'invisible', False):
                continue
            camp = getattr(entity, 'camp', None)
            if exclude_ally and camp == owner.camp or exclude_enemy and camp != owner.camp:
                continue
            if exclude_camp and camp == exclude_camp:
                continue
            if exclude_subtype and getattr(entity, 'sub_type', None) in exclude_subtype.get(kind, ()):
                continue
            length = (entity.position-center).length
            in_range = distance(length) if callable(distance) else distance is None or length <= distance
            if not in_range:
                continue
            candidates.append((length, entity.id))
        candidates.sort()
        if candidates and keep_mode in (1, 2):
            return [candidates[0 if keep_mode == 1 else -1][1]]
        return [eid for length, eid in candidates]

    def tick(self):
        for eid in list(self.summons):
            if BigWorld.entity(eid) is None:
                self.summons.pop(eid, None)
        now = BigWorld.time()
        player = BigWorld.player()
        for soul in self.souls[:]:
            if soul['space'] != player.spaceID or soul['expires'] <= now:
                self.souls.remove(soul)
                continue
            if now < soul['ready']:
                continue
            attacker = BigWorld.entity(soul['attacker'])
            if attacker is None or attacker is not player or attacker.hero_type != soul['hero_type']:
                continue
            position = soul['model'].position
            config = soul['config']
            delta = player.position-position
            if delta.x*delta.x+delta.z*delta.z > config.get('trap_range', 1.5)**2:
                continue
            if abs(delta.y) > config.get('trap_height', 1.7):
                continue
            # Use the original skill's configured resource event (one soul).
            player.mana.inform('target', soul['skill'], config['trigger_event_id'])
            self.souls.remove(soul)
            # The native lifetime callback still owns attachment/removal.
            soul['model'].visible = False

    def clear(self):
        player = BigWorld.player()
        for soul in self.souls:
            if soul['space'] == player.spaceID and soul['expires'] > BigWorld.time():
                soul['model'].visible = False
        self.souls[:] = []
        from helper import ShadowCreatureManager
        manager = ShadowCreatureManager.inst
        for eid, (attacker_id, identity) in self.summons.items():
            if BigWorld.entity(eid) is not None:
                sub_data = manager.data.get(attacker_id, {})
                if eid in sub_data.get(identity, {}):
                    manager._destroy_shadow_creature(sub_data, identity, attacker_id, eid)
                else:
                    BigWorld.destroyEntity(eid)
        self.summons.clear()
