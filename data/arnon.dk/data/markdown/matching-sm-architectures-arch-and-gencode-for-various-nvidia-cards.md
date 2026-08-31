# Matching CUDA arch and CUDA gencode for various NVIDIA architectures

- **URL:** https://arnon.dk/matching-sm-architectures-arch-and-gencode-for-various-nvidia-cards/
- **Author:** Arnon Shimoni
- **Published:** 2020-10-27T21:14:00+00:00
- **Modified:** 2026-04-13T10:37:28+00:00
- **Type:** post
- **Topics:** GPUs
- **Tags:** compute, compute_52, cuda, cuda arch, gencode, gpu, gtx 1080, nvcc, nvcc arch, nvcc flags, nvcc sm, nvidia, nvidia sm, pascal, sm
- **Reading time:** 9 minutes
- **Description:** This guide lists the various supported nvcc cuda gencode and cuda arch flags that can be used to compile your GPU code for several different GPUs

Updated Apr 13th 202

6

tl;dr

I’ve seen some confusion regarding NVIDIA’s nvcc sm flags and what they’re used for:

When compiling with NVCC, the arch flag (‘

-arch

‘) specifies the name of the NVIDIA GPU architecture that the CUDA files will be compiled for.

Gencodes (‘

-gencode

‘) allows for more PTX generations and can be repeated many times for different architectures.

Here’s a list of NVIDIA architecture names, and which compute capabilities they have:

Fermi, Kepler

†

Maxwell

‡

Pascal

§

Volta

§

Turing

Ampere

Ada

Hopper

Blackwell / Blackwell Ultra

Rubin (H2 2026)

sm_20

sm_50

sm_60

sm_70

sm_75

sm_80

sm_89

sm_90,

sm_90a (Thor)

sm_100,

sm_100a, sm_100f

sm_130?

sm_30, sm_35, sm_37

sm_52

sm_61

sm_72

(Xavier)

sm_86

sm_103, sm_103a, sm_103f

sm_53

sm_62

sm_87 (Orin)

sm_110, sm_110a, sm_110f (Thor, was sm_101 pre-CUDA 13)

sm_121, sm_121a (GB10 / DGX Spark)

†

Fermi and Kepler are deprecated from CUDA 9 and 11 onwards

‡

Maxwell is deprecated from CUDA 11.6 onwards

§ Maxwell, Pascal, and Volta offline compilation support removed in CUDA 13.0.

When should different ‘gencodes’ or ‘cuda arch’ be used?

When you compile CUDA code, you should always compile only one ‘

-arch

‘ flag that matches your most used GPU cards. This will enable faster runtime, because code generation will occur during compilation.

If you only mention ‘

-gencode

‘, but omit the ‘

-arch

‘ flag, the GPU code generation will occur on the

JIT

compiler by the CUDA driver.

When you want to speed up CUDA compilation, you want to reduce the amount of irrelevant ‘

-gencode

‘ flags. However, sometimes you may wish to have better CUDA backwards compatibility by adding more comprehensive ‘

-gencode

‘ flags.

Before you continue, identify which GPU you have and

which CUDA version you have installed

first.

Supported SM and Gencode variations

Below are the supported sm variations and sample cards from that generation.

I’ve tried to supply representative NVIDIA GPU cards for each architecture name, and CUDA version.

Note on family-specific architecture features (CUDA 12.9 and later)

Starting with CUDA 12.9, NVIDIA introduced a third compilation target suffix:

f

(family-specific). This sits between the baseline (no suffix) and architecture-specific (“a” suffix):

No suffix (e.g. compute_100): Maximum forward compatibility across major versions. Basic feature set.

"f"

suffix (e.g. compute_100f): Forward compatible within the same major version family. Enables family-specific features like certain Tensor Core ops. Code compiled for compute_100f runs on sm_100 AND sm_103 devices.

"a"

