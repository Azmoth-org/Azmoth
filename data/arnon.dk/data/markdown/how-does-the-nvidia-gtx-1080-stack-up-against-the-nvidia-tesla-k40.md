# Nvidia GTX 1080 vs Nvidia Tesla K40 – Installing a GTX1080 in a Dell R720

- **URL:** https://arnon.dk/how-does-the-nvidia-gtx-1080-stack-up-against-the-nvidia-tesla-k40/
- **Author:** Arnon Shimoni
- **Published:** 2016-06-05T14:58:57+00:00
- **Modified:** 2020-09-03T15:24:47+00:00
- **Type:** post
- **Topics:** GPUs, IT
- **Tags:** gpu, gtx 1080, gtx 1080 vs tesla k40, k40, k80 vs 1080, nvidia, nvidia gtx 1080, nvidia tesla k80 vs gtx 1080, tesla k40, tesla k40 vs gtx 1080
- **Reading time:** 2 minutes
- **Description:** At SQream Technologies, we use Nvidia graphics cards in order to perform a lot of the heavy database operations. With SQream DB, we usually recommend using a Tesla K40 or K80 card. While a Tesla K40 is designed to operate inside a server enclosure (it has no onboard fan), standard Nvidia cards like the GTX […]

At

SQream Technologies

, we use Nvidia graphics cards in order to perform a lot of the heavy database operations.

With SQream DB, we usually recommend using a Tesla K40 or K80 card. While a Tesla K40 is designed to operate inside a server enclosure (it has no onboard fan), standard Nvidia cards like the GTX series are designed to be run inside a regular chassis, and have an onboard fan to cool things down instead of relying on the server fans.

Sometimes, customers have different demands and don’t want to pay the premium for the Tesla cards that we prefer. We therefore wanted to check if we can offer our solution based on the GTX 1080.

We received a loaner GTX 1080 in early June for our tests. We decided to benchmark the GTX 1080 against our incumbent Tesla K40 (which is very similar to half a K80 in most situations), in a server environment. For that task, we decided to run the TPCH performance suite on SQream DB.

Preparation

We recompiled our database with the CUDA 8 release candidate and inserted the GTX 1080 inside the Dell R720 server enclosure.

Results

Our results show that the GTX 1080, despite being much more powerful, was

only 13% faster than the Tesla K40

at most operations, including the relatively complex TPCH-5 query.

Simpler queries like TPCH-1 did not benefit as much from the GTX 1080, and only showed a 3% performance increase.

The Tesla K40 is much more expensive however, and uses almost twice the amount of power. It averaged around 150 watts during intensive load, compared to around 80 watts with the GTX 1080.

Our main concern was overheating. We were happy to see that the GTX 1080 runs nice and cool, at around 40-50 degrees under intensive load inside a Dell R720 enclosure with fans on maximum output.

Summary

While we were pleased to see that the GTX 1080 was not slower than the K40, but it wasn’t fast enough to justify a move to this card for most users,

with a 3%-10% speed improvement for intense SQL queries

.

We were also very pleasantly surprised to see that the card did not overheat and used significantly less power when compared to the high powered Tesla series.
