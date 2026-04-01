"""SkepticalFox 2015-2024"""

# imports
from ctypes import c_uint32

# blender imports
from bl_math import clamp  # type: ignore
from mathutils import Vector  # type: ignore


def packNormal_tag3(unpacked: Vector) -> int:
    unpacked.normalize()
    x = clamp(unpacked.x, -1.0, 1.0)
    z = clamp(unpacked.y, -1.0, 1.0)
    y = clamp(unpacked.z, -1.0, 1.0)
    if x > 0.0:
        pkx = int(round(x * +127)) ^ 0b01111111
    else:
        pkx = (1 << 7) ^ int(round(x * -127))
    if y > 0.0:
        pky = int(round(y * +127)) ^ 0b01111111
    else:
        pky = (1 << 7) ^ int(round(y * -127))
    if z > 0.0:
        pkz = int(round(z * +127)) ^ 0b01111111
    else:
        pkz = (1 << 7) ^ int(round(z * -127))
    return c_uint32((pkx ^ 0b11111111) ^ ((pky ^ 0b11111111) << 8) ^ ((pkz ^ 0b11111111) << 16)).value


def packNormal(unpacked: Vector) -> int:
    unpacked.normalize()
    x = clamp(unpacked.x, -1.0, 1.0)
    z = clamp(unpacked.y, -1.0, 1.0)
    y = clamp(unpacked.z, -1.0, 1.0)
    return ((int(y * 511) & 0x3FF) << 22) | ((int(z * 1023) & 0x7FF) << 11) | (int(x * 1023.0) & 0x7FF)


def set_nodes(nodes: dict, elem, doc):
    for node_name, node in nodes.items():
        _node = doc.createElement("node")

        _identifier = doc.createElement("identifier")
        _identifier.appendChild(doc.createTextNode(node_name))
        _node.appendChild(_identifier)

        _transform = doc.createElement("transform")
        _row0 = doc.createElement("row0")
        _row1 = doc.createElement("row1")
        _row2 = doc.createElement("row2")
        _row3 = doc.createElement("row3")

        _row0.appendChild(doc.createTextNode("%f %f %f" % (node["scale"][0], 0.0, 0.0)))
        _row1.appendChild(doc.createTextNode("%f %f %f" % (0.0, node["scale"][1], 0.0)))
        _row2.appendChild(doc.createTextNode("%f %f %f" % (0.0, 0.0, node["scale"][2])))
        _row3.appendChild(doc.createTextNode("%f %f %f" % node["loc"]))

        _transform.appendChild(_row0)
        _transform.appendChild(_row1)
        _transform.appendChild(_row2)
        _transform.appendChild(_row3)

        _node.appendChild(_transform)

        set_nodes(node["children"], _node, doc)

        elem.appendChild(_node)
