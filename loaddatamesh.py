# -*- coding: utf-8 -*-
"""SkepticalFox 2015-2024 & Wotcuk (2026)"""

# imports
import logging
from struct import unpack

# blender imports
from mathutils import Vector  # type: ignore

# local imports
from .common import bwm_UnpackNormal_tag3, bwm_UnpackNormal


logger = logging.getLogger(__name__)


class LoadDataMesh:
    PrimitiveGroups = None
    uv2_list = None
    uv_list = None
    normal_list = None
    tangent_list = None
    binormal_list = None
    bones_info = None
    vertices = None
    indices = None
    __uv2_list = None
    packed_groups = None
    __pfile = None

    def __init__(self, filepath, vertices_name="", primitive_name="", uv2_name="", colour_name=""):
        self.__pfile = open(filepath, "rb")
        header = unpack("<I", self.__pfile.read(4))[0]
        assert header == 0x42A14E65
        self.__load_packed_section()
        
        # Load uv2 section if required
        if uv2_name != "":
            if self.packed_groups.get(uv2_name):
                self.__load_uv2(self.packed_groups[uv2_name]["position"], self.packed_groups[uv2_name]["length"])
                
        # Load color section if required
        self.colour_list = None
        if colour_name != "":
            if self.packed_groups.get(colour_name):
                self.__load_colour(self.packed_groups[colour_name]["position"], self.packed_groups[colour_name]["length"])
                
        # Load main geometry
        if vertices_name and primitive_name:
            self.__load_XYZNUV(self.packed_groups[primitive_name]["position"], self.packed_groups[vertices_name]["position"])
            
        self.__pfile.close()

    def __load_packed_section(self):
        self.__pfile.seek(-4, 2)
        table_start = unpack("<l", self.__pfile.read(4))[0]
        self.__pfile.seek(-4 - table_start, 2)
        position = 4
        self.packed_groups = {}
        while True:
            data = self.__pfile.read(4)
            if data is None or len(data) != 4:
                break
            section_size = unpack("<I", data)[0]
            data = self.__pfile.read(16)
            data = self.__pfile.read(4)
            if data is None or len(data) != 4:
                break
            section_name_length = unpack("<I", data)[0]
            section_name = self.__pfile.read(section_name_length).decode("utf-8")
            for item in ("vertices", "indices", "uv2", "colour"):
                if item in section_name:
                    self.packed_groups[section_name] = {"position": position, "length": section_size}
                    break
            position += section_size
            if section_size % 4 > 0:
                position += 4 - section_size % 4
            if section_name_length % 4 > 0:
                self.__pfile.read(4 - section_name_length % 4)

    def __load_XYZNUV(self, iposition, vposition):
        self.__pfile.seek(iposition)
        indexFormat = self.__pfile.read(64).split(b"\x00")[0].decode("utf-8")
        nIndices = unpack("<I", self.__pfile.read(4))[0]
        nTriangleGroups = unpack("<H", self.__pfile.read(2))[0]
        self.PrimitiveGroups = []

        UINT_LEN = 2
        if indexFormat == "list32":
            UINT_LEN = 4
        offset = nIndices * UINT_LEN + 72

        self.__pfile.seek(iposition + offset)
        for i in range(nTriangleGroups):
            startIndex = unpack("<I", self.__pfile.read(4))[0]
            nPrimitives = unpack("<I", self.__pfile.read(4))[0]
            startVertex = unpack("<I", self.__pfile.read(4))[0]
            nVertices = unpack("<I", self.__pfile.read(4))[0]
            self.PrimitiveGroups.append({"startIndex": startIndex, "nPrimitives": nPrimitives, "startVertex": startVertex, "nVertices": nVertices})

        self.__pfile.seek(vposition)
        vertices_subname = self.__pfile.read(64).split(b"\x00")[0].decode("utf-8")
        vertexFormat = ""
        flgNewFormat = False
        if "BPVT" in vertices_subname:
            flgNewFormat = True
            self.__pfile.read(4)
            vertexFormat = self.__pfile.read(64).split(b"\x00")[0].decode("utf-8")

        verticesCount = unpack("<l", self.__pfile.read(4))[0]
        pos = self.__pfile.tell()

        SIZE = 0

        is_skinned = False

        if vertexFormat == "set3/xyznuviiiwwtbpc":
            SIZE = 40
            UNPACK_FORMAT = "<3fI2f8B2I"
            is_skinned = True

        elif vertexFormat == "set3/xyznuvtbpc":
            SIZE = 32
            UNPACK_FORMAT = "<3fI2f2I"

        elif vertexFormat == "set3/xyznuvpc":
            SIZE = 24
            UNPACK_FORMAT = "<3fI2f"

        elif "xyznuvtb" in vertices_subname:
            SIZE = 32
            UNPACK_FORMAT = "<3fI2f2I"

        elif "xyznuviiiwwtb" in vertices_subname:
            SIZE = 37
            UNPACK_FORMAT = "<3fI2f5B2I"
            is_skinned = True

        elif "xyznuv" in vertices_subname:
            SIZE = 32
            UNPACK_FORMAT = "<8f"

        else:
            logger.error("vertexFormat=%s; vertices_subname=%s" % (vertexFormat, vertices_subname))

        old2new = {}
        vert_list = {}
        vidx = 0

        for i in range(verticesCount):
            self.__pfile.seek(pos)

            t, bn = None, None

            if is_skinned:
                if SIZE == 40:
                    # Parse 8 bytes for bone indices and weights
                    (x, z, y, n, u, v, *bone_raw, t, bn) = unpack(UNPACK_FORMAT, self.__pfile.read(SIZE))
                    IIIWW = tuple(bone_raw) 
                
                elif SIZE == 37:
                    # Parse 5 bytes for legacy bone structure
                    (x, z, y, n, u, v, *bone_raw, t, bn) = unpack(UNPACK_FORMAT, self.__pfile.read(SIZE))
                    IIIWW = tuple(bone_raw) 
                
                y = -y # Coordinate fix only for skinned models

            else:
                if SIZE == 32 and "xyznuvtb" not in vertices_subname:
                    (x, z, y, n0, n1, n2, u, v) = unpack(UNPACK_FORMAT, self.__pfile.read(SIZE))
                    n = Vector((n0, n1, n2))
                elif SIZE == 32:
                    (x, z, y, n, u, v, t, bn) = unpack(UNPACK_FORMAT, self.__pfile.read(SIZE))
                elif SIZE == 24:
                    (x, z, y, n, u, v) = unpack(UNPACK_FORMAT, self.__pfile.read(SIZE))
            XYZ = Vector((x, y, z))
            XYZ.freeze()

            if flgNewFormat:
                N = n if isinstance(n, Vector) else bwm_UnpackNormal_tag3(n)
                if t and bn:
                    T = bwm_UnpackNormal_tag3(t)
                    BN = bwm_UnpackNormal_tag3(bn)
                else:
                    T = Vector((0.0, 0.0, 0.0))
                    BN = Vector((0.0, 0.0, 0.0))
            else:
                N = n if isinstance(n, Vector) else bwm_UnpackNormal(n)
                if t and bn:
                    T = bwm_UnpackNormal(t)
                    BN = bwm_UnpackNormal(bn)
                else:
                    T = Vector((0.0, 0.0, 0.0))
                    BN = Vector((0.0, 0.0, 0.0))

            N.freeze()
            T.freeze()
            BN.freeze()

            UV = Vector((u, 1 - v))
            UV.freeze()

            if self.__uv2_list:
                XYZNUV2TB = (XYZ, N, UV, self.__uv2_list[i], T, BN)
            else:
                XYZNUV2TB = (XYZ, N, UV, T, BN)

            if is_skinned:
                XYZNUV2TB += (IIIWW,)
                
            # --- Pack Color Data ---
            if hasattr(self, "colour_raw_list") and self.colour_raw_list and i < len(self.colour_raw_list):
                XYZNUV2TB += (self.colour_raw_list[i],)
            else:
                # Fallback to white if no color found
                XYZNUV2TB += ((255, 255, 255, 255),)
                
            if XYZNUV2TB not in vert_list:
                old2new[i] = vidx
                vert_list[XYZNUV2TB] = vidx
                vidx += 1
            else:
                old2new[i] = vert_list[XYZNUV2TB]

            pos += SIZE

        vert_list = dict((v, k) for k, v in vert_list.items())
        vert_list = list(vert_list.values())

        # --- Dynamic Data Unpacking ---
        unpacked_data = list(zip(*vert_list))
        self.vertices = unpacked_data[0]
        self.normal_list = unpacked_data[1]
        self.uv_list = unpacked_data[2]

        idx = 3
        if self.__uv2_list:
            self.uv2_list = unpacked_data[idx]
            idx += 1

        self.tangent_list = unpacked_data[idx]
        self.binormal_list = unpacked_data[idx+1]
        idx += 2

        if is_skinned:
            self.bones_info = unpacked_data[idx]
            idx += 1

        # Extract color list if parsed
        if hasattr(self, "colour_raw_list") and self.colour_raw_list:
            self.colour_list = unpacked_data[idx]
        else:
            self.colour_list = None

        self.indices = []
        for group in self.PrimitiveGroups:
            self.__pfile.seek(iposition + group["startIndex"] * UINT_LEN + 72)
            for cnt in range(group["nPrimitives"]):
                if UINT_LEN == 2:
                    v1, v2, v3 = unpack("<3H", self.__pfile.read(6))
                elif UINT_LEN == 4:
                    v1, v2, v3 = unpack("<3I", self.__pfile.read(12))

                TRIANGLE = (old2new[v3], old2new[v2], old2new[v1])

                self.indices.append(TRIANGLE)

    def __load_uv2(self, uv2_position, uv2_length):
        self.__pfile.seek(uv2_position)

        try:
            uv2_subname = self.__pfile.read(64).split(b"\x00")[0].decode("utf-8")
        except Exception:
            self.__pfile.seek(uv2_position)
            uv2_subname = "uv2_None"

        uv2_format = ""
        if "BPVS" in uv2_subname:
            self.__pfile.read(4)
            uv2_format = self.__pfile.read(64).split(b"\x00")[0].decode("utf-8")

        if uv2_format == "set3/uv2pc":
            self.__uv2_list = []
            uv2_Count = unpack("<I", self.__pfile.read(4))[0]
            for i in range(uv2_Count):
                u, v = unpack("<2f", self.__pfile.read(8))
                UV2 = Vector((u, 1 - v))
                UV2.freeze()
                self.__uv2_list.append(UV2)

        elif uv2_subname == "uv2_None":
            self.__uv2_list = []
            for i in range(uv2_length // 8):
                u, v = unpack("<2f", self.__pfile.read(8))
                UV2 = Vector((u, 1 - v))
                UV2.freeze()
                self.__uv2_list.append(UV2)

        else:
            logger.error(f"Warning: {uv2_format=};{uv2_subname=}")
            
    def __load_colour(self, position, length):
        self.__pfile.seek(position)
        self.colour_raw_list = [] 
        
        try:
            header = self.__pfile.read(64).split(b"\x00")[0].decode("utf-8")
        except Exception:
            header = ""
            
        if "BPVS" in header:
            self.__pfile.read(4) # Padding
            self.__pfile.read(64) # 'colour' tag
            
        # BPVScolour blocks do not have a count parameter. 
        # Color count is calculated dynamically by dividing remaining bytes to 4 (RGBA)
        current_pos = self.__pfile.tell()
        remaining_bytes = length - (current_pos - position)
        color_count = remaining_bytes // 4
        
        for i in range(color_count):
            c_bytes = unpack("<4B", self.__pfile.read(4))
            self.colour_raw_list.append(c_bytes)