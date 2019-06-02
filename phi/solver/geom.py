from numbers import Number
from phi.math.blas import conjugate_gradient
from phi.solver.base import *


class GeometricCG(PressureSolver):

    def __init__(self,
                 accuracy=1e-5, gradient_accuracy='same',
                 max_iterations=2000, max_gradient_iterations='same',
                 autodiff=False):
        '''
Conjugate gradient solver that geometrically calculates laplace pressure in each iteration.
Unlike most other solvers, this algorithm is TPU compatible but usually performs worse than SparseCG.
At the moment, boundary conditions are only partly supported.
        :param accuracy: the maximally allowed error on the divergence field for each cell
        :param gradient_accuracy: accuracy applied during backpropagation, number of 'same' to use forward accuracy
        :param max_iterations: integer specifying maximum conjugent gradient loop iterations or None for no limit
        :param max_gradient_iterations: maximum loop iterations during backpropagation,
         'same' uses the number from max_iterations,
          'mirror' sets the maximum to the number of iterations that were actually performed in the forward pass
        :param autodiff: If autodiff=True, use the built-in autodiff for backpropagation.
         The intermediate results of each loop iteration will be permanently stored if backpropagation is used.
          If False, replaces autodiff by a forward pressure solve in reverse accumulation backpropagation.
           This requires less memory but is only accurate if the solution is fully converged.
        '''
        PressureSolver.__init__(self, 'Single-Phase Conjugate Gradient',
                                supported_devices=('CPU', 'GPU', 'TPU'),
                                supports_guess=True, supports_loop_counter=True, supports_continuous_masks=True)
        assert isinstance(accuracy, Number), 'invalid accuracy: %s' % accuracy
        assert gradient_accuracy == 'same' or isinstance(gradient_accuracy, Number), 'invalid gradient_accuracy: %s' % gradient_accuracy
        assert max_gradient_iterations == 'same' or max_gradient_iterations == 'mirror' or isinstance(max_gradient_iterations, Number), 'invalid max_gradient_iterations: %s' % max_gradient_iterations
        self.accuracy = accuracy
        self.gradient_accuracy = accuracy if gradient_accuracy == 'same' else gradient_accuracy
        self.max_iterations = max_iterations
        if max_gradient_iterations == 'same':
            self.max_gradient_iterations = max_iterations
        elif max_gradient_iterations == 'mirror':
            self.max_gradient_iterations = 'mirror'
        else:
            self.max_gradient_iterations = max_gradient_iterations
            assert not autodiff, 'Cannot specify max_gradient_iterations when autodiff=True'
        self.autodiff = autodiff


    def solve(self, divergence, active_mask, fluid_mask, boundaries, pressure_guess):
        fluid_mask = valid_fluid_mask(fluid_mask, divergence, boundaries)

        if self.autodiff:
            return solve_pressure_forward(divergence, fluid_mask, self.max_iterations, pressure_guess, self.accuracy, boundaries, back_prop=True)
        else:
            def pressure_gradient(op, grad):
                return solve_pressure_forward(grad, fluid_mask, max_gradient_iterations, None, self.gradient_accuracy, boundaries)[0]

            pressure, iter = math.with_custom_gradient(solve_pressure_forward,
                                      [divergence, fluid_mask, self.max_iterations, pressure_guess, self.accuracy, boundaries],
                                      pressure_gradient,
                                      input_index=0, output_index=0,
                                      name_base='geom_solve')

            max_gradient_iterations = iter if self.max_gradient_iterations == 'mirror' else self.max_gradient_iterations
            return pressure, iter


def solve_pressure_forward(divergence, fluid_mask, max_iterations, guess, accuracy, boundaries, back_prop=False):
    apply_A = lambda pressure: laplace(boundaries.pad_pressure(pressure), weights=fluid_mask, padding='valid')
    return conjugate_gradient(divergence, apply_A, guess, accuracy, max_iterations, back_prop=back_prop)


    # def pad_pressure(self, pressure):
    #     if self._has_any(True):
    #         pressure = pad(pressure, self._get_paddings(nd.spatial_rank(pressure), True), "constant")
    #     if self._has_any(False):
    #         pressure = pad(pressure, self._get_paddings(nd.spatial_rank(pressure), False), "symmetric")
    #     return pressure