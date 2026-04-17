# -*- coding: utf-8 -*-
"""SkepticalFox 2015-2024 & Wotcuk - TEXTURED VERSION (V11: VERTEX COLOR ALPHA SUPPORT)"""

import logging, os, traceback, math, tempfile, shutil, subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
import bpy
from bpy_extras.io_utils import unpack_list
from mathutils import Vector, Matrix

from .common.XmlUnpacker import XmlUnpacker
from .common import utils_AsVector
from .common.consts import visual_property_descr_dict, VERBOSE_VALIDATE
from .loaddatamesh import LoadDataMesh
from .file_finder import WoTFileFinder 

logger = logging.getLogger(__name__)

# --- UTILS ---
def build_node_matrices(elem, parent_mtx=None, result=None):
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

def write_to_blender_text(content, clear=False):
    text_name = "BW_Import_Debug_Log"
    txt = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    if clear: txt.clear()
    txt.write(str(content) + "\n")

# --- ARMATURE ---
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
    bone.head, bone.tail = (0, 0, 0), (0, 0.1, 0) 
    if parent_bone:
        bone.parent = parent_bone
        bone.matrix = parent_bone.matrix @ final_mtx 
    else: bone.matrix = final_mtx
    for child in elem.iterfind("node"): build_armature_bones(arm_obj, child, bone)

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

