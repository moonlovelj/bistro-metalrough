# Conversion workflow

## Inputs and outputs

Use the original source checkout at commit
`2bdb6a410f8ebd475d3737e7c8e038ed2b00b02e` of
<https://github.com/zeux/niagara_bistro>.
The source glTF, its two buffers and DDS textures are read without modification.

Generated files go in `build/bistro/`, which is ignored by Git:

```text
bistro_metalrough.gltf
bistro.bin
bistro-anim.bin
textures/
conversion_report.json
validation.json
```

Follow the install and run commands in [README.md](../README.md).
The Python dependency versions are pinned in `tools/requirements.txt`;
the Node CLI version is pinned in `tools/package.json`.
The Node finalizer resolves the local CLI installation under
`tools/node_modules/`. Set `GLTF_TRANSFORM_CLI_ROOT` to the CLI package
directory if using a different installation.

## Material conversion

- Resolve DDS image sources and retain alpha when decoding.
- Convert sRGB diffuse/specular colors to linear RGB and apply material factors.
- Estimate metallic and reconstruct base color with the Khronos approximation,
  using dielectric F0 = 0.04. This cannot preserve every spec/gloss BRDF exactly.
- Set roughness to `1 - glossinessFactor * specularGlossinessTexture.alpha`.
- Bake base-color PNGs with sRGB RGB and linear alpha. Bake MR PNGs with
  linear channels R=1 (unused), G=roughness, B=metallic.
- Preserve the source resolution, or match the larger input map when sizes
  differ. Color resampling is performed in linear space. Incompatible
  UV transforms or samplers are rejected.
- Normalize emissive factors above 1 and record their intensity in
  `KHR_materials_emissive_strength`.

The output has no specular/glossiness, specular, IOR or DDS extensions.
Glass transmission, emissive intensity and punctual lights retain their
respective glTF extensions. Renderers need support for those extensions
to reproduce these independent effects.

## Geometry and verification

Invalid tangents used by normal-mapped primitives are regenerated with
MikkTSpace. Undefined degenerate cases receive a finite basis perpendicular
to the original normal. Exact welding retains tangent seams; unused tangent
attributes are removed.

The finalizer compares rendered positions, normals and UVs before/after
tangent repair, checks that the source file hashes remain unchanged,
and runs Khronos glTF Validator against all buffers and PNG images.
`conversion_report.json` records these checks and the source hashes;
`validation.json` is the complete validator report.

The reference run converted 234 materials, fixed 14 emissive materials,
rebuilt tangents on 43 primitives and produced 0 errors and 0 warnings.
The retained 39 informational messages concerned unused objects, empty
nodes and non-power-of-two images.

This branch intentionally does not include precomputed release assets,
reports or checksum manifests: the regeneration creates fresh outputs.
