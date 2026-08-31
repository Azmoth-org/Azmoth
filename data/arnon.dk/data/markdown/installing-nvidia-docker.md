# Quickstart – Installing nvidia docker in one guide

- **URL:** https://arnon.dk/installing-nvidia-docker/
- **Author:** Arnon Shimoni
- **Published:** 2019-04-02T08:36:39+00:00
- **Modified:** 2020-09-03T15:24:46+00:00
- **Type:** post
- **Topics:** Uncategorized
- **Reading time:** 3 minutes
- **Description:** I have been frustrated when trying to install nvidia-docker, because the guides are split over several documents. NVIDIA’s own documents tell you to go install Docker first, but don’t tell you how. For Ubuntu 16 and 18, here are all the steps you need, one by one: Install Docker CE sudo apt update sudo apt […]

I have been frustrated when trying to install nvidia-docker, because the guides are split over several documents. NVIDIA’s own documents tell you to go install Docker first, but don’t tell you how.

For Ubuntu 16 and 18, here are all the steps you need, one by one:

Install Docker CE

sudo apt update

sudo apt install apt-transport-https ca-certificates curl software-properties-common

curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -

sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu bionic stable"

sudo apt update

apt-cache policy docker-ce

sudo apt install docker-ce

Verify docker is running:

sudo systemctl status docker

Optional – ensure Docker can run without sudo

sudo usermod -aG docker ${USER}

su - ${USER}

Enter your password and now we’ll verify that the user has been included in the docker group:

id -nG

You should see something like:

username adm cdrom sudo dip plugdev lpadmin sambashare

docker

exit

Install NVIDIA Docker

curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey |   sudo apt-key add -

distribution=$(. /etc/os-release;echo $ID$VERSION_ID)

curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list |   sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update

sudo apt-get install nvidia-docker2

sudo pkill -SIGHUP dockerd

Verify that you’ve installed it correctly with nvidia-smi

sudo docker run --runtime=nvidia --rm nvidia/cuda:10.1-base nvidia-smi

You should see something like:

Unable to find image 'nvidia/cuda:10.1-base' locally
 10.1-base: Pulling from nvidia/cuda
 898c46f3b1a1: Pull complete
 63366dfa0a50: Pull complete
 041d4cd74a92: Pull complete
 6e1bee0f8701: Pull complete
 c15c863cc43e: Pull complete
 4a9de8159c48: Pull complete
 0b62278979d8: Pull complete
 Digest: sha256:686a849123ab369523400e699bfe5d653a063c8ef983a76e24ab18a03be27f26
 Status: Downloaded newer image for nvidia/cuda:10.1-base

Followed by a successful run of

nvidia-smi

:

Tue Apr  2 08:23:30 2019
 +-----------------------------------------------------------------------------+
 | NVIDIA-SMI 418.40.04    Driver Version: 418.40.04    CUDA Version: 10.1     |
 |-------------------------------+----------------------+----------------------+
 | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
 | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
 |===============================+======================+======================|
 |   0  Tesla V100-PCIE…  On   | 00000000:25:00.0 Off |                    0 |
 | N/A   38C    P0    27W / 250W |      0MiB / 32480MiB |      0%      Default |
 +-------------------------------+----------------------+----------------------+
 |   1  Tesla V100-PCIE…  On   | 00000000:5B:00.0 Off |                    0 |
 | N/A   38C    P0    26W / 250W |      0MiB / 32480MiB |      0%      Default |
 +-------------------------------+----------------------+----------------------+
 |   2  Tesla V100-PCIE…  On   | 00000000:9B:00.0 Off |                    0 |
 | N/A   37C    P0    27W / 250W |      0MiB / 32480MiB |      0%      Default |
 +-------------------------------+----------------------+----------------------+
 |   3  Tesla V100-PCIE…  On   | 00000000:C8:00.0 Off |                    0 |
 | N/A   35C    P0    26W / 250W |      0MiB / 16130MiB |      0%      Default |
 +-------------------------------+----------------------+----------------------+
 +-----------------------------------------------------------------------------+
 | Processes:                                                       GPU Memory |
 |  GPU       PID   Type   Process name                             Usage      |
 |=============================================================================|
 |  No running processes found                                                 |
 +-----------------------------------------------------------------------------+

That’s it. Easy

Troubleshooting

If you get an error like this:

$ sudo apt-get install -y nvidia-docker2
Reading package lists... Done
Building dependency tree       
Reading state information... Done
Some packages could not be installed. This may mean that you have
requested an impossible situation or if you are using the unstable
distribution that some required packages have not yet been created
or been moved out of Incoming.
The following information may help to resolve the situation:

The following packages have unmet dependencies:
 nvidia-docker2 : Depends: docker-ce (= 5:18.09.5~3-0~ubuntu-xenial) but 18.06.0~ce~3-0~ubuntu is to be installed or
                           docker-ee (= 5:18.09.5~3-0~ubuntu-xenial) but it is not installable
E: Unable to correct problems, you have held broken packages.

You may need to pin some versions. Remove the previously installed docker (

$ sudo apt remove docker-ce

), and reinstall by forcing versions

5:18.09.5~3-0

like so:

$ sudo apt-get install docker-ce=5:18.09.5~3-0~ubuntu-xenial docker-ce-cli=5:18.09.5~3-0~ubuntu-xenial containerd.io

$ sudo apt-get install -y nvidia-docker2=2.0.3+docker18.09.5-3 nvidia-container-runtime=2.0.0+docker18.09.5-3
