import os
import subprocess
from struct import pack
from xml.dom.minidom import getDOMImplementation
import bpy
import math
from mathutils import Vector, Matrix, Euler

# --- SMART NAME AND PATH RESOLVER ---
def get_universal_config(obj, export_path, export_info):
    # Get original filename from init.py
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

    # --- NEW: If original name exists on the object, discard guessed names! ---
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

# --- VISUAL PROPERTY DEFINITIONS ---
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

def get_armature(mesh_objs):
    """Finds the main Armature object that the meshes are parented to."""
    for obj in mesh_objs:
        if obj.parent and obj.parent.type == 'ARMATURE': return obj.parent
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE' and mod.object: return mod.object
    return None

def get_pose_bone_matrix(arm_obj, bone_name):
    """Returns the world matrix of the PoseBone within the Armature."""
    if arm_obj and bone_name in arm_obj.pose.bones:
        return arm_obj.matrix_world @ arm_obj.pose.bones[bone_name].matrix
    return None

def pack_normal_int(n):
    try:
        n = n.normalized()
        x, y, z = int((n.x + 1.0) * 127.5), int((n.y + 1.0) * 127.5), int((n.z + 1.0) * 127.5)
        return ((max(0, min(255, z)) & 0xFF) << 16) | ((max(0, min(255, y)) & 0xFF) << 8) | (max(0, min(255, x)) & 0xFF)
    except: return 0x808080 

def log(msg):
    print(msg)
    text_name = "VFX_Export_Log"
    text_block = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    text_block.write(msg + "\n")

# Safely read value from node
def get_node_val(node, socket_name, default_val=0.0, is_string=False):
    if not node: return default_val
    sock = next((s for s in node.inputs if s.name.lower() == socket_name.lower()), None)
    if not sock: return default_val
    if is_string and sock.type == 'STRING': return sock.default_value
    try:
        if sock.type in ['VALUE', 'INT', 'FLOAT']: return sock.default_value
    except: pass
    return default_val


# --- BIGWORLD PATH CLEANER ---
def format_wot_path(filepath, is_shader=False):
    if not filepath:
        return ""
        
    if is_shader:
        # SHADER ARCHITECTURE: Keep original path, strictly use backslashes (\)
        clean_path = filepath.replace("/", "\\")
        
        # PRIORITY 1: If path contains \data\shaders\, extract from there
        idx_data = clean_path.lower().find("\\data\\shaders\\")
        if idx_data != -1:
            return clean_path[idx_data:]
            
        # PRIORITY 2: If no \data\, search for \shaders\
        idx = clean_path.lower().find("\\shaders\\")
        if idx != -1:
            return clean_path[idx:]
        elif clean_path.lower().startswith("shaders\\"):
            return "\\" + clean_path
            
        return clean_path

    # NORMAL ARCHITECTURE (Texture and Mesh): Use forward slashes (/)
    clean_path = filepath.replace("\\", "/").replace("//", "/")
    
    valid_roots = [
        "vehicles", "story_mode", "content", "vscript", "vegetation", 
        "system", "objects", "maps", "shaders", "server_side_replay", 
        "scripts", "resource_well", "prime_gaming_content", "particles", 
        "gui", "materials", "in_battle_achievements", "spaces", "audioww", 
        "battle_modifiers", "battle_royale", "comp7", "comp7_core", "comp7_light"
    ]
    
    clean_path_lower = clean_path.lower()
    
    for root in valid_roots:
        search_str = f"/{root}/"
        idx = clean_path_lower.find(search_str)
        if idx != -1:
            return clean_path[idx + 1:]
            
        if clean_path_lower.startswith(f"{root}/"):
            return clean_path
            
    return clean_path

# Helper to read points from a curve
def get_curve_pts(curve_node):
    pts = []
    if curve_node and curve_node.mapping.curves:
        for p in curve_node.mapping.curves[0].points:
            pts.append((float(p.location[0]), float(p.location[1])))
    return sorted(pts, key=lambda x: x[0])