suffix (e.g. compute_100a): Only runs on the exact compute capability. No forward compatibility at all. Enables the full set of architecture-specific features.

There are currently two Blackwell families:

The 10.x family (compute_100f): includes sm_100 (B100/B200) and sm_103 (B300)

The 12.x family (compute_120f): includes sm_120 (RTX 50 series) and sm_121 (GB10/DGX Spark)

These two families are NOT cross-compatible —

sm_100f

code does NOT run on

sm_120

devices and vice versa.

Fermi cards (CUDA 3.2 until CUDA 8)

Deprecated from CUDA 9, support completely dropped from CUDA 10.

SM20 or SM_20, compute_30

–

GeForce 400, 500, 600, GT-630.

Completely dropped from CUDA 10 onwards.

Kepler cards (CUDA 5 until CUDA 10)

Deprecated from CUDA 11.

SM30 or

SM_30, compute_30

–

Kepler architecture (e.g. generic Kepler, GeForce 700, GT-730).

Adds support for unified memory programming

Completely dropped from CUDA 11 onwards

.

SM35 or

SM_35, compute_35

–

Tesla K40.

Adds support for dynamic parallelism.

Deprecated from CUDA 11, will be dropped in future versions

.

SM37 or

SM_37, compute_37

–

Tesla K80.

Adds a few more registers.

Deprecated from CUDA 11, will be dropped in future versions

, strongly suggest replacing with a

32GB PCIe Tesla V100

.

Maxwell cards (CUDA 6 until CUDA 11)

SM50 or

SM_50, compute_50

–

Tesla/Quadro M series.

Deprecated from CUDA 11, will be dropped in future versions

, strongly suggest replacing with a

Quadro RTX 4000

or

A6000

.

SM52 or

SM_52, compute_52

–

Quadro M6000 , GeForce 900, GTX-970, GTX-980, GTX Titan X.

SM53 or

SM_53, compute_53

–

Tegra (Jetson) TX1 / Tegra X1, Drive CX, Drive PX, Jetson Nano.

Pascal (CUDA 8 and later)

SM60 or

SM_60, compute_60

–

Quadro GP100, Tesla P100, DGX-1 (Generic Pascal)

SM61 or

SM_61, compute_61

–

GTX 1080, GTX 1070, GTX 1060, GTX 1050, GTX 1030 (GP108), GT 1010 (GP108) Titan Xp, Tesla P40, Tesla P4, Discrete GPU on the NVIDIA Drive PX2

SM62 or

SM_62, compute_62

–

Integrated GPU on the NVIDIA Drive PX2, Tegra (Jetson) TX2

Volta (CUDA 9 and later)

SM70 or

SM_70, compute_70

–

DGX-1 with Volta, Tesla V100, GTX 1180 (GV104), Titan V, Quadro GV100

SM72 or

SM_72, compute_72

–

Jetson AGX Xavier

, Drive AGX Pegasus, Xavier NX

Turing (CUDA 10 and later)

SM75 or

SM_75, compute_75

–

GTX/RTX Turing – GTX 1660 Ti, RTX 2060,

RTX 2070

, RTX 2080, Titan RTX, Quadro RTX 4000, Quadro RTX 5000, Quadro RTX 6000, Quadro RTX 8000, Quadro T1000/T2000, Tesla T4

Ampere (CUDA 11.1 and later)

SM80 or

SM_80, compute_80

–

NVIDIA

A100

(the name “Tesla” has been dropped – GA100), NVIDIA DGX-A100

SM86 or

SM_86, compute_86

–

(from

CUDA 11.1 onwards

)

Tesla GA10x cards, RTX Ampere – RTX 3080, GA102 – RTX 3090, RTX A2000, A3000,

RTX A4000

,

RTX A5000

, RTX

A6000 Ada

, NVIDIA A40, GA106 –

RTX 3060

, GA104 – RTX 3070, GA107 – RTX 3050, RTX A10, RTX A16, RTX A40, A2 Tensor Core GPU,

