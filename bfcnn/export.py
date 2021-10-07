import os
import json
import pathlib
import argparse
import tensorflow as tf

# ---------------------------------------------------------------------
# local imports
# ---------------------------------------------------------------------

from .custom_logger import logger
from .export_model import export_model
from .model import model_builder, DenoisingInferenceModule

# ---------------------------------------------------------------------

__author__ = "Nikolas Markou"
__version__ = "0.1.0"
__license__ = "None"

# ---------------------------------------------------------------------


if __name__ == "__main__":
    # define arguments
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--pipeline-config",
        default=None,
        type=str,
        dest="pipeline_config",
        help="pipeline configuration path")

    parser.add_argument(
        "--checkpoint-directory",
        default=None,
        type=str,
        dest="checkpoint_directory",
        help="path to trained checkpoint directory")

    parser.add_argument(
        "--output-directory",
        default=None,
        type=str,
        dest="output_directory",
        help="path to write outputs")

    parser.add_argument(
        "--input-shape",
        default=[1, 256, 768, 3],
        type=list,
        dest="input_shape",
        help="input shape")

    parser.add_argument(
        "--to-tflite",
        action="store_true",
        dest="to_tflite",
        help="convert to tflite")

    parser.add_argument(
        "--test-model",
        action="store_true",
        dest="test_model",
        help="run model with random input")

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s (version {version})".format(version=__version__))

    # parse the arguments and pass them to main
    args = parser.parse_args()

    export_model(
        pipeline_config=args.pipeline_config,
        checkpoint_directory=args.checkpoint_directory,
        output_directory=args.output_directory,
        input_shape=args.input_shape,
        to_tflite=args.to_tflite,
        test_model=args.test_model)

# ---------------------------------------------------------------------
