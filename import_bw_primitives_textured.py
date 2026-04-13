# -*- coding: utf-8 -*-
"""SkepticalFox 2015-2024 & Wotcuk - TEXTURED VERSION (V11: VERTEX COLOR ALPHA SUPPORT)"""

# imports
import logging
import os
import traceback
import math
import tempfile
import shutil

TEMP_DIR = os.path.join(tempfile.gettempdir(), "WoT_Blender_Temp_Textures")

from pathlib import Path
from xml.etree import ElementTree as ET

# blender imports
import bpy
from bpy_extras.io_utils import unpack_list
from mathutils import Vector, Matrix

# local imports
from .common.XmlUnpacker import XmlUnpacker
from .common import utils_AsVector
from .common.consts import visual_property_descr_dict, VERBOSE_VALIDATE
from .loaddatamesh import LoadDataMesh

logger = logging.getLogger(__name__)

def build_node_matrices(elem, parent_mtx=None, result=None):
    """Reads node hierarchy from Visual file as pure BigWorld (Y-Up) matrices"""
    if parent_mtx is None: parent_mtx = Matrix()
    if result is None: result = {}
    
    mtx = Matrix()
    transform = elem.find("transform")
    if transform is not None:
        r0 = utils_AsVector(transform.findtext("row0"))
        r1 = utils_AsVector(transform.findtext("row1"))
        r2 = utils_AsVector(transform.findtext("row2"))
        r3 = utils_AsVector(transform.findtext("row3"))
        mtx.col[0] = [*r0, 0]; mtx.col[1] = [*r1, 0]; mtx.col[2] = [*r2, 0]; mtx.col[3] = [*r3, 1]
        
    world_mtx = parent_mtx @ mtx
    identifier = elem.findtext("identifier")
    if identifier: result[identifier.strip()] = world_mtx
        
    for child in elem.iterfind("node"):
        build_node_matrices(child, world_mtx, result)
        
    return result


def setup_temp_dir():
    """Cleans and recreates the temporary texture directory before each import."""
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
        os.makedirs(TEMP_DIR, exist_ok=True)
        write_to_blender_text(f"Temp directory ready: {TEMP_DIR}")
    except Exception as e:
        write_to_blender_text(f"[Error] Temp directory: {e}")

def write_to_blender_text(content, clear=False):
    text_name = "BW_Import_Debug_Log"
    txt = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    if clear: txt.clear()
    txt.write(str(content) + "\n")

