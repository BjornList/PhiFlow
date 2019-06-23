from phi.math import Struct, StructInfo


class TrajectoryKey(object):
    pass


class State(Struct):

    __struct__ = StructInfo((), ('_age',))

    def __init__(self, tags=(), age=0.0):
        self._tags = tuple(tags)
        self.trajectorykey = TrajectoryKey()
        self._age = age

    @property
    def tags(self):
        return self._tags

    @property
    def age(self):
        return self._age

    def default_physics(self):
        return STATIC


class Physics(object):
    """
    A Physics object describes a set of physical laws that can be used to simulate a system by moving from state to state,
tracing out a trajectory.
    Physics objects are stateless and always support an empty constructor.
    """

    def __init__(self, dependencies):
        self.dependencies = dependencies  # Map from String to List<tag or TrajectoryKey>

    def step(self, state, dependent_states, dt=1.0):
        """
Computes the next state of the simulation, given the current state.
Solves the simulation for a time increment self.dt.
        :param state: current state
        :param dependent_states: dict from String to List<State>
        :param dt: time increment (can be positive, negative or zero)
        :return next state
        """
        raise NotImplementedError(self)


class Static(Physics):

    def __init__(self):
        Physics.__init__(self, {})

    def step(self, state, dependent_states, dt=1.0):
        return state.copied_with()


STATIC = Static()