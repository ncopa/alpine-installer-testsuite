import os
import pexpect
import platform

def iso_arch(iso_file):
    return os.path.splitext(iso_file)[0].split('-')[-1]

def qemu_prog(iso_file):
    arch = iso_arch(iso_file)
    if arch == 'x86':
        return "qemu-system-i386"
    return "qemu-system-"+arch

def create_disk_image(path, size=2048*1024*1024):
    with open(path, 'wb') as f:
        f.seek(size-1024)
        f.write(b'\0'*1024)
    return path

def test_sys_install_syslinux(tmp_path, iso_file, boot_files):
    diskimg = create_disk_image(tmp_path / "disk.img")
    assert os.path.exists(diskimg) == 1

    if platform.system() == 'Linux':
        accel = 'kvm'
    elif platform.system() == 'Darwin':
        accel = 'hvf'

    arch = iso_arch(iso_file)
    if arch == 'x86' or arch == 'x86_64':
        machine = 'q35'
        console = 'ttyS0'
    elif arch == 'aarch64' or arch == 'armv7':
        machine = 'virt'
        console = 'ttyAMA0'
        if platform.system() == 'Darwin':
            machine = machine+',highmem=off'

    qemu_args = ['-nographic',
            '-machine', machine+',accel='+accel,
            '-cpu', 'host',
            '-drive', 'format=raw,file='+str(diskimg),
        ]
    p = pexpect.spawn(qemu_prog(iso_file), qemu_args + [
        '-kernel', str(boot_files['kernel']),
        '-initrd', str(boot_files['initrd']),
        '-append', 'quiet console='+console,
        '-cdrom', iso_file])

    p.expect("login:", timeout=30)
    p.send("root\n")

    p.timeout = 2
    p.expect("localhost:~#")
    p.send("export KERNELOPTS='quiet console="+console+"'\n")

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

    i = p.expect(["Enter mirror number \\(.*\\) or URL to add \\(.*\\) \\[1\\] ",
                  "Which NTP client to run\\? \\(.*\\) \\[.*\\] "], timeout=30)
    if i==1:
        p.send("\n")
        p.expect("Enter mirror number \\(.*\\) or URL to add \\(.*\\) \\[1\\] ", timeout=30)
    p.send("\n")

    p.expect("Which SSH server\\? \\(.*\\) \\[openssh\\] ", timeout=20)
    p.send("\n")

    disks = ['sda', 'sdb','vda','vdb']
    i = p.expect(disks, timeout=10)

    p.expect("Which disk\\(s\\) would you like to use\\? \\(.*\\) \\[none\\] ")
    p.send(disks[i] + "\n")

    p.expect("How would you like to use it\\? \\(.*\\) \\[.*\\] ")
    p.send("sys\n")

    p.expect("WARNING: Erase the above disk\\(s\\) and continue\\? \\(y/n\\) \\[n\\] ", timeout=10)
    p.send("y\n")

    p.expect(hostname+":~#", timeout=60)
    p.send("poweroff\n")
    p.expect(pexpect.EOF, timeout=20)

    p = pexpect.spawn(qemu_prog(iso_file), qemu_args)

    p.expect("login:", timeout=30)
    p.send("root\n")

    p.expect("Password:", timeout=3)
    p.send(password+"\n")

    p.expect(hostname+":~#", timeout=3)
    p.send('awk \'$2 == "/" {print $3}\' /proc/mounts '+"\n")
    p.expect_exact("ext4")

    p.expect(hostname+":~#", timeout=3)
    p.send("poweroff\n")
    p.expect(pexpect.EOF, timeout=20)