# --- 1. NEW ARMATURE HIERARCHY STRUCTURE ---
def build_armature_bones(arm_obj, elem, parent_bone=None):
    if (elem.find("identifier") is None) or (elem.find("transform") is None): return
    
    identifier = elem.findtext("identifier").strip()
    r0 = utils_AsVector(elem.findtext("transform/row0"))
    r1 = utils_AsVector(elem.findtext("transform/row1"))
    r2 = utils_AsVector(elem.findtext("transform/row2"))
    r3 = utils_AsVector(elem.findtext("transform/row3"))
    
    mtx = Matrix()
    mtx.col[0] = [*r0, 0]; mtx.col[1] = [*r1, 0]; mtx.col[2] = [*r2, 0]; mtx.col[3] = [*r3, 1]
    

    C = Matrix([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
    final_mtx = C @ mtx @ C

    bone = arm_obj.data.edit_bones.new(identifier)
    bone.head = (0, 0, 0)
    bone.tail = (0, 0.1, 0) 

    if parent_bone:
        bone.parent = parent_bone
        bone.matrix = parent_bone.matrix @ final_mtx 
    else:
        bone.matrix = final_mtx

    for child in elem.iterfind("node"):
        build_armature_bones(arm_obj, child, bone)

def create_armature_from_nodes(col, elem, armature_name):
    arm_data = bpy.data.armatures.new(armature_name)
    arm_data.display_type = 'WIRE'
    arm_data.show_names = False
    arm_obj = bpy.data.objects.new(armature_name, arm_data)
    col.objects.link(arm_obj)
    
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    build_armature_bones(arm_obj, elem)
    
    bpy.ops.object.mode_set(mode='OBJECT')
    arm_obj.hide_set(True)
    return arm_obj


# --- 2. TEXTURE AND NODE PROCESSING ---
def process_material_textures(mat, props_xml, base_path, has_vertex_color=False, vcol_name="BPVScolour"):
    """Creates material nodes and correctly blends Vertex Color with Texture Alpha."""
    try:
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        # --- 1. MAIN SKELETON ---
        out = nodes.new('ShaderNodeOutputMaterial')
        out.location = (400, 0)
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (0, 0)
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        
        if hasattr(bsdf.inputs.get('IOR'), 'default_value'):
            bsdf.inputs['IOR'].default_value = 1.45

        # --- 2. FILE ANALYSIS (Gather texture paths) ---
        tex_files = {} 
        for prop in props_xml:
            if prop.find("Texture") is not None:
                val = prop.findtext("Texture").strip()
                name = prop.findtext("name").strip().lower() if prop.findtext("name") else ""
                val_lower = val.lower()
                if ("diffuse" in name) or ("_am.dds" in val_lower) or ("_d.dds" in val_lower):
                    tex_files["diffuse"] = val
                elif ("normal" in name) or ("_anm.dds" in val_lower) or ("_nm.dds" in val_lower):
                    tex_files["normal"] = val
                elif ("specular" in name) or ("pbs" in name) or ("_gmm.dds" in val_lower):
                    tex_files["gmm"] = val

        # --- 3. ALPHA HIERARCHY ---
        current_alpha_handle = None 

        if has_vertex_color:
            vcol_node = nodes.new('ShaderNodeAttribute')
            vcol_node.attribute_name = vcol_name 
            vcol_node.location = (-600, 500)
            current_alpha_handle = vcol_node.outputs['Alpha']
            mat.blend_method = 'BLEND'
            mat.show_transparent_back = True

        if "diffuse" in tex_files:
            img = load_image_safe(tex_files["diffuse"], base_path)
            if img:
                tnode = nodes.new('ShaderNodeTexImage')
                tnode.image = img
                tnode.location = (-600, 200)
                links.new(tnode.outputs['Color'], bsdf.inputs['Base Color'])
                
                # Blend Vertex Color Alpha with Texture Alpha if both exist
                if current_alpha_handle:
                    math_node = nodes.new('ShaderNodeMath')
                    math_node.operation = 'MULTIPLY'
                    math_node.location = (-300, 400)
                    links.new(current_alpha_handle, math_node.inputs[0])
                    links.new(tnode.outputs['Alpha'], math_node.inputs[1])
                    current_alpha_handle = math_node.outputs[0]
                else:
                    current_alpha_handle = tnode.outputs['Alpha']

        if current_alpha_handle:
            links.new(current_alpha_handle, bsdf.inputs['Alpha'])

        # --- 4. GMM AND NORMAL ---
        if "gmm" in tex_files:
            img = load_image_safe(tex_files["gmm"], base_path, is_data=True)
            if img:
                gnode = nodes.new('ShaderNodeTexImage'); gnode.image = img
                gnode.location = (-900, -100)
                sep = nodes.new('ShaderNodeSeparateColor'); sep.location = (-600, -100)
                links.new(gnode.outputs['Color'], sep.inputs['Color'])
                links.new(sep.outputs[1], bsdf.inputs['Metallic'])
                mix_r = nodes.new('ShaderNodeMix'); mix_r.data_type = 'RGBA'; mix_r.blend_type = 'MIX'
                mix_r.location = (-300, -200)
                links.new(sep.outputs[0], mix_r.inputs[0])
                mix_r.inputs[6].default_value = (0.8, 0.8, 0.8, 1.0)
                links.new(sep.outputs[2], mix_r.inputs[7])
                links.new(mix_r.outputs[2], bsdf.inputs['Roughness'])

        if "normal" in tex_files:
            img = load_image_safe(tex_files["normal"], base_path, is_data=True)
            if img:
                nnode = nodes.new('ShaderNodeTexImage'); nnode.image = img
                nnode.location = (-1000, -500)
                snorm = nodes.new('ShaderNodeSeparateColor'); snorm.location = (-700, -500)
                links.new(nnode.outputs['Color'], snorm.inputs['Color'])
                comb = nodes.new('ShaderNodeCombineColor'); comb.location = (-400, -500)
                links.new(nnode.outputs['Alpha'], comb.inputs['Red'])
                links.new(snorm.outputs[1], comb.inputs['Green'])
                comb.inputs['Blue'].default_value = 1.0
                nm = nodes.new('ShaderNodeNormalMap'); nm.location = (-150, -500)
                links.new(comb.outputs['Color'], nm.inputs['Color'])
                links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])

    except Exception as e:
        write_to_blender_text(f"[Error] Material Node Error: {e}")

