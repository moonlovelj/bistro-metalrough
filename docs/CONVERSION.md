# Conversion and regeneration

## Source and method

Source: <https://github.com/zeux/niagara_bistro> at commit
`2bdb6a410f8ebd475d3737e7c8e038ed2b00b02e`.
Original source files and DDS textures are not duplicated in this repository.
The three input file hashes are recorded in `reports/conversion_report.json`.

1. Resolve `MSFT_texture_dds` sources and decode DDS images with alpha preserved.
2. Convert sRGB diffuse/specular channels to linear RGB before combining them with material factors.
3. Estimate metallic and reconstruct base color with the Khronos conversion approximation, using dielectric F0 = 0.04.
4. Compute roughness as `1 - glossinessFactor * specularGlossinessTexture.alpha`.
5. Bake sRGB base-color PNGs and linear MR PNGs. Preserve diffuse alpha. MR channels are R=1, G=roughness, B=metallic.
6. Preserve source resolution; use the larger dimensions if the input maps differ, with linear-space color resampling. Different source UV transforms or samplers are rejected.
7. Normalize emissive colors above 1 and store the removed scale in `KHR_materials_emissive_strength`.
8. Rebuild invalid normal-map tangents with MikkTSpace, handling undefined degenerate cases with a finite orthogonal basis. Reindex only exactly equal vertices.
9. Compare rendered position, normal and UV checksums before/after tangent repair and verify the input file hashes remain unchanged.
10. Validate the final glTF, every buffer and every image with Khronos glTF Validator.

The scalar material case is stored as factors; 222 distinct textured material
configurations were baked into base-color/MR pairs. Existing core MR materials
are retained. The method is approximate and cannot preserve every possible
specular/glossiness BRDF exactly.

## Dependencies

For regeneration, use Python 3.11 or newer, Node.js 20 or newer, and Git.
The checked asset was produced with NumPy 2.3.5, Pillow 12.3.0 and
glTF Transform 4.5.1. The CLI dependencies include MikkTSpace and glTF Validator.
These tools are optional when simply loading the provided model.

From this repository's root:

```sh
python -m pip install -r tools/requirements.txt
npm --prefix tools install
git clone https://github.com/zeux/niagara_bistro.git ../niagara_bistro-source
git -C ../niagara_bistro-source checkout 2bdb6a410f8ebd475d3737e7c8e038ed2b00b02e
python tools/convert_metalrough.py --input ../niagara_bistro-source/bistro.gltf --output build/bistro
node --max-old-space-size=8192 tools/finalize_metalrough.cjs build/bistro ../niagara_bistro-source
```

The generated asset and fresh reports will be in `build/bistro/`. It is ignored
by Git so regeneration does not overwrite the published files. Review a regenerated
model before replacing release files and refreshing `checksums.sha256`.

The finalizer loads dependencies from `tools/node_modules/`. A Windows global
`@gltf-transform/cli` installation is also supported. To select another installation,
set `GLTF_TRANSFORM_CLI_ROOT` to the directory containing the CLI's `package.json`.
The finalizer's third positional argument is the original source checkout root.

## Release integrity

```sh
python tools/verify_assets.py
```

This checks every published asset against `checksums.sha256`, verifies local
glTF references and buffer lengths, and detects LFS pointer files. It does not
rerun the Khronos schema validator; the packaged validator results are in
`reports/validation.json`.

The current validation has 0 errors, 0 warnings and 39 informational messages:
35 unused-object notices, 2 empty nodes and 2 non-power-of-two images.

## Publishing with Git LFS

`.gitattributes` tracks all PNG textures and BIN buffers with Git LFS.
Initialize LFS in your local checkout before staging these assets:

```sh
git lfs install --local
git add .
git lfs status
git lfs ls-files
git commit -m "Add converted metallic-roughness Bistro assets"
git push origin main
```

The last command uploads to the configured remote. Regeneration dependencies,
temporary builds and Python caches are excluded by `.gitignore`.
