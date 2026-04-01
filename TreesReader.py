"""
Thanks Coffee_ for providing usefull informations about ctree format
"""

# imports
from dataclasses import dataclass
from pathlib import Path
from struct import unpack
from typing import IO

# blender imports
from mathutils import Vector  # type: ignore


def unp(arg: str, value: bytes):
    return unpack(arg, value)[0]


SINGLE_FORMAT = "normal"
TRIPLE_FORMAT = "triple"


@dataclass
class Vertex:
    position: Vector | None = None
    normal: Vector | None = None
    uv: Vector | None = None
    geomInfo: Vector | None = None
    index: Vector | None = None


@dataclass
class TreeObject:
    name: str
    vertices: list[Vertex]
    indices: list[list[int]]
    diffMap: Path
    normMap: Path
    indicesFormat: str


@dataclass
class Tree:
    objects: list[TreeObject]


class TreesReader:
    """Reads .ctree files"""

    @staticmethod
    def read(f: IO[bytes]) -> Tree:
        f.seek(36)

        # Prepare for objects
        objects = []

        # Each object has different properties
        names = ["stock", "branches", "leaves", "billboard"]
        vertices_sizes = [52, 52, 88, 68]
        formats = [SINGLE_FORMAT, SINGLE_FORMAT, TRIPLE_FORMAT, TRIPLE_FORMAT]

        # Read each object
        for _m in range(4):
            # First is vertice count
            vertices_count = unp("<I", f.read(4))
            vertices = []

            # Then read each vertex
            for i in range(vertices_count):
                data = f.read(vertices_sizes[_m])

                vert = Vertex()
                vert.position = Vector(unpack("<3f", data[0:12]))
                vert.normal = Vector(unpack("<3f", data[12:24]))
                vert.uv = Vector(unpack("<2f", data[24:32]))
                vert.uv.y = -vert.uv.y

                if _m == 3:
                    vert.uv = Vector(unpack("<2f", data[9 * 4 : 11 * 4]))
                    vert.uv.y = -vert.uv.y

                elif _m == 2:
                    vert.geomInfo = Vector(unpack("<2f", data[4 * 12 : 4 * 14]))
                    vert.vn = int(unp("<f", data[4 * 15 : 4 * 16]))

                vertices.append(vert)

            # Now, read number of lods for this object
            indices_lods = unp("<I", f.read(4))

            # Load indices for each lod
            lods = []
            for lod in range(indices_lods):
                indices_count = unp("<I", f.read(4))
                indices = unpack("<%dI" % indices_count, f.read(4 * indices_count))
                lods.append(indices)

            # Now load textures
            texture = Path(f.read(unp("<I", f.read(4))).decode("utf-8"))
            texture2 = Path(f.read(unp("<I", f.read(4))).decode("utf-8"))

            # Save to result, if there is anything to save
            if vertices:
                objects.append(TreeObject(names[_m], vertices, lods, texture, texture2, formats[_m]))

        return Tree(objects)
