import os
import math
import copy
import keras
import pathlib
import numpy as np
from typing import List, Tuple, Union, Dict

# ==============================================================================

from .utilities import *
from .custom_logger import logger


from .custom_callbacks import *
from .custom_schedule import step_decay_schedule


# ==============================================================================


class BFCNN:
    """
    Bias Free De-noising Convolutional Neural Network
    """

    def __init__(
            self,
            model: keras.Model = None,
            input_dims: Union[Tuple, List[int]] = (),
            min_value: float = 0.0,
            max_value: float = 255.0,
            no_layers: int = 5,
            kernel_size: int = 3,
            filters: int = 32,
            channels_index: int = 2,
            kernel_regularizer=None,
            kernel_initializer=None):
        """
        Initialize model, left untrained

        :param model: ready made model
        :param input_dims: Input dimensions
        :param min_value: Minimum value allowed
        :param max_value: Maximum value allowed
        :param no_layers: Number of layers to use
        :param kernel_size: Kernel size
        :param filters: Number of filters per layer
        :param channels_index: Index of the channels
        :param kernel_regularizer: Kernel regularizer
        :param kernel_initializer: Kernel initializer
        """
        # --- argument checking
        # TODO
        # ---
        if model is not None:
            self._model = model
        else:
            self._model = \
                self.build_model(
                    input_dims=input_dims,
                    no_layers=no_layers,
                    kernel_size=kernel_size,
                    filters=filters,
                    min_value=min_value,
                    max_value=max_value,
                    channel_index=channels_index,
                    kernel_initializer=kernel_initializer,
                    kernel_regularizer=kernel_regularizer)

    # --------------------------------------------------

    @property
    def model(self):
        return self._model

    # --------------------------------------------------

    @model.setter
    def model(self, value):
        if not isinstance(value, keras.Model):
            raise ValueError("model should be a keras.Model")
        self._model = value

    # --------------------------------------------------

    @property
    def input_dims(self):
        return self._input_dims

    # --------------------------------------------------

    def save(self, filepath):
        self._model.save(filepath=filepath)

    # --------------------------------------------------

    @staticmethod
    def load(filepath):
        model = keras.models.load_model(filepath)
        return BFCNN(model=model)

    # --------------------------------------------------

    @staticmethod
    def build_model(
            input_dims,
            no_layers: int,
            kernel_size: int,
            filters: int,
            min_value: float = 0.0,
            max_value: float = 255.0,
            channel_index: int = 2,
            use_bn: bool = True,
            kernel_regularizer=None,
            kernel_initializer=None) -> keras.Model:
        """
        Build Bias Free CNN model

        :param input_dims:
        :param no_layers: number of convolutional layers
        :param kernel_size: convolution kernel size
        :param filters: number of filters per convolutional layer
        :param max_value:
        :param min_value:
        :param channel_index:
        :param use_bn: Use batch normalization in model
        :param kernel_initializer:
        :param kernel_regularizer:

        :return: Untrained keras model
        """
        # --- argument checking
        if input_dims is None:
            raise ValueError("input_dims should not be empty")
        if no_layers <= 0:
            raise ValueError("no_layers should be > 0")
        if channel_index < 0:
            raise ValueError("channel_index should be >= 0")

        # --- create the parts of the model
        model_normalize = \
            build_normalize_model(
                input_dims=input_dims,
                min_value=min_value,
                max_value=max_value)

        model_resnet = \
            build_resnet_model(
                use_bn=use_bn,
                filters=filters,
                no_layers=no_layers,
                input_dims=input_dims,
                kernel_size=kernel_size,
                channel_index=channel_index,
                kernel_regularizer=kernel_regularizer,
                kernel_initializer=kernel_initializer)

        model_denormalize = \
            build_denormalize_model(
                input_dims=input_dims,
                min_value=min_value,
                max_value=max_value)

        # --- connect the parts of the model
        model_input = keras.Input(shape=input_dims)
        x = model_normalize(model_input)
        x = model_resnet(x)
        model_output = model_denormalize(x)

        # --- wrap model
        return keras.Model(
            inputs=model_input,
            outputs=model_output)

    # --------------------------------------------------

    @staticmethod
    def train(
            model,
            input_dims,
            dataset,
            min_value: float = 0.0,
            max_value: float = 255.0,
            loss: List[Loss] = [Loss.MeanAbsoluteError],
            batch_size: int = 32,
            epochs: int = 1,
            lr_initial: float = 0.01,
            lr_decay: float = 0.9,
            clip_norm: float = 1.0,
            min_noise_std: float = 0.1,
            max_noise_std: float = 10,
            print_every_n_batches: int = 100,
            run_folder: str = "./training/",
            save_checkpoint_weights: bool = False):
        """
        Train the model using the dataset and return a trained model

        :param model:
        :param input_dims:
        :param dataset: dataset to train on
        :param min_value:
        :param max_value:
        :param loss:
        :param batch_size:
        :param epochs:
        :param run_folder:
        :param print_every_n_batches:
        :param lr_initial: initial learning rate
        :param lr_decay: decay of learning rate per step size
        :param clip_norm:
        :param max_noise_std:
        :param min_noise_std:
        :param save_checkpoint_weights:
        :return:
        """
        # --- argument checking
        if epochs <= 0:
            raise ValueError("epochs must be > 0")
        if batch_size <= 0:
            raise ValueError("batch size must be > 0")
        if lr_initial <= 0.0:
            raise ValueError("initial learning rate must be > 0.0")
        if lr_decay <= 0.0 or lr_decay > 1.0:
            raise ValueError("learning rate decay must be > 0.0 and < 1.0")
        if clip_norm <= 0.0:
            raise ValueError("clip normal must be > 0.0")
        if len(loss) <= 0:
            raise ValueError("losses cannot be empty")
        # decide on the type of model
        if isinstance(model, keras.Model):
            trainable_model = model
        elif isinstance(model, BFCNN):
            trainable_model = model.model
        else:
            raise ValueError("Not supported model")

        # --- set variables
        initial_epoch = 0
        batches_per_epoch = 4 * int(math.ceil(len(dataset) / batch_size))

        # --- define optimizer
        optimizer = \
            keras.optimizers.Adagrad(
                lr=lr_initial,
                learning_rate=lr_initial,
                clipnorm=clip_norm)

        # --- define loss functions
        total_loss_fn, loss_fn = build_loss_fn(loss)

        trainable_model.compile(
            optimizer=optimizer,
            loss=total_loss_fn,
            metrics=loss_fn)

        # --- fix dataset dimensions and type if they dont match
        if isinstance(dataset, np.ndarray):
            if len(input_dims) == 3:
                if len(dataset.shape[1:]) != len(input_dims):
                    dataset = np.expand_dims(dataset, axis=3)
            dataset = dataset.astype(np.float32)

        # --- define callbacks
        subset_size = min(len(dataset), 25)
        subset = dataset[0:subset_size, :, :, :]
        noisy_subset = \
            subset + \
            np.random.normal(
                loc=0.0,
                scale=max_noise_std,
                size=subset.shape)
        noisy_subset = \
            np.clip(
                noisy_subset,
                a_min=min_value,
                a_max=max_value)
        callback_intermediate_results = \
            SaveIntermediateResultsCallback(
                model=trainable_model,
                run_folder=run_folder,
                initial_epoch=initial_epoch,
                original_images=subset,
                noisy_images=noisy_subset,
                every_n_batches=print_every_n_batches)
        # --
        lr_schedule = \
            step_decay_schedule(
                initial_lr=lr_initial,
                decay_factor=lr_decay,
                step_size=batches_per_epoch)
        weights_path = os.path.join(run_folder, "weights")
        pathlib.Path(weights_path).mkdir(parents=True, exist_ok=True)

        checkpoint_filepath = os.path.join(
            run_folder,
            "weights/weights-{epoch:03d}-{loss:.2f}.h5")
        checkpoint1 = keras.callbacks.ModelCheckpoint(
            checkpoint_filepath,
            save_weights_only=True,
            verbose=1)
        checkpoint2 = keras.callbacks.ModelCheckpoint(
            os.path.join(
                run_folder,
                "weights/weights.h5"),
            save_weights_only=True,
            verbose=1)
        callback_bn_flip = \
            BatchNormalizationFlipCallback(
                model=trainable_model,
                initial_epoch=0,
                every_n_batches=print_every_n_batches)

        callback_weights_pruner = \
            WeightsPrunerCallback(model=trainable_model)
        # --
        callbacks_fns = [
            lr_schedule,
            callback_bn_flip,
            callback_weights_pruner,
            callback_intermediate_results
        ]

        if save_checkpoint_weights:
            callbacks_fns += [checkpoint1, checkpoint2]

        # --- train
        logger.info("begin training")

        history = \
            trainable_model.fit(
                noisy_image_data_generator(
                    dataset=dataset,
                    batch_size=batch_size,
                    min_value=min_value,
                    max_value=max_value,
                    min_noise_std=min_noise_std,
                    max_noise_std=max_noise_std,
                    random_invert=False,
                    vertical_flip=True,
                    horizontal_flip=True),
                steps_per_epoch=batches_per_epoch,
                initial_epoch=initial_epoch,
                shuffle=True,
                epochs=epochs,
                callbacks=callbacks_fns)

        logger.info("finished  training")

        return model, history