# --- TEXTURE PROCESSING ---
def load_image_safe(path_str, base_path, finder, context, is_data=False):
    clean_path = path_str.replace("\\", "/").strip("/")
    
    fpath = finder.find(clean_path, str(base_path), clean_path, context_pkg=context.get('last_pkg'))
            
    if not fpath:
        write_to_blender_text(f"[Warning] Texture not found: {clean_path}")
        return None

    if finder.last_found_pkg:
        context['last_pkg'] = finder.last_found_pkg

    fname = os.path.basename(fpath)
    fname_png = fname.replace(".dds", ".png").replace(".DDS", ".png")
    
    try:
        if fname_png in bpy.data.images:
            img = bpy.data.images[fname_png]
            if img.size[0] > 0 and img.size[1] > 0:
                return img
            else:
                bpy.data.images.remove(img) 

        temp_dir = tempfile.gettempdir()
        
        texconv_path = os.path.join(os.path.dirname(__file__), "texconv.exe") 
        
        try:
            subprocess.run(
                [texconv_path, "-ft", "png", "-o", temp_dir, "-y", fpath],
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            temp_png_path = os.path.join(temp_dir, fname_png)
            
            img = bpy.data.images.load(temp_png_path)
            img.pack()
            
            try:
                os.remove(temp_png_path)
            except:
                pass
                
        except subprocess.CalledProcessError as sub_err:
            write_to_blender_text(f"[Error] Texconv failed for {fname}: {sub_err}")
            return None
            
        if is_data: img.colorspace_settings.name = 'Non-Color'
        return img
        
    except Exception as e:
        write_to_blender_text(f"[Error] General Texture load error: {fname} ({e})")
        return None
def process_material_textures(mat, props_xml, base_path, finder, context, has_vertex_color=False, vcol_name="BPVScolour"):
    try:
        mat.use_nodes = True
        mat.blend_method = 'OPAQUE' 
        if hasattr(mat, "show_transparent_back"):
            mat.show_transparent_back = False
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        out = nodes.new('ShaderNodeOutputMaterial')
        out.location = (400, 0)
        
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (0, 0)
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        
        tex_files = {} 
        extra_props = {}
        
        for prop in props_xml:
            if prop.find("Texture") is not None:
                val = prop.findtext("Texture").strip()
                name = (prop.text or "").strip().lower()
                
                if val and "." not in os.path.basename(val):
                    val += ".dds"
                    
                val_l = val.lower()
                
                if "diffuse" in name or "_am.dds" in val_l or "_d.dds" in val_l: tex_files["diffuse"] = val
                elif "normal" in name or "_anm.dds" in val_l or "_nm.dds" in val_l: tex_files["normal"] = val
                elif "specular" in name or "pbs" in name or "_gmm.dds" in val_l: tex_files["gmm"] = val

            exact_name = (prop.text or "").strip()
            if exact_name:
                if prop.find("Vector4") is not None:
                    extra_props[exact_name] = [float(x) for x in prop.find("Vector4").text.split()]
                elif prop.find("Bool") is not None:
                    extra_props[exact_name] = prop.find("Bool").text.strip().lower() == "true"
                elif prop.find("Int") is not None:
                    extra_props[exact_name] = int(prop.find("Int").text.strip())
                elif prop.find("Float") is not None:
                    extra_props[exact_name] = float(prop.find("Float").text.strip())
                elif prop.find("Texture") is not None:
                    tex_val = prop.find("Texture").text.strip()
                    
                    if tex_val and "." not in os.path.basename(tex_val):
                        tex_val += ".dds"
                        
                    extra_props[exact_name] = tex_val
        prop_nodes = {}
        dump_y = 600
        for p_name, p_val in extra_props.items():
            if isinstance(p_val, list) and len(p_val) >= 3:
                if "color" in p_name.lower() or "tint" in p_name.lower():
                    vn = nodes.new('ShaderNodeRGB')
                    vn.label = p_name
                    vn.outputs[0].default_value = (p_val[0], p_val[1], p_val[2], p_val[3] if len(p_val)>3 else 1.0)
                    out_sock = vn.outputs[0]
                else:
                    vn = nodes.new('ShaderNodeCombineXYZ')
                    vn.label = p_name
                    vn.inputs['X'].default_value = p_val[0]
                    vn.inputs['Y'].default_value = p_val[1]
                    vn.inputs['Z'].default_value = p_val[2]
                    out_sock = vn.outputs['Vector']
                
                vn.location = (-1400, dump_y)
                prop_nodes[p_name] = {"node": vn, "out": out_sock}
                dump_y -= 200
        vcol_color_handle = None
        vcol_alpha_handle = None
        
        if has_vertex_color:
            vcol_node = nodes.new('ShaderNodeAttribute')
            vcol_node.attribute_name = vcol_name 
            vcol_node.location = (-1000, 400)
            vcol_color_handle = vcol_node.outputs['Color']
            vcol_alpha_handle = vcol_node.outputs['Alpha']
        uv_out = None
        if "diffuseUVSpeedAlphaOffset" in prop_nodes:
            speed_info = prop_nodes["diffuseUVSpeedAlphaOffset"]
            uv_node = nodes.new('ShaderNodeTexCoord'); uv_node.location = (-1000, 200)
            mapping = nodes.new('ShaderNodeMapping'); mapping.location = (-800, 200)
            links.new(uv_node.outputs['UV'], mapping.inputs['Vector'])
            
            links.new(speed_info["out"], mapping.inputs['Location'])
            uv_out = mapping.outputs['Vector']

        final_color = vcol_color_handle
        final_alpha = vcol_alpha_handle
        
        if "diffuse" in tex_files:
            img = load_image_safe(tex_files["diffuse"], base_path, finder, context)
            if img:
                tnode = nodes.new('ShaderNodeTexImage')
                tnode.image = img
                tnode.location = (-600, 0)
                if uv_out: links.new(uv_out, tnode.inputs['Vector'])
                
                if vcol_color_handle:
                    m_color = nodes.new('ShaderNodeMix')
                    m_color.data_type = 'RGBA'; m_color.blend_type = 'MULTIPLY'
                    m_color.inputs[0].default_value = 1.0 
                    m_color.location = (-300, 150)
                    links.new(tnode.outputs['Color'], m_color.inputs[6])
                    links.new(vcol_color_handle, m_color.inputs[7]) 
                    final_color = m_color.outputs[2]
                else:
                    final_color = tnode.outputs['Color']

                if vcol_alpha_handle:
                    m_alpha = nodes.new('ShaderNodeMath')
                    m_alpha.operation = 'MULTIPLY'; m_alpha.location = (-300, -50)
                    links.new(tnode.outputs['Alpha'], m_alpha.inputs[0])
                    links.new(vcol_alpha_handle, m_alpha.inputs[1])
                    final_alpha = m_alpha.outputs[0]
                else:
                    final_alpha = tnode.outputs['Alpha']
                    
        if "TintlColor" in prop_nodes and final_color:
            tint_info = prop_nodes["TintlColor"]
            m_tint = nodes.new('ShaderNodeMix'); m_tint.data_type = 'RGBA'; m_tint.blend_type = 'MULTIPLY'
            m_tint.inputs[0].default_value = 1.0
            m_tint.location = (-100, 150)
            links.new(final_color, m_tint.inputs[6])
            links.new(tint_info["out"], m_tint.inputs[7])
            final_color = m_tint.outputs[2]

        if final_color:
            links.new(final_color, bsdf.inputs['Base Color'])
        ramp_map = extra_props.get("rampFreshnelMap")
        if extra_props.get("alphaFreshnelEnable") is True and ramp_map:
            f_img = load_image_safe(ramp_map, base_path, finder, context)
            if f_img:
                lw = nodes.new('ShaderNodeLayerWeight'); lw.location = (-1000, -300)
                inv = nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
                inv.location = (-800, -300)
                links.new(lw.outputs['Facing'], inv.inputs[1])

                comb = nodes.new('ShaderNodeCombineXYZ'); comb.location = (-600, -300)
                links.new(inv.outputs[0], comb.inputs['X'])

                r_node = nodes.new('ShaderNodeTexImage'); r_node.image = f_img; r_node.location = (-400, -300)
                links.new(comb.outputs['Vector'], r_node.inputs['Vector'])

                m_f = nodes.new('ShaderNodeMath'); m_f.operation = 'MULTIPLY'; m_f.location = (-200, -200)
                if final_alpha: links.new(final_alpha, m_f.inputs[0])
                else: m_f.inputs[0].default_value = 1.0
                links.new(r_node.outputs['Color'], m_f.inputs[1])
                final_alpha = m_f.outputs[0]
                
        if "alphaFadeAmountSoft" in prop_nodes and final_alpha:
            fade_info = prop_nodes["alphaFadeAmountSoft"]
            sep_fade = nodes.new('ShaderNodeSeparateXYZ')
            sep_fade.location = (-200, -400)
            links.new(fade_info["out"], sep_fade.inputs['Vector'])
            
            m_fade = nodes.new('ShaderNodeMath'); m_fade.operation = 'MULTIPLY'
            m_fade.location = (0, -200)
            links.new(final_alpha, m_fade.inputs[0])
            links.new(sep_fade.outputs['X'], m_fade.inputs[1])
            final_alpha = m_fade.outputs[0]

        if final_alpha:
            links.new(final_alpha, bsdf.inputs['Alpha'])
        if extra_props.get("destBlend") == 2:
            mat.blend_method = 'BLEND'
            if hasattr(mat, "show_transparent_back"):
                mat.show_transparent_back = True 
        
        elif extra_props.get("alphaTestEnable") is True:
            mat.blend_method = 'CLIP'
            mat.alpha_threshold = 0.5
            
        if "lightMultipliers" in prop_nodes and final_color:
            l_mult_info = prop_nodes["lightMultipliers"]
            sep_light = nodes.new('ShaderNodeSeparateXYZ')
            sep_light.location = (-200, 300)
            links.new(l_mult_info["out"], sep_light.inputs['Vector'])
            
            links.new(final_color, bsdf.inputs['Emission Color'])
            links.new(sep_light.outputs['X'], bsdf.inputs['Emission Strength'])

        # --- GMM VE NORMAL ---
        if "gmm" in tex_files:
            img = load_image_safe(tex_files["gmm"], base_path, finder, context, is_data=True)
            if img:
                g = nodes.new('ShaderNodeTexImage'); g.image = img
                g.location = (-900, -600)
                sep = nodes.new('ShaderNodeSeparateColor'); sep.location = (-600, -600)
                links.new(g.outputs['Color'], sep.inputs['Color'])
                links.new(sep.outputs[1], bsdf.inputs['Metallic'])
                mix = nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MIX'
                mix.location = (-300, -600)
                links.new(sep.outputs[0], mix.inputs[0]); mix.inputs[6].default_value = (0.8, 0.8, 0.8, 1.0)
                links.new(sep.outputs[2], mix.inputs[7]); links.new(mix.outputs[2], bsdf.inputs['Roughness'])

        if "normal" in tex_files:
            img = load_image_safe(tex_files["normal"], base_path, finder, context, is_data=True)
            if img:
                n = nodes.new('ShaderNodeTexImage'); n.image = img
                n.location = (-900, -900)
                sep = nodes.new('ShaderNodeSeparateColor'); sep.location = (-600, -900)
                links.new(n.outputs['Color'], sep.inputs['Color'])
                comb = nodes.new('ShaderNodeCombineColor'); comb.location = (-400, -900)
                links.new(n.outputs['Alpha'], comb.inputs['Red'])
                links.new(sep.outputs[1], comb.inputs['Green']); comb.inputs['Blue'].default_value = 1.0
                nm = nodes.new('ShaderNodeNormalMap'); nm.location = (-200, -900)
                links.new(comb.outputs['Color'], nm.inputs['Color'])
                links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])

    except Exception as e: write_to_blender_text(f"[Error] Material Node Error: {e}")

