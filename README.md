# Bistro — Metallic-Roughness

Amazon Lumberyard Bistro converted to **glTF 2.0 core metallic-roughness**
materials, with baked PNG textures and repaired invalid tangent data.
This is an asset repository; no application build is required to use it.

The published model does **not** use `KHR_materials_pbrSpecularGlossiness`,
`KHR_materials_specular`, `KHR_materials_ior`, or DDS textures.

## Download and load

Binary buffers and PNG textures use **Git LFS**. Install Git LFS before cloning:

```sh
git lfs install
git clone https://github.com/moonlovelj/bistro-metalrough.git
cd bistro-metalrough
git lfs pull
python tools/verify_assets.py
```

Load **[`bistro_metalrough.gltf`](bistro_metalrough.gltf)** in your glTF viewer
or renderer. Keep `bistro.bin`, `bistro-anim.bin`, and `textures/` beside it;
all resource URIs are relative. The model and textures occupy about **1.55 GiB**.
Verify that you have downloaded the actual LFS objects rather than pointer files.

For a renderer that loads models over HTTP, serve the repository with:

```sh
python -m http.server 8000
```

The asset URL is `http://localhost:8000/bistro_metalrough.gltf`.
This command serves files; it does not provide a 3D viewer.

## Contents

```text
bistro_metalrough.gltf       Model entry point
bistro.bin                  Geometry buffer
bistro-anim.bin             Animation buffer
textures/                   PNG textures
reports/                    Conversion and Khronos validation reports
tools/                      Optional conversion and verification scripts
docs/CONVERSION.md          Method and regeneration instructions
checksums.sha256            SHA-256 hashes of every runtime asset
LICENSE                     Upstream MIT license
```

| Item | Count |
| --- | ---: |
| Meshes | 551 |
| Materials | 254 |
| PNG images | 573 |
| Nodes | 6,006 |
| Animations | 8 |

## Texture conventions

| Texture | Color space | Channels |
| --- | --- | --- |
| Base color | sRGB RGB; linear alpha | RGB = base color, A = opacity |
| Metallic-roughness | Linear | G = roughness, B = metallic; R = 1 and unused |
| Normal | Linear | Original normal-map data |
| Emissive | sRGB | Original emissive color |

`baseColor_*.png` and `metallicRoughness_*.png` are baked material maps.
`source_*.png` are preserved source maps, including normal and emissive maps.
The glTF material slots determine each image's meaning. The R channel of an
MR map is **not** an ambient-occlusion bake.

## Compatibility and validation

All materials use the core metallic-roughness model. These independent
extensions are retained for their respective effects:

- `KHR_materials_transmission`: glass transmission.
- `KHR_materials_emissive_strength`: emission above the core factor range.
- `KHR_lights_punctual`: scene lights.

Renderers without these extensions can load the core material representation,
but those effects will differ. Specular/glossiness-to-MR conversion is an
approximation and may change some material appearance.

The packaged [Khronos glTF Validator report](reports/validation.json) contains
**0 errors, 0 warnings**, and 39 informational messages concerning unused
objects, empty nodes, and non-power-of-two images. All external buffers and
images were included in validation.

Conversion repaired 14 emissive materials and rebuilt invalid tangents on
43 primitives. Rendered positions, normals, and UVs were checked for equality
through the repair step. See the [conversion report](reports/conversion_report.json)
and [regeneration instructions](docs/CONVERSION.md).

## Credits and license

Based on [zeux/niagara_bistro](https://github.com/zeux/niagara_bistro) at commit
[`2bdb6a410f8ebd475d3737e7c8e038ed2b00b02e`](https://github.com/zeux/niagara_bistro/commit/2bdb6a410f8ebd475d3737e7c8e038ed2b00b02e),
a lightly edited version of Amazon Lumberyard Bistro from
[NVIDIA GameWorks / RTXDI assets](https://github.com/NVIDIAGameWorks/rtxdi-assets).

The conversion follows the [Khronos workflow conversion example](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Archived/KHR_materials_pbrSpecularGlossiness/examples/convert-between-workflows/js/three.pbrUtilities.js)
and uses [glTF Transform](https://github.com/donmccurdy/glTF-Transform),
[MikkTSpace](https://github.com/donmccurdy/mikktspace-wasm), and the
[Khronos glTF Validator](https://github.com/KhronosGroup/glTF-Validator).

Distributed with the upstream [MIT license](LICENSE).
Copyright (c) 2023 NVIDIA GameWorks. Keep the license and attribution when redistributing.
