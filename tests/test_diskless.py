import os
import pexpect
import pytest
import subprocess


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
        '-smp', '4',
        '-boot', 'd',
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
            qemu_args.extend(
                ['-drive', f'if={disktype},format=raw,file={img}'])
        try:
            cmd = subprocess.run(['mkfs.'+fstype] + labelopts + [img])
        except FileNotFoundError:
            pytest.skip('mkfs.'+fstype+' not found')

        assert cmd.returncode == 0
        # only create label on the first
        labelopts = []

    if bootmode == 'UEFI':
        qemu_args.extend(
            ['-drive', 'if=pflash,format=raw,readonly=on,file='+qemu.uefi_code])

    alpine_conf_args = []
    if alpine_conf_iso != None:
        alpine_conf_args = [
            '-drive', 'media=cdrom,readonly=on,file='+alpine_conf_iso]

    p = pexpect.spawn(qemu.prog, qemu_args + alpine_conf_args)

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

    p.sendline("setup-alpine")

    i = p.expect_exact(
        ["Select keyboard layout: [none] ", "Enter system hostname"])
    if i == 0:
        p.sendline("none")

    hostname = "alpine"
    p.sendline(hostname)

    p.expect("Which one do you want to initialize\\?.*\\[eth0\\] ")
    p.sendline()

    p.expect("Ip address for eth0\\?.*\\[.*\\] ")
    p.sendline("dhcp")

    p.expect(
        "Do you want to do any manual network configuration\\? \\(y/n\\) \\[n\\] ")
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

    p.expect("Which disk\\(s\\) would you like to use\\? \\(.*\\) \\[none\\] ")
    p.sendline("none")

    p.expect("Enter where to store configs \\(.*\\) \\[LABEL=APKOVL\\] ")
    p.sendline()

    p.expect("Enter apk cache directory \\(.*\\) \\[.*\\] ")
    p.sendline()

    p.expect(hostname+":~#")
    p.sendline("grep ^LABEL=APKOVL.*ro /etc/fstab")
    p.expect("LABEL=APKOVL")

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
