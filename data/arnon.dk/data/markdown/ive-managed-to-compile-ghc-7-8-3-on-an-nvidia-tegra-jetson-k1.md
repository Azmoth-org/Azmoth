# I’ve managed to compile GHC-7.8.3 on an Nvidia Tegra (Jetson K1) and Adapteva Parallella-16!

- **URL:** https://arnon.dk/ive-managed-to-compile-ghc-7-8-3-on-an-nvidia-tegra-jetson-k1/
- **Author:** Arnon Shimoni
- **Published:** 2014-11-11T08:47:41+00:00
- **Modified:** 2014-11-16T13:27:44+00:00
- **Type:** post
- **Topics:** haskell, IT
- **Tags:** adapteva, arm, armv7, clang, gcc, ghc, ghc-7.8.3, it, jetson, jetson k1, llvm, nvidia, parallella, tegra
- **Reading time:** 1 minute
- **Description:** It took a while, but I’ve finally managed to compile and run GHC-7.8.3 on an Nvidia Jetson K1 board. The Jetson K1 board has a 32-bit Nvidia Tegra processor (essentially a quad-core ARM Cortex A15), and an integrated 192 core Nvidia GPU. Mine came with a standard Ubuntu 14.04 distribution and nothing more really. After […]

It took a while, but I’ve finally managed to compile and run GHC-7.8.3 on an Nvidia Jetson K1 board.

The Jetson K1 board has a 32-bit Nvidia Tegra processor (essentially a quad-core ARM Cortex A15), and an integrated 192 core Nvidia GPU.

Mine came with a standard Ubuntu 14.04 distribution and nothing more really.

After a lot of trial and error, I finally got it up and running without any noticeable issues.

I tested my routine on the Parallella-16 also running Ubuntu 14.04 and it seems to work excellent as well!

Here’s what I did:

Start with a fresh board, with Ubuntu 14.04 LTS

Uncomment universe lines from

/etc/apt/sources

, so that you’ll have access to the newest packages

sudo apt-get update && sudo apt-get upgrade

You will need GHC7.6.3 or earlier to bootstrap the compilation. I also decided to use clang+gold because it is quicker and gcc was a bit finicky for me.

sudo apt-get install ghc automake build-essential cabal-install groff alex happy llvm clang binutils

I installed Alex and Happy in Cabal,

cabal update && cabal install alex happy

I cloned the latest GHC-7.8 to my SD card.

git clone -b ghc-7.8 git://git.haskell.org/ghc.git ghc-7.8

cd ghc-7.8/

sudo ./sync-all get -b ghc-7.8

Copy

mk/build.mk.sample

into

mk/build.mk

. Uncomment the line about quick-llvm compilation

BuildFlavour = quick-llvm

.

Look for the line

SRC_HC_OPTS = -H64m -O0 -fllvm

and replace

-H64m

with

-H32m

perl boot

sudo ./configure --with-clang=/usr/bin/clang --with-ar=/usr/bin/ar

Because there is a linker issue, obtain the following script that will switch between standard

ld

and

gold

:

wget https://gist.githubusercontent.com/bgamari/9399430/raw/build-ghc-arm.sh

We are now ready to start compiling!

chmod ugo+rx build-ghc-arm.sh

sudo /build-ghc-arm.sh -j6

sudo make install

???

Profit!
