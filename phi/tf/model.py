from __future__ import print_function
from phi.flow import *
from .util import *
from .session import Session
from .world import tf_bake_graph
import phi.model as nontf


class FieldSequenceModel(nontf.FieldSequenceModel):

    def __init__(self, *args, **kwargs):
        nontf.FieldSequenceModel.__init__(self, *args, **kwargs)
        self.session = Session(self.scene)
        self.scalars = []
        self.scalar_names = []
        self.editable_placeholders = {}
        self.auto_bake = True
        self.add_trait('tensorflow')

    def prepare(self):
        if self.prepared:
            return
        nontf.FieldSequenceModel.prepare(self)
        self.info('Initializing variables')
        self.session.initialize_variables()
        if self.auto_bake:
            tf_bake_graph(self.world, self.session)
        return self

    def add_scalar(self, name, node):
        assert isinstance(node, tf.Tensor)
        self.scalar_names.append(name)
        self.scalars.append(node)

    def editable_float(self, name, initial_value, minmax=None, log_scale=None):
        val = EditableFloat(name, initial_value, minmax, None, log_scale)
        setattr(self, 'float_'+name.lower(), val)
        placeholder = tf.placeholder(tf.float32, (), name.lower().replace(' ', '_'))
        self.add_scalar(name, placeholder)
        self.editable_placeholders[placeholder] = 'float_'+name.lower()
        return placeholder

    def editable_int(self, name, initial_value, minmax=None):
        val = EditableInt(name, initial_value, minmax, None)
        setattr(self, 'int_'+name.lower(), val)
        placeholder = tf.placeholder(tf.int32, (), name.lower().replace(' ', '_'))
        self.add_scalar(name, placeholder)
        self.editable_placeholders[placeholder] = 'int_'+name.lower()
        return placeholder

    def editable_values_dict(self):
        feed_dict = {}
        for placeholder, attrname in self.editable_placeholders.items():
            val = getattr(self, attrname)
            if isinstance(val, EditableValue):
                val = val.initial_value
            feed_dict[placeholder] = val
        return feed_dict


