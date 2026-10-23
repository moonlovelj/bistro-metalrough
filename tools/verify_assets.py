"""Verify downloaded release assets. Requires only Python's standard library.

Checks file hashes and references; the schema validation report is precomputed.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

def local_path(relative):
    filename = (ROOT / unquote(relative)).resolve()
    if ROOT not in filename.parents:
        raise ValueError(f'Asset path outside repository: {relative}')
    return filename

def verify():
    manifest = ROOT / 'checksums.sha256'
    checked = set()
    for line in manifest.read_text(encoding='utf-8').splitlines():
        expected, relative = line.split('  ', 1)
        filename = local_path(relative)
        if relative in checked:
            raise ValueError(f'Duplicate checksum entry: {relative}')
        digest = hashlib.sha256()
        with filename.open('rb') as stream:
            prefix = stream.read(256)
            if prefix.startswith(b'version https://git-lfs.github.com/spec/v1'):
                raise ValueError(f'Git LFS pointer found: {relative}. Run git lfs pull.')
            digest.update(prefix)
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f'SHA-256 mismatch: {relative}')
        checked.add(relative)
    name = 'bistro_metalrough.gltf'
    model = json.loads((ROOT / name).read_text(encoding='utf-8'))
    resources = {name}
    for image in model.get('images', []):
        resources.add(image['uri'])
    for buffer in model.get('buffers', []):
        resources.add(buffer['uri'])
        if local_path(buffer['uri']).stat().st_size != buffer['byteLength']:
            raise ValueError(f'Buffer length mismatch: {buffer["uri"]}')
    if resources != checked:
        raise ValueError(f'Manifest/resource mismatch: {resources ^ checked}')
    for relative in resources:
        if not local_path(relative).is_file():
            raise ValueError(f'Missing resource: {relative}')
    forbidden = {'KHR_materials_pbrSpecularGlossiness', 'KHR_materials_specular', 'KHR_materials_ior', 'MSFT_texture_dds'}
    declared = set(model.get('extensionsUsed', [])) | set(model.get('extensionsRequired', []))
    for material in model['materials']:
        declared |= set(material.get('extensions', {}))
        if 'pbrMetallicRoughness' not in material:
            raise ValueError('Material missing core metallic-roughness properties')
    if declared & forbidden:
        raise ValueError(f'Unexpected material/texture extensions: {declared & forbidden}')
    validation = json.loads((ROOT / 'reports/validation.json').read_text(encoding='utf-8'))
    print(f'Verified SHA-256 and local references for all {len(checked)} asset files.')
    print(f'Core MR materials: {len(model["materials"])}; meshes: {len(model["meshes"])}; PNG images: {len(model["images"])}.')
    print(f'Packaged Khronos report: {validation["issues"]["numErrors"]} errors, {validation["issues"]["numWarnings"]} warnings.')

if __name__ == '__main__':
    verify()
