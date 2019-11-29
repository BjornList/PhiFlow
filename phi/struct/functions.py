import six

from .structdef import DATA, ALL_ITEMS
from .struct import isstruct, copy_with, equal, to_dict
from .context import anytype


def flatten(struct, leaf_condition=None, trace=False, item_condition=DATA):
    result = []
    def map_leaf(value):
        result.append(value)
        return value
    with anytype(): map(map_leaf, struct, leaf_condition, recursive=True, trace=trace, item_condition=item_condition)
    return result


def names(struct, leaf_condition=None, full_path=True, basename=None, separator='.'):
    def to_name(trace):
        if not full_path:
            return trace.name if basename is None else basename + separator + trace.name
        else:
            return trace.path(separator) if basename is None else basename + separator + trace.path(separator)
    with anytype():
        return map(to_name, struct, leaf_condition, recursive=True, trace=True)


def zip(structs, leaf_condition=None, item_condition=DATA, zip_parents_if_incompatible=False):
    # pylint: disable-msg = redefined-builtin
    assert len(structs) > 0
    first = structs[0]
    if isstruct(first, leaf_condition):
        for struct in structs[1:]:
            if to_dict(struct, item_condition=item_condition).keys() != to_dict(first, item_condition=item_condition).keys():
                if zip_parents_if_incompatible:
                    return LeafZip(structs)
                else:
                    raise IncompatibleStructs('Cannot zip %s and %s' % (struct, first))

    if not isstruct(first, leaf_condition):
        return LeafZip(structs)

    dicts = [to_dict(struct, item_condition=item_condition) for struct in structs]
    keys = dicts[0].keys()
    new_dict = {}
    for key in keys:
        values = [d[key] for d in dicts]
        values = zip(values, leaf_condition, item_condition=item_condition, zip_parents_if_incompatible=zip_parents_if_incompatible)
        new_dict[key] = values
    with anytype():
        return copy_with(first, new_dict)


class LeafZip(object):
    """
Created by struct.zip to replace data.
    """

    def __init__(self, values):
        self.values = values

    def __getitem__(self, item):
        return self.values[item]

    def __repr__(self):
        return repr(self.values)

    def __str__(self):
        return str(self.values)


class IncompatibleStructs(Exception):
    """
Thrown when two or more structs are required to have the same structure but do not.
    """
    def __init__(self, *args):
        Exception.__init__(self, *args)


def map(function, struct, leaf_condition=None, recursive=True, trace=False, item_condition=DATA):
    # pylint: disable-msg = redefined-builtin
    if trace is True:
        trace = Trace(struct, None, None)
    if not isstruct(struct, leaf_condition):
        if trace is False:
            if isinstance(struct, LeafZip):
                return function(*struct.values)
            else:
                return function(struct)
        else:
            return function(trace)
    else:
        old_values = to_dict(struct, item_condition=item_condition)
        new_values = {}
        if not recursive:
            leaf_condition = lambda x: True
        for key, value in old_values.items():
            new_values[key] = map(function, value, leaf_condition, recursive,
                                  Trace(value, key, trace) if trace is not False else False,
                                  item_condition=item_condition)

        return copy_with(struct, new_values)


class Trace(object):
    """
Used in struct.map if trace=True.
Trace objects can be used to reference a specific item of a struct or sub-struct as well as gather information about it.
    """

    def __init__(self, value, key, parent_trace):
        self.value = value
        self.key = key
        self.parent = parent_trace

    @property
    def name(self):
        if self.key is None:
            return None
        if isinstance(self.key, six.string_types):
            return self.key
        else:
            return str(self.key)

    def path(self, separator='.'):
        if self.parent is not None and self.parent.key is not None:
            return self.parent.path(separator) + separator + self.name
        else:
            return self.name

    def __repr__(self):
        return "%s = %s" % (self.path(), self.value)

    def find_in(self, base_struct):
        if self.parent is not None and self.parent.key is not None:
            base_struct = self.parent.find_in(base_struct)
        attrs = to_dict(base_struct, item_condition=ALL_ITEMS)
        return attrs[self.key]


def compare(structs, leaf_condition=None, recursive=True, item_condition=ALL_ITEMS):
    if len(structs) <= 1: return []
    result = set()
    def check(trace):
        value = trace.value
        for other in structs[1:]:
            try:
                other_value = trace.find_in(other)
                if not equal(value, other_value):
                    result.add(trace)
            except (ValueError, KeyError, TypeError):
                result.add(trace)
    with anytype(): map(check, structs[0], leaf_condition=leaf_condition, recursive=recursive, trace=True, item_condition=item_condition)
    return result


def mappable(function, leaf_condition=None, recursive=True, item_condition=DATA):
    def broadcast_function(obj, *args, **kwargs):
        def function_with_args(x): function(x, *args, **kwargs)
        result = map(function_with_args, obj, leaf_condition=leaf_condition, recursive=recursive, item_condition=item_condition)
        return result
    return broadcast_function