class TFModel(FieldSequenceModel):

    def __init__(self, name='TensorFlow application', subtitle='',
                 learning_rate=1e-3,
                 training_batch_size=4,
                 validation_batch_size=16,
                 model_scope_name='model',
                 base_dir='~/phi/model/',
                 stride=None,
                 **kwargs):
        FieldSequenceModel.__init__(self, name=name, subtitle=subtitle, base_dir=base_dir, **kwargs)
        self.add_trait('model')
        self.learning_rate = self.editable_float('Learning_Rate', learning_rate)
        self.training = tf.placeholder(tf.bool, (), 'training')
        self.all_optimizers = []
        self.training_batch_size = training_batch_size
        self.validation_batch_size = validation_batch_size
        self.model_scope_name = model_scope_name
        self.auto_bake = False
        self.scalar_values = {}
        self.set_data(None, None)
        self.base_feed_dict = {}

        self.current_batch = None
        self.custom_stride = stride

    def prepare(self):
        scalars = [tf.summary.scalar(self.scalar_names[i], self.scalars[i]) for i in range(len(self.scalars))]
        self.merged_scalars = tf.summary.merge(scalars)

        FieldSequenceModel.prepare(self)  # initializes global variables

        model_parameter_count = 0
        for var in tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope=self.model_scope_name):
            if not 'Adam' in var.name:
                model_parameter_count += int(np.prod(var.get_shape().as_list()))
                # if 'conv' in var.name and 'kernel' in var.name:
                #     tf.summary.image(var.name, var)
        self.add_custom_property('parameter_count', model_parameter_count)
        self.info('Model variables contain %d total parameters.' % model_parameter_count)

        if self.world.batch_size is not None:
            self.training_batch_size = self.world.batch_size
            self.validation_batch_size = self.world.batch_size

        if self._train_reader is not None:
            self.sequence_stride = len(self._train_reader.all_batches(batch_size=self.training_batch_size))
            self.validation_step()
        if self.custom_stride is not None:
            self.sequence_stride = min(self.custom_stride, self.sequence_stride)

        return self

    def set_data(self, train, placeholders, channels=None, val=None):
        if train is not None or val is not None:
            assert placeholders is not None
            if channels is None:
                channels = struct.map(lambda s: s.replace('.', '_'), struct.names(placeholders))  # TODO this is already defined in fluidformat
            if isinstance(placeholders, list):
                placeholders = tuple(placeholders)  # make placeholders hashable
            hash(placeholders)
        self._training_set = train
        self._validation_set = val
        self._placeholders = placeholders
        # Train
        if self._training_set is not None:
            self._train_reader = BatchReader(self._training_set, channels)
            self._train_iterator = self._train_reader.all_batches(batch_size=self.training_batch_size, loop=True)
        else:
            self._train_reader = None
            self._train_iterator = None
        # Val
        if self._validation_set is not None:
            self.value_view_training_data = False
            self._val_reader = BatchReader(self._validation_set, channels)
        else:
            self._val_reader = None

    def add_objective(self, loss, name='Loss', optimizer=None, reg=None, vars=None):
        assert len(loss.shape) <= 1, 'Loss function must be a scalar'
        if not optimizer:
            optimizer = tf.train.AdamOptimizer(self.learning_rate)

        if reg is not None:
            self.add_scalar(name+'_reg_unscaled', reg)
            reg_scale = self.editable_float(name + '_reg_scale', 1.0)
            optim_function = loss + reg * reg_scale
        else:
            optim_function = loss

        if isinstance(vars, six.string_types):
            vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope=vars)

        node = optimizer.minimize(optim_function, var_list=vars)

        self.add_scalar(name, loss)
        self.all_optimizers.append(node)
        return node

    def step(self):
        self.optimization_step(self.all_optimizers)
        if self.steps % self.sequence_stride == 0:
            self.validation_step(create_checkpoint=True)
        return self

    def optimization_step(self, optim_nodes, log_loss=True):
        if isinstance(optim_nodes, Iterable):
            optim_nodes = list(optim_nodes)
        else:
            optim_nodes = [optim_nodes]
        batch = next(self._train_iterator) if self._train_iterator is not None else None
        self.current_batch = batch
        feed_dict = self._feed_dict(batch, True)
        scalar_values = self.session.run(optim_nodes + self.scalars, feed_dict, summary_key='train', merged_summary=self.merged_scalars, time=self.steps)[len(optim_nodes):]
        self.scalar_values = {name: value for name, value in zip(self.scalar_names, scalar_values) }
        if log_loss:
            self.info('Optimization: ' + ', '.join([self.scalar_names[i]+': '+str(scalar_values[i]) for i in range(len(self.scalars))]))

    def validation_step(self, create_checkpoint=False, log_loss=True):
        if self._val_reader is None:
            return
        batch = self._val_reader[0:self.validation_batch_size]
        feed_dict = self._feed_dict(batch, False)
        self.session.run(self.scalars, feed_dict, summary_key='val', merged_summary=self.merged_scalars, time=self.steps)
        if create_checkpoint:
            self.save_model()
        self.info('Validation Done (%d).' % self.steps)

        if log_loss:
            self.info('Validation: ' + ', '.join([self.scalar_names[i]+': '+str(scalar_values[i]) for i in range(len(self.scalars))]))

    def _feed_dict(self, batch, training):
        feed_dict = self.base_feed_dict
        feed_dict.update(self.editable_values_dict())
        feed_dict[self.training] = training
        if batch is not None:
            feed_dict[self._placeholders] = batch
        return feed_dict

    # def val(self, fetches, subrange=None):
    #     return self.session.run(fetches, self._feed_dict(self.val_iterator, False, subrange=subrange))

    @property
    def view_reader(self):
        if self._val_reader is None and self._train_reader is None:
            return None
        if self._val_reader is None:
            return self._train_reader
        return self._train_reader if self.value_view_training_data else self._val_reader

    def view(self, tasks):
        if tasks is None:
            return None
        reader = self.view_reader
        #batch = reader[0:self.validation_batch_size] if reader is not None else None
        batch = self.current_batch if self.current_batch is not None else reader[0:self.validation_batch_size] if reader is not None else None
        return self.session.run(tasks, self._feed_dict(batch, False))

    @property
    def viewed_batch(self):
        assert self.view_reader is not None, 'There is no data to view.'
        return self.view_reader[0:self.validation_batch_size]


    def view_batch(self, get_attribute):
        batch = self.view_reader[0:self.validation_batch_size]
        return get_attribute(batch)

    def save_model(self):
        dir = self.scene.subpath('checkpoint_%08d' % self.steps)
        self.session.save(dir)
        return dir

    def load_model(self, checkpoint_dir):
        self.session.restore(checkpoint_dir, scope=self.model_scope_name)

    def model_scope(self):
        return tf.variable_scope(self.model_scope_name)

    def add_field(self, name, field):
        """

        :param name: channel name
        :param field: Tensor, string (database fieldname) or function
        """
        if istensor(field):
            FieldSequenceModel.add_field(self, name, lambda: self.view(field))
        # elif isinstance(field, StructAttributeGetter):
        #     FieldSequenceModel.add_field(self, name, lambda: self.view_batch(field))
        else:
            FieldSequenceModel.add_field(self, name, field)
