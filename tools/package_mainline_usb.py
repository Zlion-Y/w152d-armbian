"""Package an already built W152D Linux 6.12 bundle for the stock USB entry."""

import argparse
import hashlib
import re
import struct
from pathlib import Path

from build_bootstrap import script_image


TEMPLATES = Path(__file__).resolve().parents[1] / "usb/mainline"
INPUTS = ("Image", "integrated-probe.dtb", "initramfs.cpio.gz", "kernel.config")


def read_artifacts(directory):
    checksums = {}
    for line in (directory / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if not match:
            raise ValueError("Malformed build SHA256SUMS")
        digest, name = match.groups()
        if name not in INPUTS or name in checksums:
            raise ValueError(f"Unexpected or duplicate build manifest entry: {name}")
        checksums[name] = digest.lower()
    if checksums.keys() != set(INPUTS):
        raise ValueError("Manifest must cover Image, integrated-probe.dtb, initramfs.cpio.gz and kernel.config")

    files = {}
    for name in INPUTS:
        data = (directory / name).read_bytes()
        if not data or hashlib.sha256(data).hexdigest() != checksums[name]:
            raise ValueError(f"Empty file or SHA-256 mismatch: {name}")
        files[name] = data
    return files


def build(artifacts, output):
    files = read_artifacts(artifacts)
    image = files["Image"]
    initrd = files["initramfs.cpio.gz"]
    dtb = files["integrated-probe.dtb"]
    if len(image) < 64 or image[56:60] != b"ARM\x64":
        raise ValueError("Expected an uncompressed ARM64 Image")
    if not initrd.startswith(b"\x1f\x8b") or not dtb.startswith(b"\xd0\x0d\xfe\xed"):
        raise ValueError("Expected a gzip initramfs and a DTB")

    # Mirror the load windows in w152d-usb-mainline.cmd and the DT carveouts.
    image_memory_size, = struct.unpack_from("<Q", image, 16)
    if not image_memory_size or max(len(image), image_memory_size) > 0x0B800000 - 0x08600000:
        raise ValueError("Image exceeds its W152D load window")
    if len(initrd) > 0x0D000000 - 0x0B800000:
        raise ValueError("Initramfs exceeds its W152D load window")
    if len(dtb) + 0x10000 > 0x11000000 - 0x0D000000:
        raise ValueError("DTB with expansion space exceeds its W152D load window")

    boot = (TEMPLATES / "w152d-usb-mainline.cmd").read_text(encoding="ascii")
    boot = boot.replace("@IMAGE_SIZE@", f"{len(image):x}")
    boot = boot.replace("@INITRD_SIZE@", f"{len(initrd):x}")
    boot = boot.replace("@DTB_SIZE@", f"{len(dtb):x}")
    dispatcher = (TEMPLATES / "w152d-usb-dispatch.cmd").read_text(encoding="ascii")
    files["boot.scr"] = script_image(boot.encode("ascii"), b"W152D mainline USB boot")
    files["aml_autoscript"] = script_image(dispatcher.encode("ascii"), b"W152D USB boot dispatcher")
    sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in files.items())

    output.mkdir(parents=True)
    for name, data in files.items():
        (output / name).write_bytes(data)
    (output / "SHA256SUMS").write_bytes(sums.encode("ascii"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True, help="Kernel bundle with SHA256SUMS")
    parser.add_argument("--output", type=Path, required=True, help="New directory for the packaged files")
    args = parser.parse_args()
    try:
        build(args.artifacts, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(args.output)


if __name__ == "__main__":
    main()
