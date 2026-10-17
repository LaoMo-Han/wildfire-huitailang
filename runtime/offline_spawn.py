# -*- coding: utf-8 -*-
"""One ground-level hall spawn, shared by the early entry and city runtime."""
SCENE = 'zc_new01'
# Ground measured in the original 1.0.192 hall; never use the old Y=229 seed.
POSITION = (52.0, 219.05, 178.0)


def place(player):
    from helper import ClientUtils
    x, y, z = POSITION
    hit = ClientUtils.get_collide_info(player.spaceID, (x, y+1.0, z),
        (x, y-3.0, z), comp_collide=False)
    if hit is None:
        return None
    point = (x, hit.position[1]+0.02, z)
    player.physics.teleport(point, (0.0, 0.0, 0.0))
    return point
