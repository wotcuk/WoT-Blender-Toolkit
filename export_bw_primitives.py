import os
import subprocess
from struct import pack
from xml.dom.minidom import getDOMImplementation
import bpy
import math
from mathutils import Vector, Matrix, Euler

# --- Smart Name and Path Resolver ---
def get_universal_config(obj, export_path, export_info):
    # Get original filename from export_info (passed from __init__.py)
    original_filename = export_info.get("original_filename", "")
    
    lower_name = obj.name.lower()
    if "gun" in lower_name:
        forced_filename, part_suffix = "Gun_01", "guns" 
    elif "turret" in lower_name:
        forced_filename, part_suffix = "Turret_01", "turret_01"
    elif "hull" in lower_name:
        forced_filename, part_suffix = "Hull", "hull"
    elif "chassis" in lower_name:
        forced_filename, part_suffix = "Chassis", "chassis"
    else:
        forced_filename = obj.name.split('.')[0]
        part_suffix = forced_filename.lower()

    # Use original filename if it exists in custom properties
    if original_filename:
        forced_filename = original_filename

    normalized_path = export_path.replace('\\', '/')
    tank_base_path = "vehicles/american/A191_Ares_90_C" 
    tank_pure_name = "Ares_90_C" 

    if 'vehicles/' in normalized_path:
        try:
            parts = normalized_path.split('vehicles/')[-1] 
            path_segments = parts.split('/')
            if len(path_segments) >= 2:
                nation, tank_folder = path_segments[0], path_segments[1]
                tank_base_path = f"vehicles/{nation}/{tank_folder}"
                tank_pure_name = tank_folder.split('_', 1)[1] if '_' in tank_folder else tank_folder
        except: pass 

    texture_basename = f"{tank_pure_name}_{part_suffix}"
    return forced_filename, texture_basename, tank_base_path

ROTATION_OFFSET_X = ROTATION_OFFSET_Y = ROTATION_OFFSET_Z = 0.0    

# --- Visual Property Definitions ---
try:
    from .common.consts import visual_property_descr_dict
    from .common.export_utils import set_nodes
except ImportError:
    class VisualProp:
        def __init__(self, t): self.type = t
    visual_property_descr_dict = {
        'normalMap': VisualProp('Texture'), 'metallicGlossMap': VisualProp('Texture'),
        'diffuseMap': VisualProp('Texture'), 'doubleSided': VisualProp('Bool'),
        'alphaReference': VisualProp('Int'), 'alphaTestEnable': VisualProp('Bool'),
        'metallicDetailMap': VisualProp('Texture'), 'g_detailUVTiling': VisualProp('Vector4'),
        'g_detailParams': VisualProp('Vector4'), 'g_useDetailMetallic': VisualProp('Bool'),
        'g_heatMap': VisualProp('Texture'), 'g_heatColorGradient': VisualProp('Texture'),
        'g_heatEmissionCoefficient': VisualProp('Float'), 'colorIdMap': VisualProp('Texture'),
        'g_useNormalPackDXT1': VisualProp('Bool')
    }

