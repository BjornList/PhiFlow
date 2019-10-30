from .world import World, StateProxy
from .field.mask import union_mask


def obstacle_mask(world_or_proxy):
    world = world_or_proxy.world if isinstance(world_or_proxy, StateProxy) else world_or_proxy
    assert isinstance(world, World)
    geometries = [obstacle.geometry for obstacle in world.state.get_by_tag('obstacle')]
    return union_mask(geometries)
