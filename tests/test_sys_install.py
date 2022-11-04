
import os
import pexpect
import pytest
import sys

@pytest.mark.parametrize('rootfs', ['ext4', 'xfs', 'btrfs'])
@pytest.mark.parametrize('bootmode', ['UEFI', 'bios'])
@pytest.mark.parametrize('diskmode', ['sys', 'lvmsys', 'cryptsys'])
@pytest.mark.parametrize('numdisks', [1, 2])
@pytest.mark.parametrize('disktype', ['virtio', 'ide', 'nvme'])
def test_sys_install(qemu, alpine_conf_iso, rootfs, disktype, diskmode, bootmode):
    # fails to boot with UEFI for some reason
    if disktype == 'nvme' and bootmode == 'UEFI':
        pytest.skip()

    if bootmode == 'bios' and (qemu.arch == 'aarch64' or qemu.arch == 'arm'):
        pytest.skip("Only UEFI is supported on ARM")

    if disktype == 'ide' and (qemu.arch == 'aarch64' or qemu.arch == 'arm'):
        pytest.skip("IDE is not supported on ARM")

    qemu_args = qemu.machine_args + [
            '-nographic',
            '-m', '512M',
            '-smp', '2',
        ]

    for img in qemu.images:
        driveid = os.path.splitext(os.path.basename(img))[0]
        if disktype == 'nvme':
            qemu_args.extend([ '-drive', f'if=none,id={driveid},format=raw,file={img}',
                        '-device', f'nvme,serial={driveid},drive={driveid}',
                        ])
        else:
            qemu_args.extend([ '-drive', f'if={disktype},format=raw,file={img}'])

    if bootmode == 'UEFI':
        qemu_args.extend(['-drive', 'if=pflash,format=raw,readonly=on,file='+qemu.uefi_code])

    alpine_conf_args=[]
    if alpine_conf_iso != None:
        alpine_conf_args = ['-drive', 'media=cdrom,readonly=on,file='+alpine_conf_iso]

    p = pexpect.spawn(qemu.prog, qemu_args + [
        '-kernel', qemu.boot['kernel'],
        '-initrd', qemu.boot['initrd'],
        '-append', 'quiet console='+qemu.console,
        '-cdrom', qemu.boot['iso']] + alpine_conf_args)

#    p.logfile = sys.stdout.buffer

    p.expect("login:", timeout=30)
    p.send("root\n")

    p.timeout = 2
    p.expect("localhost:~#")

    if alpine_conf_iso != None:
        p.send("mkdir -p /media/ALPINECONF && mount LABEL=ALPINECONF /media/ALPINECONF && cp -r /media/ALPINECONF/* / && echo OK\n")
        p.expect("OK")
        p.expect("localhost:~#")

    p.send("export KERNELOPTS='quiet console="+qemu.console+"'\n")
    p.send("export ROOTFS="+rootfs+"\n")

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
    p.send("juser\n")
    p.expect("Full name for user juser")
    p.send("\n")
    p.expect("New password")
    p.send(password+"\n")
    p.expect("Retype password")
    p.send(password+"\n")
    p.expect("Enter ssh key or URL for juser")
    p.send("none\n")

    p.expect("Which ssh server\\? \\(.*\\) \\[openssh\\] ", timeout=20)
    p.send("none\n")

    p.expect("Available disks are")
    disks = ['sda', 'sdb','vda','vdb', 'nvme0n1', 'nvme1n1']
    i = p.expect(disks, timeout=10)

    p.expect("Which disk\\(s\\) would you like to use\\? \\(.*\\) \\[none\\] ")
    if len(qemu.images) == 2:
        d = {'ide': "sda sdb", 'virtio': "vda vdb", 'nvme': "nvme0n1 nvme1n1" }
        p.send(d[disktype]+"\n")
    else:
        p.send(disks[i] + "\n")

    p.expect("How would you like to use (it|them)\\? \\(.*\\) \\[.*\\] ")
    p.send(diskmode+"\n")
    if diskmode == "crypt":
        p.expect("How would you like to use (it|them)\\? \\(.*\\) \\[.*\\] ")
        p.send("sys\n")


    p.expect("WARNING: Erase the above disk\\(s\\) and continue\\? \\(y/n\\) \\[n\\] ", timeout=10)
    p.send("y\n")

    if diskmode == "crypt" or diskmode == "cryptsys":
        p.expect("Enter passphrase for .*:", timeout=10)
        p.send(password+"\n")
        p.expect("Verify passphrase:")
        p.send("WRONGPASSWORD\n")
        p.expect("Enter passphrase for .*:", timeout=10)
        p.send(password+"\n")
        p.expect("Verify passphrase:")
        p.send(password+"\n")
        p.expect("Enter passphrase for .*:", timeout=30)
        p.send(password+"\n")

    p.expect(hostname+":~#", timeout=60)
    p.send("cat /proc/mdstat\n")
    p.expect(hostname+":~#")
    p.send("poweroff\n")
    p.expect(pexpect.EOF, timeout=60)

    p = pexpect.spawn(qemu.prog, qemu_args)

    p.logfile = sys.stdout.buffer
    if diskmode == "crypt" or diskmode == "cryptsys":
        p.expect("Enter passphrase for .*:")
        p.send(password+"\n")

    p.expect("login:", timeout=60)
    p.send("juser\n")

    p.expect("Password:", timeout=3)
    p.send(password+"\n")

    p.expect(hostname+":~\\$", timeout=3)
    # disable echo so we dont get the match the command line we send
    p.sendline("stty -echo")

    p.expect(hostname+":~\\$", timeout=3)
    p.send('awk \'$2 == "/" {print $3}\' /proc/mounts '+"\n")
    p.expect_exact(rootfs)

    p.expect(hostname+":~\\$", timeout=3)
    p.send("apk info | grep linux-firmware\n")
    p.expect_exact("linux-firmware-none")

    p.expect(hostname+":~\\$", timeout=3)
    p.send("pwd\n")
    p.expect_exact("/home/juser")

    # verify that /boot partition is at least 90MB
    p.expect(hostname+":~\\$", timeout=3)
    p.sendline("df -k /boot")
    p.expect(hostname+":~\\$", timeout=3)
    p.sendline("""
               out=$(df -k /boot | awk '$6 == "/boot" || $6 == "/" {print $2}');
               [ ${out:-0} -ge 90000 ] && echo OK || { echo FAIL:${out:-0}; }
               """)
    i = p.expect([r'OK', r'FAIL:\d+[^\d]'])
    if i != 0:
        pytest.fail("/boot is less than 90000 kb")

    p.expect(hostname+":~\\$", timeout=3)
    p.send("doas poweroff\n")
    p.expect("doas.*password:")
    p.send(password+"\n")

    p.expect(pexpect.EOF, timeout=20)

    for img in qemu.images:
        os.unlink(img)
