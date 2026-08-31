# How to check which CUDA version is installed on Linux

- **URL:** https://arnon.dk/check-cuda-installed/
- **Author:** Arnon Shimoni
- **Published:** 2017-08-16T07:44:53+00:00
- **Modified:** 2020-11-24T12:44:02+00:00
- **Type:** post
- **Topics:** GPUs, IT
- **Tags:** cuda, nvcc, nvidia, version
- **Reading time:** 3 minutes
- **Description:** Get the CUDA version and which Nvidia GPU is installed in your machine in several ways, including API calls and shell commands

There are several ways and steps you could check which CUDA version is installed on your Linux box.

Check if CUDA is installed and it’s location  with NVCC

Run

which nvcc

to find if nvcc is installed properly.

You should see something like

/usr/bin/nvcc

. If that appears, your NVCC is installed in the standard directory.

~ $ which nvcc
/usr/bin/nvcc

If you have installed the CUDA toolkit but

which nvcc

returns no results, you might need to add the directory to your path.

You can check

nvcc --version

to get the CUDA compiler version, which matches the toolkit version:

~ $ nvcc --version
nvcc: NVIDIA (R) Cuda compiler driver
Copyright (c) 2005-2016 NVIDIA Corporation
Built on Tue_Jan_10_13:22:03_CST_2017
Cuda compilation tools, release 8.0, V8.0.61

This means that we have CUDA version 8.0.61 installed.

Note that

if the

nvcc

version doesn’t match the driver version

, you may have multiple

nvcc

s in your

PATH

. Figure out which one is the relevant one for you, and modify the environment variables to match, or get rid of the older versions.

Get CUDA version from CUDA code

When you’re writing your own code, figuring out how to check the CUDA version, including capabilities is often accomplished  with the

cudaDriverGetVersion

()

API call.

The API call gets the CUDA version from the active driver, currently loaded in Linux or Windows.

You can find a full

example of using cudaDriverGetVersion() here:

#include <cuda.h>

#include <stdio.h>

int main(int argc, char** argv) {

int driver_version = 0, runtime_version = 0;

cudaDriverGetVersion(&driver_version);

cudaRuntimeGetVersion(&runtime_version);

printf("Driver Version: %d\n"

"Runtime Version: %d\n",

driver_version, runtime_version);

return 0;

}

Identifying which CUDA driver version is installed and active in the kernel

You can also use the kernel to run a CUDA version check:

~ $ cat /proc/driver/nvidia/version
NVRM version: NVIDIA UNIX x86_64 Kernel Module  367.48  Sat Sep  3 18:21:08 PDT 2016
GCC version:  gcc version 4.8.5 20150623 (Red Hat 4.8.5-11) (GCC)

Identifying which GPU card is installed and what version

In many cases, I just use

nvidia-smi

to check the CUDA version on CentOS and Ubuntu.

For me,

nvidia-smi

is the most straight-forward and simplest way to get a holistic view of everything – both GPU card model and driver version, as well as some additional information like the topology of the cards on the PCIe bus, temperatures, memory utilization, and more.

The driver version is

367.48

as seen below, and the cards are two

Tesla K40m.

~ $ nvidia-smi
Tue Jun  6 12:43:17 2017
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 367.48                 Driver Version: 367.48                    |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  Tesla K40m          On   | 0000:04:00.0     Off |                   0* |
| N/A   48C    P0    67W / 235W |  12MiB / 11439MiB    |      0%      Default |
+-------------------------------+----------------------+----------------------+
|   1  Tesla K40m          On   | 0000:42:00.0     Off |                   0* |
| N/A   54C    P0    68W / 235W |  0MiB / 11439MiB     |      0%      Default |
+-------------------------------+----------------------+----------------------+

+-----------------------------------------------------------------------------+
| Processes:                                                       GPU Memory |
|  GPU       PID  Type  Process name                               Usage      |
|=============================================================================

Troubleshooting

After installing a new version of CUDA, there are some situations that require rebooting the machine to have the driver versions load properly. It is my recommendation to reboot after performing the

kernel-headers

upgrade/install process, and after installing CUDA – to verify that everything is loaded correctly.
