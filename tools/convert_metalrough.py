"""Bake Bistro's specular/glossiness materials into core metallic/roughness.

Requires Python, NumPy and Pillow. Run this before finalize_metalrough.cjs.
All generated files go in build/bistro; the source checkout is read only.

The approximation follows Khronos' conversion example, in linear color space:
https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Archived/
KHR_materials_pbrSpecularGlossiness/examples/convert-between-workflows/js/three.pbrUtilities.js
"""

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

SG = "KHR_materials_pbrSpecularGlossiness"
REMOVED = {SG, "MSFT_texture_dds", "KHR_materials_specular", "KHR_materials_ior"}
LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)
EPS = 1e-6


def to_linear(value):
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def to_srgb(value):
    value = np.clip(value, 0, 1)
    return np.where(value <= 0.0031308, value * 12.92, 1.055 * value ** (1 / 2.4) - 0.055)


def convert_pixels(diffuse, specular, glossiness):
    """Inputs and returned base color are linear; alpha is handled separately."""
    diffuse_brightness = np.sqrt(np.sum(diffuse * diffuse * LUMA, axis=-1))
    specular_brightness = np.sqrt(np.sum(specular * specular * LUMA, axis=-1))
    remaining = 1 - np.max(specular, axis=-1)
    b = diffuse_brightness * remaining / 0.96 + specular_brightness - 0.08
    discriminant = np.maximum(b * b - 0.16 * (0.04 - specular_brightness), 0)
    metallic = np.where(specular_brightness < 0.04, 0, np.clip((-b + np.sqrt(discriminant)) / 0.08, 0, 1))
    diffuse_base = diffuse * (remaining / 0.96 / np.maximum(1 - metallic, EPS))[..., None]
    specular_base = (specular - 0.04 * (1 - metallic)[..., None]) / np.maximum(metallic, EPS)[..., None]
    base = np.clip(diffuse_base * (1 - metallic * metallic)[..., None] + specular_base * (metallic * metallic)[..., None], 0, 1)
    return base, metallic, np.clip(1 - glossiness, 0, 1)


class TextureSampler:
    """Decode DDS without dropping alpha; resample RGB in linear space."""

    def __init__(self, filename, size):
        self.image = None
        self.planes = None
        if filename is None:
            return
        with Image.open(filename) as source:
            self.image = source.convert("RGBA")
        if self.image.size != size:
            self.planes = []
            for channel in range(4):
                pixels = np.asarray(self.image.getchannel(channel), dtype=np.float32) / 255
                if channel < 3:
                    pixels = to_linear(pixels)
                self.planes.append(Image.fromarray(pixels).resize(size, Image.Resampling.BILINEAR))
            self.image.close()
            self.image = None

    def rows(self, box):
        if self.planes is not None:
            return np.stack([np.asarray(plane.crop(box)) for plane in self.planes], axis=-1)
        if self.image is None:
            return np.ones((box[3] - box[1], box[2] - box[0], 4), dtype=np.float32)
        pixels = np.asarray(self.image.crop(box), dtype=np.float32) / 255
        pixels[..., :3] = to_linear(pixels[..., :3])
        return pixels

    def close(self):
        if self.image is not None:
            self.image.close()
        for plane in self.planes or []:
            plane.close()