def set_nodes(nodes, elem, doc):
    if not nodes: return
    from mathutils import Matrix
    for name, data in nodes.items():
        node_elem = doc.createElement('node')
        ident = doc.createElement('identifier'); ident.appendChild(doc.createTextNode(name))
        node_elem.appendChild(ident); transform = doc.createElement('transform')
        
        m_list = data.get("matrix", [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
        m = Matrix(m_list)
        
        C = Matrix((
            (1, 0, 0, 0),
            (0, 0, 1, 0),
            (0, 1, 0, 0),
            (0, 0, 0, 1)
        ))
        
        m_bw = C @ m @ C.inverted()
    
        rows = []
        for i in range(4):
            v = m_bw.col[i]
            rows.append(f"{v.x:.6f} {v.y:.6f} {v.z:.6f}")
            
        for i, row_txt in enumerate(rows):
            row = doc.createElement(f'row{i}'); row.appendChild(doc.createTextNode(row_txt))
            transform.appendChild(row)
            
        node_elem.appendChild(transform); elem.appendChild(node_elem)
        if 'children' in data: set_nodes(data['children'], node_elem, doc)

def get_real_mesh_objects(selected_objs):
    if not selected_objs: return []
    if not isinstance(selected_objs, list): selected_objs = [selected_objs]
    return [o for o in selected_objs if hasattr(o, 'type') and o.type == 'MESH']

def pack_normal_int(n):
    try:
        n = n.normalized()
        x, y, z = int((n.x + 1.0) * 127.5), int((n.y + 1.0) * 127.5), int((n.z + 1.0) * 127.5)
        return ((max(0, min(255, z)) & 0xFF) << 16) | ((max(0, min(255, y)) & 0xFF) << 8) | (max(0, min(255, x)) & 0xFF)
    except: return 0x808080 

def convert_png_to_dds(png_path):
    """Converts PNG to DDS using Texconv with appropriate compression."""
    addon_dir = os.path.dirname(__file__)
    texconv_path = os.path.join(addon_dir, "texconv.exe")
    
    if not os.path.exists(texconv_path):
        print(f"[Warning] texconv.exe not found! Leaving as PNG: {png_path}")
        return False
        
    try:
        # Use BC7 for Normals to preserve Blue/Alpha channels, BC1 for others
        if "_anm" in png_path.lower():
            format_arg = "BC7_UNORM" 
        else:
            format_arg = "BC1_UNORM"
            
        subprocess.run(
            [texconv_path, "-f", format_arg, "-y", "-o", os.path.dirname(png_path), png_path],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            check=True
        )
        
        if os.path.exists(png_path):
            os.remove(png_path)
        return True
    except Exception as e:
        print(f"[Error] DDS Conversion Failed ({png_path}): {e}")
        return False

class BigWorldModelExporter:
    def export(self, export_obj, model_filepath: str, export_info: dict):
        mesh_objs = get_real_mesh_objects(export_obj)
        if not mesh_objs: raise RuntimeError("No valid Mesh objects found!")
        
        FORCED_FILENAME, TEXTURE_BASENAME, TANK_BASE_PATH = get_universal_config(mesh_objs[0], model_filepath, export_info)
        
        all_bone_names = set()
        for o in mesh_objs:
            for vg in o.vertex_groups:
                if "blendbone" in vg.name.lower(): all_bone_names.add(vg.name)
        bone_palette = sorted(list(all_bone_names), reverse=True)

        dir_name = os.path.dirname(model_filepath)
        final_model_path, final_visual_path, final_primitives_path = [os.path.join(dir_name, FORCED_FILENAME + ext) for ext in [".model", ".visual_processed", ".primitives_processed"]]

        processed_groups, all_vertices_flat, all_colors_flat = [], [], []
        global_v_offset = global_i_offset = 0
        global_has_colors = False
        bb_min, bb_max = Vector((99999.0, 99999.0, 99999.0)), Vector((-99999.0, -99999.0, -99999.0))

        for obj in mesh_objs:
            vg_id_map = {vg.index: bone_palette.index(vg.name) for vg in obj.vertex_groups if vg.name in bone_palette}
            mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
            mesh.calc_loop_triangles()
            if mesh.uv_layers.active:
                try: mesh.calc_tangents()
                except: pass 
            uv_layer = mesh.uv_layers.active.data[:] if mesh.uv_layers.active else None
            
            root_matrix = export_info.get("root_matrix", Matrix())
            root_inv_matrix = root_matrix.inverted()
            user_rot = Euler((math.radians(ROTATION_OFFSET_X), 0, 0), 'XYZ').to_matrix().to_4x4()
            
            # Keep final_matrix in World space for skinned models to prevent distortion
            final_matrix = user_rot @ obj.matrix_world
            rotation_matrix = final_matrix.to_3x3()

            # --- Color Attribute Detection ---
            target_color_name = None
            color_layer = None
            if obj.data.color_attributes and obj.data.color_attributes.active:
                target_color_name = obj.data.color_attributes.active.name
            elif obj.data.color_attributes and len(obj.data.color_attributes) > 0:
                target_color_name = obj.data.color_attributes[0].name

            if target_color_name and target_color_name in obj.data.attributes:
                color_layer = obj.data.attributes[target_color_name]
            elif 'BPVScolour' in obj.data.attributes:
                color_layer = obj.data.attributes['BPVScolour']
            elif 'colour' in obj.data.attributes:
                color_layer = obj.data.attributes['colour']
                
            color_data_flat = []
            color_domain = 'POINT'
            
            if color_layer:
                global_has_colors = True
                color_domain = color_layer.domain
                count = len(obj.data.loops) if color_domain == 'CORNER' else len(obj.data.vertices)
                color_data_flat = [1.0] * (count * 4) 
                try:
                    color_layer.data.foreach_get("color", color_data_flat)
                except: pass
            
            tris_by_mat = {}
            for tri in mesh.loop_triangles: tris_by_mat.setdefault(tri.material_index, []).append(tri)
            
            for mat_idx in sorted(tris_by_mat.keys()):
                bmat = mesh.materials[mat_idx] if mat_idx < len(mesh.materials) else None
                mat_name = bmat.name if bmat else f"mat_{mat_idx}"
                fx_path = "shaders/std_effects/PBS_tank_skinned.fx"
                
                group_data = {
                    'mat_name': mat_name,
                    'bmat': bmat, 
                    'fx': fx_path,
                    'vertices': [], 'indices': [], 'colors': [], 'startVertex': global_v_offset, 'startIndex': global_i_offset
                }
                local_v_cache = {} 
                for tri in tris_by_mat[mat_idx]:
                    for loop_idx in reversed(tri.loops):
                        loop_data, vert = mesh.loops[loop_idx], mesh.vertices[mesh.loops[loop_idx].vertex_index]
                        
                        world_co = final_matrix @ vert.co
                        world_n = rotation_matrix @ loop_data.normal

                        # Get vertex colors if available
                        if global_has_colors and color_data_flat:
                            idx = loop_idx if color_domain == 'CORNER' else vert.index
                            base_i = idx * 4
                            r, g, b, a = color_data_flat[base_i:base_i+4]
                            rgba = (max(0, min(255, int(b * 255.0))), 
                                    max(0, min(255, int(g * 255.0))), 
                                    max(0, min(255, int(r * 255.0))), 
                                    max(0, min(255, int(a * 255.0))))
                        else:
                            rgba = (0, 0, 0, 0)

                        bone_name = None
                        main_bone_idx = 0
                        if vert.groups:
                            g_list = sorted(vert.groups, key=lambda g: g.weight, reverse=True)[:1]
                            if g_list and g_list[0].group in vg_id_map:
                                main_bone_idx = vg_id_map[g_list[0].group]
                                bone_name = bone_palette[main_bone_idx]
                        
                        bone_obj = bpy.data.objects.get(bone_name) if bone_name else None

                        if bone_obj:
                            valid_groups = []
                            if vert.groups:
                                g_list = sorted(vert.groups, key=lambda g: g.weight, reverse=True)
                                valid_groups = [g for g in g_list if g.group in vg_id_map][:3]
                            
                            # Filter active weights > 0
                            active_groups = [g for g in valid_groups if g.weight > 0.0]
                            
                            # Multiple Bone Blend Logic (Matrix Interpolation)
                            if len(active_groups) > 1:
                                total_weight = sum(g.weight for g in active_groups)
                                blended_mat = Matrix(((0.0,0.0,0.0,0.0),(0.0,0.0,0.0,0.0),(0.0,0.0,0.0,0.0),(0.0,0.0,0.0,0.0)))
                                
                                for g in active_groups:
                                    b_idx = vg_id_map[g.group]
                                    b_obj = bpy.data.objects.get(bone_palette[b_idx])
                                    w_ratio = g.weight / total_weight
                                    mat = b_obj.matrix_world if b_obj else Matrix()
                                    blended_mat += mat * w_ratio
                                
                                try: inv_m = blended_mat.inverted()
                                except:
                                    fallback_obj = bpy.data.objects.get(bone_palette[vg_id_map[active_groups[0].group]])
                                    inv_m = fallback_obj.matrix_world.inverted() if fallback_obj else Matrix()
                                    
                                local_co = inv_m @ world_co
                                local_n = inv_m.to_3x3() @ world_n
                                if local_n.length > 0.0001: local_n.normalize()
                                    
                            else: # Single Bone Logic
                                p_bone_name = bone_name
                                if active_groups: p_bone_name = bone_palette[vg_id_map[active_groups[0].group]]
                                elif valid_groups: p_bone_name = bone_palette[vg_id_map[valid_groups[0].group]]
                                    
                                p_bone_obj = bpy.data.objects.get(p_bone_name) if p_bone_name else None
                                if p_bone_obj:
                                    inv_m = p_bone_obj.matrix_world.inverted()
                                    local_co, local_n = inv_m @ world_co, inv_m.to_3x3() @ world_n
                                else: # Static fallback to scene root
                                    local_co, local_n = root_inv_matrix @ world_co, root_inv_matrix.to_3x3() @ world_n
                        else:
                            local_co, local_n = root_inv_matrix @ world_co, root_inv_matrix.to_3x3() @ world_n

                        pos_bw = (local_co.x, local_co.z, local_co.y) 
                        n_bw = Vector((local_n.x, local_n.z, local_n.y)).normalized()

                        for i in range(3):
                            bb_min[i], bb_max[i] = min(bb_min[i], pos_bw[i] - 0.01), max(bb_max[i], pos_bw[i] + 0.01)

                        n_packed = pack_normal_int(n_bw)
                        t_packed = b_packed = 0x808080
                        if uv_layer:
                            t_bw = (rotation_matrix @ loop_data.tangent).normalized()
                            t_bw = Vector((t_bw.x, t_bw.z, -t_bw.y)).normalized()
                            b_bw = n_bw.cross(t_bw).normalized()
                            t_packed, b_packed = pack_normal_int(t_bw), pack_normal_int(b_bw)

                        u, v = uv_layer[loop_idx].uv if uv_layer else (0.0, 0.0)
                        
                        # --- 3-Bone Skinning Logic ---
                        bone_indices = [0, 0, 0]
                        bone_weights = [0, 0, 0]
                        
                        if vert.groups:
                            g_list = sorted(vert.groups, key=lambda g: g.weight, reverse=True)
                            v_groups = [g for g in g_list if g.group in vg_id_map][:3]
                            t_weight = sum(g.weight for g in v_groups)
                            
                            if t_weight > 0:
                                for i, g in enumerate(v_groups):
                                    bone_indices[i] = vg_id_map[g.group] * 3
                                    bone_weights[i] = int(round((g.weight / t_weight) * 255.0))
                                
                                # Ensure weight sum equals exactly 255
                                diff = 255 - sum(bone_weights)
                                if diff != 0: bone_weights[0] += diff
                            else: bone_weights[0] = 255
                        else: bone_weights[0] = 255
                            
                        bone_bytes = (bone_indices[0], bone_indices[1], bone_indices[2], 0, 0, 
                                      bone_weights[1], bone_weights[2], bone_weights[0])
                        
                        v_cache_key = (*pos_bw, n_packed, u, 1.0-v, *bone_bytes, t_packed, b_packed, rgba)
                        v_data = (*pos_bw, n_packed, u, 1.0-v, *bone_bytes, t_packed, b_packed)
                        
                        if v_cache_key not in local_v_cache:
                            local_v_cache[v_cache_key] = len(group_data['vertices'])
                            group_data['vertices'].append(v_data)
                            if global_has_colors: group_data['colors'].append(rgba)
                        group_data['indices'].append(local_v_cache[v_cache_key] + global_v_offset)

                group_data['nVertices'], group_data['nPrimitives'] = len(group_data['vertices']), len(group_data['indices']) // 3
                processed_groups.append(group_data); all_vertices_flat.extend(group_data['vertices'])
                all_colors_flat.extend(group_data['colors'])
                global_v_offset += len(group_data['vertices']); global_i_offset += len(group_data['indices'])

        # --- Binary Export (.primitives) ---
        if export_info.get("export_models", True):
            with open(final_primitives_path, 'wb') as f:
                f.write(pack('<I', 0x42a14e65))
                start_i = f.tell(); is_large = global_v_offset > 65535
                f.write(pack('64s', b'list32' if is_large else b'list'))
                f.write(pack('<II', global_i_offset, len(processed_groups))) 
                for g in processed_groups:
                    for idx in g['indices']: f.write(pack('<I' if is_large else '<H', idx))
                for pg in processed_groups: f.write(pack('<4I', pg['startIndex'], pg['nPrimitives'], pg['startVertex'], pg['nVertices']))
                
                pad_i = (4 - (f.tell() % 4)) % 4
                if pad_i > 0: f.write(b'\x00' * pad_i)
                size_i = f.tell() - start_i
                
                start_v = f.tell(); f.write(pack('64s', b'BPVTxyznuviiiwwtb')); f.write(pack('<I', 0))
                f.write(pack('64s', b'set3/xyznuviiiwwtbpc')); f.write(pack('<I', global_v_offset))
                for v in all_vertices_flat: f.write(pack('<3fI2f8B2I', *v))
                
                pad_v = (4 - (f.tell() % 4)) % 4
                if pad_v > 0: f.write(b'\x00' * pad_v)
                size_v = f.tell() - start_v
                
                if global_has_colors:
                    start_c = f.tell()
                    f.write(pack('64s', b'BPVScolour'))
                    f.write(pack('<I', 0)); f.write(pack('64s', b'colour'))
                    for c in all_colors_flat: f.write(pack('4B', *c))
                    pad_c = (4 - (f.tell() % 4)) % 4
                    if pad_c > 0: f.write(b'\x00' * pad_c)
                    size_c = f.tell() - start_c

                s_data = b''; v_n, i_n, c_n = f"{FORCED_FILENAME}.vertices", f"{FORCED_FILENAME}.indices", "colour"
                sections_to_write = [(i_n, start_i, size_i), (v_n, start_v, size_v)]
                if global_has_colors: sections_to_write.append((c_n, start_c, size_c))
                    
                for n, o, s in sections_to_write:
                    n_b = n.encode('utf-8'); pad = (4 - (len(n_b) % 4)) % 4
                    s_data += pack('<II12sI', s, o, b'\x00'*12, len(n_b)) + n_b + (b'\x00' * pad)
                f.write(s_data); f.write(pack('<I', len(s_data)))

            # --- XML Export (.visual) ---
            impl = getDOMImplementation(); doc = impl.createDocument(None, 'root', None); root = doc.documentElement
            if 'nodes' in export_info: set_nodes(export_info['nodes'], root, doc)
            rs = doc.createElement('renderSet'); root.appendChild(rs); rs.appendChild(doc.createElement('treatAsWorldSpaceObject')).appendChild(doc.createTextNode('true'))
            for bb_name in bone_palette: rs.appendChild(doc.createElement('node')).appendChild(doc.createTextNode(bb_name))
            geo = doc.createElement('geometry'); rs.appendChild(geo); geo.appendChild(doc.createElement('vertices')).appendChild(doc.createTextNode(v_n))
            geo.appendChild(doc.createElement('primitive')).appendChild(doc.createTextNode(i_n))
            
            if global_has_colors: geo.appendChild(doc.createElement('stream')).appendChild(doc.createTextNode(c_n))
                
            for i, pg in enumerate(processed_groups):
                pge = doc.createElement('primitiveGroup'); pge.appendChild(doc.createTextNode(str(i))); geo.appendChild(pge)
                me = doc.createElement('material'); pge.appendChild(me); me.appendChild(doc.createElement('identifier')).appendChild(doc.createTextNode(pg['mat_name']))
                me.appendChild(doc.createElement('fx')).appendChild(doc.createTextNode(pg['fx']))
                
                bmat = pg.get('bmat')
                # Write custom properties if they exist, else use legacy fallbacks
                if bmat and any(k.startswith("bw_") for k in bmat.keys()):
                    for key in bmat.keys():
                        if key.startswith("bw_tex_"):
                            prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(key[7:])); me.appendChild(prop)
                            prop.appendChild(doc.createElement('Texture')).appendChild(doc.createTextNode(str(bmat[key])))
                        elif key.startswith("bw_bool_"):
                            prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(key[8:])); me.appendChild(prop)
                            prop.appendChild(doc.createElement('Bool')).appendChild(doc.createTextNode(str(bmat[key])))
                        elif key.startswith("bw_int_"):
                            prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(key[7:])); me.appendChild(prop)
                            prop.appendChild(doc.createElement('Int')).appendChild(doc.createTextNode(str(bmat[key])))
                        elif key.startswith("bw_float_"):
                            prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(key[9:])); me.appendChild(prop)
                            prop.appendChild(doc.createElement('Float')).appendChild(doc.createTextNode(str(bmat[key])))
                        elif key.startswith("bw_vector4_"):
                            prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(key[11:])); me.appendChild(prop)
                            prop.appendChild(doc.createElement('Vector4')).appendChild(doc.createTextNode(str(bmat[key])))
                else:
                    for p_n, p_t, p_v in [('doubleSided','Bool','false'),('alphaTestEnable','Bool','false'),('alphaReference','Int','0'),('g_useNormalPackDXT1','Bool','false')]:
                         prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(p_n)); me.appendChild(prop)
                         prop.appendChild(doc.createElement(p_t)).appendChild(doc.createTextNode(p_v))
                    for p, s in [('diffuseMap','AM'),('normalMap','ANM'),('metallicGlossMap','GMM'),('excludeMaskAndAOMap','AO'),('colorIdMap','ID')]:
                        prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(p)); me.appendChild(prop)
                        prop.appendChild(doc.createElement('Texture')).appendChild(doc.createTextNode(f"{TANK_BASE_PATH}/{TEXTURE_BASENAME}_{s}.dds"))
                    prop = doc.createElement('property'); prop.appendChild(doc.createTextNode('metallicDetailMap')); me.appendChild(prop)
                    prop.appendChild(doc.createElement('Texture')).appendChild(doc.createTextNode("vehicles/russian/Tank_detail/Details_map.dds"))
                    for p_n, p_v in [('g_detailUVTiling',"4.000000 4.000000 0.000000 0.000000"),('g_detailParams',"0.000000 0.000000 0.000000 0.000000")]:
                        prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(p_n)); me.appendChild(prop)
                        prop.appendChild(doc.createElement('Vector4')).appendChild(doc.createTextNode(p_v))
                    prop = doc.createElement('property'); prop.appendChild(doc.createTextNode('g_useDetailMetallic')); me.appendChild(prop)
                    prop.appendChild(doc.createElement('Bool')).appendChild(doc.createTextNode("true"))
                
            bb = doc.createElement('boundingBox'); root.appendChild(bb)
            bb.appendChild(doc.createElement('min')).appendChild(doc.createTextNode(f"{bb_min.x:.3f} {bb_min.y:.3f} {bb_min.z:.3f}"))
            bb.appendChild(doc.createElement('max')).appendChild(doc.createTextNode(f"{bb_max.x:.3f} {bb_max.y:.3f} {bb_max.z:.3f}"))
            with open(final_visual_path, 'w') as f: f.write(doc.toprettyxml())
            
            # --- Dynamic LOD Export (.model) ---
            mdm = impl.createDocument(None, 'root', None); mroot = mdm.documentElement
            exp_lods = export_info.get("wot_export_with_lods", False)
            exp_lod = export_info.get("wot_export_lod", "lod0")
            exp_parent = export_info.get("wot_export_has_parent", False)
            exp_extent = export_info.get("wot_export_extent", 20.0)
            
            base_path = export_info.get("wot_base_path", TANK_BASE_PATH + "/")
            if not base_path.endswith('/'): base_path += '/'
            
            if exp_lods:
                if exp_parent:
                    current_lod_num = int(exp_lod.replace("lod", ""))
                    parent_lod = f"lod{current_lod_num + 1}"
                    parent_path = f"{base_path}{parent_lod}/{FORCED_FILENAME}"
                    mroot.appendChild(mdm.createElement('parent')).appendChild(mdm.createTextNode(parent_path))
                    mroot.appendChild(mdm.createElement('extent')).appendChild(mdm.createTextNode(f"{exp_extent:.6f}"))
                nodefull_path = f"{base_path}{exp_lod}/{FORCED_FILENAME}"
            else:
                nodefull_path = f"{base_path}lod0/{FORCED_FILENAME}"
                
            mroot.appendChild(mdm.createElement('nodefullVisual')).appendChild(mdm.createTextNode(nodefull_path))
            mbb = mdm.createElement('visibilityBox'); mroot.appendChild(mbb)
            mbb.appendChild(mdm.createElement('min')).appendChild(mdm.createTextNode(f"{bb_min.x:.3f} {bb_min.y:.3f} {bb_min.z:.3f}"))
            mbb.appendChild(mdm.createElement('max')).appendChild(mdm.createTextNode(f"{bb_max.x:.3f} {bb_max.y:.3f} {bb_max.z:.3f}"))
            mroot.appendChild(mdm.createElement('tank')).appendChild(mdm.createTextNode("true"))
            with open(final_model_path, 'w') as f: f.write(mdm.toprettyxml())

        # --- Texture Export Pipeline ---
        if export_info.get("export_textures", True):
            export_dir = os.path.dirname(model_filepath)
            processed_images = set() 
            
            for pg in processed_groups:
                bmat = pg.get('bmat')
                if not bmat or not bmat.use_nodes: continue
                
                for node in bmat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.name not in processed_images:
                        img = node.image
                        processed_images.add(img.name)
                        original_dds_name = img.name.replace(".png", ".dds")
                        target_rel_path = ""
                        
                        for key, val in bmat.items():
                            if key.startswith("bw_tex_") and original_dds_name.lower() in str(val).lower():
                                target_rel_path = str(val).replace('\\', '/')
                                break
                                
                        # Resolve final directory hierarchy
                        if target_rel_path:
                            norm_export = export_dir.replace('\\', '/')
                            if '/vehicles/' in norm_export:
                                base_root = norm_export.split('/vehicles/')[0]
                                final_tex_path = os.path.join(base_root, target_rel_path)
                            elif norm_export.endswith('/vehicles'):
                                base_root = norm_export[:-9]
                                final_tex_path = os.path.join(base_root, target_rel_path)
                            else:
                                final_tex_path = os.path.join(export_dir, os.path.basename(target_rel_path))
                        else:
                            final_tex_path = os.path.join(export_dir, img.name)
                        
                        final_tex_path_png = final_tex_path.replace(".dds", ".png").replace(".DDS", ".png")
                        os.makedirs(os.path.dirname(final_tex_path_png), exist_ok=True)
                        
                        temp_img = bpy.data.images.new(name="temp_export_tex", width=img.size[0], height=img.size[1], alpha=True)
                        temp_img.pixels = img.pixels[:] 
                        
                        scene = bpy.context.scene
                        old_view_transform = scene.view_settings.view_transform
                        
                        try:
                            # Use RAW to preserve Blue/Alpha channel integrity during export
                            scene.view_settings.view_transform = 'Raw'
                            temp_img.filepath_raw = final_tex_path_png
                            temp_img.file_format = 'PNG'
                            temp_img.save()
                            convert_png_to_dds(final_tex_path_png)
                        except Exception as e:
                            print(f"[Error] Texture could not be saved or converted: {e}")
                        finally:
                            scene.view_settings.view_transform = old_view_transform
                            bpy.data.images.remove(temp_img)