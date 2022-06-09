<div align="center">

**A library for blind image denoising algorithms using bias free denoising CNN's**
___

[Getting Started](#Pretrained) •
[License](https://github.com/NikolasMarkou/blind_image_denoising/blob/main/LICENSE)

[![python](https://img.shields.io/badge/python-3.6%2B-green)]()
[![tensorflow](https://img.shields.io/badge/tensorflow-2.6%2B-green)]()

</div>

___

# Blind Image Denoising

## Target
The target is to create a series of:

* interpretable
* multi scale
* high performance
* low memory footprint
 
models that performs denoising on an input (grayscale or colored) image. 

The bias-free nature of the model allows for easy interpretation and use as prior
for hard inverse problems.

## Interpretation 
Interpretation comes naturally by implementing the CVPR 2020 paper : 

["ROBUST AND INTERPRETABLE BLIND IMAGE DENOISING VIA BIAS - FREE CONVOLUTIONAL NEURAL NETWORKS"](https://arxiv.org/abs/1906.05478)

This paper provides excellent results

![](images/readme/bfcnn_noisy_1.png "single channel bias free denoising")

Which can also be completely interpretable as a mask per pixel

![](images/readme/bfcnn_noisy_2.png "pixel smoothing interpretability")

## Multi-Scale
The system is trained in multiple scales by implementing ideas 
from LapSRN (Laplacian Pyramid Super-Resolution Network) and MS-LapSRN (Multi-Scale Laplacian Pyramid Super-Resolution Network)

![](images/readme/laplacian_pyramid_decomposition.png "laplacian pyramid decomposition")

![](images/readme/laplacian_pyramid_recomposition.png "laplacian pyramid recomposition")

## Low-Memory footprint
By using a gaussian pyramid and a shared bias-free CNN model between each scale, 
we can ensure that we have a small enough model to run on very small devices while ensure we
have a big enough ERF (effective receptive field) for the task at hand.

## Corruption types
In order to train such a model we corrupt an input image using 
several types of noise and then try to recover the original image

* subsampling noise
* normally distributed additive noise (same per channel / different same per channel)
* normally distributed multiplicative noise (same per channel / different same per channel)

## Image examples

* these images were gathered while training on patches of 128x128
* we can clearly see that the model adapts well to different ranges of noise

|Normal                   |  Noisy                  |  Denoised               |
|-------------------------|-------------------------|-------------------------|
![](images/readme/bfcnn_input_normal_2.png "normal") | ![](images/readme/bfcnn_input_noisy_2.png "noisy") |![](images/readme/bfcnn_input_denoised_2.png "denoised")|
![](images/readme/bfcnn_input_normal_6.png "normal") | ![](images/readme/bfcnn_input_noisy_6.png "noisy") |![](images/readme/bfcnn_input_denoised_6.png "denoised")|
![](images/readme/bfcnn_input_normal_5.png "normal") | ![](images/readme/bfcnn_input_noisy_5.png "noisy") |![](images/readme/bfcnn_input_denoised_5.png "denoised")|
![](images/readme/bfcnn_input_normal_0.png "normal") | ![](images/readme/bfcnn_input_noisy_0.png "noisy") |![](images/readme/bfcnn_input_denoised_0.png "denoised")|
![](images/readme/bfcnn_input_normal_3.png "normal") | ![](images/readme/bfcnn_input_noisy_3.png "noisy") |![](images/readme/bfcnn_input_denoised_3.png "denoised")|
![](images/readme/bfcnn_input_normal_1.png "normal") | ![](images/readme/bfcnn_input_noisy_1.png "noisy") |![](images/readme/bfcnn_input_denoised_1.png "denoised")|


## How to use (from scratch)

1. prepare training input
2. prepare training configuration
3. run training
4. export to tflite and saved_model format
5. use models

### Train
Prepare a training configuration and train with the following command:  
```
python -m bfcnn.train \ 
  --model-directory ${TRAINING_DIR} \ 
  --pipeline-config ${PIPELINE}
```
### Export
Export to frozen graph and/or tflite with the following command:
```
python -m bfcnn.export \
    --checkpoint-directory ${TRAINING_DIR} \
    --pipeline-config ${PIPELINE} \
    --output-directory ${OUTPUT_DIR} \
    --to-tflite
```

## How to use (pretrained)

Use any of the pretrained models included in the package:
* [resnet_color_1x5_non_shared_bn_16x3x3_128x128](bfcnn/pretrained/resnet_color_1x5_non_shared_bn_16x3x3_128x128)
* [resnet_color_1x5_non_shared_bn_16x3x3_128x128_skip_input](bfcnn/pretrained/resnet_color_1x5_non_shared_bn_16x3x3_128x128_skip_input)
* [resnet_color_laplacian_2x5_non_shared_bn_16x3x3_128x128_skip_input](bfcnn/pretrained/resnet_color_laplacian_2x5_non_shared_bn_16x3x3_128x128_skip_input)

```python
import bfcnn
import tensorflow as tf

# load model
denoiser_model = \
    bfcnn.load_model(
        "resnet_color_1x5_non_shared_bn_16x3x3_128x128")

# create random tensor
input_tensor = \
    tf.random.uniform(
        shape=[1, 256, 256, 3],
        minval=0,
        maxval=255,
        dtype=tf.int32)
input_tensor = \
    tf.cast(
        input_tensor,
        dtype=tf.uint8)

# run inference
denoised_tensor = denoiser_model(input_tensor)
```

## Model types
We have used traditional (bias free) architectures.
* resnet
* resnet with sparse constraint
* resnet with on/off per resnet block gates 
* all the above models with multi-scale processing

### Additions
#### [Multi-Scale Laplacian Pyramid](bfcnn/pyramid.py)
Our addition (not in the paper) is the laplacian multi-scale pyramid
that expands the effective receptive field without the need to add many more layers (keeping it cheap computationally).
![](images/readme/laplacian_model.png "Laplacian model")

Which breaks down the original image into 3 different scales and processes them independently:

![](images/readme/laplacian_decomposition_lena.png "Laplacian Decomposition Lena")

We also have the option to add residuals at the end of each processing levels, so it works like an iterative process:

![](images/readme/laplacian_model_residual.png "Laplacian model residual")


#### [Multi-Scale Gaussian Pyramid](bfcnn/pyramid.py)
Our addition (not in the paper) is the gaussian multi-scale pyramid
that expands the effective receptive field without the need to add many more layers (keeping it cheap computationally).

#### [Noise estimation model Multi-Scale mixer](bfcnn/model_noise_estimation.py)
Our addition (not in the paper) is a noise estimation model that
decides the contribution of each layer when mixing them back in.

#### [Squeeze and Excite with residual](bfcnn/utilities.py)
Every resnet block has the option to include a residual squeeze and excite element (not in the paper) to it.

#### Normalization layer
Our addition (not in the paper) is a (non-channel wise and non-learnable) normalization layer (not BatchNorm) 
after the DepthWise operations. This is to enforce sparsity with the differentiable relu below.

#### Differentiable RELU
Our addition (not in the paper) is a differentiable relu for specific operations.
![](images/readme/differentiable_relu.png "Differentiable RELU")

#### [Soft Orthogonal Regularization](bfcnn/regularizer.py)
Added optional orthogonality regularization. 

## References
1. [Robust and interpretable blind image denoising via bias-free convolutional neural networks](https://arxiv.org/abs/1906.05478)
2. [Fast and Accurate Image Super-Resolution with Deep Laplacian Pyramid Networks](https://arxiv.org/abs/1710.01992)
3. [Densely Residual Laplacian Super-Resolution](https://arxiv.org/abs/1906.12021)
4. [Can We Gain More from Orthogonality Regularizations in Training Deep CNNs?](https://arxiv.org/abs/1810.09102)
5. [Squeeze-and-Excitation Networks](https://arxiv.org/abs/1709.01507)




