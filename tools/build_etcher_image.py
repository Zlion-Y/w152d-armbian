"""Build a W152D MBR image with FAT32 boot and ext4 root partitions."""

import argparse
import subprocess
import tempfile
from pathlib import Path

from package_mainline_usb import INPUTS, USB_ID, read_artifacts
from prepare_usb import write_boot_files


SECTOR_SIZE = 512
START_SECTOR = 2048
BOOT_SECTORS = 128 * 1024**2 // SECTOR_SIZE
ROOT_START = START_SECTOR + BOOT_SECTORS


def build(bundle, rootfs, output):
    if output.suffix.lower() != ".img":
        raise ValueError("Expected an .img output path")
    if not rootfs.is_file():
        raise ValueError("Use a regular rootfs image")
    root_size = rootfs.stat().st_size
    if root_size == 0 or root_size % SECTOR_SIZE:
        raise ValueError("Rootfs size must be a positive multiple of 512 bytes")
    root_sectors = root_size // SECTOR_SIZE
    if ROOT_START + root_sectors > 0xffffffff:
        raise ValueError("Image exceeds MBR capacity")
    subprocess.run(["e2fsck", "-fn", rootfs], check=True)
    marker = subprocess.check_output(["debugfs", "-R", "cat /etc/w152d-udisk", rootfs])
    if marker.strip() != USB_ID:
        raise ValueError("Expected the W152D mainline rootfs marker")
    for private_file in (
        "/root/.ssh/authorized_keys",
        "/etc/ssh/ssh_host_ed25519_key_w152d",
        "/etc/wpa_supplicant/w152d.conf",
        "/var/lib/w152d/provisioned",
    ):
        metadata = subprocess.check_output(
            ["debugfs", "-R", f"stat {private_file}", rootfs], stderr=subprocess.DEVNULL,
        )
        if metadata.startswith(b"Inode:"):
            raise ValueError(f"Expected a fresh, unprovisioned rootfs without {private_file}")
    with tempfile.TemporaryDirectory(dir=output.parent, prefix="w152d-image-") as directory:
        stage = Path(directory)
        filesystem = stage / "files"
        filesystem.mkdir()
        files = read_artifacts(bundle, (*INPUTS, "boot.scr", "aml_autoscript"))
        write_boot_files(filesystem, files)
        board = filesystem / "w152d"
        (board / "ROOT_LAYOUT").write_bytes(b"P2\n")
        (board / "mainline/boot.arm").write_bytes(b"BOOT")
        (board / "mainline/continuous").touch()
        (board / "config").mkdir()
        (board / "firmware").mkdir()
        image = stage / "disk.img"
        with image.open("xb") as file:
            file.truncate((ROOT_START + root_sectors) * SECTOR_SIZE)
        partition_table = (
            f"label: dos\nunit: sectors\n\nstart={START_SECTOR}, size={BOOT_SECTORS}, type=c, bootable\n"
            f"start={ROOT_START}, size={root_sectors}, type=83\n"
        )
        subprocess.run(["sfdisk", "--no-reread", "--no-tell-kernel", image], input=partition_table, text=True, check=True)
        fat = stage / "boot.fat"
        with fat.open("xb") as file:
            file.truncate(BOOT_SECTORS * SECTOR_SIZE)
        subprocess.run(
            ["mkfs.vfat", "-F", "32", "-s", "2", "-n", "W152DBOOT", "-h", str(START_SECTOR), fat],
            check=True,
        )
        subprocess.run(["mcopy", "-i", fat, "-s", filesystem / "aml_autoscript", board, "::/"], check=True)
        subprocess.run(["fsck.vfat", "-n", fat], check=True)
        for partition, start in ((fat, START_SECTOR), (rootfs, ROOT_START)):
            subprocess.run(
                ["dd", f"if={partition}", f"of={image}", "bs=1M",
                 f"seek={start * SECTOR_SIZE // 1024**2}", "conv=notrunc,sparse", "status=none"],
                check=True,
            )
        # Hard-link the completed image into place so existing files cannot be overwritten.
        output.hardlink_to(image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--rootfs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.exit(1, "Output already exists\n")
    try:
        build(args.bundle, args.rootfs, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")
    print(args.output)


if __name__ == "__main__":
    main()
