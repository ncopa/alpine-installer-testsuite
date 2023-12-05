
import os
import pexpect
import pytest
import subprocess
import sys


@pytest.mark.parametrize('bootmode', ['bios', 'UEFI'])
@pytest.mark.parametrize('numdisks', [1])
@pytest.mark.parametrize('disktype', ['virtio', 'ide', 'nvme', 'usb'])
# setup-bootable only support vfat so far
@pytest.mark.parametrize('fstype', ['vfat'])
def test_setup_bootable(qemu, alpine_conf_iso, disktype, bootmode, fstype):
    if qemu.arch == 'arm' or qemu.arch == 'aarch64':
        pytest.skip("ARM is not (yet) supported")

    if bootmode == 'UEFI' and disktype == 'nvme':
        pytest.skip("UEFI does not boot from nvme")

    qemu_args = qemu.machine_args + [
        '-nographic',
        '-m', '512M',
        '-smp', '2',
    ]

    for img in qemu.images:
        driveid = os.path.splitext(os.path.basename(img))[0]
        if disktype == 'nvme':
            qemu_args.extend([
                '-drive', f'if=none,id={driveid},format=raw,file={img}',
                '-device', f'nvme,serial={driveid},drive={driveid}'
            ])
        elif disktype == 'usb':
            qemu_args.extend([
                '-drive', f'if=none,id={driveid},format=raw,file={img}',
                '-device', 'qemu-xhci',
                '-device', f'usb-storage,drive={driveid}',
            ])
        else:
            qemu_args.extend(
                ['-drive', f'if={disktype},format=raw,file={img}'])

    if bootmode == 'UEFI':
        qemu_args.extend(
            ['-drive', 'if=pflash,format=raw,readonly=on,file='+qemu.uefi_code])

    alpine_conf_args = []
    if alpine_conf_iso != None:
        alpine_conf_args = [
            '-drive', 'media=cdrom,readonly=on,file='+alpine_conf_iso]

    p = pexpect.spawn(qemu.prog, qemu_args + alpine_conf_args + [
        '-kernel', qemu.boot['kernel'],
        '-initrd', qemu.boot['initrd'],
        '-append', 'quiet console='+qemu.console,
        '-cdrom', qemu.boot['iso'],
    ])

#    p.logfile = sys.stdout.buffer

    p.expect("login:", timeout=30)
    p.send("root\n")

    p.timeout = 2
    p.expect("localhost:~#")

    if alpine_conf_iso != None:
        p.send("mkdir -p /media/ALPINECONF && mount LABEL=ALPINECONF /media/ALPINECONF && cp -r /media/ALPINECONF/* / && echo OK\n")
        p.expect("OK")
        p.expect("localhost:~#")

    p.send("setup-interfaces -a -r && setup-apkrepos -1\n")
    p.expect("localhost:~#", timeout=10)

    devs = {'virtio': ['/dev/vda', '/dev/vda1'],
            'ide': ['/dev/sda', '/dev/sda1'],
            'nvme': ['/dev/nvme0n1', '/dev/nvme0n1p1'],
            'usb': ['/dev/sda', '/dev/sda1'],
            }

    dev = devs[disktype]
    disk = dev[0]
    partition = dev[1]

    if bootmode == 'bios':
        p.send("fdisk "+disk+"\n")
        p.expect("Command \\(m for help\\):")
        p.send("m\n")
        p.send("n\n")
        p.expect("Partition type")
        p.send("p\n")
        p.expect("Partition number .*:")
        p.send("1\n")
        p.expect("First sector .*: ")
        p.send("\n")
        p.expect("Last sector or .*:")
        p.send("\n")
        p.expect("Command \\(m for help\\):")
        p.send("a\n")
        p.expect("Partition number .*:")
        p.send("1\n")
        p.expect("Command \\(m for help\\):")
        p.send("w\n")
    else:
        p.send("apk add sfdisk\n")
        p.expect("localhost:~#", timeout=10)
        p.send("echo ',,U,*' | sfdisk --label gpt "+disk+"\n")
        p.expect("localhost:~#")

    p.send("mkfs."+fstype+" "+partition+" && echo OK\n")
    p.expect("OK")

    p.send("modprobe "+fstype+"\n")
    p.expect("localhost:~#")

    p.send("setup-bootable /media/cdrom "+partition+" && echo OK\n")
    p.expect("OK", timeout=10)
    p.send("mount -t "+fstype+" "+partition+" /mnt\n")
    p.send(
        f"sed -i -E -e '/^APPEND/s/modules=[^ ]+( [^-]+)(.*)/console={qemu.console} \\2/' /mnt/boot/syslinux/syslinux.cfg\n")
    p.send("cat /mnt/boot/syslinux/syslinux.cfg\n")
    p.send(
        f"sed -i -E -e '/^linux/s/console=[^ ]+//g' -e '/^linux/s/$/ console={qemu.console}/' /mnt/boot/grub/grub.cfg\n")
    p.send("cat /mnt/boot/grub/grub.cfg\n")
    p.send("umount /mnt\n")
    p.send("poweroff\n")
    p.expect(pexpect.EOF, timeout=20)

    # boot the generated image
    p = pexpect.spawn(qemu.prog, qemu_args + alpine_conf_args)
