
import os
import pexpect
import pytest
import subprocess
import sys

@pytest.mark.parametrize('bootmode', ['UEFI', 'bios'])
@pytest.mark.parametrize('numdisks', [1])
@pytest.mark.parametrize('disktype', ['virtio', 'ide', 'nvme', 'usb'])
@pytest.mark.parametrize('fstype', ['vfat', 'ext4'])
def test_diskless(qemu, alpine_conf_iso, disktype, bootmode, fstype):
    if (disktype == 'ide' or bootmode == 'bios') and (qemu.arch == 'aarch64' or qemu.arch == 'arm'):
        pytest.skip("not supported on this architecture")

    qemu_args = qemu.machine_args + [
            '-nographic',
            '-m', '512M',
            '-smp', '2',
            '-kernel', qemu.boot['kernel'],
            '-initrd', qemu.boot['initrd'],
            '-append', 'quiet usbdelay=2 console='+qemu.console,
            '-cdrom', qemu.boot['iso'],
        ]

    labelopts = ['-L', 'APKOVL']
    if fstype == 'vfat':
        labelopts = ['-n', 'APKOVL']

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
            qemu_args.extend([ '-drive', f'if={disktype},format=raw,file={img}'])
        try:
            cmd = subprocess.run(['mkfs.'+fstype] + labelopts + [img])
        except FileNotFoundError:
            pytest.skip('mkfs.'+fstype+' not found')

        assert cmd.returncode == 0
        # only create label on the first
        labelopts=[]

    if bootmode == 'UEFI':
        qemu_args.extend(['-drive', 'if=pflash,format=raw,readonly=on,file='+qemu.uefi_code])

    alpine_conf_args=[]
    if alpine_conf_iso != None:
        alpine_conf_args = ['-drive', 'media=cdrom,readonly=on,file='+alpine_conf_iso]

    p = pexpect.spawn(qemu.prog, qemu_args + alpine_conf_args)

#    p.logfile = sys.stdout.buffer

    p.expect("login:", timeout=30)
    p.send("root\n")

    p.timeout = 2
    p.expect("localhost:~#")

    if alpine_conf_iso != None:
        p.send("mkdir -p /media/ALPINECONF && mount LABEL=ALPINECONF /media/ALPINECONF && cp -r /media/ALPINECONF/* / && echo OK\n")
        p.expect("OK")
        p.expect("localhost:~#")

    p.send("setup-alpine\n")

    i = p.expect_exact(["Select keyboard layout: [none] ", "Enter system hostname"])
    if i == 0:
        p.send("none\n")

    hostname = "alpine"
    p.send(hostname+"\n")

    p.expect("Which one do you want to initialize\\?.*\\[eth0\\] ")
    p.send("\n")

    p.expect("Ip address for eth0\\?.*\\[.*\\] ")
    p.send("dhcp\n")

    p.expect("Do you want to do any manual network configuration\\? \\(y/n\\) \\[n\\] ")
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

    i = p.expect(["Enter mirror number \\(.*\\) or URL to add \\(.*\\) \\[1\\] ",
                  "Which NTP client to run\\? \\(.*\\) \\[.*\\] "], timeout=30)
    if i==1:
        p.send("\n")
        p.expect("Enter mirror number \\(.*\\) or URL to add \\(.*\\) \\[1\\] ", timeout=30)
    p.send("\n")

    p.expect("Setup a user")
    p.send("no\n")

    p.expect("Which ssh server\\? \\(.*\\) \\[openssh\\] ", timeout=20)
    p.send("none\n")

    p.expect("Which disk\\(s\\) would you like to use\\? \\(.*\\) \\[none\\] ")
    p.send("none\n")

    p.expect("Enter where to store configs \\(.*\\) \\[LABEL=APKOVL\\] ")
    p.send("\n")

    p.expect("Enter apk cache directory \\(.*\\) \\[.*\\] ")
    p.send("\n")

    p.expect(hostname+":~#")
    p.send("grep ^LABEL=APKOVL /etc/fstab\n")
    p.expect("LABEL=APKOVL")

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

