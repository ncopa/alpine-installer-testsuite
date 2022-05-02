import pytest
import libarchive
import os

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
                kernel = outdir.join(entry.pathname)
                libarchive.extract.extract_entries([entry])

            if entry.pathname.startswith("boot/initramfs"):
                initrd = outdir.join(entry.pathname)
                libarchive.extract.extract_entries([entry])

    return {'kernel': kernel, 'initrd': initrd}