def load_image_safe(path_str, base_path, is_data=False):
    clean_path = path_str.replace("\\", "/").strip("/")
    fname = os.path.basename(clean_path)
    
    candidates = []
    exact_temp_path = Path(TEMP_DIR) / clean_path
    candidates.append(exact_temp_path)
    candidates.append(base_path / fname)
    candidates.append(base_path.parent / fname)
    candidates.append(base_path.parent.parent / fname)
    
    try:
        parts = base_path.parts
        if 'vehicles' in parts:
            idx = parts.index('vehicles')
            root_path = Path(*parts[:idx])
            candidates.append(root_path / clean_path)
    except Exception:
        pass
        
    curr = base_path
    for _ in range(4):
        candidates.append(curr / clean_path)
        curr = curr.parent
        
    fpath = None
    for p in candidates:
        if p.is_file():
            fpath = str(p)
            break
            
    if not fpath:
        write_to_blender_text(f"[Warning] Texture not found, skipped: {fname}")
        return None

    # --- PNG CONVERSION AND PACKING ---
    fname_png = fname.replace(".dds", ".png").replace(".DDS", ".png")
    temp_png_path = os.path.join(TEMP_DIR, fname_png)

    try:
        if fname_png in bpy.data.images:
            img_png = bpy.data.images[fname_png]
            if is_data: img_png.colorspace_settings.name = 'Non-Color'
            return img_png

        img_dds = bpy.data.images.load(fpath)
        
        img_png = bpy.data.images.new(name=fname_png, width=img_dds.size[0], height=img_dds.size[1], alpha=True)
        img_png.pixels = img_dds.pixels[:]
        
        img_png.filepath_raw = temp_png_path
        img_png.file_format = 'PNG'
        img_png.save()
        
        img_png.pack()
        
        bpy.data.images.remove(img_dds)
        
        if is_data: 
            img_png.colorspace_settings.name = 'Non-Color'
            
        write_to_blender_text(f"[Success] {fname} -> Converted to PNG and Packed.")
        return img_png

    except Exception as e:
        write_to_blender_text(f"[Warning] Texture could not be loaded: {fname} ({e})")
        return None

