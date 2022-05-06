import libarchive
import os
import platform
import pytest

def pytest_addoption(parser):
    parser.addoption("--iso", action="store", help="iso image to test")
    parser.addoption("--alpine-conf-iso", action="store", help='optional iso image with alpine-conf')


@pytest.fixture(scope='session')
def iso_file(request):
    return request.config.getoption("--iso")

@pytest.fixture(scope='session')
def alpine_conf_iso(request):
    return request.config.getoption("--alpine-conf-iso")

@pytest.fixture(scope='session')
def boot_files(tmpdir_factory, iso_file):
    with libarchive.file_reader(iso_file) as a:
        outdir = tmpdir_factory.mktemp('data')
        os.chdir(outdir)
        for entry in a:
            entry.perm=0o640
            if entry.pathname.startswith("boot/vmlinuz"):
                kernel = str(outdir.join(entry.pathname))
                libarchive.extract.extract_entries([entry])

            if entry.pathname.startswith("boot/initramfs"):
                initrd = str(outdir.join(entry.pathname))
                libarchive.extract.extract_entries([entry])

    return {'kernel': kernel, 'initrd': initrd, 'iso': iso_file}


def create_disk_image(path, size=1024*1024*1024):
    with open(path, 'wb') as f:
        f.seek(size-1024)
        f.write(b'\0'*1024)
    return path

class QemuVM:
    def __init__(self, iso, tmp_path, numdisks, boot_files):
        self.iso_arch = os.path.splitext(iso)[0].split('-')[-1]

        if self.iso_arch == 'x86':
            self.arch = 'i386'
        elif self.iso_arch == 'armv7' or self.iso_arch == 'armhf':
            self.arch = 'arm'
        else:
            self.arch = self.iso_arch

        if platform.system() == 'Linux':
            self.accel = 'kvm'
        elif platform.system() == 'Darwin':
            self.accel = 'hvf'

        highmemopt = ''
        if self.arch == 'i386' or self.arch == 'x86_64':
            self.machine = 'q35'
            self.console = 'ttyS0'
        elif self.arch == 'aarch64' or self.arch == 'arm':
            self.machine = 'virt'
            self.console = 'ttyAMA0'
            if platform.system() == 'Darwin':
                highmemopt = ',highmem=off'

        self.machine_args = ['-machine', self.machine+',accel='+self.accel+highmemopt, '-cpu', 'host']
        self.prog = "qemu-system-"+self.arch

        if platform.system() == 'Darwin':
            edk2_path = '/opt/homebrew/share/qemu'
        else:
            edk2_path = '/usr/share/qemu'

        self.uefi_code = edk2_path+'/edk2-'+self.arch+'-code.fd'

        self.images = []
        for i in range(numdisks):
            self.images.append(create_disk_image(tmp_path / f"disk{i}.img"))

        self.boot = boot_files

@pytest.fixture
def qemu(iso_file, tmp_path, numdisks, boot_files):
    return QemuVM(iso_file, tmp_path, numdisks, boot_files)

