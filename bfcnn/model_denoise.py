# ---------------------------------------------------------------------

__author__ = "Nikolas Markou"
__version__ = "1.0.0"
__license__ = "MIT"

# ---------------------------------------------------------------------
import abc

from tensorflow import keras
from typing import List, Tuple, Union, Dict

# ---------------------------------------------------------------------
# local imports
# ---------------------------------------------------------------------

from .utilities import *
from .custom_logger import logger
from .pyramid import build_pyramid_model, PyramidType


# ---------------------------------------------------------------------


def model_builder(
        config: Dict) -> Tuple[keras.Model, keras.Model, keras.Model]:
    """
    Reads a configuration and returns 3 models,

    :param config: configuration dictionary
    :return: denoiser model, normalize model, denormalize model
    """
    logger.info("building model with config [{0}]".format(config))

    # --- argument parsing
    model_type = config["type"]
    levels = config.get("levels", 1)
    filters = config.get("filters", 32)
    no_layers = config.get("no_layers", 5)
    min_value = config.get("min_value", 0)
    max_value = config.get("max_value", 255)
    batchnorm = config.get("batchnorm", True)
    kernel_size = config.get("kernel_size", 3)
    pyramid_config = config.get("pyramid", None)
    clip_values = config.get("clip_values", False)
    shared_model = config.get("shared_model", False)
    input_shape = config.get("input_shape", (None, None, 3))
    output_multiplier = config.get("output_multiplier", 1.0)
    local_normalization = config.get("local_normalization", -1)
    final_activation = config.get("final_activation", "linear")
    kernel_regularizer = config.get("kernel_regularizer", "l1")
    inverse_pyramid_config = config.get("inverse_pyramid", None)
    add_intermediate_results = config.get("intermediate_results", False)
    kernel_initializer = config.get("kernel_initializer", "glorot_normal")
    use_local_normalization = local_normalization > 0
    use_global_normalization = local_normalization == 0
    use_normalization = use_local_normalization or use_global_normalization
    local_normalization_kernel = [local_normalization, local_normalization]
    for i in range(len(input_shape)):
        if input_shape[i] == "?" or \
                input_shape[i] == "" or \
                input_shape[i] == "-1":
            input_shape[i] = None

    # --- argument checking
    if levels <= 0:
        raise ValueError("levels must be > 0")
    if filters <= 0:
        raise ValueError("filters must be > 0")
    if kernel_size <= 0:
        raise ValueError("kernel_size must be > 0")

    # --- build normalize denormalize models
    model_normalize = \
        build_normalize_model(
            input_dims=input_shape,
            min_value=min_value,
            max_value=max_value)

    model_denormalize = \
        build_denormalize_model(
            input_dims=input_shape,
            min_value=min_value,
            max_value=max_value)

    # --- build denoise model
    model_params = dict(
        add_gates=False,
        filters=filters,
        use_bn=batchnorm,
        add_sparsity=False,
        no_layers=no_layers,
        input_dims=input_shape,
        kernel_size=kernel_size,
        final_activation=final_activation,
        kernel_regularizer=kernel_regularizer,
        kernel_initializer=kernel_initializer,
        add_intermediate_results=add_intermediate_results
    )

    if model_type == "resnet":
        pass
    elif model_type == "sparse_resnet":
        model_params["add_sparsity"] = True
    elif model_type == "gatenet":
        model_params["add_gates"] = True
    else:
        raise ValueError(
            "don't know how to build model [{0}]".format(model_type))

    def func_sigma_norm(args):
        y, mean_y, sigma_y = args
        return (y - mean_y) / sigma_y

    def func_sigma_denorm(args):
        y, mean_y, sigma_y = args
        return (y * sigma_y) + mean_y

    # --- connect the parts of the model
    # setup input
    input_layer = \
        keras.Input(
            shape=input_shape,
            name="input_tensor")
    x = input_layer

    logger.info("building model with multiscale pyramid")
    # build pyramid
    model_pyramid = \
        build_pyramid_model(
            input_dims=input_shape,
            config=pyramid_config)
    # build inverse pyramid
    model_inverse_pyramid = \
        build_pyramid_model(
            input_dims=input_shape,
            config=inverse_pyramid_config)
    # define normalization/denormalization layers
    local_normalization_layer = \
        keras.layers.Lambda(
            name="local_normalization",
            function=func_sigma_norm,
            trainable=False)
    local_denormalization_layer = \
        keras.layers.Lambda(
            name="local_denormalization",
            function=func_sigma_denorm,
            trainable=False)
    global_normalization_layer = \
        keras.layers.Lambda(
            name="global_normalization",
            function=func_sigma_norm,
            trainable=False)
    global_denormalization_layer = \
        keras.layers.Lambda(
            name="global_denormalization",
            function=func_sigma_denorm,
            trainable=False)

    # --- run inference
    x_levels = model_pyramid(x)

    means = []
    sigmas = []

    # local/global normalization cap
    if use_normalization:
        for i, x_level in enumerate(x_levels):
            mean, sigma = None, None
            if use_local_normalization:
                mean, sigma = \
                    mean_sigma_local(
                        input_layer=x_level,
                        kernel_size=local_normalization_kernel)
                x_level = \
                    local_normalization_layer(
                        [x_level, mean, sigma])
            if use_global_normalization:
                mean, sigma = \
                    mean_sigma_global(
                        input_layer=x_level,
                        axis=[1, 2])
                x_level = \
                    global_normalization_layer(
                        [x_level, mean, sigma])
            means.append(mean)
            sigmas.append(sigma)
            x_levels[i] = x_level

    # --- shared or separate models
    if shared_model:
        logger.info("building shared model")
        resnet_model = \
            build_resnet_model(
                name="level_shared",
                **model_params)
        x_levels = [
            resnet_model(x_level)
            for i, x_level in enumerate(x_levels)
        ]
    else:
        logger.info("building per scale model")
        x_levels = [
            build_resnet_model(
                name=f"level_{i}",
                **model_params)(x_level)
            for i, x_level in enumerate(x_levels)
        ]

    # --- split intermediate results and actual results
    x_levels_intermediate = []
    if add_intermediate_results:
        for i, x_level in enumerate(x_levels):
            x_levels_intermediate += x_level[1::]
        x_levels = [
            x_level[0]
            for i, x_level in enumerate(x_levels)
        ]

    # --- optional multiplier to help saturation
    if output_multiplier is not None and \
            output_multiplier != 1:
        x_levels = [
            x_level * output_multiplier
            for x_level in x_levels
        ]

    # --- local/global denormalization cap
    if use_normalization:
        for i, x_level in enumerate(x_levels):
            if use_local_normalization:
                x_level = \
                    local_denormalization_layer(
                        [x_level, means[i], sigmas[i]])
            if use_global_normalization:
                x_level = \
                    global_denormalization_layer(
                        [x_level, means[i], sigmas[i]])
            x_levels[i] = x_level

    # --- merge levels together
    x_result = \
        model_inverse_pyramid(x_levels)

    # clip to [-0.5, +0.5]
    if clip_values:
        x_result = \
            keras.backend.clip(
                x_result,
                min_value=-0.5,
                max_value=+0.5)

    # name output
    output_layer = \
        keras.layers.Layer(name="output_tensor")(
            x_result)

    # add intermediate results
    output_layers = [output_layer]
    if add_intermediate_results:
        x_levels_intermediate = [
            keras.layers.Layer(
                name=f"intermediate_tensor_{i}")(x_level_intermediate)
            for i, x_level_intermediate in enumerate(x_levels_intermediate)
        ]
        output_layers = output_layers + x_levels_intermediate

    # --- wrap and name model
    model_denoise = \
        keras.Model(
            inputs=input_layer,
            outputs=output_layers,
            name=f"{model_type}_denoiser")

    return \
        model_denoise, \
        model_normalize, \
        model_denormalize


