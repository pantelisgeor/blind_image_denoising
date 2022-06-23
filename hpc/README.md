# Running on Cyclone (HPC, The Cyprus Institute)


>## Installation instructions

NOTE: The guide was compiled using conda, but same principles apply for pure python installations

1) Download Miniconda and install it
* wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
* chmod +x Miniconda3-latest-Linux-x86_64.sh
* Close and open another terminal to initialise conda

2) Create a virtual environment for the project
* conda create -n denoise python=3.9

3) Activate the virtual environment
* conda activate denoise

4) Clone the github repository
* git clone https://github.com/pantelisgeor/blind_image_denoising

5) Make the Makefile executable
* chmod +x Makefile

6) Run the Makefile to install bfcnn package
* ./Makefile

7) Check if the package has been installed. If no errors show up, it was successfull!
* Open a python shell
* import bfcnn 
* `wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh`
* `chmod +x Miniconda3-latest-Linux-x86_64.sh`
* Close and open another terminal to initialise conda

2) Create a virtual environment for the project
* `conda create -n denoise python=3.9`

3) Activate the virtual environment
* `conda activate denoise`

4) Clone the github repository
* `git clone https://github.com/pantelisgeor/blind_image_denoising`

5) Make the Makefile executable
* `chmod +x Makefile`

6) Run the Makefile to install bfcnn package
* `./Makefile`

7) Check if the package has been installed. If no errors show up, it was successfull!
* Open a python shell
* `import bfcnn`


> ## Train the model (eg. test to check everything is working)

1) Request a gpu interactive node (1 GPU node for 6 hours with 12 cores)
* salloc --gres=gpu:1 --time=6:00:00 --ntasks-per-node=12

2) Load the required modules for CUDA 
* module load cuDNN/8.1.0.77-fosscuda-2020b CUDA/11.2.0

3) To test if tensorflow sees the GPU, open a python shell and run
* import tensorflow as tf
* tf.config.list_physical_devices('GPU')
* `salloc --gres=gpu:1 --time=6:00:00 --ntasks-per-node=12`

2) Load the required modules for CUDA 
* `module load cuDNN/8.1.0.77-fosscuda-2020b CUDA/11.2.0`

3) To test if tensorflow sees the GPU, open a python shell and run
* `import tensorflow as tf`
* `tf.config.list_physical_devices('GPU')`
* Output should contain no errors and look like -> [PhysicalDevice(name='/physical_device:GPU:0', device_type='GPU')]
* Close the python terminal with "exit()"

4) Downloaded some data from Kitti in /nvme/h/pgeorgiades/data_p069/denoiser_project/data/data_object_image_2/training/image_2/
* Image size is 1224x370 pixels
* Need to change the last two lines in the json config files located in bfcnn/configs

5) In this case the resnet_color_laplacian_2x5_non_shared_bn_16x3x3_128x128_skip_input.json config file is used and the model is saved to a test folder 
* python -m bfcnn.train --model-directory /nvme/h/pgeorgiades/data_p069/denoiser_pantelis/tests -- pipeline-config bfcnn/configs/resnet_color_laplacian_2x5_non_shared_bn_16x3x3_128x128_skip_input.json
=======
* `python -m bfcnn.train --model-directory /nvme/h/pgeorgiades/data_p069/denoiser_pantelis/tests -- pipeline-config bfcnn/configs/resnet_color_laplacian_2x5_non_shared_bn_16x3x3_128x128_skip_input.json`
