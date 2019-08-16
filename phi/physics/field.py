from .physics import *
from phi.math.geom import *
from phi import math


class Field(Struct):
    __struct__ = Struct.__struct__.extend((), ('_bounds',))

    def __init__(self, bounds=None):
        Struct.__init__(self)
        self._bounds = bounds

    @property
    def bounds(self):
        return self._bounds

    def sample_at(self, location):
        raise NotImplementedError(self)

    def sample_component_at(self, component, location):
        all_components = self.sample_at(location)
        return all_components[..., component]

    def sample_grid(self, grid, staggered=False):
        if not staggered:
            loc = grid.center_points()
            return self.sample_at(loc)
        else:
            components = []
            for dim in range(grid.rank):
                loc = grid.staggered_points(dim)
                components.append(self.sample_component_at(dim, loc))
            return math.stack(components, axis=-1)

    @staticmethod
    def to_field(value):
        if isinstance(value, Field):
            return value
        if isinstance(value, Geometry):
            return ConstantField(bounds=value, value=1.0)
        if isinstance(value, Number):
            return ConstantField(bounds=None, value=value)
        raise ValueError('Cannot to_field Field from type %s' % type(value))


class ConstantField(Field):

    __struct__ = Field.__struct__.extend((), ('_value',))

    def __init__(self, bounds=None, value=1.0):
        Field.__init__(self, bounds)
        if isinstance(value, math.Number):
            value = math.expand_dims(value)
        self._value = value

    @property
    def value(self):
        return self._value

    def sample_at(self, location):
        if self._bounds is None:
            return self.value
        else:
            return self.bounds.value_at(location) * self.value

    def __repr__(self):
        return repr(self._value)


class GridField(Field):

    def __init__(self, domain, values):
        Field.__init__(self, domain.grid.box)
        self._values = values
        self._domain = domain

    def sample_grid(self, grid, staggered=False):
        if staggered:
            raise NotImplementedError(self)
        if grid == self._domain.grid:
            return self._values
        else:
            return self.sample_at(grid.center_points())

    @property
    def values(self):
        return self._values

    @property
    def domain(self):
        return self._domain