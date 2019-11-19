from .field import advect
from .domain import DomainState
from .physics import Physics, StateDependency
from .field.util import diffuse
from .field.effect import effect_applied
from phi import struct


class Burgers(DomainState):

    def __init__(self, domain, velocity, viscosity=0.1, tags=('burgers', 'velocityfield'), **kwargs):
        DomainState.__init__(**struct.kwargs(locals()))

    def default_physics(self):
        return BurgersPhysics()

    @struct.attr(default=0.0)
    def velocity(self, velocity):
        return self.centered_grid('velocity', velocity, components=self.rank)

    @struct.prop(default=0.1)
    def viscosity(self, viscosity): return viscosity


class BurgersPhysics(Physics):

    def __init__(self):
        Physics.__init__(self, [StateDependency('effects', 'velocity_effect', blocking=True)])

    def step(self, state, dt=1.0, effects=()):
        v = state.velocity
        v = advect.semi_lagrangian(v, v, dt)
        v = diffuse(v, dt * state.viscosity, substeps=1)
        for effect in effects:
            v = effect_applied(effect, v, dt)
        return state.copied_with(velocity=v, age=state.age + dt)
