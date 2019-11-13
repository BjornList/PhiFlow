from phi import struct
from phi.math import staticshape


class State(struct.Struct):

    def __init__(self, batch_size=None, **kwargs):
        self._batch_size = batch_size
        struct.Struct.__init__(self, **kwargs)

    @struct.prop(default=())
    def tags(self, tags): return tuple(tags)

    @struct.prop(default=0.0)
    def age(self, age): return age

    @struct.prop()
    def name(self, name):
        if name is None: return '%s_%d' % (self.__class__.__name__.lower(), id(self))
        else: return str(name)

    def default_physics(self):
        return STATIC

    @property
    def shape(self):
        def tensorshape(tensor):
            if tensor is None: return None
            default_batched_shape = staticshape(tensor)
            if len(default_batched_shape) >= 2:
                return (self._batch_size,) + default_batched_shape[1:]
        with struct.anytype():
            return struct.map(tensorshape, self)

    @property
    def state(self): return self


class StateDependency(object):

    def __init__(self, parameter_name, tag, single_state=False, blocking=False, state_name=None):
        self.parameter_name = parameter_name
        self.tag = tag
        self.single_state = single_state
        self.blocking = blocking
        self.state_name = state_name
        if state_name is not None: assert single_state

    def __repr__(self):
        if self.state_name is not None:
            return '[key=%s, blocking=%s]' % (self.state_name, self.blocking)
        else:
            return '[tag=%s, blocking=%s]' % (self.tag, self.blocking)


class Physics(object):
    """
    A Physics object describes a set of physical laws that can be used to simulate a system by moving from state to state, tracing out a trajectory.
    Physics objects are stateless and always support an empty constructor.
    """

    def __init__(self, dependencies=()):
        self.dependencies = tuple(dependencies)

    def step(self, state, dt=1.0, **dependent_states):
        """
        Computes the next state of the simulation, given the current state.
        Solves the simulation for a time increment self.dt.

        :param state: current state
        :param dependent_states: dict from String to List<State>
        :param dt: time increment (can be positive, negative or zero)
        :return next state
        """
        raise NotImplementedError(self)

    @property
    def blocking_dependencies(self):
        return filter(lambda d: d.blocking, self.dependencies)

    @property
    def non_blocking_dependencies(self):
        return filter(lambda d: not d.blocking, self.dependencies)


class Static(Physics):

    def step(self, state, dt=1.0, **dependent_states):
        return state.copied_with(age=state.age + dt)


STATIC = Static()