# MATHEMATICAL FILLING (Linear Interpolation)
def interpolate_value(pts, target_time):
    if not pts: return 1.0 
    if target_time <= pts[0][0]: return pts[0][1]
    if target_time >= pts[-1][0]: return pts[-1][1]
    
    for i in range(len(pts) - 1):
        t1, v1 = pts[i]
        t2, v2 = pts[i+1]
        if t1 <= target_time <= t2:
            if t1 == t2: return v1
            ratio = (target_time - t1) / (t2 - t1)
            return v1 + ratio * (v2 - v1)
    return 1.0

# Find node by hidden ID or user-defined Label
def find_curve_node(tree, search_name):
    if not tree: return None
    # 1. Direct match
    if search_name in tree.nodes:
        return tree.nodes[search_name]
    
    # 2. Scan labels and visible names
    search_clean = search_name.lower()
    for node in tree.nodes:
        if node.label and search_clean in node.label.lower():
            return node
        if search_clean in node.name.lower():
            return node
    return None

def extract_curve_points(curve_node, xml_parent, tag_name, offset=None):
    curve_elem = ET.SubElement(xml_parent, tag_name)
    if offset: 
        curve_elem.set("offset", offset)
        
    if not curve_node or not curve_node.mapping.curves:
        curve_elem.set("points", "0")
        return
        
    points = curve_node.mapping.curves[0].points
    curve_elem.set("points", str(len(points)))
    
    for pt in points:
        pt_elem = ET.SubElement(curve_elem, "Point")
        pt_elem.set("time", str(round(pt.location[0], 4)))
        pt_elem.set("value", str(round(pt.location[1], 4)))

