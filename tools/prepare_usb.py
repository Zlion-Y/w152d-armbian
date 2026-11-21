"""Copy a W152D mainline bundle and a fresh ext4 rootfs to a mounted USB."""

import argparse
import shutil
from pathlib import Path

from package_mainline_usb import INPUTS, USB_ID, read_artifacts


BOOT_FILES = ("Image", "integrated-probe.dtb", "initramfs.cpio.gz", "boot.scr")


def write_boot_files(usb, files):
    board = usb / "w152d"
    target = board / "mainline"
    target.mkdir(parents=True)
    (board / "USB_ID").write_bytes(USB_ID + b"\n")
    for name in BOOT_FILES:
        (target / name).write_bytes(files[name])
    with (usb / "aml_autoscript").open("xb") as destination:
        destination.write(files["aml_autoscript"])


def prepare(usb, bundle, rootfs):
    if not usb.is_dir():
        raise ValueError("Mount the target volume before copying")
    board = usb / "w152d"
    entry = usb / "aml_autoscript"
    if board.exists() or entry.exists() or board.is_symlink() or entry.is_symlink():
        raise ValueError("Use a volume with no existing w152d directory or aml_autoscript")
    files = read_artifacts(bundle, (*INPUTS, "boot.scr", "aml_autoscript"))
    if not rootfs.is_file():
        raise ValueError("Rootfs must be a regular file")
    with rootfs.open("rb") as source:
        source.seek(1080)
        if source.read(2) != b"\x53\xef":
            raise ValueError("Expected an uncompressed ext4 rootfs file")
    size = rootfs.stat().st_size
    if size >= 2**32 or shutil.disk_usage(usb).free < size + sum(map(len, files.values())) + 1024**2:
        raise ValueError("Rootfs must fit FAT32 and the target volume must have enough free space")
    board.mkdir()
    with (board / "rootfs.ext4").open("xb") as destination, rootfs.open("rb") as source:
        shutil.copyfileobj(source, destination)
    write_boot_files(usb, files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usb", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--rootfs", type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.usb, args.bundle, args.rootfs)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print("USB files copied. Configure your SSH key and arm the first boot before ejecting.")


if __name__ == "__main__":
    main()
