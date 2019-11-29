import numpy as np
from phi import struct, math
from phi.geom import AABox
from phi.geom.geometry import assert_same_rank
from phi.physics.field.staggered_grid import staggered_component_box
from . import State
from .material import Material, OPEN
from .field import CenteredGrid, StaggeredGrid, Field, DIVERGENCE_FREE


@struct.definition()
class Domain(struct.Struct):

    def __init__(self, resolution, boundaries=OPEN, box=None, **kwargs):
        """
        Simulation domain that specifies size and boundary conditions.

        If all boundary surfaces should have the same behaviour, pass a single Material instance.

        To specify the boundary constants_dict per dimension or surface, pass a tuple or list with as many elements as there are spatial dimensions (highest dimension first).
        Each element can either be a Material, specifying the faces perpendicular to that axis, or a pair
        of Material holding (lower_face_material, upper_face_material).

        Examples:

        Domain(grid, OPEN) - all surfaces are open

        DomainBoundary(grid, boundaries=[(SLIPPY, OPEN), SLIPPY]) - creates a 2D domain with an open top and otherwise solid boundaries

        :param grid: Grid object or 1D tensor specifying the grid dimensions
        :param boundaries: Material or list of Material/Pair of Material
        """
        struct.Struct.__init__(self, **struct.kwargs(locals()))

    @struct.constant()
    def resolution(self, resolution):
        if len(math.staticshape(resolution)) == 0:
            resolution = [resolution]
        return np.array(resolution)

    @struct.constant(dependencies='resolution')
    def box(self, box):
        return AABox.to_box(box, resolution_hint=self.resolution)

    @struct.constant(default=OPEN)
    def boundaries(self, boundaries):
        assert isinstance(boundaries, (Material, list, tuple))
        if isinstance(boundaries, (tuple, list)):
            assert len(boundaries) == self.rank
        return _collapse_equals(boundaries, leaf_type=Material)

    @property
    def rank(self):
        return len(self.resolution)

    def cell_index(self, global_position):
        local_position = self.box.global_to_local(global_position) * self.resolution
        position = math.to_int(local_position - 0.5)
        position = math.maximum(0, position)
        position = math.minimum(position, self.resolution-1)
        return position

    def center_points(self):
        idx_zyx = np.meshgrid(*[np.arange(0.5, dim+0.5, 1) for dim in self.resolution], indexing="ij")
        return math.expand_dims(math.stack(idx_zyx, axis=-1), 0)

    def staggered_points(self, dimension):
        idx_zyx = np.meshgrid(*[np.arange(0.5, dim+1.5, 1)
                                if dim != dimension else np.arange(0, dim+1, 1)
                                for dim in self.resolution], indexing="ij")
        return math.expand_dims(math.stack(idx_zyx, axis=-1), 0)


    def indices(self):
        """
        Constructs a grid containing the index-location as components.
        Each index denotes the location within the tensor starting from zero.
        Indices are encoded as vectors in the index tensor.
        
        :param dtype: a numpy data type (default float32)
        :return: an index tensor of shape (1, spatial dimensions..., spatial rank)
        """
        idx_zyx = np.meshgrid(*[range(dim) for dim in self.resolution], indexing="ij")
        return math.expand_dims(np.stack(idx_zyx, axis=-1))

    @staticmethod
    def equal(grid1, grid2):
        assert isinstance(grid1, Domain), 'Not a Domain: %s' % type(grid1)
        assert isinstance(grid2, Domain), 'Not a Domain: %s' % type(grid2)
        return np.all(grid1.resolution == grid2.resolution) and grid1.box == grid2.box

    def centered_shape(self, components=1, batch_size=1, name=None, extrapolation=None):
        with struct.anytype():
            return CenteredGrid(name, tensor_shape(batch_size, self.resolution, components), box=self.box, batch_size=batch_size, extrapolation=extrapolation)

    def staggered_shape(self, batch_size=1, name=None, extrapolation=None):
        with struct.anytype():
            grids = []
            for axis in range(self.rank):
                shape = _extend1(tensor_shape(batch_size, self.resolution, 1), axis)
                box = staggered_component_box(self.resolution, axis, self.box)
                grid = CenteredGrid(None, shape, box, batch_size=batch_size, extrapolation=extrapolation)
                grids.append(grid)
            return StaggeredGrid(name, grids, box=self.box, batch_size=batch_size, extrapolation=extrapolation)

    def centered_grid(self, data, components=1, dtype=np.float32, name=None, batch_size=None, extrapolation=None):
        shape = self.centered_shape(components, batch_size=batch_size, name=name, extrapolation=extrapolation)
        if callable(data):  # data is an initializer
            try:
                data = data(shape, dtype=dtype)
            except TypeError:
                data = data(shape)
        if isinstance(data, Field):
            assert_same_rank(data.rank, self.rank, 'data does not match Domain')
            data = data.at(CenteredGrid.getpoints(self.box, self.resolution))
            if name is not None:
                data = data.copied_with(name=name)
            grid = data
        elif isinstance(data, (int, float)):
            grid = math.zeros(shape, dtype=dtype) + data
        else:
            grid = CenteredGrid(name, data, box=self.box, extrapolation=extrapolation)
        return grid

    def staggered_grid(self, data, dtype=np.float32, name=None, batch_size=None, extrapolation=None):
        shape = self.staggered_shape(batch_size=batch_size, name=name, extrapolation=extrapolation)
        if callable(data):  # data is an initializer
            try:
                data = data(shape, dtype=dtype)
            except TypeError:
                data = data(shape)
        if isinstance(data, Field):
            assert isinstance(data, StaggeredGrid)
            assert np.all(data.resolution == self.resolution)
            assert data.box == self.box
            grid = data
        elif isinstance(data, (int, float)):
            grid = (math.zeros(shape, dtype=dtype) + data).copied_with(flags=[DIVERGENCE_FREE])
        else:
            grid = StaggeredGrid(name, data, self.box, batch_size=None, extrapolation=extrapolation)
        return grid

    def _get_paddings(self, material_condition, margin=1):
        true_paddings = [[0, 0] for i in range(self.rank)]
        false_paddings = [[0, 0] for i in range(self.rank)]
        for dim in range(self.rank):
            for upper in (False, True):
                if material_condition(self.surface_material(dim, upper)):
                    true_paddings[dim][upper] = margin
                else:
                    false_paddings[dim][upper] = margin
        return [[0, 0]] + true_paddings + [[0, 0]], [[0, 0]] + false_paddings + [[0, 0]]

    def surface_material(self, axis=0, upper_boundary=False):
        if isinstance(self.boundaries, Material):
            return self.boundaries
        else:
            dim_boundaries = self.boundaries[axis]
            if isinstance(dim_boundaries, Material):
                return dim_boundaries
            else:
                return dim_boundaries[upper_boundary]


