# -*- coding: utf-8 -*-
"""SkepticalFox 2015-2024 & Wotcuk (2026)- TEXTURED VERSION (V11: VERTEX COLOR ALPHA SUPPORT)"""

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

def load_image_safe(path_str, base_path, finder, context, is_data=False):
    clean_path = path_str.replace("\\", "/").strip("/")
    
    fpath = finder.find(clean_path, str(base_path), clean_path, context_pkg=context.get('last_pkg'))
            
    if not fpath:
        write_to_blender_text(f"[Warning] Texture not found: {clean_path}")
        return None

    if finder.last_found_pkg:
        context['last_pkg'] = finder.last_found_pkg

    fname = os.path.basename(fpath)
    fname_tga = fname.replace(".dds", ".tga").replace(".DDS", ".tga")
    fname_png = fname.replace(".dds", ".png").replace(".DDS", ".png")
    
    try:
        # Önce Blender'da yüklü mü diye hem TGA hem PNG için kontrol et
        for existing_fname in [fname_tga, fname_png]:
            if existing_fname in bpy.data.images:
                img = bpy.data.images[existing_fname]
                if img.size[0] > 0 and img.size[1] > 0:
                    return img
                else:
                    bpy.data.images.remove(img) 

        temp_dir = tempfile.gettempdir()
        texconv_path = os.path.join(os.path.dirname(__file__), "texconv.exe") 
        
        img = None
        
        # 1. DENEME: Asıl tercih edilen TGA formatı
        try:
            subprocess.run(
                [texconv_path, "-ft", "tga", "-o", temp_dir, "-y", fpath],
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            temp_path = os.path.join(temp_dir, fname_tga)
            img = bpy.data.images.load(temp_path)
            img.pack()
            
            try:
                os.remove(temp_path)
            except:
                pass
                
        except subprocess.CalledProcessError as sub_err_tga:
            write_to_blender_text(f"[Info] TGA conversion failed for {fname}, falling back to PNG...")
            
            # 2. DENEME (FALLBACK): TGA çöktüyse gradyan haritaları için PNG dene
            try:
                subprocess.run(
                    [texconv_path, "-ft", "png", "-o", temp_dir, "-y", fpath],
                    check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                temp_path = os.path.join(temp_dir, fname_png)
                img = bpy.data.images.load(temp_path)
                img.pack()
                
                try:
                    os.remove(temp_path)
                except:
                    pass
                    
            except subprocess.CalledProcessError as sub_err_png:
                write_to_blender_text(f"[Error] Both TGA and PNG conversion failed for {fname}. TGA Error: {sub_err_tga}")
                return None
            
        if img and is_data: 
            img.colorspace_settings.name = 'Non-Color'
            
        return img
        
    except Exception as e:
        write_to_blender_text(f"[Error] General Texture load error: {fname} ({e})")
        return None
def process_material_textures(mat, props_xml, base_path, finder, context, has_vertex_color=False, vcol_name="BPVScolour"):
    try:
        # --- %100 TÜM FORMATLARI İÇEREN Gelişmiş DDS DEDEKTÖRÜ (TARAMA RAPORUNA GÖRE GÜNCELLENDİ) ---
        import struct
        def get_dds_format(filepath):
            if not os.path.exists(filepath): return "BC1_UNORM"
            try:
                with open(filepath, 'rb') as f:
                    if f.read(4) != b'DDS ': return "BC1_UNORM"
                    
                    f.seek(80) # PixelFormat.dwFlags konumuna zıpla
                    pf_flags = struct.unpack('<I', f.read(4))[0]
                    fourcc = f.read(4) # Offset 84
                    
                    # 1. DDPF_FOURCC (0x4) Bayrağı Varsa:
                    if pf_flags & 0x4:
                        # Standart 8-Bit / 16-Bit / 32-Bit Metin (String) Sıkıştırmaları
                        if fourcc == b'DXT1': return "BC1_UNORM"
                        elif fourcc == b'DXT3': return "BC2_UNORM"
                        elif fourcc == b'DXT5': return "BC3_UNORM"
                        elif fourcc in [b'ATI1', b'BC4U']: return "BC4_UNORM"
                        elif fourcc in [b'ATI2', b'BC5U', b'DXT5' if fourcc==b'ATI2' else b'']: return "BC5_UNORM"
                        
                        # Modern DX10 Genişletilmiş Başlık
                        elif fourcc == b'DX10': 
                            f.seek(128) # DX10 header başlangıcı
                            dxgi_format = struct.unpack('<I', f.read(4))[0]
                            
                            # Tam Doğru DXGI Format Haritası (SRGB ve UNORM Ayrımı Korunarak):
                            if dxgi_format in [70, 71]: return "BC1_UNORM"
                            elif dxgi_format == 72: return "BC1_UNORM_SRGB"
                            elif dxgi_format in [73, 74]: return "BC2_UNORM"
                            elif dxgi_format == 75: return "BC2_UNORM_SRGB"
                            elif dxgi_format in [76, 77]: return "BC3_UNORM"
                            elif dxgi_format == 78: return "BC3_UNORM_SRGB"
                            elif dxgi_format in [79, 80]: return "BC4_UNORM"
                            elif dxgi_format == 81: return "BC4_SNORM"
                            elif dxgi_format in [82, 83]: return "BC5_UNORM"
                            elif dxgi_format == 84: return "BC5_SNORM"
                            elif dxgi_format in [97, 98]: return "BC7_UNORM"
                            elif dxgi_format == 99: return "BC7_UNORM_SRGB"
                            elif dxgi_format == 61: return "R8_UNORM"
                            elif dxgi_format in [27, 28]: return "R8G8B8A8_UNORM"
                            elif dxgi_format == 29: return "R8G8B8A8_UNORM_SRGB"
                            elif dxgi_format in [2, 10]: return "R32G32B32A32_FLOAT"
                            elif dxgi_format in [87, 93]: return "B8G8R8A8_UNORM"
                            elif dxgi_format == 91: return "B8G8R8A8_UNORM_SRGB"
                            
                        # Klasik D3DFORMAT Integer (Sayısal) Kodları
                        else:
                            fourcc_int = struct.unpack('<I', fourcc)[0]
                            if fourcc_int == 116: return "R32G32B32A32_FLOAT"   # 74000000 (Gradients/Ramp)
                            elif fourcc_int == 113: return "R16G16B16A16_FLOAT" # 71000000 (Küpler / sh_grid)
                            elif fourcc_int == 114: return "R32_FLOAT"          # 72000000 (inv_table)
                            elif fourcc_int == 111: return "R16_FLOAT"
                            elif fourcc_int == 36: return "R16G16B16A16_UNORM" 
                            elif fourcc_int == 21: return "B8G8R8A8_UNORM"      # A8R8G8B8
                            
                    # 2. Sıkıştırılmamış Ham (RGB/RGBA) formatlar (DDPF_RGB vb.) -> 0x40
                    elif pf_flags & 0x40: 
                        f.seek(88) # RGB Bit Count
                        bit_count = struct.unpack('<I', f.read(4))[0]
                        if bit_count == 32: return "B8G8R8A8_UNORM"    # RAW_UNCOMPRESSED 32-bit
                        elif bit_count == 24: return "B8G8R8X8_UNORM"  # RAW_UNCOMPRESSED 24-bit
                        elif bit_count == 8: return "R8_UNORM"         # RAW_UNCOMPRESSED 8-bit
                        
                    # 3. Yalnızca Alpha İçeren Formatlar (DDPF_ALPHA) -> 0x2
                    elif pf_flags & 0x2:
                        return "A8_UNORM"                              # ALPHA_ONLY 8-bit (Bulut maskeleri)
                        
                    # 4. Luminance Formatı (DDPF_LUMINANCE) -> 0x20000
                    elif pf_flags & 0x20000:
                        return "R8_UNORM"                              # UNIDENTIFIED (Ateş / Cookie maskeleri)

            except: pass
            return "BC1_UNORM" # Bulunamazsa güvenli varsayılan değer
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
            # Orijinal DDS formatını tara ve materyale mühürle
            if exact_name and prop.find("Texture") is not None and val:
                clean_path = val.replace("\\", "/").strip("/")
                fpath = finder.find(clean_path, str(base_path), clean_path, context_pkg=context.get('last_pkg'))
                if fpath:
                    mat[f"bw_dds_format_{exact_name}"] = get_dds_format(fpath)

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
        # --- BÜTÜN PARAMETRELERİ NODE OLARAK SAHNEYE EKLEME ---
        # Temiz düzen:
        #   - Her tür solda ayrı ana frame içinde durur.
        #   - Frame'ler iç içe DEĞİL; solda alt alta geniş boşlukla dizilir.
        #   - Vector4 artık Color/RGB node değil:
        #       g_detailUVTiling.xyz -> Combine XYZ
        #       g_detailUVTiling.w   -> Value
        #     İkisi aynı Vector4 frame içinde aynı satırda durur.
        #   - Shader scriptleri sonraki adımda .xyz/.w node düzenini okuyacak.

        def _new_frame(name, label, loc, color):
            frame = nodes.new('NodeFrame')
            frame.name = name
            frame.label = label
            frame.location = loc
            try:
                frame.use_custom_color = True
                frame.color = color
            except Exception:
                pass
            return frame

        def _set_node_color(node, color):
            try:
                node.use_custom_color = True
                node.color = color
            except Exception:
                pass

        def _put_in_frame(node, frame, rel_loc):
            # Önce parent ver, sonra relative location ayarla.
            # Böylece node'lar frame içine düzgün, üst üste binmeden yerleşir.
            try:
                node.parent = frame
            except Exception:
                pass
            node.location = rel_loc

        # 1. Parametreleri türlerine göre ayır.
        bool_props = []
        tex_props = []
        vec4_props = []
        float_props = []
        int_props = []

        # bool, int'in alt sınıfı olduğu için bool kontrolü önce.
        for p_name, p_val in extra_props.items():
            if isinstance(p_val, bool):
                bool_props.append((p_name, p_val))
            elif isinstance(p_val, str) and p_val.lower().endswith(".dds"):
                tex_props.append((p_name, p_val))
            elif isinstance(p_val, list) and len(p_val) >= 4:
                vec4_props.append((p_name, p_val))
            elif isinstance(p_val, list) and len(p_val) >= 3:
                vec4_props.append((p_name, list(p_val) + [0.0]))
            elif isinstance(p_val, float):
                float_props.append((p_name, p_val))
            elif isinstance(p_val, int):
                int_props.append((p_name, p_val))

        bool_props.sort(key=lambda x: x[0].lower())
        tex_props.sort(key=lambda x: x[0].lower())
        vec4_props.sort(key=lambda x: x[0].lower())
        float_props.sort(key=lambda x: x[0].lower())
        int_props.sort(key=lambda x: x[0].lower())

        # 2. Soldaki ana frame yerleşimi.
        # Yüksekliği tahmini hesaplıyoruz ki frame'ler birbirinin üstüne binmesin.
        left_x = -2600
        top_y = 1200
        gap_y = 260

        bool_h = max(260, len(bool_props) * 120 + 160)
        tex_h = max(360, len(tex_props) * 320 + 180)
        vec4_h = max(360, len(vec4_props) * 210 + 180)
        float_h = max(260, len(float_props) * 120 + 160)
        int_h = max(260, len(int_props) * 120 + 160)

        y_bool = top_y
        y_tex = y_bool - bool_h - gap_y
        y_vec4 = y_tex - tex_h - gap_y
        y_float = y_vec4 - vec4_h - gap_y
        y_int = y_float - float_h - gap_y

        frame_bool = _new_frame("BW_FRAME_Bools", "BW BOOL PARAMETERS", (left_x, y_bool), (0.18, 0.32, 0.95))
        frame_tex = _new_frame("BW_FRAME_Textures", "BW TEXTURE PARAMETERS", (left_x, y_tex), (0.55, 0.24, 0.85))
        frame_vec4 = _new_frame("BW_FRAME_Vector4", "BW VECTOR4 PARAMETERS", (left_x, y_vec4), (0.14, 0.62, 0.36))
        frame_float = _new_frame("BW_FRAME_Floats", "BW FLOAT PARAMETERS", (left_x, y_float), (0.95, 0.55, 0.18))
        frame_int = _new_frame("BW_FRAME_Ints", "BW INT PARAMETERS", (left_x, y_int), (0.85, 0.25, 0.20))

        # 3. Bool node'ları: tek kolon, rahat boşluk.
        rel_y = 0
        for p_name, p_val in bool_props:
            vn = nodes.new('ShaderNodeValue')
            vn.label = p_name
            vn.name = p_name
            vn.outputs[0].default_value = 1.0 if p_val else 0.0
            _set_node_color(vn, (0.18, 0.32, 0.95))
            _put_in_frame(vn, frame_bool, (40, rel_y))
            rel_y -= 120

        # 4. Texture node'ları: tek kolon, her texture arasında geniş boşluk.
        rel_y = 0
        for p_name, p_val in tex_props:
            is_data = any(x in p_name.lower() for x in [
                "normal", "gmm", "pbs", "metallic", "roughness", "gloss",
                "ao", "mask", "id", "detail", "depth"
            ])
            img = load_image_safe(p_val, base_path, finder, context, is_data=is_data)
            if img:
                vn = nodes.new('ShaderNodeTexImage')
                vn.image = img
                vn.label = p_name
                vn.name = p_name
                try:
                    vn.extension = 'REPEAT'
                except Exception:
                    pass
                _set_node_color(vn, (0.55, 0.24, 0.85))
                _put_in_frame(vn, frame_tex, (40, rel_y))
                rel_y -= 320

        # 5. Vector4 node'ları: iç içe frame yok.
        # Her Vector4 satırında solda .xyz, sağda .w durur.
        rel_y = 0
        for p_name, p_val in vec4_props:
            vals = [0.0, 0.0, 0.0, 0.0]
            for idx in range(min(4, len(p_val))):
                try:
                    vals[idx] = float(p_val[idx])
                except Exception:
                    vals[idx] = 0.0

            xyz = nodes.new('ShaderNodeCombineXYZ')
            xyz.name = f"{p_name}.xyz"
            xyz.label = f"{p_name}.xyz"
            xyz.inputs['X'].default_value = vals[0]
            xyz.inputs['Y'].default_value = vals[1]
            xyz.inputs['Z'].default_value = vals[2]
            _set_node_color(xyz, (0.14, 0.62, 0.36))
            _put_in_frame(xyz, frame_vec4, (40, rel_y))

            wv = nodes.new('ShaderNodeValue')
            wv.name = f"{p_name}.w"
            wv.label = f"{p_name}.w"
            wv.outputs[0].default_value = vals[3]
            _set_node_color(wv, (0.14, 0.62, 0.36))
            _put_in_frame(wv, frame_vec4, (340, rel_y))

            # İsim etiketi için ayrı küçük Value node kullanmıyorum; node label zaten yeterli.
            rel_y -= 210

        # 6. Float node'ları.
        rel_y = 0
        for p_name, p_val in float_props:
            vn = nodes.new('ShaderNodeValue')
            vn.label = p_name
            vn.name = p_name
            vn.outputs[0].default_value = float(p_val)
            _set_node_color(vn, (0.95, 0.55, 0.18))
            _put_in_frame(vn, frame_float, (40, rel_y))
            rel_y -= 120

        # 7. Int node'ları.
        rel_y = 0
        for p_name, p_val in int_props:
            vn = nodes.new('ShaderNodeValue')
            vn.label = p_name
            vn.name = p_name
            vn.outputs[0].default_value = float(int(p_val))
            _set_node_color(vn, (0.85, 0.25, 0.20))
            _put_in_frame(vn, frame_int, (40, rel_y))
            rel_y -= 120

        # 8. Vertex Color ayrı dursun; shader scriptleri bunu doğrudan VertexColor adıyla arıyor.
        if has_vertex_color:
            vcol = nodes.new('ShaderNodeAttribute')
            vcol.attribute_name = vcol_name
            vcol.name = "VertexColor"
            vcol.label = "VertexColor"
            vcol.location = (left_x, y_int - int_h - gap_y)
            _set_node_color(vcol, (0.25, 0.55, 1.0))

        # --- İLGİLİ SHADER SCRIPTINI ÇAĞIR ---
        fx_name = mat.get("bw_custom_fx", "").lower()
        
        try:
            from .shaders.shader_registry import SHADER_SCRIPT_MAP
            matched = False
            for key, script in SHADER_SCRIPT_MAP.items():
                if key in fx_name:
                    script.setup_nodes(mat, nodes, links)
                    matched = True
                    break
            
            # Eğer kayıtlı bir shader yoksa fallback olarak pbs_tank shaderını bağla
            if not matched:
                default_script = SHADER_SCRIPT_MAP.get("pbs_tank")
                if default_script:
                    default_script.setup_nodes(mat, nodes, links)
                else:
                    # pbs_tank bile yüklenemezse en son çare olarak sadece diffuse bağla
                    diff = nodes.get("diffuseMap")
                    if diff: links.new(diff.outputs['Color'], bsdf.inputs['Base Color'])
                
        except Exception as shader_err:
            write_to_blender_text(f"[Shader Registry Error] {fx_name} için hata: {shader_err}")
            
    except Exception as e: 
        write_to_blender_text(f"[Error] Material Node Error: {e}")

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
            # 1. Shader TAWSO (Skinned) mu istiyor?
            tawso = rs.find("treatAsWorldSpaceObject")
            is_tawso = True if (tawso is not None and "true" in tawso.text.lower()) else False
            
            # 2. SENİN TESPİTİN: renderSet içinde gerçekten BlendBone veya özel bir kemik (node) var mı?
            # Eğer model kemiksizse exporter buraya <node> etiketi yazmaz (0 olur).
            has_bones = len(rs.findall("node")) > 0
            
            # 3. Sadece TAWSO ise DEĞİL, aynı zamanda içinde kemik barındırıyorsa gerçekten Skinned'dir!
            truly_skinned = is_tawso and has_bones

            vres = rs.findtext("geometry/vertices").strip()
            mesh_name = os.path.splitext(vres)[0]
            uv2, col_name = "", ""
            for s in rs.findall("geometry/stream"):
                if "uv2" in s.text: uv2 = s.text.strip()
                elif "colour" in s.text: col_name = s.text.strip()

            # truly_skinned bilgisini loaddatamesh'e yolluyoruz
            dm = LoadDataMesh(str(p_path), vres, rs.findtext("geometry/primitive").strip(), uv2, col_name, is_truly_skinned=truly_skinned)
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
            ob["bw_renderSet_tawso"] = bool(is_tawso)
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