A800 40GB

SM87 or

SM_87, compute_87

–

(from

CUDA 11.4 onwards

, introduced with PTX ISA 7.4 / Driver r470 and newer) – for Jetson AGX Orin and Drive AGX Orin only

“

Devices of compute capability 8.6 have 2x more FP32 operations per cycle per SM than devices of compute capability 8.0. While a binary compiled for 8.0 will run as is on 8.6, it is recommended to compile explicitly for 8.6 to benefit from the increased FP32 throughput.

“

https://docs.nvidia.com/cuda/ampere-tuning-guide/index.html#improved_fp32

Ada Lovelace (CUDA 11.8 and later)

SM89 or

SM_89, compute_

89

–

NVIDIA GeForce RTX 4090, RTX 4080,

RTX 6000

Ada,

Tesla L40

,

L40s Ada

,

L4 Ada

,

RTX 4500

Hopper (CUDA 12 and later)

Requires PTX 8.0

SM90 or

SM_90, compute_90

–

NVIDIA H100 (GH100), NVIDIA

H200

SM90a or

SM_90a, compute_90a

– (not forwards compatible, specialized accelerated features) – adds acceleration for features like

wgmma

and

setmaxnreg

. This is required for NVIDIA CUTLASS

Blackwell (CUDA 12.8 and later)

Requires PTX 8.6 (sm_100), PTX 8.7 (sm_120), PTX 8.8 (sm_103, sm_121 — CUDA 12.9)

SM100 or

SM_100, compute_

100

–

SM100 or SM_100, compute_100 – NVIDIA B100 (GB100), B200, NVIDIA B40. Datacenter Blackwell.

SM100a or

SM_100A, compute_

100a

– (not forwards compatible, specialized accelerated features)

NVIDIA B100 (GB100), B200, NVIDIA B40. Required for CUTLASS and architecture-accelerated features on datacenter Blackwell.

SM100f or SM_100F, compute_100f

– (family-specific, forwards compatible within 10.x family) –

NEW in CUDA 12.9

Compatible with all CC 10.x devices (sm_100, sm_103). Use this when you want one binary for all datacenter Blackwell GPUs.

Blackwell Ultra (CUDA 12.9 and later)

SM103 or SM_103, compute_103

– (from CUDA 12.9 onwards)

NVIDIA B300, GB300 NVL72. Blackwell Ultra datacenter.

Part of the sm_100f family — code compiled for compute_100f runs on both sm_100 and sm_103 devices.

SM103a or SM_103a, compute_103a

– (not forwards compatible, specialized accelerated features)

NVIDIA B300, GB300 NVL72.

SM103f or SM_103f, compute_103f

– (family-specific)

NVIDIA B300, GB300 NVL72.

SM120 or SM_120, compute_120

–

GeForce RTX 5090, RTX 5080, RTX 5070 Ti, RTX 5070, RTX 5060, RTX PRO 6000 Blackwell (GB202, GB203, GB205, GB206, GB207). Consumer/workstation Blackwell.

Note: sm_120 is NOT compatible with sm_100 datacenter cubins, these are separate compilation targets despite both being “Blackwell”.

SM120a or SM_120a, compute_120a

– (not forwards compatible, specialized accelerated features)

GeForce RTX 5090, RTX 5080, RTX 5070 Ti, RTX 5070, RTX 5060, RTX PRO 6000 Blackwell.

SM120f or SM_120F, compute_120f

– (family-specific, forwards compatible within 12.x family) – NEW in CUDA 12.9

Compatible with all CC 12.x devices (sm_120, sm_121).

Blackwell – Thor (CUDA 13 and later)

SM110 or SM_110, compute_110

– NVIDIA Jetson Thor.

Was named sm_101 in CUDA 12.8/12.9, renumbered to sm_110 in CUDA 13.0.

If compiling with CUDA 12.8 or 12.9, use