def _collapse_equals(obj, leaf_type):
    if isinstance(obj, leaf_type):
        return obj
    else:
        list = tuple([_collapse_equals(element, leaf_type) for element in obj])
        first = list[0]
        for element in list[1:]:
            if element != first:
                return list
        return first


def _friction_mask(masks_and_multipliers):
    for mask, multiplier in masks_and_multipliers:
        return mask


def tensor_shape(batch_size, resolution, components):
    return np.concatenate([[batch_size], resolution, [components]])


def _extend1(shape, axis):
    shape = list(shape)
    shape[axis+1] += 1
    return shape


@struct.definition()
class DomainState(State):

    @struct.constant()
    def domain(self, domain):
        assert domain is not None
        if isinstance(domain, Domain): return domain
        if isinstance(domain, int): return Domain([domain])
        if isinstance(domain, (tuple, list)): return Domain(domain)
        raise ValueError('Not a valid domain: %s' % domain)

    @property
    def resolution(self):
        return self.domain.resolution

    @property
    def rank(self):
        return self.domain.rank

    def centered_grid(self, name, value, components=1, dtype=np.float32):
        extrapolation = Material.extrapolation_mode(self.domain.boundaries)
        return self.domain.centered_grid(value, dtype=dtype, name=name, components=components,
                                         batch_size=self._batch_size, extrapolation=extrapolation)

    def staggered_grid(self, name, value, dtype=np.float32):
        extrapolation = Material.extrapolation_mode(self.domain.boundaries)
        return self.domain.staggered_grid(value, dtype=dtype, name=name,
                                          batch_size=self._batch_size, extrapolation=extrapolation)
