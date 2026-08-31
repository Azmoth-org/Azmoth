# X crashes after installing Nvidia driver on CentOS or RHEL

- **URL:** https://arnon.dk/x-crashes-after-installing-nvidia-driver-on-centos-or-rhel/
- **Author:** Arnon Shimoni
- **Published:** 2016-02-11T10:05:51+00:00
- **Modified:** 2020-09-03T15:24:47+00:00
- **Type:** post
- **Topics:** IT
- **Tags:** centos, crashes, cuda, driver, linux, nvidia, x
- **Reading time:** 1 minute
- **Description:** Recently I’ve been having trouble with the Nvidia driver on CentOS 6. Opening any kind of app that uses the GPU like Google Chrome, Firefox or even Nvidia’s own nvidia-settings causes X to crash and restart. Luckily, I’ve found the solution, and it has to do with libglx.so. Navigate to < pre>/usr/lib64/xorg/modules/extensions/ < pre> and […]

Recently I’ve been having trouble with the Nvidia driver on CentOS 6.

Opening any kind of app that uses the GPU like Google Chrome, Firefox or even Nvidia’s own nvidia-settings causes X to crash and restart.

Luckily, I’ve found the solution, and it has to do with libglx.so.

Navigate to

<

pre>/usr/lib64/xorg/modules/extensions/

<

pre> and have a look at the contents with

ls -al

.

You’ll likely see something like this:

u@Host151 /usr/lib64/xorg/modules/extensions $ ls -al
[...]
-rwxr-xr-x  1 root root   148120 Jan 24  2013 libextmod.so
-rwxr-xr-x  1 root root   467513 Feb 10 12:55 libglx.so
-rwxr-xr-x  1 root root 12258728 Feb 10 11:33 libglx.so.346.46
-rwxr-xr-x  1 root root    31248 Jan 24  2013 librecord.so

What you’ll now want to do is remove the smaller of the libglx.so, and create a symbolic link so that the operating system will use the correct version.

In my case, the Nvidia driver is 346.46 so the filename has that extension.

Run:

$ sudo mv libglx.so libglx.so.old
$ sudo ln -s libglx.so.346.46 libglx.so

Now, reload X and enjoy using all your apps as usual!
