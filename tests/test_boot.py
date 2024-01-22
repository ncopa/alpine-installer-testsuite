
import os
import pexpect
import pytest
import subprocess
import sys


@pytest.mark.parametrize('bootmode', ['UEFI', 'bios'])
@pytest.mark.parametrize('numdisks', [0])
@pytest.mark.parametrize('disktype', ['virtio', 'ide', 'nvme', 'usb'])
def test_boot(qemu, disktype, bootmode):
    if (disktype == 'ide' or bootmode == 'bios') and (qemu.arch == 'aarch64' or qemu.arch == 'arm'):
        pytest.skip("not supported on this architecture")

    qemu_args = qemu.machine_args + [
        '-nographic',
        '-m', '512M',
        '-smp', '4',
    ]

    img = qemu.boot['iso']
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
            '-device', f'usb-storage,drive={driveid}'
        ])
    else:
        qemu_args.extend(
            ['-drive', f'if={disktype},format=raw,file={img}'])

    if bootmode == 'UEFI':
        qemu_args.extend([
            '-drive', 'if=pflash,format=raw,readonly=on,file='+qemu.uefi_code,
            '-boot', 'menu=on,splash-time=0'
        ])

    p = pexpect.spawn(qemu.prog, qemu_args)

    p.logfile = sys.stdout.buffer

    p.expect("login:", timeout=30)
    p.sendline("root")

    p.timeout = 2
    p.expect("localhost:~#")
    p.sendline("poweroff")
    p.expect(pexpect.EOF, timeout=10)