# ---------------------------------------------------------------------


class DenoisingInferenceModule(tf.Module, abc.ABC):
    """denoising inference module."""

    def __init__(
            self,
            model_denoise: keras.Model = None,
            model_normalize: keras.Model = None,
            model_denormalize: keras.Model = None,
            training_channels: int = 1,
            iterations: int = 1,
            cast_to_uint8: bool = True):
        """
        Initializes a module for denoising.

        :param model_denoise: denoising model to use for inference.
        :param model_normalize: model that normalizes the input
        :param model_denormalize: model that denormalizes the output
        :param training_channels: how many color channels were used in training
        :param iterations: how many times to run the model
        :param cast_to_uint8: cast output to uint8

        """
        # --- argument checking
        if model_denoise is None:
            raise ValueError("model_denoise should not be None")
        if iterations <= 0:
            raise ValueError("iterations should be > 0")
        if training_channels <= 0:
            raise ValueError("training channels should be > 0")

        # --- setup instance variables
        self._iterations = iterations
        self._cast_to_uint8 = cast_to_uint8
        self._model_denoise = model_denoise
        self._model_normalize = model_normalize
        self._model_denormalize = model_denormalize
        self._training_channels = training_channels

    def _run_inference_on_images(self, image):
        """
        Cast image to float and run inference.

        :param image: uint8 Tensor of shape
        :return: denoised image: uint8 Tensor of shape if the input
        """
        # --- argument checking
        # --- argument checking
        if image is None:
            raise ValueError("input image cannot be empty")

        x = tf.cast(image, dtype=tf.float32)

        # --- normalize
        if self._model_normalize is not None:
            x = self._model_normalize(x)

        # --- run denoise model as many times as required
        for i in range(self._iterations):
            x = self._model_denoise(x)
            x = tf.clip_by_value(x, clip_value_min=-0.5, clip_value_max=+0.5)

        # --- denormalize
        if self._model_denormalize is not None:
            x = self._model_denormalize(x)

        # --- cast to uint8
        if self._cast_to_uint8:
            x = tf.round(x)
            x = tf.cast(x, dtype=tf.uint8)

        return x

    @abc.abstractmethod
    def __call__(self, input_tensor):
        pass

