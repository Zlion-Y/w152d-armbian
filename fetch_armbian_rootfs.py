"""Fetch a digest-pinned official Armbian ARM64 rootfs cache from GHCR."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'deps'))
REPO = 'armbian/os/rootfs-arm64-bookworm-minimal'
DIGEST = 'sha256:ecf9ac2659c96e7cb6199e2bb92633710800b4630acefb83c0ec9f621313d10a'
PACKAGE_PAGE = 'https://github.com/armbian/os/pkgs/container/os%2Frootfs-arm64-bookworm-minimal'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    target = HERE / 'downloads/armbian-bookworm'
    target.mkdir(parents=True, exist_ok=True)
    query = urllib.parse.urlencode({'service': 'ghcr.io', 'scope': 'repository:' + REPO + ':pull'})
    with urllib.request.urlopen('https://ghcr.io/token?' + query, timeout=30) as r:
        token = json.load(r)['token']
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.index.v1+json'}

    def get(path):
        return urllib.request.urlopen(urllib.request.Request('https://ghcr.io/v2/' + REPO + '/' + path, headers=headers), timeout=45)

    with get('manifests/' + DIGEST) as r:
        data = r.read()
    assert 'sha256:' + hashlib.sha256(data).hexdigest() == DIGEST
    manifest = json.loads(data)
    (target / 'oci-manifest.json').write_bytes(data)
    layers = manifest.get('layers', [])
    result = {'repository': REPO, 'manifest_digest': DIGEST, 'package_page': PACKAGE_PAGE, 'mediaType': manifest.get('mediaType'), 'layers': layers}
    print(json.dumps(result, indent=2), flush=True)
    if not args.download:
        return
    assert len(layers) == 1 and layers[0]['size'] < 400 * 1024 * 1024, 'Inspect layer structure/size before downloading'
    layer = layers[0]
    filename = layer.get('annotations', {}).get('org.opencontainers.image.title', 'rootfs.tar.zst')
    assert Path(filename).name == filename and filename.endswith('.tar.zst')
    dest = target / filename
    if not dest.exists():
        partial = dest.with_suffix('.partial')
        with get('blobs/' + layer['digest']) as src, partial.open('wb') as out:
            while chunk := src.read(1024 * 1024):
                out.write(chunk)
        assert partial.stat().st_size == layer['size']
        assert 'sha256:' + hashlib.sha256(partial.read_bytes()).hexdigest() == layer['digest']
        partial.replace(dest)
    assert 'sha256:' + hashlib.sha256(dest.read_bytes()).hexdigest() == layer['digest']
    result['downloaded_file'] = str(dest)
    result['verified'] = True
    (target / 'source.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    unpacked = dest.with_suffix('')
    if not unpacked.exists():
        import zstandard
        partial_tar = unpacked.with_suffix('.tar.partial')
        with dest.open('rb') as compressed, partial_tar.open('wb') as output:
            with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
                shutil.copyfileobj(reader, output)
        partial_tar.replace(unpacked)
    print('Verified rootfs:', dest, flush=True)


if __name__ == '__main__':
    main()
