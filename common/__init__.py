"""SkepticalFox 2015-2024"""

# blender imports
from mathutils import Vector  # type: ignore


def utils_AsVector(vector_str: str) -> Vector:
    return Vector(tuple(map(float, vector_str.strip().split())))


def bwm_UnpackNormal(packed: int) -> Vector:
    pky = (packed >> 22) & 0x1FF
    pkz = (packed >> 11) & 0x3FF
    pkx = packed & 0x3FF
    x = pkx / 1023.0
    if pkx & (1 << 10):
        x = -x
    y = pky / 511.0
    if pky & (1 << 9):
        y = -y
    z = pkz / 1023.0
    if pkz & (1 << 10):
        z = -z
    return Vector((x, z, y))


def bwm_UnpackNormal_tag3(packed: int) -> Vector:
    pkz = (packed >> 16) & 0xFF ^ 0xFF
    pky = (packed >> 8) & 0xFF ^ 0xFF
    pkx = packed & 0xFF ^ 0xFF
    if pkx > 0x7F:
        x = -float(pkx & 0x7F) / 0x7F
    else:
        x = float(pkx ^ 0x7F) / 0x7F
    if pky > 0x7F:
        y = -float(pky & 0x7F) / 0x7F
    else:
        y = float(pky ^ 0x7F) / 0x7F
    if pkz > 0x7F:
        z = -float(pkz & 0x7F) / 0x7F
    else:
        z = float(pkz ^ 0x7F) / 0x7F
    return Vector((x, z, y))
