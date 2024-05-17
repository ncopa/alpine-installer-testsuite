
import os
import pexpect
import pytest
import sys


@pytest.mark.parametrize('rootfs', ['ext4', 'xfs', 'btrfs'])
@pytest.mark.parametrize('bootmode', ['UEFI', 'bios'])
@pytest.mark.parametrize('diskmode', ['sys', 'lvmsys', 'cryptsys'])
@pytest.mark.parametrize('numdisks', [1, 2])
@pytest.mark.parametrize('disktype', ['virtio', 'ide', 'nvme'])
@pytest.mark.parametrize('disklabel', ['', 'gpt'])
def test_sys_install(qemu, alpine_conf_iso, rootfs, disktype, diskmode, bootmode, disklabel):
    # fails to boot with UEFI for some reason
    if disktype == 'nvme' and bootmode == 'UEFI':
        pytest.skip()

    if bootmode == 'bios' and (qemu.arch == 'aarch64' or qemu.arch == 'arm'):
        pytest.skip("Only UEFI is supported on ARM")

    if disktype == 'ide' and (qemu.arch == 'aarch64' or qemu.arch == 'arm'):
        pytest.skip("IDE is not supported on ARM")

    if bootmode == 'UEFI' and disklabel == 'gpt':
        pytest.skip()

    qemu_args = qemu.machine_args + [
        '-nographic',
        '-m', '512M',
        '-smp', '4',
    ]

    for img in qemu.images:
        driveid = os.path.splitext(os.path.basename(img))[0]
        if disktype == 'nvme':
            qemu_args.extend(['-drive', f'if=none,id={driveid},format=raw,file={img}',
                              '-device', f'nvme,serial={driveid},drive={driveid}',
                              ])
        else:
            qemu_args.extend(
                ['-drive', f'if={disktype},format=raw,file={img}'])

    if bootmode == 'UEFI':
        qemu_args.extend(
            ['-drive', 'if=pflash,format=raw,readonly=on,file='+qemu.uefi_code])

    alpine_conf_args = []
    if alpine_conf_iso is not None:
        alpine_conf_args = [
            '-drive', 'media=cdrom,readonly=on,file='+alpine_conf_iso]

    p = pexpect.spawn(qemu.prog, qemu_args + [
        '-boot', 'd',
        '-cdrom', qemu.boot['iso']] + alpine_conf_args)