# --- 3. MAIN IMPORT FUNCTION ---
def load_bw_primitive_textured(col: bpy.types.Collection, model_filepath: Path, import_empty: bool = False):
    setup_temp_dir()
    write_to_blender_text("=== V11 VERTEX COLORED IMPORT ===", clear=True)
    try:
        visual_filepath = model_filepath.with_suffix(".visual_processed")
        if not visual_filepath.exists(): visual_filepath = model_filepath.with_suffix(".visual")
        prim_path = model_filepath.with_suffix(".primitives_processed")
        if not prim_path.exists(): prim_path = model_filepath.with_suffix(".primitives")
        if not prim_path.exists(): return {"CANCELLED"}

        visual = smart_xml_read(visual_filepath)
        if not visual: return {"CANCELLED"}

        root_empty_ob = None
        for rs_idx, renderSet in enumerate(visual.findall("renderSet")):
            vres_name = renderSet.findtext("geometry/vertices").strip()
            pres_name = renderSet.findtext("geometry/primitive").strip()
            mesh_name = os.path.splitext(vres_name)[0]
            
            uv2_name = ""
            colour_name = ""
            for stream in renderSet.findall("geometry/stream"):
                s_text = stream.text.strip()
                if "uv2" in s_text: uv2_name = s_text
                elif "colour" in s_text: colour_name = s_text

            dataMesh = LoadDataMesh(str(prim_path), vres_name, pres_name, uv2_name, colour_name)
            
            bmesh = bpy.data.meshes.new(mesh_name)
            bmesh.vertices.add(len(dataMesh.vertices))
            
            # --- FULLY AUTOMATIC COORDINATE FIX FOR SKINNED MODELS ---
            is_skinned = False
            for pg in renderSet.findall("geometry/primitiveGroup"):
                fx = pg.findtext("material/fx")
                if fx and "skinned" in fx.lower():
                    is_skinned = True
                    break

            if is_skinned and hasattr(dataMesh, "bones_info") and dataMesh.bones_info:
                write_to_blender_text(f"[Info] Fixing skinned model ({mesh_name})...")
                
                visual_root_node = visual.find("node")
                node_matrices = build_node_matrices(visual_root_node) if visual_root_node else {}
                bone_names = [node.text.strip() for node in renderSet.findall("node")]
                
                # Conversion Matrix (BigWorld Y-Up -> Blender Z-Up)
                C = Matrix([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
                
                # Rotation Fix (180° X-axis and -1 Z-scale)
                T_fix = Matrix.Diagonal((1.0, -1.0, 1.0, 1.0)) 

                root_bw = node_matrices.get("Scene Root", Matrix())
                root_blender_inv = (C @ root_bw @ C).inverted()

                bone_final_matrices = []
                for b_name in bone_names:
                    b_bw = node_matrices.get(b_name, Matrix())
                    m_final = root_blender_inv @ (C @ b_bw @ C) @ T_fix
                    bone_final_matrices.append(m_final)

                transformed_verts = []
                for i, co in enumerate(dataMesh.vertices):
                    v_local = Vector(co) 
                    iiiww = dataMesh.bones_info[i]
                    
                    best_bone_idx = 0
                    max_weight = -1
                    mapping = [(iiiww[0], iiiww[7]), (iiiww[1], iiiww[5]), (iiiww[2], iiiww[6])] if len(iiiww) == 8 else \
                              [(iiiww[0], iiiww[3]), (iiiww[1], iiiww[4]), (iiiww[2], max(0, 255-(iiiww[3]+iiiww[4])))]
                    
                    for r_idx, w_val in mapping:
                        if w_val > max_weight:
                            max_weight = w_val
                            best_bone_idx = r_idx // 3

                    if best_bone_idx < len(bone_final_matrices):
                        new_pos = bone_final_matrices[best_bone_idx] @ v_local
                        transformed_verts.extend([new_pos.x, new_pos.y, new_pos.z])
                    else:
                        transformed_verts.extend([co[0], co[1], co[2]])
                        
                bmesh.vertices.foreach_set("co", transformed_verts)
            else:
                # Do not touch LoadDataMesh output for static models
                bmesh.vertices.foreach_set("co", unpack_list(dataMesh.vertices))
            
            nbr_faces = len(dataMesh.indices)
            bmesh.polygons.add(nbr_faces)
            bmesh.polygons.foreach_set("loop_start", range(0, nbr_faces * 3, 3))
            bmesh.polygons.foreach_set("loop_total", (3,) * nbr_faces)
            bmesh.loops.add(nbr_faces * 3)
            bmesh.loops.foreach_set("vertex_index", unpack_list(dataMesh.indices))
            bmesh.polygons.foreach_set("use_smooth", [True] * nbr_faces)

            # UVs
            if dataMesh.uv_list:
                uv = bmesh.uv_layers.new(name="uv1")
                for p in bmesh.polygons:
                    for l in p.loop_indices: uv.data[l].uv = dataMesh.uv_list[bmesh.loops[l].vertex_index]
            if dataMesh.uv2_list:
                uv2 = bmesh.uv_layers.new(name="uv2")
                for p in bmesh.polygons:
                    for l in p.loop_indices: uv2.data[l].uv = dataMesh.uv2_list[bmesh.loops[l].vertex_index]

            # --- APPLY VERTEX COLOR (DYNAMIC AND POINT DOMAIN) ---
            has_vcol = False
            vcol_name = colour_name if colour_name else "BPVScolour" 
            
            if hasattr(dataMesh, "colour_list") and dataMesh.colour_list:
                color_attr = bmesh.color_attributes.new(name=vcol_name, type='FLOAT_COLOR', domain='POINT')
                flat_colors = [1.0] * (len(bmesh.vertices) * 4)
                
                for v_idx, c in enumerate(dataMesh.colour_list):
                    # BigWorld uses BGRA, Blender expects RGBA.
                    flat_colors[v_idx*4 + 0] = c[2] / 255.0 # R
                    flat_colors[v_idx*4 + 1] = c[1] / 255.0 # G
                    flat_colors[v_idx*4 + 2] = c[0] / 255.0 # B
                    flat_colors[v_idx*4 + 3] = c[3] / 255.0 # A
                        
                color_attr.data.foreach_set("color", flat_colors)
                has_vcol = True
                write_to_blender_text(f"[Info] Vertex Color added ({mesh_name} - {vcol_name})")

            # Materials
            primitiveGroupInfo = {}
            for pg in renderSet.findall("geometry/primitiveGroup"):
                primitiveGroupInfo[int(pg.text)] = {
                    "identifier": pg.findtext("material/identifier").strip(),
                    "fx": pg.findtext("material/fx").strip() if pg.find("material/fx") is not None else "shaders/std_effects/PBS_tank_skinned.fx",
                    "props": pg.findall("material/property")
                }

            for i, pg in enumerate(dataMesh.PrimitiveGroups):
                pgVisual = primitiveGroupInfo.get(i)
                mat_name = pgVisual["identifier"] if pgVisual else f"mat_{i}"
                material = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
                bmesh.materials.append(material)
                
                if pgVisual:
                    material["bw_custom_fx"] = pgVisual["fx"]
                    for prop in pgVisual["props"]:
                        prop_name = prop.text.strip() if prop.text else ""
                        if not prop_name: continue
                        
                        for child in prop:
                            tag = child.tag
                            val = child.text.strip() if child.text else ""
                            if tag == "Texture":
                                material[f"bw_tex_{prop_name}"] = val
                            elif tag in ["Bool", "Int", "Float", "Vector4"]:
                                material[f"bw_{tag.lower()}_{prop_name}"] = val
                    process_material_textures(material, pgVisual["props"], model_filepath.parent, has_vertex_color=has_vcol, vcol_name=vcol_name)
                    
                startIndex = pg["startIndex"] // 3
                count = pg["nPrimitives"]
                for fidx in range(startIndex, startIndex + count):
                    if fidx < len(bmesh.polygons): bmesh.polygons[fidx].material_index = i

            bmesh.validate(); bmesh.update()
            ob = bpy.data.objects.new(mesh_name, bmesh)
            col.objects.link(ob)

            # Skinning / Bone Weights
            if renderSet.find("treatAsWorldSpaceObject") is not None and "true" in renderSet.findtext("treatAsWorldSpaceObject").lower():
                if hasattr(dataMesh, "bones_info") and dataMesh.bones_info:
                    bone_nodes = renderSet.findall("node")
                    bone_arr = []
                    for node in bone_nodes:
                        bn = node.text.strip()
                        bone_arr.append({"name": bn, "group": ob.vertex_groups.new(name=bn)})

                    for vert_idx, iiiww in enumerate(dataMesh.bones_info):
                        weights_sum_map = {}
                        
                        # NEW GEN (8-BYTE) iiiww STRUCTURE
                        if len(iiiww) == 8: 
                            mapping = [
                                (iiiww[0], iiiww[7]),
                                (iiiww[1], iiiww[5]),
                                (iiiww[2], iiiww[6])
                            ]
                        # OLD GEN (5-BYTE) iiiww STRUCTURE
                        elif len(iiiww) == 5:
                            w1, w2 = iiiww[3], iiiww[4]
                            w3 = max(0, 255 - (w1 + w2))
                            mapping = [
                                (iiiww[0], w1),
                                (iiiww[1], w2),
                                (iiiww[2], w3)
                            ]
                        else:
                            continue
                        
                        for raw_idx, weight_val in mapping:
                            if weight_val > 0:
                                bone_id = raw_idx // 3
                                norm_weight = weight_val / 255.0
                                weights_sum_map[bone_id] = weights_sum_map.get(bone_id, 0.0) + norm_weight

                        for b_id, final_w in weights_sum_map.items():
                            if b_id < len(bone_arr) and final_w > 0.0001:
                                bone_arr[b_id]["group"].add([vert_idx], final_w, "ADD")
            
            if import_empty and visual.find("node") is not None:
                armature_name = model_filepath.stem
                
                if root_empty_ob is None: 
                    root_empty_ob = create_armature_from_nodes(col, visual.findall("node")[0], armature_name)
                
                if root_empty_ob: 
                    ob.parent = root_empty_ob
                    mod = ob.modifiers.new(type='ARMATURE', name="Armature")
                    mod.object = root_empty_ob

        write_to_blender_text("[Success] Import completed successfully")

        write_to_blender_text("[Success] Import completed successfully")
        return {"FINISHED"}
    except Exception as e:
        write_to_blender_text(f"[Critical Error] {traceback.format_exc()}")
        return {"CANCELLED"}

def smart_xml_read(filepath):
    unpacker = XmlUnpacker()
    try:
        with open(filepath, "r", errors="ignore") as f: raw = f.read()
        if "<root" in raw: return ET.fromstring(raw)
    except: pass
    try:
        with open(filepath, "rb") as f: return unpacker.read(f)
    except: pass
    return None