# --- MAIN ---
def load_bw_primitive_textured(col: bpy.types.Collection, model_filepath: Path, import_empty: bool = False, finder=None, context=None):
    write_to_blender_text("=== SMART RESOLVER IMPORT (V11) ===", clear=True)
    
    if finder is None: finder = WoTFileFinder()
    if context is None: context = {'last_pkg': None}
    
    try:
        model_xml = smart_xml_read(model_filepath)
        visual_internal_name = ""
        
        if model_xml is not None:
            for child in model_xml:
                tag_lower = child.tag.lower()
                if "node" in tag_lower and "parent" not in tag_lower:
                    visual_internal_name = child.text.strip()
                    break
                    
        if not visual_internal_name:
            visual_internal_name = model_filepath.stem
        v_path = None
        for ext in [".visual_processed", ".visual"]:
            target = visual_internal_name + ext
            v_path = finder.find(target, str(model_filepath.parent), target, context_pkg=context.get('last_pkg'))
            if v_path: break
            
        p_path = None
        for ext in [".primitives_processed", ".primitives"]:
            target = visual_internal_name + ext
            p_path = finder.find(target, str(model_filepath.parent), target, context_pkg=context.get('last_pkg'))
            if p_path: break

        if not v_path or not p_path:
            write_to_blender_text(f"[Error] Visual or Primitives not found for: {visual_internal_name}")
            return {"CANCELLED"}

        visual = smart_xml_read(v_path)
        if not visual: return {"CANCELLED"}

        root_empty_ob = None
        for rs in visual.findall("renderSet"):
            vres = rs.findtext("geometry/vertices").strip()
            mesh_name = os.path.splitext(vres)[0]
            uv2, col_name = "", ""
            for s in rs.findall("geometry/stream"):
                if "uv2" in s.text: uv2 = s.text.strip()
                elif "colour" in s.text: col_name = s.text.strip()

            dm = LoadDataMesh(str(p_path), vres, rs.findtext("geometry/primitive").strip(), uv2, col_name)
            bmesh = bpy.data.meshes.new(mesh_name); bmesh.vertices.add(len(dm.vertices))
            
            is_skinned = any("skinned" in (pg.findtext("material/fx") or "").lower() for pg in rs.findall("geometry/primitiveGroup"))
            if is_skinned and dm.bones_info:
                nm = build_node_matrices(visual.find("node"))
                bn = [n.text.strip() for n in rs.findall("node")]
                C = Matrix([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
                T = Matrix.Diagonal((1.0, -1.0, 1.0, 1.0)) 
                ri = (C @ nm.get("Scene Root", Matrix()) @ C).inverted()
                fm = [ri @ (C @ nm.get(b, Matrix()) @ C) @ T for b in bn]
                tv = []
                for i, co in enumerate(dm.vertices):
                    iw = dm.bones_info[i]
                    mp = [(iw[0], iw[7]), (iw[1], iw[5]), (iw[2], iw[6])] if len(iw)==8 else [(iw[0], iw[3]), (iw[1], iw[4]), (iw[2], max(0, 255-(iw[3]+iw[4])))]
                    bi = max(mp, key=lambda x: x[1])[0] // 3
                    if bi < len(fm):
                        p = fm[bi] @ Vector(co)
                        tv.extend([p.x, p.y, p.z])
                    else: tv.extend(co)
                bmesh.vertices.foreach_set("co", tv)
            else: bmesh.vertices.foreach_set("co", unpack_list(dm.vertices))
            
            nf = len(dm.indices); bmesh.polygons.add(nf)
            bmesh.polygons.foreach_set("loop_start", range(0, nf*3, 3))
            bmesh.polygons.foreach_set("loop_total", (3,)*nf)
            bmesh.loops.add(nf*3); bmesh.loops.foreach_set("vertex_index", unpack_list(dm.indices))
            if dm.uv_list:
                u = bmesh.uv_layers.new(name="uv1")
                for p in bmesh.polygons:
                    for l in p.loop_indices: u.data[l].uv = dm.uv_list[bmesh.loops[l].vertex_index]
            
            hv = False; vn = col_name or "BPVScolour"
            if hasattr(dm, "colour_list") and dm.colour_list:
                ca = bmesh.color_attributes.new(name=vn, type='FLOAT_COLOR', domain='POINT')
                fc = [1.0] * (len(bmesh.vertices)*4)
                for vi, c in enumerate(dm.colour_list): fc[vi*4:vi*4+4] = [c[2]/255.0, c[1]/255.0, c[0]/255.0, c[3]/255.0]
                ca.data.foreach_set("color", fc); hv = True

            for i, pg in enumerate(dm.PrimitiveGroups):
                pgv = next((v for v in rs.findall("geometry/primitiveGroup") if int(v.text) == i), None)
                mn = pgv.findtext("material/identifier").strip() if pgv is not None else f"mat_{i}"
                material = bpy.data.materials.get(mn) or bpy.data.materials.new(mn)
                bmesh.materials.append(material)
                
                if pgv is not None:
                    fx_node = pgv.find("material/fx")
                    material["bw_custom_fx"] = fx_node.text.strip() if fx_node is not None else "shaders/std_effects/PBS_tank_skinned.fx"
                    
                    props = pgv.findall("material/property")
                    for prop in props:
                        prop_name = prop.text.strip() if prop.text else ""
                        if not prop_name: continue
                        for child in prop:
                            tag = child.tag
                            val = child.text.strip() if child.text else ""
                            if tag == "Texture":
                                material[f"bw_tex_{prop_name}"] = val
                            elif tag in ["Bool", "Int", "Float", "Vector4"]:
                                material[f"bw_{tag.lower()}_{prop_name}"] = val
                    process_material_textures(material, props, str(model_filepath.parent), finder, context, has_vertex_color=hv, vcol_name=vn)
                    
                s_i = pg["startIndex"] // 3
                for fidx in range(s_i, s_i + pg["nPrimitives"]):
                    if fidx < len(bmesh.polygons): bmesh.polygons[fidx].material_index = i

            bmesh.validate(); bmesh.update()
            ob = bpy.data.objects.new(mesh_name, bmesh); col.objects.link(ob)

            if rs.find("treatAsWorldSpaceObject") is not None and "true" in rs.findtext("treatAsWorldSpaceObject").lower():
                if dm.bones_info:
                    barr = [{"n": n.text.strip(), "g": ob.vertex_groups.new(name=n.text.strip())} for n in rs.findall("node")]
                    for vi, iw in enumerate(dm.bones_info):
                        mp = [(iw[0], iw[7]), (iw[1], iw[5]), (iw[2], iw[6])] if len(iw)==8 else [(iw[0], iw[3]), (iw[1], iw[4]), (iw[2], max(0, 255-(iw[3]+iw[4])))]
                        for ri, w in mp:
                            if w > 0 and (ri // 3) < len(barr): barr[ri//3]["g"].add([vi], w/255.0, "ADD")
            
            if import_empty and visual.find("node") is not None:
                if root_empty_ob is None: root_empty_ob = create_armature_from_nodes(col, visual.findall("node")[0], model_filepath.stem)
                ob.parent = root_empty_ob
                ob.modifiers.new(type='ARMATURE', name="Armature").object = root_empty_ob

        return {"FINISHED"}
    except Exception:
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