sm_101

. If compiling with CUDA 13.0+, use

sm_110

.

SM110a or SM_110a, compute_110a

– (not forwards compatible, specialized accelerated features) – NVIDIA Jetson Thor.

Sample

nvcc

gencode

and

arch

Flags in GCC

According to NVIDIA:

The

arch=

clause of the

-gencode=

command-line option to

nvcc

specifies the front-end compilation target and must always be a PTX version. The

code=

clause specifies the back-end compilation target and can either be cubin or PTX or both. Only the back-end target version(s) specified by the

code=

clause will be retained in the resulting binary; at least one must be PTX to provide Ampere compatibility.

Sample flags for GCC generation on CUDA 7.0 for maximum compatibility with all cards from the era:

-arch=sm_30 \

-gencode=arch=compute_20,code=sm_20 \

-gencode=arch=compute_30,code=sm_30 \

-gencode=arch=compute_50,code=sm_50 \

-gencode=arch=compute_52,code=sm_52 \

-gencode=arch=compute_52,code=compute_52

Sample flags for generation on CUDA 8.1 for maximum compatibility with cards predating Volta:

-arch=sm_30 \

-gencode=arch=compute_20,code=sm_20 \

-gencode=arch=compute_30,code=sm_30 \

-gencode=arch=compute_50,code=sm_50 \

-gencode=arch=compute_52,code=sm_52 \

-gencode=arch=compute_60,code=sm_60 \

-gencode=arch=compute_61,code=sm_61 \

-gencode=arch=compute_61,code=compute_61

Sample flags for generation on CUDA 9.2 for maximum

compatibility

with Volta cards:

-arch=sm_50 \

-gencode=arch=compute_50,code=sm_50 \

-gencode=arch=compute_52,code=sm_52 \

-gencode=arch=compute_60,code=sm_60 \

-gencode=arch=compute_61,code=sm_61 \

-gencode=arch=compute_70,code=sm_70 \

-gencode=arch=compute_70,code=compute_70

Sample flags for generation on

CUDA 10.1

for maximum

compatibility

with V100 and T4 Turing cards:

-arch=sm_50 \

-gencode=arch=compute_50,code=sm_50 \

-gencode=arch=compute_52,code=sm_52 \

-gencode=arch=compute_60,code=sm_60 \

-gencode=arch=compute_61,code=sm_61 \

-gencode=arch=compute_70,code=sm_70 \

-gencode=arch=compute_75,code=sm_75 \

-gencode=arch=compute_75,code=compute_75

Sample flags for generation on

CUDA 11.0

for maximum

compatibility

with V100 and T4 Turing cards:

-arch=sm_52 \

-gencode=arch=compute_52,code=sm_52 \

-gencode=arch=compute_60,code=sm_60 \

-gencode=arch=compute_61,code=sm_61 \

-gencode=arch=compute_70,code=sm_70 \

-gencode=arch=compute_75,code=sm_75 \

-gencode=arch=compute_80,code=sm_80 \

-gencode=arch=compute_80,code=compute_80

Sample flags for generation on

CUDA 11.7

for maximum

compatibility

with V100 and

T4 Turing Datacenter

cards, but also support newer RTX 3080, and Drive AGX Orin:

-arch=sm_52 \

-gencode=arch=compute_52,code=sm_52 \

-gencode=arch=compute_60,code=sm_60 \

-gencode=arch=compute_61,code=sm_61 \

-gencode=arch=compute_70,code=sm_70 \

-gencode=arch=compute_75,code=sm_75 \

-gencode=arch=compute_80,code=sm_80 \

-gencode=arch=compute_86,code=sm_86 \

-gencode=arch=compute_87,code=sm_87

-gencode=arch=compute_86,code=compute_86

Sample flags for generation on

CUDA 11.4

for best performance with RTX 3080 cards:

-arch=sm_80 \

-gencode=arch=compute_80,code=sm_80 \