#    p.logfile = sys.stdout.buffer
    p.delaybeforesend = None

    p.expect_exact(["boot:", "Press enter to boot the selected OS"])
    p.sendline()

    p.expect("login:", timeout=30)
    p.sendline("root")

    p.timeout = 2
    p.expect("localhost:~#")

    if alpine_conf_iso is not None:
        p.sendline(
            "mkdir -p /media/ALPINECONF && mount LABEL=ALPINECONF /media/ALPINECONF && cp -r /media/ALPINECONF/* / && echo OK")
        p.expect("OK")
        p.expect("localhost:~#")

    p.sendline("export KERNELOPTS='quiet console="+qemu.console+"'")
    p.sendline("export ROOTFS="+rootfs)
    if disklabel != "":
        p.sendline("export DISKLABEL="+disklabel)

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
                      r'Enter mirror number.*or URL.* \[1\] ',],
                     timeout=30)
        if i == 0:  # ntp
            p.sendline()
        elif i == 1:  # --More --
            p.sendline("q")
        else:  # prompt for mirror
            p.sendline()
            break

    p.expect("Setup a user")
    p.sendline("juser")
    p.expect("Full name for user juser")
    p.sendline()
    p.expect("New password")
    p.waitnoecho()
    p.sendline(password)
    p.expect("Retype password")
    p.waitnoecho()
    p.sendline(password)
    p.expect("Enter ssh key or URL for juser")
    p.sendline("none")

    p.expect("Which ssh server\\? \\(.*\\) \\[openssh\\] ", timeout=20)
    p.sendline("none")

    p.expect("Available disks are")
    disks = ['sda', 'sdb', 'vda', 'vdb', 'nvme0n1', 'nvme1n1']
    i = p.expect(disks, timeout=10)

    p.expect("Which disk\\(s\\) would you like to use\\? \\(.*\\) \\[none\\] ")
    if len(qemu.images) == 2:
        d = {'ide': "sda sdb", 'virtio': "vda vdb", 'nvme': "nvme0n1 nvme1n1"}
        p.sendline(d[disktype])
    else:
        p.sendline(disks[i])

    p.expect("How would you like to use (it|them)\\? \\(.*\\) \\[.*\\] ")
    p.sendline(diskmode)
    if diskmode == "crypt":
        p.expect("How would you like to use (it|them)\\? \\(.*\\) \\[.*\\] ")
        p.sendline("sys")

    p.expect(
        "WARNING: Erase the above disk\\(s\\) and continue\\? \\(y/n\\) \\[n\\] ", timeout=10)
    p.sendline("y")

    if diskmode == "crypt" or diskmode == "cryptsys":
        p.expect("Enter passphrase for .*:", timeout=20)
        p.waitnoecho()
        p.sendline(password)
        p.expect("Verify passphrase:")
        p.waitnoecho()
        p.sendline("WRONGPASSWORD")
        p.expect("Enter passphrase for .*:", timeout=5)
        p.waitnoecho()
        p.sendline(password)
        p.expect("Verify passphrase:", timeout=5)
        p.waitnoecho()
        p.sendline(password)
        p.expect_exact(
            "Enter password again to unlock disk for installation.",
            timeout=60)
        p.expect("Enter passphrase for .*:")
        p.waitnoecho()
        p.sendline(password)

    p.expect(hostname+":~#", timeout=60)
    p.sendline("cat /proc/mdstat")
    p.expect(hostname+":~#")
    p.sendline("poweroff")
    p.expect(pexpect.EOF, timeout=60)

    p = pexpect.spawn(qemu.prog, qemu_args)
    p.delaybeforesend = None
    p.logfile = sys.stdout.buffer

    if diskmode == "crypt" or diskmode == "cryptsys":
        p.expect("Enter passphrase for .*:")
        p.waitnoecho()
        p.sendline(password)

    i = p.expect(["login:",
                  "Start PXE",
                  "No key available with this passphrase."],
                 timeout=60)

    if i == 1:
        pytest.fail("Failed to boot from disk")

    if i == 2:
        pytest.fail("Failed to open encrypted disk")

    p.sendline("juser")

    p.expect("Password:", timeout=3)
    p.waitnoecho()
    p.sendline(password)

    p.expect(hostname+":~\\$", timeout=3)
    # disable echo so we dont get the match the command line we send
    p.sendline("stty -echo")

    p.expect(hostname+":~\\$", timeout=3)
    p.sendline('awk \'$2 == "/" {print $3}\' /proc/mounts ')
    p.expect_exact(rootfs)

    p.expect(hostname+":~\\$", timeout=3)
    p.sendline("apk info | grep linux-firmware")
    p.expect_exact("linux-firmware-none")

    p.expect(hostname+":~\\$", timeout=3)
    p.sendline("pwd")
    p.expect_exact("/home/juser")

    # verify that /boot partition is at least 90MB
    p.expect(hostname+":~\\$", timeout=3)
    p.sendline("df -P -k /boot")
    p.expect(hostname+":~\\$", timeout=3)
    p.sendline("""
               out=$(df -P -k /boot | awk '$6 == "/boot" || $6 == "/" {print $2}');
               [ ${out:-0} -ge 90000 ] && echo OK || { echo FAIL:${out:-0}; }
               """)
    i = p.expect([r'OK', r'FAIL:\d+[^\d]'])
    if i != 0:
        pytest.fail("/boot is less than 90000 kb")

    p.expect(hostname+":~\\$", timeout=3)
    p.sendline("doas poweroff")
    p.expect("doas.*password:")
    p.waitnoecho()
    p.sendline(password)

    p.expect(pexpect.EOF, timeout=20)

    for img in qemu.images:
        os.unlink(img)
