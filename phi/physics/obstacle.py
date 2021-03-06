from phi import struct
from phi.geom.geometry import Geometry
from .field.effect import FieldEffect, GeometryMask
from .physics import State, Physics
from .material import Material, CLOSED


@struct.definition()
class Obstacle(State):

    def __init__(self, geometry, material=CLOSED, velocity=0, tags=('obstacle',), **kwargs):
        State.__init__(self, **struct.kwargs(locals()))

    @struct.constant()
    def geometry(self, geometry):
        assert isinstance(geometry, Geometry)
        return geometry

    @struct.constant(default=CLOSED)
    def material(self, material):
        assert isinstance(material, Material)
        return material

    @struct.constant(default=0)
    def velocity(self, velocity): return velocity


class GeometryMovement(Physics):

    def __init__(self, geometry_function):
        Physics.__init__(self)
        self.geometry_at = geometry_function

    def step(self, obj, dt=1.0, **dependent_states):
        next_geometry = self.geometry_at(obj.age + dt)
        h = 1e-2 * dt if dt > 0 else 1e-2
        perturbed_geometry = self.geometry_at(obj.age + dt + h)
        velocity = (perturbed_geometry.center - next_geometry.center) / h
        if isinstance(obj, Obstacle):
            return obj.copied_with(geometry=next_geometry, velocity=velocity, age=obj.age + dt)
        if isinstance(obj, FieldEffect):
            field = obj.field
            assert isinstance(field, GeometryMask)
            assert len(field.geometries) == 1
            return obj.copied_with(field=obj.field.copied_with(geometries=(next_geometry,)), age=obj.age + dt)
