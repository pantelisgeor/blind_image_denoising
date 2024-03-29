r"""Constructs model, inputs, and training environment."""

# ---------------------------------------------------------------------

__author__ = "Nikolas Markou"
__version__ = "1.0.0"
__license__ = "MIT"

# ---------------------------------------------------------------------

import os
import time
import tensorflow as tf
from pathlib import Path
from typing import Union, Dict

# ---------------------------------------------------------------------
# local imports
# ---------------------------------------------------------------------

from .constants import *
from .visualize import visualize
from .custom_logger import logger
from .utilities import load_config
from .loss import loss_function_builder
from .optimizer import optimizer_builder
from .model_denoise import model_builder as model_denoise_builder
from .pruning import prune_function_builder, PruneStrategy, get_conv2d_weights
from .dataset import \
    dataset_builder, \
    DATASET_TESTING_FN_STR, \
    DATASET_FN_STR, \
    AUGMENTATION_FN_STR


# ---------------------------------------------------------------------


def train_loop(
        pipeline_config_path: Union[str, Dict, Path],
        model_dir: Union[str, Path]):
    """
    Trains a blind image denoiser

    This method:
        1. Processes the pipeline configs
        2. (Optionally) saves the as-run config
        3. Builds the model & optimizer
        4. Gets the training input data
        5. Loads a fine-tuning detection
        6. Loops over the train data
        7. Checkpoints the model every `checkpoint_every_n` training steps.
        8. Logs the training metrics as TensorBoard summaries.

    :param pipeline_config_path: filepath to the configuration
    :param model_dir: directory to save checkpoints into
    :return:
    """
    # --- load configuration
    config = load_config(pipeline_config_path)

    # --- create model_dir if not exist
    if not os.path.isdir(str(model_dir)):
        # if path does not exist attempt to make it
        Path(str(model_dir)).mkdir(parents=True, exist_ok=True)
        # if it fails again throw exception
        if not os.path.isdir(str(model_dir)):
            raise ValueError("Model directory [{0}] is not valid".format(
                model_dir))

    # --- build dataset
    dataset_res = dataset_builder(config=config["dataset"])
    dataset = dataset_res[DATASET_FN_STR]
    augmentation_fn = tf.function(dataset_res[AUGMENTATION_FN_STR])

    # --- build loss function
    loss_fn = loss_function_builder(config=config["loss"])

    # --- build optimizer
    optimizer, lr_schedule = \
        optimizer_builder(config=config["train"]["optimizer"])

    # --- create the help variables
    global_step = tf.Variable(
        0, trainable=False, dtype=tf.dtypes.int64, name="global_step")
    global_epoch = tf.Variable(
        0, trainable=False, dtype=tf.dtypes.int64, name="global_epoch")
    summary_writer = tf.summary.create_file_writer(model_dir)

    # --- get the train configuration
    train_config = config["train"]
    epochs = train_config["epochs"]
    global_total_epochs = tf.Variable(
        epochs, trainable=False, dtype=tf.dtypes.int64, name="global_total_epochs")
    trace_every = train_config.get("trace_every", 100)
    weight_buckets = train_config.get("weight_buckets", 100)
    error_buckets = train_config.get("error_buckets", 255)
    total_steps = \
        tf.constant(
            train_config.get("total_steps", -1),
            dtype=tf.dtypes.int64,
            name="total_steps")
    # how many checkpoints to keep
    checkpoints_to_keep = train_config.get("checkpoints_to_keep", 3)
    # checkpoint every so many steps
    checkpoint_every = \
        tf.constant(
            train_config.get("checkpoint_every", -1),
            dtype=tf.dtypes.int64,
            name="checkpoint_every")
    # how many steps to make a visualization
    visualization_every = \
        tf.constant(
            train_config.get("visualization_every", 1000),
            dtype=tf.dtypes.int64,
            name="visualization_every")
    # how many visualizations to show
    visualization_number = train_config.get("visualization_number", 5)
    # how many times the random batch will be iterated
    random_batch_iterations = \
        train_config.get("random_batch_iterations", 1)
    # size of the random batch
    random_batch_size = \
        [visualization_number] + \
        train_config.get("random_batch_size", [128, 128, 3])
    # --- prune strategy
    prune_config = \
        train_config.get("prune", {"strategies": []})
    prune_start_epoch = \
        tf.constant(
            prune_config.get("start_epoch", 0),
            dtype=tf.dtypes.int64,
            name="prune_start_epoch")
    prune_steps = \
        tf.constant(
            prune_config.get("steps", -1),
            dtype=tf.dtypes.int64,
            name="prune_steps")
    prune_strategies = prune_config["strategies"]
    if prune_strategies is None:
        use_prune = False
    elif isinstance(prune_strategies, list):
        use_prune = len(prune_strategies) > 0
    elif isinstance(prune_strategies, dict):
        use_prune = True
    else:
        use_prune = False
    use_prune = tf.constant(use_prune)
    prune_fn = \
        prune_function_builder(prune_strategies)

    # --- build the denoise model
    tf.summary.trace_on(graph=True, profiler=False)
    with summary_writer.as_default():
        models = \
            model_denoise_builder(config=config[MODEL_DENOISE_STR])

        # The function to be traced.
        @tf.function
        def optimized_model(x_input):
            return models.denoiser(x_input, training=False)

        x = \
            tf.random.truncated_normal(
                seed=0,
                mean=0.0,
                stddev=0.25,
                shape=random_batch_size)
        _ = optimized_model(x)
        tf.summary.trace_export(
            step=0,
            name="denoiser")
        tf.summary.flush()
        tf.summary.trace_off()

    # get each model
    pyramid = models.pyramid
    denoiser = models.denoiser
    normalizer = models.normalizer
    denormalizer = models.denormalizer
    inverse_pyramid = models.inverse_pyramid
    denoiser_decomposition = models.denoiser_decomposition

    # summary of model
    denoiser.summary(print_fn=logger.info)
    # save model so we can visualize it easier
    denoiser.save(
        filepath=os.path.join(model_dir, MODEL_DENOISE_DEFAULT_NAME_STR),
        include_optimizer=False)

    # --- create random image and iterate through the model
    def create_random_batch():
        x_iteration = 0
        x_random = \
            tf.random.truncated_normal(
                seed=0,
                mean=0.0,
                stddev=0.25,
                shape=random_batch_size)
        while x_iteration < random_batch_iterations:
            x_random = denoiser(x_random, training=False)
            x_random = \
                tf.clip_by_value(
                    x_random,
                    clip_value_min=-0.5,
                    clip_value_max=+0.5)
            x_iteration += 1
        return \
            denormalizer(
                x_random,
                training=False)

    # --- train the model
    with summary_writer.as_default():
        checkpoint = \
            tf.train.Checkpoint(
                step=global_step,
                epoch=global_epoch,
                optimizer=optimizer,
                model_denoise=denoiser,
                model_normalize=normalizer,
                model_denormalize=denormalizer,
                model_denoise_decomposition=denoiser_decomposition)
        manager = \
            tf.train.CheckpointManager(
                checkpoint=checkpoint,
                directory=model_dir,
                max_to_keep=checkpoints_to_keep)
        status = \
            checkpoint.restore(manager.latest_checkpoint).expect_partial()

        # --- define denoise fn
        if inverse_pyramid is not None:
            @tf.function
            def denoise_fn(x):
                # denoised decomposition
                x0 = \
                    denoiser_decomposition(
                        x,
                        training=True)
                # denoised merged
                x1 = \
                    inverse_pyramid(
                        x0,
                        training=False)
                # denoised denormalized
                x2 = \
                    denormalizer(x1, training=False)
                return x0, x1, x2
        else:
            @tf.function
            def denoise_fn(x):
                # denoised decomposition
                x0 = None
                # denoised merged
                x1 = \
                    denoiser(
                        x,
                        training=True)
                # denoised denormalized
                x2 = \
                    denormalizer(x1, training=False)
                return x0, x1, x2

        # ---

        while global_epoch < global_total_epochs:
            logger.info("epoch: {0}, step: {1}".format(
                int(global_epoch), int(global_step)))

            # --- pruning strategy
            if use_prune and (global_epoch >= prune_start_epoch):
                logger.info(f"pruning weights at step [{int(global_step)}]")
                denoiser_decomposition = \
                    prune_fn(model=denoiser_decomposition)

            model_denoise_weights = \
                denoiser_decomposition.trainable_weights

            # --- iterate over the batches of the dataset
            for input_batch in dataset:
                start_time = time.time()

                # augment data
                noisy_batch = augmentation_fn(input_batch)

                # normalize input and noisy batch
                normalized_input_batch = normalizer(input_batch, training=False)
                normalized_noisy_batch = normalizer(noisy_batch, training=False)

                if pyramid is not None:
                    # split input image into pyramid levels
                    normalized_input_batch_decomposition = \
                        pyramid(
                            normalized_input_batch,
                            training=False)
                else:
                    normalized_input_batch_decomposition = None

                # Open a GradientTape to record the operations run
                # during the forward pass,
                # which enables auto-differentiation.
                with tf.GradientTape() as tape:
                    # run the forward pass of the layer.
                    # The operations that the layer applies
                    # to its inputs are going to be recorded
                    # on the GradientTape.
                    denoised_batch_decomposition, \
                    denoised_batch, \
                    denormalized_denoised_batch = \
                        denoise_fn(normalized_noisy_batch)

                    # compute the loss value for this mini-batch
                    loss_map = \
                        loss_fn(
                            input_batch=input_batch,
                            noisy_batch=noisy_batch,
                            model_losses=denoiser.losses,
                            prediction_batch=denormalized_denoised_batch,
                            prediction_batch_decomposition=denoised_batch_decomposition,
                            input_batch_decomposition=normalized_input_batch_decomposition
                        )

                    # use the gradient tape to automatically retrieve
                    # the gradients of the trainable variables
                    # with respect to the loss.
                    grads = \
                        tape.gradient(
                            target=loss_map[MEAN_TOTAL_LOSS_STR],
                            sources=model_denoise_weights)

                # run one step of gradient descent by updating
                # the value of the variables to minimize the loss.
                optimizer.apply_gradients(
                    grads_and_vars=zip(grads, model_denoise_weights))

                # --- add loss summaries for tensorboard
                for name, key in [
                    ("loss/mae", MAE_LOSS_STR),
                    ("loss/total", MEAN_TOTAL_LOSS_STR),
                    ("loss/nae", NAE_PREDICTION_LOSS_STR),
                    ("loss/regularization", REGULARIZATION_LOSS_STR),
                    ("loss/mae_decomposition", MAE_DECOMPOSITION_LOSS_STR),
                    ("quality/nae_noise", "nae_noise"),
                    ("quality/signal_to_noise_ratio", "snr"),
                    ("quality/nae_improvement", NAE_IMPROVEMENT_QUALITY_STR)
                ]:
                    if key not in loss_map:
                        continue
                    tf.summary.scalar(
                        name=name,
                        data=loss_map[key],
                        step=global_step)

                # --- add image prediction for tensorboard
                if (global_step % visualization_every) == 0:
                    random_batch = create_random_batch()
                    visualize(
                        global_step=global_step,
                        input_batch=input_batch,
                        noisy_batch=noisy_batch,
                        random_batch=random_batch,
                        prediction_batch=denormalized_denoised_batch,
                        visualization_number=visualization_number)
                    # add weight visualization
                    weights = \
                        get_conv2d_weights(
                            model=denoiser)
                    tf.summary.histogram(
                        data=weights,
                        step=global_step,
                        buckets=weight_buckets,
                        name="training/weights")

                    # --- prediction error distribution
                    input_prediction_error = \
                        (input_batch - denormalized_denoised_batch) / 255
                    input_prediction_error = \
                        tf.reshape(input_prediction_error, shape=[-1])
                    tf.summary.histogram(
                        data=input_prediction_error,
                        step=global_step,
                        buckets=error_buckets,
                        name="training/error_distribution")

                if use_prune and (global_epoch >= prune_start_epoch) and \
                        (int(prune_steps) != -1) and (global_step % prune_steps == 0):
                    logger.info(f"pruning weights at step [{int(global_step)}]")
                    denoiser = \
                        prune_fn(model=denoiser)

                # --- check if it is time to save a checkpoint
                if checkpoint_every > 0:
                    if (global_step % checkpoint_every == 0):
                        logger.info("checkpoint at step: {0}".format(
                            int(global_step)))
                        manager.save()

                # --- keep time of steps per second
                stop_time = time.time()
                step_time = stop_time - start_time

                tf.summary.scalar(
                    "training/steps_per_second",
                    1.0 / (step_time + 0.00001),
                    step=global_step)

                tf.summary.scalar(
                    "training/epoch",
                    int(global_epoch),
                    step=global_step)

                tf.summary.scalar(
                    "training/learning_rate",
                    lr_schedule(int(global_step)),
                    step=global_step)

                # ---
                global_step.assign_add(1)

                # --- check if total steps reached
                if total_steps > 0:
                    if total_steps <= global_step:
                        logger.info("total_steps reached [{0}]".format(
                            int(total_steps)))
                        break

            # --- end of the epoch
            logger.info("checkpoint at end of epoch: {0}".format(
                int(global_epoch)))
            global_epoch.assign_add(1)
            manager.save()
            # save model so we can visualize it easier
            denoiser.save(
                os.path.join(model_dir, MODEL_DENOISE_DEFAULT_NAME_STR))

    logger.info("finished training")

# ---------------------------------------------------------------------