-gencode=arch=compute_86,code=sm_86 \

-gencode=arch=compute_87,code=sm_87 \

-gencode=arch=compute_86,code=compute_86

Sample flags for generation on

CUDA 12

for best performance with

GeForce RTX 4080

, L40s,

L4

, and

RTX A6000 Ada

cards:

-arch=sm_89 \

-gencode=arch=compute_89,code=sm_89 \

-gencode=arch=compute_89,code=compute_89

Sample flags for generation on

CUDA 12

(PTX ISA version 8.0) for best performance with NVIDIA H100 and H200 (Hopper) GPUs, and no backwards OR FORWARDS compatibility for previous generations:

-arch=sm_90 \

-gencode=arch=compute_90,code=sm_90 \

-gencode=arch=compute_90a,code=sm_90a \

-gencode=arch=compute_90a,code=compute_90a

Note that sm_90a implies that it includes specific architecture-accelerated features that are not supported on other architectures, and can’t be run on later generation devices. They are neither forward nor backward compatible.

Sample flags for generation on

CUDA 12.8

(PTX ISA version 8.7) for best performance with NVIDIA GB100 and GB20x (Blackwell) GPUs like the B40 or RTX 50 series:

-arch=sm_100 \

-gencode=arch=compute_100,code=sm_100 \

-gencode=arch=compute_100,code=compute_100

For RTX 50xx series specifically,

-arch=sm_100 \ 
-gencode=arch=compute_100,code=sm_100 \
-gencode=arch=compute_120,code=sm_120 \
-gencode=arch=compute_120,code=compute_120

To add more compatibility for Blackwell GPUs and some backwards compatibility:

-arch=sm_52 \

-gencode=arch=compute_52,code=sm_52 \

-gencode=arch=compute_60,code=sm_60 \

-gencode=arch=compute_61,code=sm_61 \

-gencode=arch=compute_70,code=sm_70 \

-gencode=arch=compute_75,code=sm_75 \

-gencode=arch=compute_80,code=sm_80 \

-gencode=arch=compute_86,code=sm_86 \

-gencode=arch=compute_87,code=sm_87 \

-gencode=arch=compute_90,code=sm_90 \

-gencode=arch=compute_100,code=sm_100 \

-gencode=arch=compute_100,code=compute_100

For

RTX50xx

, and full backwards compatibility, add

sm_120

and

compute_120

, like this:

-arch=sm_52 \

-gencode=arch=compute_52,code=sm_52 \

-gencode=arch=compute_60,code=sm_60 \

-gencode=arch=compute_61,code=sm_61 \

-gencode=arch=compute_70,code=sm_70 \

-gencode=arch=compute_75,code=sm_75 \

-gencode=arch=compute_80,code=sm_80 \

-gencode=arch=compute_86,code=sm_86 \

-gencode=arch=compute_87,code=sm_87 \

-gencode=arch=compute_90,code=sm_90 \

-gencode=arch=compute_100,code=sm_100 \

-gencode=arch=compute_120,code=sm_120 \

-gencode=arch=compute_120,code=compute_120

Sample flags for generation on CUDA 12.9 for datacenter Blackwell including B300 (Blackwell Ultra):

-arch=sm_100 \

-gencode=arch=compute_100,code=sm_100 \

-gencode=arch=compute_103,code=sm_103 \

-gencode=arch=compute_103,code=compute_103

Sample flags for CUDA 12.9 targeting both datacenter and consumer Blackwell, plus DGX Spark:

-arch=sm_100 \

-gencode=arch=compute_100,code=sm_100 \

-gencode=arch=compute_103,code=sm_103 \

-gencode=arch=compute_120,code=sm_120 \

-gencode=arch=compute_121,code=sm_121 \

-gencode=arch=compute_120,code=compute_120

Sample flags for CUDA 13.0+ with maximum backwards compatibility (note: minimum is now sm_75):

