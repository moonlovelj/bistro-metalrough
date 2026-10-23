# Bistro metallic-roughness conversion tools

A lightweight branch for regenerating the converted Bistro model on another
machine. It contains scripts, dependency lists and documentation, with no
generated models, textures, binary buffers or Git LFS objects.

## Requirements

- Python 3.11 or newer.
- Node.js 20 or newer, with npm.
- Git and enough disk space for the source checkout and generated assets.

## Clone only this branch

```sh
git clone --single-branch --branch reproduce https://github.com/moonlovelj/bistro-metalrough.git bistro-metalrough-tools
cd bistro-metalrough-tools
```

Git LFS is not needed to download this lightweight branch. The original
Bistro source and DDS textures are downloaded separately in the next step.

## Regenerate

Run from this repository's root:

```sh
python -m pip install -r tools/requirements.txt
npm --prefix tools install
git clone https://github.com/zeux/niagara_bistro.git ../niagara_bistro-source
git -C ../niagara_bistro-source checkout 2bdb6a410f8ebd475d3737e7c8e038ed2b00b02e
python tools/convert_metalrough.py --input ../niagara_bistro-source/bistro.gltf --output build/bistro
node --max-old-space-size=8192 tools/finalize_metalrough.cjs build/bistro ../niagara_bistro-source
```

Use `python3` instead of `python` if required by your environment.
Load `build/bistro/bistro_metalrough.gltf` in your renderer, keeping both
BIN buffers and the `textures/` directory beside it. Fresh conversion and
validation reports are generated in the same directory.

The scripts bake core metallic-roughness materials, repair invalid tangents,
normalize HDR emissive factors, and validate every external resource.
The finalizer exits unsuccessfully on any validation error. The reference
conversion produced 0 errors and 0 warnings.

No files from the full asset branch are required. `build/`, `node_modules/`
and Python caches are excluded from Git. [Conversion details](docs/CONVERSION.md)
explain the method and retained material extensions.

## Source and license

Based on [zeux/niagara_bistro](https://github.com/zeux/niagara_bistro) at
`2bdb6a410f8ebd475d3737e7c8e038ed2b00b02e`, derived from Amazon Lumberyard
Bistro / [NVIDIA GameWorks RTXDI assets](https://github.com/NVIDIAGameWorks/rtxdi-assets).
The workflow follows the [Khronos conversion example](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Archived/KHR_materials_pbrSpecularGlossiness/examples/convert-between-workflows/js/three.pbrUtilities.js)
and uses [glTF Transform](https://github.com/donmccurdy/glTF-Transform),
[MikkTSpace](https://github.com/donmccurdy/mikktspace-wasm), and the
[Khronos glTF Validator](https://github.com/KhronosGroup/glTF-Validator).

The upstream [MIT license](LICENSE) is preserved.
Copyright (c) 2023 NVIDIA GameWorks.