# ---------------------------------------------------------------------


class DenoisingInferenceModule1Channel(DenoisingInferenceModule):
    def __init__(
            self,
            model_denoise: keras.Model = None,
            model_normalize: keras.Model = None,
            model_denormalize: keras.Model = None,
            iterations: int = 1,
            cast_to_uint8: bool = True):
        super().__init__(
            model_denoise=model_denoise,
            model_normalize=model_normalize,
            model_denormalize=model_denormalize,
            training_channels=1,
            iterations=iterations,
            cast_to_uint8=cast_to_uint8)

    @tf.function(
        input_signature=[
            tf.TensorSpec(shape=[None, None, None, 1], dtype=tf.uint8)])
    def __call__(self, input_tensor):
        return self._run_inference_on_images(input_tensor)


# ---------------------------------------------------------------------


class DenoisingInferenceModule3Channel(DenoisingInferenceModule):
    def __init__(
            self,
            model_denoise: keras.Model = None,
            model_normalize: keras.Model = None,
            model_denormalize: keras.Model = None,
            iterations: int = 1,
            cast_to_uint8: bool = True):
        super().__init__(
            model_denoise=model_denoise,
            model_normalize=model_normalize,
            model_denormalize=model_denormalize,
            training_channels=3,
            iterations=iterations,
            cast_to_uint8=cast_to_uint8)

    @tf.function(
        input_signature=[
            tf.TensorSpec(shape=[None, None, None, 3], dtype=tf.uint8)])
    def __call__(self, input_tensor):
        return self._run_inference_on_images(input_tensor)


# ---------------------------------------------------------------------


def module_builder(
        model_denoise: keras.Model = None,
        model_normalize: keras.Model = None,
        model_denormalize: keras.Model = None,
        training_channels: int = 1,
        iterations: int = 1,
        cast_to_uint8: bool = True) -> DenoisingInferenceModule:
    """
    builds a module for denoising.

    :param model_denoise: denoising model to use for inference.
    :param model_normalize: model that normalizes the input
    :param model_denormalize: model that denormalizes the output
    :param training_channels: how many color channels were used in training
    :param iterations: how many times to run the model
    :param cast_to_uint8: cast output to uint8

    :return: denoiser module
    """
    logger.info(
        f"building denoising module with "
        f"iterations:{iterations}, "
        f"training_channels:{training_channels}, "
        f"cast_to_uint8:{cast_to_uint8}")

    if training_channels == 1:
        return \
            DenoisingInferenceModule1Channel(
                model_denoise=model_denoise,
                model_normalize=model_normalize,
                model_denormalize=model_denormalize,
                iterations=iterations,
                cast_to_uint8=cast_to_uint8)
    elif training_channels == 3:
        return \
            DenoisingInferenceModule3Channel(
                model_denoise=model_denoise,
                model_normalize=model_normalize,
                model_denormalize=model_denormalize,
                iterations=iterations,
                cast_to_uint8=cast_to_uint8)
    else:
        raise ValueError("don't know how to handle training_channels:{0}".format(training_channels))

# ---------------------------------------------------------------------