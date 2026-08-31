# Using Tesla K80 cards, or AWS P2 instances? The end is near

- **URL:** https://arnon.dk/using-tesla-k80-cards-or-aws-p2-instances-the-end-is-near/
- **Author:** Arnon Shimoni
- **Published:** 2020-06-18T18:24:24+00:00
- **Modified:** 2021-03-04T11:06:52+00:00
- **Type:** post
- **Topics:** Uncategorized
- **Reading time:** 2 minutes
- **Description:** A bit under the radar, NVIDIA’s CUDA 11 has dropped support for cards using sm_30 and sm_32. Furthermore, cards using sm_35, sm_37 and sm_50 have been deprecated, and their support will be removed in future versions of CUDA. These cards include the NVIDIA Tesla K40, Tesla K80, and Tesla M60 cards. Several of the companies […]

A bit under the radar, NVIDIA’s CUDA 11 has dropped support for cards using

sm_30

and

sm_32

.

Furthermore, cards using

sm_35

,

sm_37

and

sm_50

have been deprecated, and their support will be removed in future versions of CUDA.

These cards include the NVIDIA Tesla K40, Tesla K80, and Tesla M60 cards.

Deprecated features, captured from the NVIDIA

CUDA 11 release notes

.

Several of the companies I work with still rely on the K80 cards for most of their “heavy lifting”. The K80 is the top price-performance on Amazon AWS since it’s introduction inside

p2.xlarge

,

p2.8xlarge

and

p2.16xlarge

EC2 instances.

If you rely on the AWS P2 instances, or you have Tesla K and M series cards in your servers, you should consider upgrading very soon.

There are good alternatives…

With the introduction of Tesla A100 and the V100

S

in 2020, the original V100 cards have seen some minor price reductions.

If you’re not ready to jump the shark and buy rather pricey Tesla A100s,

the standard V100

offers the best price-performance and “future-proofness” among the NVIDIA Tesla card range.

If you need the extra RAM, you can also spring

for the 32GB V100, but it is a lot more expensive

.

The

16GB NVIDIA Tesla V100

is my recommendation for good price-performance and decent future-proofing.
