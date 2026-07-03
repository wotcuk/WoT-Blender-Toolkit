import bpy
import os
import math
import random
from mathutils import Vector
import xml.etree.ElementTree as ET

try:
    from .file_finder import WoTFileFinder
    from .blender_vfx_node_connections import setup_vfx_material_nodes, setup_vfx_geometry_nodes, fill_emitter_nodes_from_xml
except ImportError as e:
    print(f"[VFX ERROR] Modüller bulunamadı! {e}")

def log(msg):
    print(msg)

def create_empty(name, parent=None):
    empty = bpy.data.objects.new(name or "Unnamed", None)
    empty.empty_display_type = 'PLAIN_AXES'
    bpy.context.collection.objects.link(empty)
    if parent:
        empty.parent = parent
    return empty

def create_plane(name, size_x=1.0, size_y=1.0):
    """Standart Plane oluşturucu (UV hazırlığı için)"""
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    
    hx, hy = size_x / 2.0, size_y / 2.0
    mesh.from_pydata([(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0)], [], [(0,1,2,3)])
    mesh.uv_layers.new(name="UVMap")
    return obj

def create_primitive(name, p_type='PLANE', parent=None):
    """Belirtilen tipte (PLANE veya CUBE) bir nesne oluşturur."""
    if p_type == 'CUBE':
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        obj = bpy.context.active_object
        obj.name = name
    else:
        obj = create_plane(name, 1.0, 1.0)
    
    if parent:
        obj.parent = parent
    return obj

def setup_global_wind():
    """Rüzgar (Wind) sistemi"""
    wind_col = bpy.data.collections.get("Wind")
    if not wind_col:
        wind_col = bpy.data.collections.new("Wind")
        bpy.context.scene.collection.children.link(wind_col)

    wind_obj = bpy.data.objects.get("Global_Wind_Emitter")
    if not wind_obj:
        wind_obj = create_plane("Global_Wind_Emitter", 2.0, 2.0)
        bpy.context.collection.objects.unlink(wind_obj) 
        wind_col.objects.link(wind_obj)
        
        loc = Vector((random.uniform(-30, 30), random.uniform(-30, 30), random.uniform(5, 15)))
        wind_obj.location = loc
        direction = -loc.normalized()
        wind_obj.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()
        wind_obj.rotation_euler[0] += math.radians(random.uniform(-15, 15))
    return wind_col

def sanitize_wot_xml(raw_text):
    cleaned = raw_text.replace("</hybrid_effect>", "<hybrid_effect/>")
    return cleaned

def parse_lod_block(lod_node, parent_empty, finder, dir_path):
    """LOD bloğu içindeki isim, maske, klip ve emitter hiyerarşisini işler."""
    # 1. LOD Name
    lod_name = lod_node.findtext("s_effect_name", "LOD_Unnamed").strip()
    lod_empty = create_empty(lod_name, parent=parent_empty)

    # 2. i_lod_mask (Custom Properties)
    mask_node = lod_node.find("i_lod_mask")
    if mask_node is not None:
        for bit in mask_node:
            if bit.text:
                lod_empty[bit.tag] = bool(int(bit.text.strip()))

    # 3. General LOD Settings
    for prop in ["f_near_clip", "f_far_clip", "f_Skip_time"]:
        val = lod_node.findtext(prop)
        if val:
            lod_empty[prop] = float(val.strip())

    # 4. dw_mode (LOD)
    dw_mode = lod_node.find("dw_mode")
    if dw_mode is not None:
        off_node = dw_mode.find("ps_element_off")
        if off_node is not None and off_node.text:
            lod_empty["ps_element_off"] = bool(int(off_node.text.strip()))

    # 5. Emitter 
    for em_node in lod_node.findall("emitter"):
        em_name = em_node.findtext("s_emitter_name", "Unnamed_Emitter").strip()
        
        
        emitter_obj = create_primitive(f"{em_name}_Emitter", 'CUBE', parent=lod_empty)
        instance_obj = create_primitive(f"{em_name}_Instance", 'PLANE', parent=lod_empty)
        settings_obj = create_primitive(f"{em_name}_EmitterSettings", 'PLANE', parent=lod_empty)
        
        
        emitter_obj.location = (0, 0, 0)
        instance_obj.location = (2, 0, 0)
        settings_obj.location = (4, 0, 0)

        setup_vfx_material_nodes(instance_obj)
        setup_vfx_geometry_nodes(settings_obj)
        fill_emitter_nodes_from_xml(em_node, instance_obj, settings_obj, emitter_obj, finder, dir_path)

def load_vfx_pipeline(filepath, parent_gn_tree=None):
    log(f"=== LOD & EMITTER HIERARCHY IMPORT ===")
    
    if parent_gn_tree is None:
        setup_global_wind()

    finder = WoTFileFinder()
    dir_path = os.path.dirname(filepath)
    
    xml_path = filepath

    with open(xml_path, 'r', encoding='utf-8', errors='ignore') as f:
        safe_xml_text = sanitize_wot_xml(f.read())

    try:
        root = ET.fromstring(safe_xml_text)
    except Exception as e:
        log(f"XML Parsing Error: {e}")
        return

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    root_empty = create_empty(f"Root_{base_name}")

    has_influx = root.find("influx") is not None
    has_gpu = root.find("gpu") is not None
    is_hybrid = has_influx and has_gpu
    root_empty["hybrid_effect"] = is_hybrid

    if is_hybrid:
        influx_empty = create_empty("influx", parent=root_empty)
        gpu_empty = create_empty("gpu", parent=root_empty)
        
        influx_node = root.find("influx")
        if influx_node is not None:
            dw_mode_lod = influx_node.find("dw_mode_lod_effect")
            if dw_mode_lod is not None:
                mut = dw_mode_lod.findtext("dw_mode_lodeffect_mutable")
                influx_empty["dw_mode_lodeffect_mutable"] = bool(int(mut)) if mut else False
            
            for lod in influx_node.findall("lod"):
                parse_lod_block(lod, influx_empty, finder, dir_path)
    else:
        # Mutable (Non-hybrid)
        dw_mode_lod = root.find("dw_mode_lod_effect")
        if dw_mode_lod is not None:
            mut = dw_mode_lod.findtext("dw_mode_lodeffect_mutable")
            root_empty["dw_mode_lodeffect_mutable"] = bool(int(mut)) if mut else False

        # Process LOD's
        for lod in root.findall("lod"):
            parse_lod_block(lod, root_empty, finder, dir_path)

    log("=== IMPORT COMPLETED ===")