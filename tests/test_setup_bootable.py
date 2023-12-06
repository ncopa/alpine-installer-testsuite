
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
        '-smp', '4',
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
        '-boot', 'd',
        '-cdrom', qemu.boot['iso'],
    ])

#    p.logfile = sys.stdout.buffer

    p.expect("login:", timeout=30)
    p.sendline("root")

    p.timeout = 2
    p.expect("localhost:~#")

    if alpine_conf_iso != None:
        p.sendline(
            "mkdir -p /media/ALPINECONF && mount LABEL=ALPINECONF /media/ALPINECONF && cp -r /media/ALPINECONF/* / && echo OK")
        p.expect("OK")
        p.expect("localhost:~#")

    p.sendline("setup-interfaces -a -r && setup-apkrepos -1")
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
        p.sendline("fdisk "+disk)
        p.expect("Command \\(m for help\\):")
        p.sendline("m")
        p.sendline("n")
        p.expect("Partition type")
        p.sendline("p")
        p.expect("Partition number .*:")
        p.sendline("1")
        p.expect("First sector .*: ")
        p.sendline()
        p.expect("Last sector or .*:")
        p.sendline()
        p.expect("Command \\(m for help\\):")
        p.sendline("a")
        p.expect("Partition number .*:")
        p.sendline("1")
        p.expect("Command \\(m for help\\):")
        p.sendline("w")
    else:
        p.sendline("apk add sfdisk")
        p.expect("localhost:~#", timeout=10)
        p.sendline("echo ',,U,*' | sfdisk --label gpt "+disk)
        p.expect("localhost:~#")

    p.sendline("mkfs."+fstype+" "+partition+" && echo OK")
    p.expect("OK")

    p.sendline("modprobe "+fstype)
    p.expect("localhost:~#")

    p.sendline("setup-bootable /media/cdrom "+partition+" && echo OK")
    p.expect("OK", timeout=10)
    p.sendline("mount -t "+fstype+" "+partition+" /mnt")
    p.sendline(
        f"sed -i -E -e '/^APPEND/s/modules=[^ ]+( [^-]+)(.*)/console={qemu.console} \\2/' /mnt/boot/syslinux/syslinux.cfg")
    p.sendline("cat /mnt/boot/syslinux/syslinux.cfg")
    p.sendline(
        f"sed -i -E -e '/^linux/s/console=[^ ]+//g' -e '/^linux/s/$/ console={qemu.console}/' /mnt/boot/grub/grub.cfg")
    p.sendline("cat /mnt/boot/grub/grub.cfg")
    p.sendline("umount /mnt")
    p.sendline("poweroff")
    p.expect(pexpect.EOF, timeout=20)

    # boot the generated image
    p = pexpect.spawn(qemu.prog, qemu_args + alpine_conf_args)
#    p.logfile = sys.stdout.buffer

    p.expect("login:", timeout=30)
    p.sendline("root")

    p.timeout = 5
    p.expect("localhost:~#")

    if alpine_conf_iso != None:
        p.sendline(
            "mkdir -p /media/ALPINECONF && mount LABEL=ALPINECONF /media/ALPINECONF && cp -r /media/ALPINECONF/* / && echo OK")
        p.expect("OK")
        p.expect("localhost:~#")

    p.sendline("setup-alpine")

    i = p.expect_exact(
        ["Select keyboard layout: [none] ", "Enter system hostname"])
    if i == 0:
        p.sendline("none")

    hostname = "alpine"
    p.sendline(hostname)

    p.expect("Which one do you want to initialize\\?.*\\[eth0\\] ")
    p.sendline()

    i = p.expect(["Do you want to bridge the interface eth0\\?.*\\[.*\\] ",
                  "Ip address for eth0\\?.*\\[.*\\] "])
    if i == 0:
        p.sendline("no")
        p.expect("Ip address for eth0\\?.*\\[.*\\] ", 30)

    p.sendline("dhcp")

    p.expect(
        "Do you want to do any manual network configuration\\? \\(y/n\\) \\[n\\] ", 10)
    p.sendline()

    password = 'testpassword'
    p.expect("New password: ", timeout=20)
    p.waitnoecho()
    p.sendline(password)

    p.expect("Retype password: ")
    p.waitnoecho()
    p.sendline(password)

    p.expect("Which timezone.*\\[UTC\\] ")
    p.sendline()

    p.expect("HTTP/FTP proxy URL\\?.* \\[none\\] ", timeout=10)
    p.sendline()

    while True:
        i = p.expect([r'Which NTP client to run\? \(.*\) \[.*\] ',
                      r'--More--',
                      r'Enter mirror number.*or URL.* \[1\] ',], timeout=30)
        if i == 0:  # ntp
            p.sendline()
        elif i == 1:  # --More --
            p.sendline("q")
        else:  # prompt for mirror
            p.sendline()
            break

    p.expect("Setup a user")
    p.sendline("no")

    p.expect("Which ssh server\\? \\(.*\\) \\[openssh\\] ", timeout=20)
    p.sendline("none")

    i = p.expect(
        ["Allow root ssh login\\? \\(.*\\) \\[.*\\] ", "Available disks are"])
    if i == 0:
        p.sendline()
        p.expect("Available disks are")

    p.expect("Which disk\\(s\\) would you like to use\\? \\(.*\\) \\[none\\] ")
    p.sendline("none")

    p.expect("Enter where to store configs \\(.*\\) \\[.*\\] ")
    p.sendline()

    p.expect("Enter apk cache directory \\(.*\\) \\[.*\\] ")
    p.sendline()

    p.expect(hostname+":~#")
    p.sendline("lbu commit")

    p.expect(hostname+":~#")
    p.sendline("poweroff")
    p.expect(pexpect.EOF, timeout=10)

    p = pexpect.spawn(qemu.prog, qemu_args)

    p.expect("login:", timeout=60)
    p.sendline("root")

    p.expect("Password:", timeout=3)
    p.waitnoecho()
    p.sendline(password)

    p.expect(hostname+":~#", timeout=3)
    p.sendline("poweroff")
    p.expect(pexpect.EOF, timeout=20)

    for img in qemu.images:
        os.unlink(img)