#    p.logfile = sys.stdout.buffer

    p.expect("login:", timeout=30)
    p.send("root\n")

    p.timeout = 5
    p.expect("localhost:~#")

    if alpine_conf_iso != None:
        p.send("mkdir -p /media/ALPINECONF && mount LABEL=ALPINECONF /media/ALPINECONF && cp -r /media/ALPINECONF/* / && echo OK\n")
        p.expect("OK")
        p.expect("localhost:~#")

    p.send("setup-alpine\n")

    i = p.expect_exact(
        ["Select keyboard layout: [none] ", "Enter system hostname"])
    if i == 0:
        p.send("none\n")

    hostname = "alpine"
    p.send(hostname+"\n")

    p.expect("Which one do you want to initialize\\?.*\\[eth0\\] ")
    p.send("\n")

    i = p.expect(["Do you want to bridge the interface eth0\\?.*\\[.*\\] ",
                  "Ip address for eth0\\?.*\\[.*\\] "])
    if i == 0:
        p.send("no\n")
        p.expect("Ip address for eth0\\?.*\\[.*\\] ", 30)

    p.send("dhcp\n")

    p.expect(
        "Do you want to do any manual network configuration\\? \\(y/n\\) \\[n\\] ", 10)
    p.send("\n")

    password = 'testpassword'
    p.expect("New password: ", timeout=20)
    p.send(password+"\n")

    p.expect("Retype password: ")
    p.send(password+"\n")

    p.expect("Which timezone.*\\[UTC\\] ")
    p.send("\n")

    p.expect("HTTP/FTP proxy URL\\?.* \\[none\\] ", timeout=10)
    p.send("\n")

    while True:
        i = p.expect([r'Which NTP client to run\? \(.*\) \[.*\] ',
                      r'--More--',
                      r'Enter mirror number \(.*\) or URL to add \(.*\) \[1\] ',], timeout=30)
        if i == 0:  # ntp
            p.send("\n")
        elif i == 1:  # --More --
            p.send("q\n")
        else:  # prompt for mirror
            p.send("\n")
            break

    p.expect("Setup a user")
    p.send("no\n")

    p.expect("Which ssh server\\? \\(.*\\) \\[openssh\\] ", timeout=20)
    p.send("none\n")

    i = p.expect(
        ["Allow root ssh login\\? \\(.*\\) \\[.*\\] ", "Available disks are"])
    if i == 0:
        p.send("\n")
        p.expect("Available disks are")

    p.expect("Which disk\\(s\\) would you like to use\\? \\(.*\\) \\[none\\] ")
    p.send("none\n")

    p.expect("Enter where to store configs \\(.*\\) \\[.*\\] ")
    p.send("\n")

    p.expect("Enter apk cache directory \\(.*\\) \\[.*\\] ")
    p.send("\n")

    p.expect(hostname+":~#")
    p.send("lbu commit\n")

    p.expect(hostname+":~#")
    p.send("poweroff\n")
    p.expect(pexpect.EOF, timeout=10)

    p = pexpect.spawn(qemu.prog, qemu_args)

    p.expect("login:", timeout=60)
    p.send("root\n")

    p.expect("Password:", timeout=3)
    p.send(password+"\n")

    p.expect(hostname+":~#", timeout=3)
    p.send("poweroff\n")
    p.expect(pexpect.EOF, timeout=20)

    for img in qemu.images:
        os.unlink(img)