-arch=sm_75 \

-gencode=arch=compute_75,code=sm_75 \

-gencode=arch=compute_80,code=sm_80 \

-gencode=arch=compute_86,code=sm_86 \

-gencode=arch=compute_89,code=sm_89 \

-gencode=arch=compute_90,code=sm_90 \

-gencode=arch=compute_100,code=sm_100 \

-gencode=arch=compute_103,code=sm_103 \

-gencode=arch=compute_110,code=sm_110 \

-gencode=arch=compute_120,code=sm_120 \

-gencode=arch=compute_121,code=sm_121 \

-gencode=arch=compute_120,code=compute_120

Note: sm_101 was renumbered to sm_110 in CUDA 13.0. If compiling with CUDA 12.8/12.9, use sm_101 instead.

Note: sm_87 (Jetson Orin) is not listed above but is still supported in CUDA 13.0 separately.

Using TORCH_CUDA_ARCH_LIST for PyTorch

If you’re using PyTorch you can set the architectures using the

TORCH_CUDA_ARCH_LIST

env variable during installation like this:

$ TORCH_CUDA_ARCH_LIST="7.0 7.5 8.0 8.6" python3 setup.py install

Note that while you can specify every single arch in this variable, each one will prolong the build time as kernels will have to compiled for every architecture.

You can also tell PyTorch to generate PTX code that is forward compatible by newer cards by adding a

+PTX

suffix to the most recent architecture you specify:

$ TORCH_CUDA_ARCH_LIST="7.0 7.5 8.0 8.6+PTX" python3 build_my_extension.py

For Blackwell RTX 50 series and datacenter B200/B300:

$ TORCH_CUDA_ARCH_LIST="8.0 8.6 8.9 9.0 10.0 10.3 12.0 12.1+PTX" python3 setup.py install

Note that PyTorch stable builds may not yet support all Blackwell architectures. Check your PyTorch version’s CUDA support before setting these flags.

Using Cmake for TensorRT

If you’re compiling TensorRT with CMAKE, drop the

sm_

and

compute_

prefixes, refer only to the compute capabilities instead.

Example for Tesla V100 and Volta cards in general:

cmake <...>

-DGPU_ARCHS="70"

Example for NVIDIA RTX 2070 and Tesla T4:

cmake <...> -DGPU_ARCHS="75"

Example for NVIDIA A100:

cmake <...>

-DGPU_ARCHS="80"

Example for NVIDIA RTX 3080 and A100 together:

cmake <...> -DGPU_ARCHS="80 86"

Example for NVIDIA H100:

cmake <...> -DGPU_ARCHS="90"

Example for NVIDIA B300 (Blackwell Ultra):

cmake <…> -DGPU_ARCHS="103"

Example for NVIDIA RTX 5090 (consumer Blackwell):

cmake <…> -DGPU_ARCHS="120"

Example for DGX Spark (GB10):

cmake <…> -DGPU_ARCHS="121"

Example for all Blackwell variants together:

cmake <…> -DGPU_ARCHS="100 103 120 121"

Using Cmake for CUTLASS with Hopper GH100

cmake .. -DCUTLASS_NVCC_ARCHS=90a

What does

"Value 'sm_86' is not defined for option 'gpu-architecture'"

mean?

If you get an error that looks like this:

nvcc fatal : Value 'sm_86' is not defined for option 'gpu-architecture'

You probably have an older version of CUDA and/or the driver installed. Upgrade to a more recent driver, at least

450.36.06

or higher, to support

sm_8x

cards like the A100,

RTX 3080

.

What does “CUDA runtime error: operation not supported” mean?

If you get an

std::runtime_error

that looks like this:

CUDA runtime error: operation not supported

The implication is that your card is not supported with the runtime code that was generated.

Check with

nvidia-smi

to see which card and driver version you have. Then, try to match the gencodes to generate the correct runtime code suitable for your card.
