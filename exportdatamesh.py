# -*- coding: utf-8 -*-
import os
from struct import pack
from mathutils import Vector, Matrix

class ExportDataMesh:
    """
    BigWorld Geometri Protokolü Yöneticisi (.primitives)
    Sadece üst dosyadan gelen parametrelere (Format, Uzay, Renk) göre veriyi standartlaştırır ve paketler.
    Tüm 64+(4)+64 BigWorld varyasyonlarını destekler.
    """
    
    def __init__(self, filepath, forced_filename):
        self.filepath = filepath
        self.forced_filename = forced_filename
        
        self.vertex_format = "set3/xyznuviiiwwtbpc" 
        self.coordinate_mode = "LOCAL" # "LOCAL" OR "GLOBAL"
        self.transform_matrix = None  
        self.export_vertex_colors = False


        self.processed_groups = []    # {'mat_name', 'startIndex', 'nPrimitives', 'startVertex', 'nVertices', 'indices': []}
        self.all_vertices_packed = [] 
        self.all_colors = []          

    def _get_padding(self, current_pos):
        return (4 - (current_pos % 4)) % 4

    def _pack_normal_int(self, n):
        """Vektörü 3-byte integer'a sıkıştırır."""
        if not hasattr(n, "x"): return 0x808080
        try:
            n = n.normalized()
            x, y, z = int((n.x + 1.0) * 127.5), int((n.y + 1.0) * 127.5), int((n.z + 1.0) * 127.5)
            return ((max(0, min(255, z)) & 0xFF) << 16) | ((max(0, min(255, y)) & 0xFF) << 8) | (max(0, min(255, x)) & 0xFF)
        except:
            return 0x808080

    def _process_bones(self, raw_bones):
        """Kemik indexlerini (*3) ve ağırlıklarını (Toplam 255) BigWorld standardına hazırlar."""
        if not raw_bones:
            return (0, 0, 0, 0, 0, 0, 0, 255)
            
        sorted_bones = sorted(raw_bones, key=lambda x: x[1], reverse=True)[:3]
        
        # BONE INDEX * 3 
        indices = [(b[0] * 3) for b in sorted_bones] + [0] * (3 - len(sorted_bones))
        
        # WEİGHT NORMALIZATION (255)
        raw_weights = [b[1] for b in sorted_bones]
        total_w = sum(raw_weights) if sum(raw_weights) > 0 else 1.0
        weights = [int(round((w / total_w) * 255.0)) for w in raw_weights] + [0] * (3 - len(raw_weights))
        
        diff = 255 - sum(weights)
        if diff != 0:
            weights[0] += diff
            
        return (indices[0], indices[1], indices[2], 0, 0, weights[1], weights[2], weights[0])

    def add_vertex(self, pos, norm, uv, bones=None, rgba=None, tang=None, binorm=None):
        """
        Ham veriyi alır, coordinate_mode durumuna göre uzay dönüşümünü yapar, 
        BigWorld (XZY) eksenine çevirip listeye ekler.
        """
        if self.coordinate_mode == "GLOBAL" and self.transform_matrix:
            final_pos = self.transform_matrix @ pos
            final_norm = self.transform_matrix.to_3x3() @ norm if hasattr(norm, "x") else norm
            final_tang = self.transform_matrix.to_3x3() @ tang if hasattr(tang, "x") else tang
            final_binorm = self.transform_matrix.to_3x3() @ binorm if hasattr(binorm, "x") else binorm
        else:
            final_pos = pos
            final_norm = norm
            final_tang = tang
            final_binorm = binorm
        bw_pos = (final_pos[0], final_pos[2], final_pos[1])
        bw_norm = Vector((final_norm[0], final_norm[2], final_norm[1])).normalized() if hasattr(final_norm, "x") else None
        norm_packed = self._pack_normal_int(bw_norm)
        tang_packed = binorm_packed = 0x808080
        if hasattr(final_tang, "x") and hasattr(final_binorm, "x"):
            bw_tang = Vector((final_tang[0], final_tang[2], -final_tang[1])).normalized() # Y ekseni taklası
            bw_binorm = bw_norm.cross(bw_tang).normalized()
            tang_packed = self._pack_normal_int(bw_tang)
            binorm_packed = self._pack_normal_int(bw_binorm)
        bw_bones = self._process_bones(bones)
        bw_u, bw_v = uv[0], 1.0 - uv[1] 
        if self.export_vertex_colors:
            if rgba:
                b_val = max(0, min(255, int(rgba[2] * 255.0)))
                g_val = max(0, min(255, int(rgba[1] * 255.0)))
                r_val = max(0, min(255, int(rgba[0] * 255.0)))
                a_val = max(0, min(255, int(rgba[3] * 255.0)))
                self.all_colors.append((b_val, g_val, r_val, a_val))
            else:
                self.all_colors.append((0, 0, 0, 0))
        v_entry = (*bw_pos, norm_packed, bw_u, bw_v, *bw_bones, tang_packed, binorm_packed)
        self.all_vertices_packed.append(v_entry)
        
        return len(self.all_vertices_packed) - 1
    def _pack_xyz(self, v): 
        return pack('<3f', *v[:3]) # Pos (12b)

    def _pack_xyznuvpc(self, v): 
        return pack('<3fI2f', *v[:6]) # Pos, Norm, UV (24b)

    def _pack_xyznuviiiwwpc(self, v): 
        return pack('<3fI2f8B', *v[:6], *v[6:14]) # Pos, Norm, UV, Bones (32b)

    def _pack_xyznuvtbpc(self, v): 
        return pack('<3fI2f2I', *v[:6], v[14], v[15]) # Pos, Norm, UV, Tang, Binorm (32b)

    def _pack_xyznuvitbpc(self, v): 
        # Sadece 1. kemik indexini alır, 3 byte sıfır ile doldurur, Tang, Binorm (36b)
        return pack('<3fI2fB3b2I', *v[:6], v[6], 0, 0, 0, v[14], v[15])

    def _pack_xyznuviiiwwtbpc(self, v): 
        return pack('<3fI2f8B2I', *v[:6], *v[6:14], v[14], v[15]) #(40b)

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
        v_count = len(self.all_vertices_packed)
        i_count = sum(len(g['indices']) for g in self.processed_groups)

        with open(self.filepath, 'wb') as f:
            f.write(pack('<I', 0x42a14e65)) # MAGIC
            
            # --- 1. INDICES ---
            start_i = f.tell()
            is_large = v_count > 65535
            f.write(pack('64s', b'list32' if is_large else b'list'))
            f.write(pack('<II', i_count, len(self.processed_groups)))
            for g in self.processed_groups:
                for idx in g['indices']: 
                    f.write(pack('<I' if is_large else '<H', idx))
            for g in self.processed_groups:
                f.write(pack('<4I', g['startIndex'], len(g['indices'])//3, g['startVertex'], g['nVertices']))
            
            f.write(b'\x00' * self._get_padding(f.tell()))
            size_i = f.tell() - start_i
            
            # --- 2. VERTICES ---
            start_v = f.tell()
            f.write(pack('64s', magic)); f.write(pack('<I', 0))
            f.write(pack('64s', section)); f.write(pack('<I', v_count))
            for v in self.all_vertices_packed: 
                f.write(packer(v))
                
            f.write(b'\x00' * self._get_padding(f.tell()))
            size_v = f.tell() - start_v
            
            # --- 3. BPVScolour ---
            start_c = size_c = 0
            if self.export_vertex_colors and self.all_colors:
                start_c = f.tell()
                f.write(pack('64s', b'BPVScolour'))
                f.write(pack('<I', 0)); f.write(pack('64s', b'colour'))
                for c in self.all_colors: 
                    f.write(pack('4B', *c))
                    
                f.write(b'\x00' * self._get_padding(f.tell()))
                size_c = f.tell() - start_c

            # --- 4. TOC (Table of Contents) ---
            toc_data = b''
            v_name = "vertices"
            i_name = "indices"
            sections = [
                (i_name, start_i, size_i), 
                (v_name, start_v, size_v)
            ]
            if start_c > 0: 
                sections.append(("colour", start_c, size_c))
            
            for name, offset, size in sections:
                nb = name.encode('utf-8')
                pad = self._get_padding(len(nb))
                toc_data += pack('<II12sI', size, offset, b'\x00'*12, len(nb))
                toc_data += nb + (b'\x00' * pad)
                
            f.write(toc_data)
            f.write(pack('<I', len(toc_data)))