def export_vfx_pipeline(export_dir, filename_base):
    log("=== VFX EXPORT STARTED ===")
    
    root = ET.Element("VFX_Data")
    root.set("source_file", f"{filename_base}.vfxbin")
    
    # Use "in" to catch .001, .002 suffixes
    settings_objs = [obj for obj in bpy.context.scene.objects if "_emitter_settings" in obj.name]
    
    if not settings_objs:
        log("ERROR: No VFX settings object found in the scene to export!")
        return None

    for idx, settings_obj in enumerate(settings_objs):
        # 1. Separate names and suffixes like '.001'
        parts = settings_obj.name.split("_emitter_settings")
        base_name = parts[0]
        suffix = parts[1] if len(parts) > 1 else ""
        
        # 2. REAL NAME for XML (Never contains .001)
        if "Original_Layer_Name" in settings_obj:
            real_layer_name = str(settings_obj["Original_Layer_Name"])
        else:
            real_layer_name = base_name
            
        log(f"Processing: {real_layer_name} (Blender Object: {settings_obj.name})")
        
        layer_elem = ET.SubElement(root, "Layer")
        layer_elem.set("id", str(idx))
        
        # CLEAN NAME HERE (NO .001)
        layer_elem.set("name", real_layer_name)
        
        known_data = ET.SubElement(layer_elem, "Known_Parameters")
        
        # --- WRITE CHILD EFFECT INFO TO XML (SAFE ARCHITECTURE) ---
        if "Is_Child_Effect" in settings_obj:
            ET.SubElement(layer_elem, "Is_Child_Effect").text = "True"
            ET.SubElement(layer_elem, "Child_Source_File").text = str(settings_obj.get("Child_Source_File", ""))
            log(f"-> This layer is marked as a child effect ({real_layer_name})")
        else:
            # Write False for main effect to prevent Packer errors
            ET.SubElement(layer_elem, "Is_Child_Effect").text = "False"
            ET.SubElement(layer_elem, "Child_Source_File").text = "None"
        
        # Shortcut to add element and offset to XML
        def add_p(parent, name, offset, val):
            el = ET.SubElement(parent, name)
            if offset: el.set("offset", offset)
            el.text = str(val)

        # Find Nodes
        gn_mod = settings_obj.modifiers.get("VFX_WoT_Controller")
        wot_node = gn_mod.node_group.nodes.get("Wot .vfxbin to blender") if gn_mod and gn_mod.node_group else None
        
        # STRICTLY combine base_name and suffix when searching Blender objects
        anim_obj = bpy.data.objects.get(f"{base_name}_anim_instance{suffix}") or bpy.data.objects.get(f"{base_name}_mesh_instance{suffix}")
        mat = anim_obj.data.materials[0] if anim_obj and anim_obj.data.materials else None
        m_tree = mat.node_tree if mat and mat.use_nodes else None
        
        anim_n = m_tree.nodes.get("VFX_WoT_Animation") if m_tree else None
        alpha_calc = m_tree.nodes.get("Alpha calculator") if m_tree else None
        bsdf = m_tree.nodes.get("Principled BSDF") if m_tree else None
        tex_node = m_tree.nodes.get("Image Texture") if m_tree else None
        
        # 1. COMMON DATA AND OFFSETS
        emitter_obj = bpy.data.objects.get(f"{base_name}_Emitter{suffix}")
        
        # Get Blender's 3-axis dimensions
        b_size_x = round(emitter_obj.dimensions.x, 4) if emitter_obj else 0.2
        b_size_y = round(emitter_obj.dimensions.y, 4) if emitter_obj else 0.2
        b_size_z = round(emitter_obj.dimensions.z, 4) if emitter_obj else 0.0
        
        add_p(known_data, "Orientation_Vector_X", "0x14", "0.0")
        add_p(known_data, "Orientation_Vector_Y", "0x18", "0.0")
        add_p(known_data, "Orientation_Vector_Z", "0x1c", "0.0")
        add_p(known_data, "Particle_Count", "0x20", int(get_node_val(wot_node, "Count", 12)))
        
        spawn = ET.SubElement(known_data, "Spawn_Area")
        
        # Map axes DIRECTLY
        add_p(spawn, "Size_X", "0x28", b_size_x) 
        
        # Z Size (0x2C) -> Blender Z axis. If 0, write 0.2.
        bw_size_z = b_size_z
        if bw_size_z == 0.0:
            bw_size_z = 0.2
        add_p(spawn, "Size_Z", "0x2c", bw_size_z) 
        
        add_p(spawn, "Size_Y", "0x30", b_size_y) 
        
        add_p(spawn, "Spread_Angle_or_Radius", "0x34", "0.0")
        add_p(spawn, "Cone_Radius_Multiplier", "0x220", round(get_node_val(wot_node, "Distribution ratio (cone)", 0.2), 4))
        
        add_p(known_data, "Initial_Angle_Max", "0x38", round(math.radians(get_node_val(wot_node, "Inital Angle Max", 0.0)), 4))
        add_p(known_data, "Rotation_Speed_Max", "0x3c", round(math.radians(get_node_val(wot_node, "Rotation Speed Max", 0.0)), 4))
        add_p(known_data, "Rotation_Speed_Min", "0x40", round(math.radians(get_node_val(wot_node, "Rotation Speed Min", 0.0)), 4))
        
        # --- ALPHA OFFSET (READ FROM HIDDEN MEMORY) ---
        # Use original Alpha if saved in object, else get from Blender
        if "Original_Alpha_Offset" in settings_obj:
            orijinal_alpha = float(settings_obj["Original_Alpha_Offset"])
        else:
            orijinal_alpha = round(get_node_val(wot_node, "Alpha_Offset", 1.0), 4) 
            
        add_p(known_data, "Alpha_Offset", "0x4c", orijinal_alpha)
        add_p(known_data, "Wind_Multiplier_Min", "0x50", round(get_node_val(wot_node, "Wind Min", 0.0), 4))
        add_p(known_data, "Wind_Multiplier_Max", "0x54", round(get_node_val(wot_node, "Wind Max", 0.0), 4))
        
        add_p(known_data, "FFFF_Block_0x5C", "0x5c", "FF FF FF FF")
        add_p(known_data, "Unknown_Flag_0x94", "0x94", "02 00 00 00")
        add_p(known_data, "Unknown_Flag_0xBC", "0xbc", "01 00 00 00")
        add_p(known_data, "FFFF_Block_0x160", "0x160", "FF FF FF FF")
        
        add_p(known_data, "Life_Time_Min", "0xa0", round(get_node_val(wot_node, "Life Time Min", 3.0), 4))
        add_p(known_data, "Life_Time_Max", "0xa4", round(get_node_val(wot_node, "Life Time Max", 3.5), 4))
        add_p(known_data, "Trigger_Delay_Min", "0xa8", "0.0")
        add_p(known_data, "Trigger_Delay_Max", "0xac", "0.0")
        
        # 1. TEXTURE PATH (MESH & SPRITE STRICT RULE)
        is_mesh = False
        if anim_obj and "Original_Visual_Path" in anim_obj:
            if str(anim_obj["Original_Visual_Path"]).strip() != "":
                is_mesh = True
                
        if "Child_VFX_Path" in settings_obj:
            # Valid for Mesh and Sprite: If there is a child effect, that is the path!
            tex_path = str(settings_obj["Child_VFX_Path"])
        elif is_mesh:
            # STRICT RULE: If object is a Mesh and has no child effect, texture MUST be "None"!
            tex_path = "None"
        else:
            # IF NOT MESH (Sprite): Get image path
            tex_path = tex_node.image.filepath if tex_node and tex_node.image else ""
            
        tex_path = format_wot_path(tex_path, is_shader=False) 
        add_p(known_data, "Texture_Path", "0xc0", tex_path)
        
        # 2. Shader Path (Get original from node and format ONLY as Shader)
        fx_path = get_node_val(wot_node, "FX file location", "\\shaders\\wg_particles\\pbs_mesh_particles.fx", True)
        fx_path = format_wot_path(fx_path, is_shader=True) 
        add_p(known_data, "Shader_Path", "0x1a0", fx_path)
        
        # --- NEW ARCHITECTURE: SHADERS WHERE WIDTH CONTROLS LENGTH ---
        UNIFORM_SHADERS = ["pbs_mesh_particles.fx"]
        is_uniform_scale = any(s in fx_path.lower() for s in UNIFORM_SHADERS)
        
        # 3. Mesh Path
        mesh_path = ""
        if anim_obj and "Original_Visual_Path" in anim_obj:
            mesh_path = str(anim_obj["Original_Visual_Path"])
            
        mesh_path = format_wot_path(mesh_path, is_shader=False)
        add_p(known_data, "Mesh_Path", "0x490", mesh_path)
        
        # 4. Size and Speeds
        add_p(known_data, "Width_Min", "0x140", round(get_node_val(wot_node, "Base X Scale Min", 0.1), 4))
        add_p(known_data, "Width_Max", "0x144", round(get_node_val(wot_node, "Base X Scale Max", 0.4), 4))
        add_p(known_data, "Init_Vertical_Speed_Min", "0x148", round(get_node_val(wot_node, "Vertical Speed Min", 1.0), 4))
        add_p(known_data, "Init_Vertical_Speed_Max", "0x14c", round(get_node_val(wot_node, "Vertical Speed Max", 6.0), 4))
        
        add_p(known_data, "V_Max", "0x150", round(get_node_val(anim_n, "V_Max", 1.0), 4))
        add_p(known_data, "U_Max", "0x15c", round(get_node_val(anim_n, "U_Max", 1.0), 4))
        add_p(known_data, "V_Min", "0x158", round(get_node_val(anim_n, "V_Min", 0.0), 4))
        add_p(known_data, "U_Min", "0x154", round(get_node_val(anim_n, "U_Min", 0.0), 4))
        
        add_p(known_data, "Acceleration_Min", "0x164", round(get_node_val(wot_node, "Acc Min", 0.28), 4))
        add_p(known_data, "Acceleration_Max", "0x17c", round(get_node_val(wot_node, "Acc Max", 0.6), 4))
        
        # 5. Length Architecture (Offset Hiding)
        if is_uniform_scale:
            # Pass 'None' to offset parameter to PREVENT writing offset="" to XML.
            # This makes Packer skip these lines and write the original 0x178/0x424 values in Unknown Parameters.
            add_p(known_data, "Length_Max", None, round(get_node_val(wot_node, "Base Y Scale Max", 0.4), 4))
            add_p(known_data, "Length_Min", None, round(get_node_val(wot_node, "Base Y Scale Min", 0.1), 4))
        else:
            add_p(known_data, "Length_Max", "0x178", round(get_node_val(wot_node, "Base Y Scale Max", 0.4), 4))
        add_p(known_data, "Z_Bias", "0x19c", "0.0")
        
        flags = ET.SubElement(known_data, "Flags")
        add_p(flags, "Animation_Mode", "0x168", "3")
        add_p(flags, "Flip_Visual_180", "0x169", "0")
        add_p(flags, "Axis_Orientation", "0x16b", "0")
        
        add_p(known_data, "Cols", "0x16c", int(get_node_val(anim_n, "Cols", 1)))
        add_p(known_data, "Rows", "0x170", int(get_node_val(anim_n, "Rows", 1)))
        add_p(known_data, "Animation_Speed", "0x174", round(get_node_val(anim_n, "Rate", 1.0), 4))
        
        add_p(known_data, "Rot_Speed_Z_Max", "0x180", round(get_node_val(wot_node, "z rotation speed max", 0.0), 4))
        add_p(known_data, "Rot_Speed_Z_Min", "0x184", round(get_node_val(wot_node, "z rotation speed min", 0.0), 4))
        add_p(known_data, "Rot_Speed_X_Max", "0x188", round(get_node_val(wot_node, "x rotation speed max", 0.0), 4))
        add_p(known_data, "Rot_Speed_X_Min", "0x18c", round(get_node_val(wot_node, "x rotation speed min", 0.0), 4))
        add_p(known_data, "Rot_Speed_Y_Max", "0x190", round(get_node_val(wot_node, "y rotation speed max", 0.0), 4))
        add_p(known_data, "Rot_Speed_Y_Min", "0x194", round(get_node_val(wot_node, "y rotation speed min", 0.0), 4))
        add_p(known_data, "Unknown_Deflection_0x198", "0x198", "0.0")
        add_p(known_data, "Info_String", "0x350", "")
        
        add_p(known_data, "Init_Rot_Range_Z_Rad", "0x3bc", round(get_node_val(wot_node, "z first rotation value", 3.142), 4))
        add_p(known_data, "Init_Rot_Range_X_Rad", "0x3c0", round(get_node_val(wot_node, "x first rotation value", 3.142), 4))
        add_p(known_data, "Init_Rot_Range_Y_Rad", "0x3c4", round(get_node_val(wot_node, "y first rotation value", 3.142), 4))
        
        glow = ET.SubElement(known_data, "Lighting_and_Glow")
        add_p(glow, "Base_Emission", "0x3dc", round(bsdf.inputs['Emission Strength'].default_value if bsdf else 1.0, 4))
        
        # 2. CURVES AND OFFSETS
        curves_elem = ET.SubElement(layer_elem, "Curves")
        x_curve = gn_mod.node_group.nodes.get("X Scale Curve") if gn_mod and gn_mod.node_group else None
        extract_curve_points(x_curve, curves_elem, "Curve_Scale", "0x590")
        
        # --- TIME POOL AND MATHEMATICAL FILLING ---
        r_node = find_curve_node(m_tree, "R Curve")
        g_node = find_curve_node(m_tree, "G Curve")
        b_node = find_curve_node(m_tree, "B Curve")
        a_node = find_curve_node(m_tree, "Alpha Curve")

        r_pts = get_curve_pts(r_node)
        g_pts = get_curve_pts(g_node)
        b_pts = get_curve_pts(b_node)
        a_pts = get_curve_pts(a_node)

        # 1. TIME POOL: Collect all unique times
        time_pool = set()
        for pts in [r_pts, g_pts, b_pts, a_pts]:
            for t, v in pts:
                time_pool.add(round(t, 4))
        
        sorted_times = sorted(list(time_pool))

        # 2. Write empty if no color points exist
        if not sorted_times:
            extract_curve_points(r_node, curves_elem, "Curve_Color_R", "0x638")
            extract_curve_points(g_node, curves_elem, "Curve_Color_G", "0x638")
            extract_curve_points(b_node, curves_elem, "Curve_Color_B", "0x638")
            extract_curve_points(a_node, curves_elem, "Curve_Alpha_A", "0x638")
        else:
            # 3. Calculate value for each curve based on pooled times and write EQUALLY to XML
            def write_pooled_curve(tag_name, pts_data):
                c_elem = ET.SubElement(curves_elem, tag_name)
                c_elem.set("offset", "0x638")
                c_elem.set("points", str(len(sorted_times)))
                for t in sorted_times:
                    val = interpolate_value(pts_data, t)
                    pt_elem = ET.SubElement(c_elem, "Point")
                    pt_elem.set("time", str(t))
                    pt_elem.set("value", str(round(val, 4)))

            write_pooled_curve("Curve_Color_R", r_pts)
            write_pooled_curve("Curve_Color_G", g_pts)
            write_pooled_curve("Curve_Color_B", b_pts)
            write_pooled_curve("Curve_Alpha_A", a_pts)

        # =========================================================================
        # 3. UNKNOWN PARAMETERS & HEADER SYSTEM (READ FROM BLENDER MEMORY)
        # =========================================================================
        unknown_data = None
        
        # PRIORITY 1: Original Unknown and Header data saved to object memory!
        if "Unknown_Params_XML" in settings_obj:
            try:
                xml_str = str(settings_obj["Unknown_Params_XML"])
                unknown_data = ET.fromstring(xml_str)
                log(f"-> Unknown_Parameters loaded from original object memory! ({real_layer_name})")
            except Exception as e:
                log(f"-> Failed to read XML from memory: {e}")

        # FALLBACK 2: If not in memory (created from scratch), look for static file
        if unknown_data is None:
            possible_paths = [
                os.path.join(export_dir, "default_unknowns.xml"), 
                r"C:\Users\ahmet\OneDrive\Documentos\default_unknowns.xml", 
                os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "default_unknowns.xml"), 
                os.path.join(os.path.dirname(__file__), "default_unknowns.xml") 
            ]
            
            found_path = None
            for p in possible_paths:
                if os.path.exists(p):
                    found_path = p
                    break
                    
            if found_path:
                try:
                    temp_tree = ET.parse(found_path)
                    temp_root = temp_tree.getroot()
                    
                    if temp_root.tag == "Unknown_Parameters":
                        unknown_data = temp_root
                    else:
                        unknown_data = temp_root.find(".//Unknown_Parameters")
                        
                    if unknown_data is not None:
                        log(f"-> Unknown_Parameters added from external file: {found_path} ({real_layer_name})")
                except Exception as e:
                    log(f"-> Warning: Failed to read {found_path}! Error: {e}")
            else:
                log("-> WARNING: default_unknowns.xml not found in any path!")
                
        # If not found in both, append an empty block
        if unknown_data is None:
            unknown_data = ET.SubElement(layer_elem, "Unknown_Parameters")
            ET.SubElement(unknown_data, "Offset_0x0").text = "0.0"
        else:
            # Append found original (or fallback) data to XML
            layer_elem.append(unknown_data)

    # =========================================================================
    # CLEAN XML OUTPUT (Prevent excessive spacing)
    # =========================================================================
    if hasattr(ET, "indent"):
        ET.indent(root, space="    ", level=0)
    
    # Write XML data directly (without minidom)
    xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    out_path = os.path.join(export_dir, f"e_{filename_base}.vfxxml")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
        
    log(f"=== SUCCESS: {out_path} created! ===")
    
    # 4. HOOK FOR PACKER (.vfxbin converter)
    try:
        from .pack_vfxbin import pack_xml_to_vfxbin
        final_vfxbin_path = os.path.join(export_dir, f"{filename_base}.vfxbin")
        log("Packer found. Compiling .vfxbin file...")
        pack_xml_to_vfxbin(out_path, final_vfxbin_path)
    except ImportError:
        log("Note: pack_vfxbin.py module not found, .vfxbin conversion skipped. Only XML generated.")
        
    return out_path