# Backing up and restoring a Jetson TK1 – or how our first Jetson TK1 just died….

- **URL:** https://arnon.dk/restoring-a-jetson-tk1-or-how-our-first-jetson-tk1-just-died/
- **Author:** Arnon Shimoni
- **Published:** 2015-04-16T16:30:50+00:00
- **Modified:** 2017-05-16T12:54:32+00:00
- **Type:** post
- **Topics:** GPUs, IT
- **Tags:** arm, centos, jetson, jetson k1, nvidia, ubuntu
- **Reading time:** 2 minutes
- **Description:** Unfortunately, our first Jetson TK1 board just died. Overnight, the board shut down at some point and in the morning it wouldn’t boot up. No SSH access, no ping and no output over HDMI. While a lot of the data was saved on an external hard-drive, some data was saved on the on-board eMMC, due to […]

Unfortunately, our first

Jetson TK1

board just died. Overnight, the board shut down at some point and in the morning it wouldn’t boot up. No SSH access, no ping and no output over HDMI.

While a lot of the data was saved on an external hard-drive, some data was saved on the on-board eMMC, due to the speed benefits.

I decided to attempt to restore the device from my CentOS host. This ultimately failed, and I had to reflash the filesystem from the old device to a new device.

So how do you reflash the filesystem from one Jetson TK1 to another?

With the old device

First, I obtained the latest flashing utilities and file system from Nvidia

mkdir tk1
cd tk1
wget https://developer.nvidia.com/sites/default/files/akamai/mobile/files/L4T/Tegra124_Linux_R21.3.0_armhf.tbz2
wget https://developer.nvidia.com/sites/default/files/akamai/mobile/files/L4T/Tegra_Linux_Sample-Root-Filesystem_R21.3.0_armhf.tbz2

I extracted the tars

sudo tar xpf Tegra124_Linux_R21.3.0_armhf.tbz2
cd Linux_for_Tegra/rootfs
sudo tar xpf ../../Tegra_Linux_Sample-Root-Filesystem_R21.3.0_armhf.tbz2

Now, I wanted to obtain the old system.img.

I connected the device with the micro USB cable, and hit the Recovery + Reset buttons.

Ensure the device is connected

lsusb | grep -i nvidia

You should see something like

Bus 002 Device 004: ID 0955:7140 NVidia Corp.

Now, let’s obtain the partition.

cd ../bootloader
./nvflash --getpartitiontable table --bl ardbeg/fastboot.bin --go

This generates a file called

table

that contains the list of partitions on the device.

Look for the partition id for the partition named

APP

In my case, it was

id=12

I ran this command to get the partition

sudo ./nvflash --read 12 system.img --bl ardbeg/fastboot.bin --go

Swap out 12 for your partition number if it is different.

Downloading the image will take quite some time, depending on the size. Mine was 14580MiB.

Unfortunately, all attempts at factory restoring the old Jetson TK1 failed.

So, I opened up a brand new board and put it in recovery mode too.

I repeated the lsusb command to see that it is indeed connected, and then ran

cd tk1/Linux_for_Tegra/
sudo ./flash.sh -r -S 14580MiB jetson-tk1 mmcblk0p1

What this does is it reflashes the device with the system.img that we downloaded earlier from the previous device.

The

-r

flag tells the flashing utility not to regenerate the entire filesystem.

After the process finished, I reset the device as instructed and it was as if nothing had changed. Our new Jetson was running smoothly, just like the old one had prior to it croaking out on us.
