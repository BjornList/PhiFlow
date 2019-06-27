from .struct import *
from .nd import upsample2x
from .base import backend as math
import numpy as np
from numbers import Number


def _is_python_1d_tensor(obj):
    if not isinstance(obj, (tuple, list)): return False
    for element in obj:
        if not isinstance(element, Number): return False


def _map_shapes(f, shape):
    assert not isinstance(shape, Number)
    if _is_python_1d_tensor(shape):
        return f(shape)
    if Struct.isstruct(shape):
        return Struct.map(lambda s: _map_shapes(f, s), shape)
    return f(shape)


def zeros(shape, dtype=np.float32):
    return _map_shapes(lambda s: np.zeros(s, dtype), shape)


def zeros_like(object):
    return Struct.flatmap(lambda tensor: math.zeros_like(tensor), object)


def ones(shape, dtype=np.float32):
    return _map_shapes(lambda s: np.ones(s, dtype), shape)


def empty(shape, dtype=np.float32):
    return _map_shapes(lambda s: np.empty(s, dtype), shape)


def empty_like(object):
    return Struct.flatmap(lambda tensor: np.empty_like(tensor), object)


def randn(levels=(1.0,)):  # TODO pass mean, sigma, doesn't correctly scale staggered grids
    def randn_impl(shape):
        return Struct.flatmap(lambda s: _random_tensor(s, levels), shape)
    return randn_impl


def _random_tensor(shape, levels):
    result = 0
    for i in range(len(levels)): # high-res first
        lowres_shape = np.array(shape)
        lowres_shape[1:-1] //= 2 ** i
        rnd = np.random.randn(*lowres_shape) * levels[i]
        for j in range(i):
            rnd = upsample2x(rnd)
        result = result + rnd
    return result