# -*- coding: utf-8 -*-
import os
from struct import pack
from mathutils import Vector, Matrix

class ExportDataMesh:
    """
    BigWorld Geometry Protocol Manager (.primitives)
    MULTI-MESH SUPPORT HAS BEEN ADDED. (Multi-RenderSet)
    """
    
    def __init__(self, filepath, forced_filename):
        self.filepath = filepath
        self.forced_filename = forced_filename
        
        self.vertex_format = "set3/xyznuviiiwwtbpc" 
        self.coordinate_mode = "LOCAL" 
        self.transform_matrix = None  
        self.export_vertex_colors = False

        self.meshes = {} 
        self.current_mesh = None

    def add_mesh_section(self, mesh_name):
        """Opens an isolated memory block for a new mesh object."""
        clean_name = mesh_name.replace(".", "_")
        self.current_mesh = clean_name
        self.meshes[clean_name] = {
            'groups': [],
            'vertices': [],
            'colors': []
        }

    def _get_padding(self, current_pos):
        return (4 - (current_pos % 4)) % 4

    def _pack_normal_int(self, n):
        if not hasattr(n, "x"): return 0x808080
        try:
            n = n.normalized()
            x, y, z = int((n.x + 1.0) * 127.5), int((n.y + 1.0) * 127.5), int((n.z + 1.0) * 127.5)
            return ((max(0, min(255, z)) & 0xFF) << 16) | ((max(0, min(255, y)) & 0xFF) << 8) | (max(0, min(255, x)) & 0xFF)
        except:
            return 0x808080

    def _process_bones(self, raw_bones):
        if not raw_bones:
            return (0, 0, 0, 0, 0, 0, 0, 255)
            
        sorted_bones = sorted(raw_bones, key=lambda x: x[1], reverse=True)[:3]
        indices = [(b[0] * 3) for b in sorted_bones] + [0] * (3 - len(sorted_bones))
        raw_weights = [b[1] for b in sorted_bones]
        total_w = sum(raw_weights) if sum(raw_weights) > 0 else 1.0
        weights = [int(round((w / total_w) * 255.0)) for w in raw_weights] + [0] * (3 - len(raw_weights))
        
        diff = 255 - sum(weights)
        if diff != 0: weights[0] += diff
            
        return (indices[0], indices[1], indices[2], 0, 0, weights[1], weights[2], weights[0])

    def add_vertex(self, pos, norm, uv, bones=None, rgba=None, tang=None, binorm=None):
        if self.coordinate_mode == "GLOBAL" and self.transform_matrix:
            final_pos = self.transform_matrix @ pos
            final_norm = self.transform_matrix.to_3x3() @ norm if hasattr(norm, "x") else norm
            final_tang = self.transform_matrix.to_3x3() @ tang if hasattr(tang, "x") else tang
            final_binorm = self.transform_matrix.to_3x3() @ binorm if hasattr(binorm, "x") else binorm
        else:
            final_pos, final_norm, final_tang, final_binorm = pos, norm, tang, binorm
            
        bw_pos = (final_pos[0], final_pos[2], final_pos[1])
        bw_norm = Vector((final_norm[0], final_norm[2], final_norm[1])).normalized() if hasattr(final_norm, "x") else None
        norm_packed = self._pack_normal_int(bw_norm)
        tang_packed = binorm_packed = 0x808080
        
        if hasattr(final_tang, "x") and hasattr(final_binorm, "x"):
            bw_tang = Vector((final_tang[0], final_tang[2], -final_tang[1])).normalized() 
            bw_binorm = bw_norm.cross(bw_tang).normalized()
            tang_packed = self._pack_normal_int(bw_tang)
            binorm_packed = self._pack_normal_int(bw_binorm)
            
        bw_bones = self._process_bones(bones)
        bw_u, bw_v = uv[0], 1.0 - uv[1] 
        
        if self.export_vertex_colors:
            if rgba:
                self.meshes[self.current_mesh]['colors'].append((
                    max(0, min(255, int(rgba[2] * 255.0))),
                    max(0, min(255, int(rgba[1] * 255.0))),
                    max(0, min(255, int(rgba[0] * 255.0))),
                    max(0, min(255, int(rgba[3] * 255.0)))
                ))
            else:
                self.meshes[self.current_mesh]['colors'].append((0, 0, 0, 0))
                
        v_entry = (*bw_pos, norm_packed, bw_u, bw_v, *bw_bones, tang_packed, binorm_packed)
        self.meshes[self.current_mesh]['vertices'].append(v_entry)
        
        return len(self.meshes[self.current_mesh]['vertices']) - 1

    def _pack_xyz(self, v): return pack('<3f', *v[:3])
    def _pack_xyznuvpc(self, v): return pack('<3fI2f', *v[:6])
    def _pack_xyznuviiiwwpc(self, v): return pack('<3fI2f8B', *v[:6], *v[6:14])
    def _pack_xyznuvtbpc(self, v): return pack('<3fI2f2I', *v[:6], v[14], v[15])
    def _pack_xyznuvitbpc(self, v): return pack('<3fI2fB3b2I', *v[:6], v[6], 0, 0, 0, v[14], v[15])
    def _pack_xyznuviiiwwtbpc(self, v): return pack('<3fI2f8B2I', *v[:6], *v[6:14], v[14], v[15])

    def export(self):
        fmt_map = {
            "xyz":                  (b'BPVTxyz',           b'xyz',                  self._pack_xyz),
            "set3/xyznuvpc":        (b'BPVTxyznuv',        b'set3/xyznuvpc',        self._pack_xyznuvpc),
            "set3/xyznuviiiwwpc":   (b'BPVTxyznuviiiww',   b'set3/xyznuviiiwwpc',   self._pack_xyznuviiiwwpc),
            "set3/xyznuvtbpc":      (b'BPVTxyznuvtb',      b'set3/xyznuvtbpc',      self._pack_xyznuvtbpc),
            "set3/xyznuvitbpc":     (b'BPVTxyznuvitb',     b'set3/xyznuvitbpc',     self._pack_xyznuvitbpc),
            "set3/xyznuviiiwwtbpc": (b'BPVTxyznuviiiwwtb', b'set3/xyznuviiiwwtbpc', self._pack_xyznuviiiwwtbpc)
        }

        if self.vertex_format not in fmt_map:
            raise ValueError(f"Desteklenmeyen Vertex Formatı: {self.vertex_format}")

        magic, section, packer = fmt_map[self.vertex_format]

        with open(self.filepath, 'wb') as f:
            f.write(pack('<I', 0x42a14e65)) # MAGIC
            
            toc_sections = []

            for m_name, m_data in self.meshes.items():
                v_count = len(m_data['vertices'])
                i_count = sum(len(g['indices']) for g in m_data['groups'])

                # --- 1. INDICES ---
                start_i = f.tell()
                is_large = v_count > 65535
                f.write(pack('64s', b'list32' if is_large else b'list'))
                f.write(pack('<II', i_count, len(m_data['groups'])))
                
                for g in m_data['groups']:
                    for idx in g['indices']: f.write(pack('<I' if is_large else '<H', idx))
                for g in m_data['groups']:
                    f.write(pack('<4I', g['startIndex'], len(g['indices'])//3, g['startVertex'], g['nVertices']))
                
                f.write(b'\x00' * self._get_padding(f.tell()))
                size_i = f.tell() - start_i
                
                # --- 2. VERTICES ---
                start_v = f.tell()
                f.write(pack('64s', magic)); f.write(pack('<I', 0))
                f.write(pack('64s', section)); f.write(pack('<I', v_count))
                for v in m_data['vertices']: f.write(packer(v))
                    
                f.write(b'\x00' * self._get_padding(f.tell()))
                size_v = f.tell() - start_v
                
                # --- 3. BPVScolour ---
                start_c = size_c = 0
                if self.export_vertex_colors and m_data['colors']:
                    start_c = f.tell()
                    f.write(pack('64s', b'BPVScolour'))
                    f.write(pack('<I', 0)); f.write(pack('64s', b'colour'))
                    for c in m_data['colors']: f.write(pack('4B', *c))
                        
                    f.write(b'\x00' * self._get_padding(f.tell()))
                    size_c = f.tell() - start_c
                
                if m_name == "vertices":
                    sec_indices = "indices"
                    sec_vertices = "vertices"
                    sec_colour = "colour"
                else:
                    sec_indices = f"{m_name}.indices"
                    sec_vertices = f"{m_name}.vertices"
                    sec_colour = f"{m_name}.colour"

                toc_sections.append((sec_indices, start_i, size_i))
                toc_sections.append((sec_vertices, start_v, size_v))
                if start_c > 0: 
                    toc_sections.append((sec_colour, start_c, size_c))

            # --- 4. TOC -
            toc_data = b''
            for name, offset, size in toc_sections:
                nb = name.encode('utf-8')
                pad = self._get_padding(len(nb))
                toc_data += pack('<II12sI', size, offset, b'\x00'*12, len(nb))
                toc_data += nb + (b'\x00' * pad)
                
            f.write(toc_data)
            f.write(pack('<I', len(toc_data)))