import os
import pexpect

def qemu_prog(iso_file):
    arch = os.path.splitext(iso_file)[0].split('-')[-1]
    if arch == 'x86':
        return "qemu-system-i386"
    return "qemu-system-"+arch

def create_disk_image(path, size=1024*1024*1024):
    with open(path, 'wb') as f:
        f.seek(size-1024)
        f.write(b'\0'*1024)
    return path

def test_sys_install_syslinux(tmp_path, iso_file, boot_files):
    diskimg = create_disk_image(tmp_path / "disk.img")
    assert os.path.exists(diskimg) == 1

    qemu_args = ['-nographic', '-enable-kvm',
            '-cdrom', iso_file,
            '-drive', 'format=raw,file='+str(diskimg),
            '-kernel', str(boot_files['kernel']),
            '-initrd', str(boot_files['initrd']),
            '-append', 'quiet console=ttyS0',
        ]
    p = pexpect.spawn(qemu_prog(iso_file), qemu_args)
    p.expect("login:", timeout=30)
    p.send("root\n")

    p.timeout = 2
    p.expect("localhost:~#")
    p.send("export KERNELOPTS='quiet console=ttyS0'\n")

    p.expect("localhost:~#")
    p.send("setup-alpine\n")

    p.expect_exact("Select keyboard layout: [none] ")
    p.send("\n")

    hostname = "alpine"
    p.expect("Enter system hostname \\(.*\\) \\[.*\\] ")
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

    p.expect("HTTP/FTP proxy URL\\?.* \\[none\\] ")
    p.send("\n")

    p.expect("Enter mirror number \\(.*\\) or URL to add \\(.*\\) \\[1\\] ", timeout=10)
    p.send("\n")

    p.expect("Which SSH server\\? \\(.*\\) \\[openssh\\] ")
    p.send("\n")

    p.expect("Which disk\\(s\\) would you like to use\\? \\(.*\\) \\[none\\] ", timeout=10)
    p.send("sda\n")

    p.expect("How would you like to use it\\? \\(.*\\) \\[.*\\] ")
    p.send("sys\n")

    p.expect("WARNING: Erase the above disk\\(s\\) and continue\\? \\(y/n\\) \\[n\\] ")
    p.send("y\n")

    p.expect(hostname+":~#", timeout=30)
    p.send("poweroff\n")
    p.expect_exact("Requesting system poweroff", timeout=30)
    p.expect(pexpect.EOF, timeout=5)

    p = pexpect.spawn(qemu_prog(iso_file), ['-nographic', '-enable-kvm',
            '-drive', 'format=raw,file='+str(diskimg),
        ])

    p.expect("login:", timeout=30)
    p.send("root\n")

    p.expect("Password:", timeout=3)
    p.send(password+"\n")

    p.expect(hostname+":~#", timeout=3)
    p.send('awk \'$2 == "/" {print $3}\' /proc/mounts '+"\n")
    p.expect_exact("ext4")

    p.expect(hostname+":~#", timeout=3)
    p.send("poweroff\n")
    p.expect_exact("Requesting system poweroff", timeout=30)
    p.expect(pexpect.EOF, timeout=5)