def texture_infos(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith("Texture") and isinstance(child, dict) and "index" in child:
                yield child
            else:
                yield from texture_infos(child)
    elif isinstance(value, list):
        for child in value:
            yield from texture_infos(child)


def bake(source_path, output_dir):
    source_path = source_path.resolve()
    output_dir = output_dir.resolve()
    root = source_path.parent
    if output_dir == root or output_dir in root.parents:
        raise ValueError("Output must not overwrite the source directory or its parents")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "textures").mkdir(exist_ok=True)
    gltf = json.loads(source_path.read_text(encoding="utf-8"))
    source_hashes = {source_path.name: hashlib.sha256(source_path.read_bytes()).hexdigest()}
    for buffer in gltf["buffers"]:
        filename = root / buffer["uri"]
        source_hashes[buffer["uri"]] = hashlib.sha256(filename.read_bytes()).hexdigest()
        target = output_dir / buffer["uri"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(filename, target)

    # There are PNG fallback URIs in the original JSON, but only the DDS files
    # are shipped. Resolve the DDS extension before changing any texture index.
    original_images = gltf["images"]
    gltf["images"] = []
    source_images = {}
    source_image_indices = {}
    for texture in gltf["textures"]:
        ext = texture.get("extensions", {}).pop("MSFT_texture_dds", None)
        index = ext["source"] if ext is not None else texture["source"]
        filename = root / original_images[index]["uri"]
        if not filename.is_file():
            raise FileNotFoundError(filename)
        key = str(filename)
        if key not in source_image_indices:
            new_index = len(gltf["images"])
            source_image_indices[key] = new_index
            source_images[new_index] = filename
            gltf["images"].append({"uri": f"textures/source_{new_index:03d}.png"})
        texture["source"] = source_image_indices[key]
        if not texture.get("extensions"):
            texture.pop("extensions", None)

    report = {"source_hashes": source_hashes, "workflow": "core metallic-roughness", "algorithm": "Khronos spec/gloss to metal/rough approximation; linear RGB; dielectric F0=0.04", "materials_converted": 0, "emissive_materials_fixed": [], "baked_materials": [], "resampled_materials": []}
    cache = {}

    def source_texture(info):
        if info is None:
            return None
        return source_images[gltf["textures"][info["index"]]["source"]]

    def add_texture(uri, template):
        image_index = len(gltf["images"])
        gltf["images"].append({"uri": uri})
        texture = {"source": image_index}
        if template is not None and "sampler" in gltf["textures"][template["index"]]:
            texture["sampler"] = gltf["textures"][template["index"]]["sampler"]
        index = len(gltf["textures"])
        gltf["textures"].append(texture)
        result = copy.deepcopy(template or {})
        result["index"] = index
        return result

    for index, material in enumerate(gltf["materials"]):
        emissive = material.get("emissiveFactor", [0, 0, 0])
        strength = max(emissive)
        if strength > 1:
            material["emissiveFactor"] = [value / strength for value in emissive]
            material.setdefault("extensions", {})["KHR_materials_emissive_strength"] = {"emissiveStrength": strength}
            report["emissive_materials_fixed"].append({"index": index, "original": emissive, "strength": strength})

        spec_gloss = material.get("extensions", {}).pop(SG, None)
        if spec_gloss is None:
            material.setdefault("pbrMetallicRoughness", {})
            continue
        report["materials_converted"] += 1
        key = json.dumps(spec_gloss, sort_keys=True)
        if key in cache:
            material["pbrMetallicRoughness"] = copy.deepcopy(cache[key])
            continue
        diffuse_info = spec_gloss.get("diffuseTexture")
        specular_info = spec_gloss.get("specularGlossinessTexture")
        diffuse_factor = np.array(spec_gloss.get("diffuseFactor", [1, 1, 1, 1]), dtype=np.float32)
        specular_factor = np.array(spec_gloss.get("specularFactor", [1, 1, 1]), dtype=np.float32)
        gloss_factor = spec_gloss.get("glossinessFactor", 1)
        diffuse_path, specular_path = source_texture(diffuse_info), source_texture(specular_info)
        if diffuse_info is not None and specular_info is not None:
            if {k: v for k, v in diffuse_info.items() if k != "index"} != {k: v for k, v in specular_info.items() if k != "index"}:
                raise ValueError(f"Material {index}: source UV transforms differ")
            if gltf["textures"][diffuse_info["index"]].get("sampler") != gltf["textures"][specular_info["index"]].get("sampler"):
                raise ValueError(f"Material {index}: source samplers differ")

        if diffuse_path is None and specular_path is None:
            base, metal, rough = convert_pixels(diffuse_factor[:3], specular_factor, np.asarray(gloss_factor))
            pbr = {"baseColorFactor": [*base.tolist(), float(diffuse_factor[3])], "metallicFactor": float(metal), "roughnessFactor": float(rough)}
        else:
            sizes = []
            for filename in (diffuse_path, specular_path):
                if filename is not None:
                    with Image.open(filename) as image:
                        sizes.append(image.size)
            size = max(s[0] for s in sizes), max(s[1] for s in sizes)
            if len(set(sizes)) > 1:
                report["resampled_materials"].append({"index": index, "source_sizes": sizes, "output_size": size})
            diffuse = TextureSampler(diffuse_path, size)
            specular = TextureSampler(specular_path, size)
            base_image = Image.new("RGBA", size)
            mr_image = Image.new("RGB", size)
            metal_range = [1.0, 0.0]
            for top in range(0, size[1], 128):
                box = (0, top, size[0], min(top + 128, size[1]))
                d = diffuse.rows(box) * diffuse_factor
                s = specular.rows(box)
                base, metal, rough = convert_pixels(d[..., :3], s[..., :3] * specular_factor, s[..., 3] * gloss_factor)
                rgba = np.empty(d.shape, dtype=np.uint8)
                rgba[..., :3] = np.rint(to_srgb(base) * 255).astype(np.uint8)
                rgba[..., 3] = np.rint(np.clip(d[..., 3], 0, 1) * 255).astype(np.uint8)
                mr = np.empty((*metal.shape, 3), dtype=np.uint8)
                mr[..., 0] = 255
                mr[..., 1] = np.rint(rough * 255).astype(np.uint8)
                mr[..., 2] = np.rint(metal * 255).astype(np.uint8)
                base_image.paste(Image.fromarray(rgba), (0, top))
                mr_image.paste(Image.fromarray(mr), (0, top))
                metal_range = [min(metal_range[0], float(metal.min())), max(metal_range[1], float(metal.max()))]
            diffuse.close()
            specular.close()
            base_uri = f"textures/baseColor_{index:03d}.png"
            mr_uri = f"textures/metallicRoughness_{index:03d}.png"
            base_image.save(output_dir / base_uri, compress_level=3)
            mr_image.save(output_dir / mr_uri, compress_level=3)
            base_image.close()
            mr_image.close()
            template = diffuse_info if diffuse_info is not None else specular_info
            pbr = {"baseColorTexture": add_texture(base_uri, template), "metallicRoughnessTexture": add_texture(mr_uri, template), "metallicFactor": 1, "roughnessFactor": 1}
            report["baked_materials"].append({"index": index, "name": material.get("name"), "size": size, "metallic_range": metal_range, "baseColor": base_uri, "metallicRoughness": mr_uri})
        material["pbrMetallicRoughness"] = pbr
        cache[key] = copy.deepcopy(pbr)
        if report["materials_converted"] % 10 == 0:
            print(f"Baked {report['materials_converted']}/234 spec/gloss materials", flush=True)

    # Copy only images still used by material slots, avoiding the original
    # duplicate PNG/DDS pairs and obsolete diffuse/specular images.
    infos = list(texture_infos(gltf["materials"]))
    texture_indices = sorted({info["index"] for info in infos})
    texture_remap = {old: new for new, old in enumerate(texture_indices)}
    gltf["textures"] = [gltf["textures"][index] for index in texture_indices]
    for info in infos:
        info["index"] = texture_remap[info["index"]]
    image_indices = sorted({texture["source"] for texture in gltf["textures"]})
    image_remap = {old: new for new, old in enumerate(image_indices)}
    for index in image_indices:
        if index in source_images:
            with Image.open(source_images[index]) as image:
                image.convert("RGBA").save(output_dir / gltf["images"][index]["uri"], compress_level=3)
    gltf["images"] = [gltf["images"][index] for index in image_indices]
    for texture in gltf["textures"]:
        texture["source"] = image_remap[texture["source"]]
    for material in gltf["materials"]:
        if not material.get("extensions"):
            material.pop("extensions", None)
    for field in ("extensionsUsed", "extensionsRequired"):
        gltf[field] = [ext for ext in gltf.get(field, []) if ext not in REMOVED]
        if not gltf[field]:
            gltf.pop(field, None)
    if report["emissive_materials_fixed"]:
        gltf.setdefault("extensionsUsed", []).append("KHR_materials_emissive_strength")
    gltf["asset"]["generator"] = "Bistro core MR bake (Khronos approximation)"
    output_path = output_dir / "bistro_metalrough.gltf"
    output_path.write_text(json.dumps(gltf, indent=2, allow_nan=False), encoding="utf-8")
    report["images"] = len(gltf["images"])
    report["textures"] = len(gltf["textures"])
    (output_dir / "conversion_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Baked {report['materials_converted']} materials; fixed {len(report['emissive_materials_fixed'])} emissive materials; wrote {output_path}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    project = Path(__file__).resolve().parents[1]
    parser.add_argument("--input", type=Path, default=project.parent / "niagara_bistro-source" / "bistro.gltf")
    parser.add_argument("--output", type=Path, default=project / "build" / "bistro")
    args = parser.parse_args()
    bake(args.input, args.output)
