"""Coherent PBR image I/O and material-response integration for Trees 2.0.

Generated texture data should not depend on Blender's image-save refresh timing.
This module replaces procedural_pbr._new_image with a deterministic direct PNG
writer:

* color/albedo maps are written as 8-bit RGBA PNGs,
* non-color PBR maps are written as 16-bit RGBA PNGs,
* the file is written first and then loaded into Blender,
* source-map range statistics are stored on the Blender Image datablock,
* generated normal/height material-response metadata is consumed by the bark
  material builder.

Only this module owns the runtime patching for generated image I/O.  It replaces
the older pbr_data_runtime compatibility layer.
"""

import binascii
import struct
import zlib
from pathlib import Path

import bpy

try:
    import numpy as np
except Exception:  # pragma: no cover - Blender normally ships NumPy
    np = None

from . import generator, procedural_pbr


_PREVIOUS_NEW_IMAGE = None
_PREVIOUS_CREATE_BARK_MATERIAL = None
_INSTALLED = False

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(kind, payload):
    crc = binascii.crc32(kind)
    crc = binascii.crc32(payload, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _as_float_pixels(pixels, width, height):
    expected = int(width) * int(height) * 4
    if np is None:
        data = [float(value) for value in pixels]
        if len(data) != expected:
            raise ValueError(f"PBR pixel buffer has {len(data)} values; expected {expected}")
        return data

    try:
        # array('f') and other contiguous float32 buffers take this zero-copy path.
        values = np.frombuffer(memoryview(pixels), dtype=np.float32)
    except Exception:
        values = np.asarray(pixels, dtype=np.float32).reshape(-1)
    if values.size != expected:
        raise ValueError(f"PBR pixel buffer has {values.size} values; expected {expected}")
    values = np.nan_to_num(values, nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip(values, 0.0, 1.0).reshape((int(height), int(width), 4))


def _source_stats(pixel_data, non_color):
    """Return min/max/mean/std from meaningful RGB data before quantization."""
    if np is None:
        values = pixel_data[0::4] if non_color else [
            channel
            for index, channel in enumerate(pixel_data)
            if (index % 4) != 3
        ]
        if not values:
            return 0.0, 0.0, 0.0, 0.0
        lo = min(values)
        hi = max(values)
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return float(lo), float(hi), float(mean), float(variance ** 0.5)

    if non_color:
        values = pixel_data[..., 0]
    else:
        values = pixel_data[..., :3]
    return (
        float(values.min()),
        float(values.max()),
        float(values.mean()),
        float(values.std()),
    )


def _write_png(path, width, height, pixel_data, bit_depth):
    """Write a standards-compliant RGBA PNG without Blender image-save APIs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width = int(width)
    height = int(height)
    bit_depth = 16 if int(bit_depth) == 16 else 8

    compressor = zlib.compressobj(level=7)
    compressed_parts = []

    if np is not None:
        for y in range(height):
            row = pixel_data[y]
            if bit_depth == 16:
                # PNG stores 16-bit samples big-endian.
                quantized = np.rint(row * 65535.0).astype(">u2", copy=False)
            else:
                quantized = np.rint(row * 255.0).astype(np.uint8, copy=False)
            compressed_parts.append(compressor.compress(b"\x00" + quantized.tobytes()))
    else:
        stride = width * 4
        for y in range(height):
            source = pixel_data[y * stride:(y + 1) * stride]
            if bit_depth == 16:
                raw = bytearray(stride * 2)
                offset = 0
                for value in source:
                    q = max(0, min(65535, int(round(float(value) * 65535.0))))
                    raw[offset] = (q >> 8) & 0xFF
                    raw[offset + 1] = q & 0xFF
                    offset += 2
            else:
                raw = bytearray(max(0, min(255, int(round(float(value) * 255.0)))) for value in source)
            compressed_parts.append(compressor.compress(b"\x00" + bytes(raw)))

    compressed_parts.append(compressor.flush())
    compressed = b"".join(compressed_parts)
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, 6, 0, 0, 0)  # RGBA

    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(_PNG_SIGNATURE)
        handle.write(_png_chunk(b"IHDR", ihdr))
        handle.write(_png_chunk(b"IDAT", compressed))
        handle.write(_png_chunk(b"IEND", b""))
    temporary.replace(path)


def _replace_blender_image(name, filepath, non_color, pack, stats, bit_depth):
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old, do_unlink=True)

    image = bpy.data.images.load(str(filepath), check_existing=False)
    image.name = name
    image.filepath_raw = str(filepath)
    image["trees2_generated_pbr"] = True
    image["trees2_png_writer"] = "DIRECT_PNG_V2"
    image["trees2_png_bit_depth"] = int(bit_depth)
    image["trees2_map_min"] = float(stats[0])
    image["trees2_map_max"] = float(stats[1])
    image["trees2_map_mean"] = float(stats[2])
    image["trees2_map_std"] = float(stats[3])

    try:
        image.alpha_mode = "STRAIGHT"
    except Exception:
        pass
    if non_color:
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
    if pack:
        try:
            image.pack()
        except Exception:
            pass
    return image


def _new_image_direct(name, width, height, pixels, filepath, non_color=False, pack=False):
    """Unified generated-image writer used by bark and foliage synthesis."""
    data = _as_float_pixels(pixels, width, height)
    stats = _source_stats(data, bool(non_color))

    # Data maps need the extra precision; normal/height/AO/roughness can otherwise
    # quantize fine bark relief away. Albedo remains conventional 8-bit sRGB.
    bit_depth = 16 if non_color else 8
    _write_png(filepath, width, height, data, bit_depth)
    image = _replace_blender_image(name, filepath, bool(non_color), bool(pack), stats, bit_depth)

    # Make bad generator output obvious in Blender's console instead of silently
    # producing an apparently blank texture.
    dynamic_range = stats[1] - stats[0]
    if non_color and dynamic_range < 1.0e-5:
        print(
            f"[Trees2 PBR] WARNING: {name} is effectively flat "
            f"(min={stats[0]:.6f}, max={stats[1]:.6f}, std={stats[3]:.6f})"
        )
    else:
        print(
            f"[Trees2 PBR] {name}: {bit_depth}-bit PNG, "
            f"min={stats[0]:.4f}, max={stats[1]:.4f}, std={stats[3]:.4f}"
        )
    return image


def _image_float(image, key, default):
    if image is None:
        return float(default)
    try:
        return float(image.get(key, default))
    except Exception:
        return float(default)


def _create_bark_material_with_metadata(settings, suffix):
    """Apply generator-provided physical response without species hard-coding."""
    material = _PREVIOUS_CREATE_BARK_MATERIAL(settings, suffix)
    if material is None or not getattr(material, "use_nodes", False):
        return material

    nodes = material.node_tree.nodes

    normal_image = getattr(settings, "bark_normal_image", None)
    normal_node = nodes.get("Bark Normal Decode")
    if normal_node is not None:
        strength = _image_float(normal_image, "trees2_normal_node_strength", 0.30)
        socket = normal_node.inputs.get("Strength")
        if socket is not None:
            socket.default_value = max(0.0, min(2.0, strength))

    height_image = getattr(settings, "bark_height_image", None)
    bump = nodes.get("Bark Micro Height")
    if bump is not None:
        strength = _image_float(height_image, "trees2_bump_strength", 0.075)
        distance = _image_float(height_image, "trees2_bump_distance", 0.018)
        if bump.inputs.get("Strength") is not None:
            bump.inputs["Strength"].default_value = max(0.0, min(1.0, strength))
        if bump.inputs.get("Distance") is not None:
            bump.inputs["Distance"].default_value = max(0.0, min(0.25, distance))

    return material


def install():
    global _PREVIOUS_NEW_IMAGE, _PREVIOUS_CREATE_BARK_MATERIAL, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_NEW_IMAGE = procedural_pbr._new_image
    procedural_pbr._new_image = _new_image_direct

    # generator imports create_bark_material by value, so patch its bound symbol.
    _PREVIOUS_CREATE_BARK_MATERIAL = generator.create_bark_material
    generator.create_bark_material = _create_bark_material_with_metadata
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    procedural_pbr._new_image = _PREVIOUS_NEW_IMAGE
    generator.create_bark_material = _PREVIOUS_CREATE_BARK_MATERIAL
    _INSTALLED = False
