# Printing to a POS-5890K thermal printer from a Raspberry Pi

- **URL:** https://arnon.dk/printing-to-a-pos-5890k-thermal-printer-from-a-raspberry-pi/
- **Author:** Arnon Shimoni
- **Published:** 2022-03-31T08:22:48+00:00
- **Modified:** 2022-03-31T17:27:34+00:00
- **Type:** post
- **Topics:** Uncategorized
- **Reading time:** 3 minutes
- **Description:** For a small project, I wanted to print some graphic receipts from a Raspberry Pi. I bought the cheapest one I could find on Amazon, the POS-5890K. (I paid €43 on Amazon.de). It’s not a very high quality device, but the price was hard to argue with. However, printing to it was a bit more […]

For a small project, I wanted to print some graphic receipts from a Raspberry Pi.

I bought the

cheapest one I could find on Amazon, the POS-5890K

. (I paid

€43 on Amazon.de

). It’s not a very high quality device, but the price was hard to argue with.

At just €43, the POS-5890k is very affordable, but it is also very cheaply made

However, printing to it was a bit more complicated than I thought. For example, I couldn’t figure out how to set it up properly on a Mac to test print.

Windows drivers are readily available, but MacOS drivers were nowhere to be found. So I went directly to the Raspberry Pi.

1. Install Python and python-escpos

Installing

escpos

under Python is super-easy:

$ pip3 install escpos

But you’re not ready yet. You have to set some permissions

2. Setting up the correct permissions with udev

If you connect the printer over USB, you’ll need to give non-superuser access to the USB port.

However, you’ll need to find the printer first.

Use

`lsusb -vvv

to find it, and make note of the idVendor and idProduct:

pi@arnon-receipt-printer:~ $ lsusb -vvv 
[...]

Bus 001 Device 004: ID 0416:5011 Winbond Electronics Corp. Virtual Com Port
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0 
  bDeviceSubClass         0 
  bDeviceProtocol         0 
  bMaxPacketSize0        64

idVendor           0x0416 Winbond Electronics Corp.
  idProduct          0x5011 Virtual Com Port

bcdDevice            2.00

iManufacturer           1 STMicroelectronics
  iProduct                2 POS58 Printer USB       
  iSerial                 3 Printer

bNumConfigurations      1
  Configuration Descriptor:
    bLength                 9
    bDescriptorType         2
    wTotalLength       0x0020
    bNumInterfaces          1
    bConfigurationValue     1
    iConfiguration          5 (error)
    bmAttributes         0xc0
      Self Powered
    MaxPower              100mA
    Interface Descriptor:
      bLength                 9
      bDescriptorType         4
      bInterfaceNumber        0
      bAlternateSetting       0
      bNumEndpoints           2
      bInterfaceClass         7 Printer
      bInterfaceSubClass      1 Printer
      bInterfaceProtocol      2 Bidirectional
      iInterface              4 (error)
      Endpoint Descriptor:
        bLength                 7
        bDescriptorType         5
        bEndpointAddress     0x81  EP 1 IN
        bmAttributes            2
          Transfer Type            Bulk
          Synch Type               None
          Usage Type               Data
        wMaxPacketSize     0x0040  1x 64 bytes
        bInterval               0
      Endpoint Descriptor:
        bLength                 7
        bDescriptorType         5
        bEndpointAddress     0x03  EP 3 OUT
        bmAttributes            2
          Transfer Type            Bulk
          Synch Type               None
          Usage Type               Data
        wMaxPacketSize     0x0040  1x 64 bytes
        bInterval               0
[...]

With the vendor (

0416

) and product code (

5011

) noted down, we will create a new rule to allow access to it.

Create a new file in

/etc/udev/rules.d/

, called

99-usb.rules

:

SUBSYSTEM=="usb", ATTR{idVendor}=="

0416

", ATTR{idProduct}=="

5011

", MODE="666"

Restart udev, log back in, or reboot the Raspberry Pi to get all changes active.

3. A minimal example

If you follow the instructions on

escpos’ own documentation

, you may get this error

ValueError: Invalid endpoint address 0x1

. If that’s the case, please see the example below, which sets the

in_ep

and

out_ep

explicitly.

So here’s a sample piece of code that should work:

#!/usr/bin/env python3

from escpos.printer import Usb

# 0x416 and 0x5011 are the details we extracted from lsusb
# 0x81 and 0x03 are the bEndpointAddress for input and output

p = Usb(0x416, 0x5011,

in_ep=0x81, out_ep=0x03

, profile="POS-5890")

p.text("Hello world!\n")
p.text("This print should work!\n")
p.text("---------------\n\n\n")

4. This printer doesn’t support barcodes

Unfortunately this printer doesn’t support barcodes. Nothing I tried works. Luckily you can create barcodes or QR codes in Python!

(You should already have

qrcode

installed, if you installed

escpos

):

#!/usr/bin/env python3

from escpos.printer import Usb
import qrcode

# 0x416 and 0x5011 are the details we extracted from lsusb
# 0x81 and 0x03 are the bEndpointAddress for input and output

p = Usb(0x416, 0x5011,

in_ep=0x81, out_ep=0x03

, profile="POS-5890")

# Create a QR code
qr = qrcode.make('https://arnon.dk')
qr.save('qrcode.png')

# Print the image
p.image('qrcode.png')

A successful print!
