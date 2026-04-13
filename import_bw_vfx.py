import bpy
import os
import math
import random
import xml.etree.ElementTree as ET
from mathutils import Vector

# Import Unpacker module
try:
    from .unpack_vfxbin import unpack_vfxbin_to_xml
    from .import_bw_primitives_textured import load_bw_primitive_textured
    from pathlib import Path
except ImportError as e:
    print(f"[VFX ERROR] unpack_vfxbin.py not found! {e}")

def log(msg):
    print(msg)
    text_name = "VFX_Log"
    text_block = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    text_block.write(msg + "\n")

def init_log(filepath):
    text_name = "VFX_Log"
    text_block = bpy.data.texts.get(text_name)
    if text_block: text_block.clear()
    else: text_block = bpy.data.texts.new(text_name)
    log(f"=== VFX IMPORT V6.10 (Scale Curves Added) ===")
    log(f"File: {filepath}\n")

def find_texture_smart(base_path, rel_path):
    if not rel_path or str(rel_path).strip().lower() == "none": 
        return None
        
    clean = rel_path.replace("\\", "/").strip("/")
    
    # BigWorld Trap: XML specifies .tex but actual file is .dds, or .vfx but actually .vfxbin
    if clean.lower().endswith(".tex"):
        clean = clean[:-4] + ".dds"
    elif clean.lower().endswith(".vfx"):
        clean = clean[:-4] + ".vfxbin"
        
    parts = clean.split("/")
    target_file = parts[-1] 
    curr = base_path
    
    # Loop up to 15 times moving up the directory tree
    for _ in range(15):
        # Search directly in the current folder
        test_direct = os.path.join(curr, target_file)
        if os.path.isfile(test_direct): 
            return test_direct
            
        # If not found, search through other folder segments
        if len(parts) > 1:
            for i in range(len(parts) - 2, -1, -1):
                test_path = os.path.join(curr, *parts[i:])
                if os.path.isfile(test_path):
                    return test_path
                    
        # Move to parent directory
        next_curr = os.path.dirname(curr)
        if next_curr == curr: 
            break
        curr = next_curr
        
    return None

# ==========================================================================
# 1. NODE GROUP GENERATOR (Called by init menu)
# ==========================================================================
def ensure_wot_animation_node():
    group_name = "VFX_WoT_Animation_Node"
    if group_name in bpy.data.node_groups:
        return bpy.data.node_groups[group_name]

    log(f"Warning: '{group_name}' not found. Generating in background...")
    group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
    
    for name in ["Cols", "Rows", "Rate", "U_Min", "U_Max", "V_Min", "V_Max", "Frame"]:
        group.interface.new_socket(name=name, in_out='INPUT', socket_type='NodeSocketFloat')
    
    group.interface.new_socket(name="UV_Vector", in_out='OUTPUT', socket_type='NodeSocketVector')
    
    nodes = group.nodes
    links = group.links
    
    gin = nodes.new('NodeGroupInput'); gin.location = (-1800, 0)
    gout = nodes.new('NodeGroupOutput'); gout.location = (800, 0)

    # Frame and Speed Calculation
    math_total = nodes.new('ShaderNodeMath'); math_total.operation = 'MULTIPLY'; math_total.location = (-1500, 500)
    links.new(gin.outputs['Cols'], math_total.inputs[0]); links.new(gin.outputs['Rows'], math_total.inputs[1])

    math_rate_mul = nodes.new('ShaderNodeMath'); math_rate_mul.operation = 'MULTIPLY'; math_rate_mul.location = (-1500, 200)
    links.new(gin.outputs['Frame'], math_rate_mul.inputs[0])
    links.new(gin.outputs['Rate'], math_rate_mul.inputs[1])

    math_fps_div = nodes.new('ShaderNodeMath'); math_fps_div.operation = 'DIVIDE'; math_fps_div.location = (-1300, 200)
    links.new(math_rate_mul.outputs[0], math_fps_div.inputs[0])
    math_fps_div.inputs[1].default_value = 24.0

    math_loop = nodes.new('ShaderNodeMath'); math_loop.operation = 'MODULO'; math_loop.location = (-1100, 200)
    links.new(math_fps_div.outputs[0], math_loop.inputs[0]); links.new(math_total.outputs[0], math_loop.inputs[1])
      
    math_floor = nodes.new('ShaderNodeMath'); math_floor.operation = 'FLOOR'; math_floor.location = (-900, 200)
    links.new(math_loop.outputs[0], math_floor.inputs[0])

    # X/Y Index
    x_idx_raw = nodes.new('ShaderNodeMath'); x_idx_raw.operation = 'MODULO'; x_idx_raw.location = (-700, 350)
    links.new(math_floor.outputs[0], x_idx_raw.inputs[0]); links.new(gin.outputs['Cols'], x_idx_raw.inputs[1])

    x_idx_inv = nodes.new('ShaderNodeMath'); x_idx_inv.operation = 'SUBTRACT'; x_idx_inv.location = (-500, 350)
    math_c_minus_1 = nodes.new('ShaderNodeMath'); math_c_minus_1.operation = 'SUBTRACT'; math_c_minus_1.inputs[1].default_value = 1.0
    links.new(gin.outputs['Cols'], math_c_minus_1.inputs[0])
    links.new(math_c_minus_1.outputs[0], x_idx_inv.inputs[0]); links.new(x_idx_raw.outputs[0], x_idx_inv.inputs[1])

    y_div = nodes.new('ShaderNodeMath'); y_div.operation = 'DIVIDE'; y_div.location = (-700, 100)
    links.new(math_floor.outputs[0], y_div.inputs[0]); links.new(gin.outputs['Cols'], y_div.inputs[1])
    y_idx = nodes.new('ShaderNodeMath'); y_idx.operation = 'FLOOR'; y_idx.location = (-500, 100)
    links.new(y_div.outputs[0], y_idx.inputs[0])

    # UV Mapping
    uv_in = nodes.new('ShaderNodeUVMap'); uv_in.location = (-1200, 700)
    sep_uv = nodes.new('ShaderNodeSeparateXYZ'); sep_uv.location = (-1000, 700)
    links.new(uv_in.outputs['UV'], sep_uv.inputs[0])

    # U Calc
    sub_u = nodes.new('ShaderNodeMath'); sub_u.operation = 'SUBTRACT'
    links.new(sep_uv.outputs['X'], sub_u.inputs[0]); links.new(gin.outputs['U_Min'], sub_u.inputs[1])
    div_u = nodes.new('ShaderNodeMath'); div_u.operation = 'DIVIDE'
    links.new(sub_u.outputs[0], div_u.inputs[0]); links.new(gin.outputs['Cols'], div_u.inputs[1])
    fw_calc = nodes.new('ShaderNodeMath'); fw_calc.operation = 'SUBTRACT'
    links.new(gin.outputs['U_Max'], fw_calc.inputs[0]); links.new(gin.outputs['U_Min'], fw_calc.inputs[1])
    fw_node = nodes.new('ShaderNodeMath'); fw_node.operation = 'DIVIDE'
    links.new(fw_calc.outputs[0], fw_node.inputs[0]); links.new(gin.outputs['Cols'], fw_node.inputs[1])
    off_u = nodes.new('ShaderNodeMath'); off_u.operation = 'MULTIPLY'
    links.new(x_idx_raw.outputs[0], off_u.inputs[0]); links.new(fw_node.outputs[0], off_u.inputs[1])
    final_u = nodes.new('ShaderNodeMath'); final_u.operation = 'ADD'
    links.new(div_u.outputs[0], final_u.inputs[0]); links.new(off_u.outputs[0], final_u.inputs[1])
    base_u = nodes.new('ShaderNodeMath'); base_u.operation = 'ADD'
    links.new(final_u.outputs[0], base_u.inputs[0]); links.new(gin.outputs['U_Min'], base_u.inputs[1])

    # V Calc
    sub_v = nodes.new('ShaderNodeMath'); sub_v.operation = 'SUBTRACT'
    links.new(sep_uv.outputs['Y'], sub_v.inputs[0]); links.new(gin.outputs['V_Min'], sub_v.inputs[1])
    div_v = nodes.new('ShaderNodeMath'); div_v.operation = 'DIVIDE'
    links.new(sub_v.outputs[0], div_v.inputs[0]); links.new(gin.outputs['Rows'], div_v.inputs[1])
    fh_calc = nodes.new('ShaderNodeMath'); fh_calc.operation = 'SUBTRACT'
    links.new(gin.outputs['V_Max'], fh_calc.inputs[0]); links.new(gin.outputs['V_Min'], fh_calc.inputs[1])
    fh_node = nodes.new('ShaderNodeMath'); fh_node.operation = 'DIVIDE'
    links.new(fh_calc.outputs[0], fh_node.inputs[0]); links.new(gin.outputs['Rows'], fh_node.inputs[1])
    math_r_minus_1 = nodes.new('ShaderNodeMath'); math_r_minus_1.operation = 'SUBTRACT'; math_r_minus_1.inputs[1].default_value = 1.0
    links.new(gin.outputs['Rows'], math_r_minus_1.inputs[0])
    inv_v_idx = nodes.new('ShaderNodeMath'); inv_v_idx.operation = 'SUBTRACT'
    links.new(math_r_minus_1.outputs[0], inv_v_idx.inputs[0]); links.new(y_idx.outputs[0], inv_v_idx.inputs[1])
    off_v = nodes.new('ShaderNodeMath'); off_v.operation = 'MULTIPLY'
    links.new(inv_v_idx.outputs[0], off_v.inputs[0]); links.new(fh_node.outputs[0], off_v.inputs[1])
    final_v = nodes.new('ShaderNodeMath'); final_v.operation = 'ADD'
    links.new(div_v.outputs[0], final_v.inputs[0]); links.new(off_v.outputs[0], final_v.inputs[1])
    base_v = nodes.new('ShaderNodeMath'); base_v.operation = 'ADD'
    links.new(final_v.outputs[0], base_v.inputs[0]); links.new(gin.outputs['V_Min'], base_v.inputs[1])

    # Final Output
    comb_uv = nodes.new('ShaderNodeCombineXYZ'); comb_uv.location = (500, 300)
    links.new(base_u.outputs[0], comb_uv.inputs[0]); links.new(base_v.outputs[0], comb_uv.inputs[1])
    
    links.new(comb_uv.outputs[0], gout.inputs['UV_Vector'])
    return group


# ==========================================================================
# 2. MAIN MATERIAL GENERATOR (Multi-Material / Anti-Conflict System)
# ==========================================================================
def create_material_slicing(block_info):
    mat_name = f"Mat_{block_info['name']}"
    
    # FIX: Always use new() instead of get() to prevent material overriding.
    mat = bpy.data.materials.new(name=mat_name)
    
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()

    # Helper: Find input/output socket by name
    def get_socket(node, name, is_output=False):
        sockets = node.outputs if is_output else node.inputs
        return next((s for s in sockets if name.lower() in s.name.lower()), sockets[0] if sockets else None)

    # 1. WoT Animation Node
    wot_node_tree = ensure_wot_animation_node()
    anim_node = nodes.new('ShaderNodeGroup')
    if wot_node_tree: anim_node.node_tree = wot_node_tree
    anim_node.name = "VFX_WoT_Animation"
    anim_node.location = (-800, 400)
    anim_node.width = 250 

    for k in ['Cols', 'Rows', 'Rate', 'U_Min', 'U_Max', 'V_Min', 'V_Max']:
        if k in anim_node.inputs:
            anim_node.inputs[k].default_value = block_info[k.lower()]

    v_frame = nodes.new('ShaderNodeValue'); v_frame.label = "Current_Frame"; v_frame.location = (-1000, 400)
    v_frame.outputs[0].driver_add("default_value").driver.expression = "frame"
    if 'Frame' in anim_node.inputs: links.new(v_frame.outputs[0], anim_node.inputs['Frame'])

    # 2. Texture (DDS)
    tex = nodes.new('ShaderNodeTexImage'); tex.location = (-400, 400)
    
    # NEW: Check for existing texture from mesh
    if block_info.get('existing_image'):
        tex.image = block_info['existing_image']
        log(f"Texture linked directly from 3D Mesh: {tex.image.name}")
    elif block_info.get('tex_path'):
        tex_path = block_info['tex_path']
        img_name = os.path.basename(tex_path)
        
        # Use existing image if already loaded to prevent duplicates
        if img_name in bpy.data.images:
            tex.image = bpy.data.images[img_name]
            log(f"Texture linked from scene: {img_name}")
        else:
            try: 
                tex.image = bpy.data.images.load(tex_path)
                log(f"Texture loaded from file: {tex_path}")
            except Exception as e:
                log(f"ERROR: File found but could not load into Texture Node! Path: {tex_path} | Reason: {e}")
                
    if 'UV_Vector' in anim_node.outputs and 'Vector' in tex.inputs:
        links.new(anim_node.outputs['UV_Vector'], tex.inputs['Vector'])

    # 3. Curve Driver
    curve_driver = nodes.new('ShaderNodeGroup')
    curve_driver_tree = bpy.data.node_groups.get("Curve Driver")
    if curve_driver_tree: curve_driver.node_tree = curve_driver_tree
    curve_driver.name = "Curve Driver"
    curve_driver.location = (-400, -100)

    # 4. RGB Separation and Curves
    sep_color = nodes.new('ShaderNodeSeparateColor')
    sep_color.location = (-150, 400)
    
    comb_color = nodes.new('ShaderNodeCombineColor')
    comb_color.location = (250, 400)

    # R Curve
    r_curve = nodes.new('ShaderNodeFloatCurve')
    r_curve.name = "R Curve"
    r_curve.label = "R Curve"
    r_curve.location = (50, 600)
    apply_points_to_curve_node(r_curve, block_info.get('curve_r'))

    # G Curve
    g_curve = nodes.new('ShaderNodeFloatCurve')
    g_curve.name = "G Curve"
    g_curve.label = "G Curve"
    g_curve.location = (50, 400)
    apply_points_to_curve_node(g_curve, block_info.get('curve_g'))

    # B Curve
    b_curve = nodes.new('ShaderNodeFloatCurve')
    b_curve.name = "B Curve"
    b_curve.label = "B Curve"
    b_curve.location = (50, 200)
    apply_points_to_curve_node(b_curve, block_info.get('curve_b'))

    # Alpha Curve
    alpha_curve = nodes.new('ShaderNodeFloatCurve')
    alpha_curve.name = "Alpha Curve"
    alpha_curve.label = "Alpha Curve"
    alpha_curve.location = (50, -50)
    apply_points_to_curve_node(alpha_curve, block_info.get('curve_a'))

    # 5. Alpha Calculator
    alpha_calc = nodes.new('ShaderNodeGroup')
    alpha_calc_tree = bpy.data.node_groups.get("Alpha calculator")
    if alpha_calc_tree: alpha_calc.node_tree = alpha_calc_tree
    alpha_calc.name = "Alpha calculator"
    alpha_calc.location = (250, -50)
    if 'Base Alpha' in alpha_calc.inputs:
        raw_alpha = block_info.get('alpha_ref', 1.0)
        alpha_calc.inputs['Base Alpha'].default_value = 1.0 if raw_alpha == 0.0 else raw_alpha

    # 6. BSDF and Output
    bsdf = nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (550, 400)
    out = nodes.new('ShaderNodeOutputMaterial'); out.location = (850, 400)
    
    # === SHADER LINKS (SAFE LINKING SYSTEM) ===
    
    # Shift nodes to the right for layout
    comb_color.location = (450, 400)
    bsdf.location = (700, 400)
    out.location = (1000, 400)
    
    # Link Texture Color to Separator
    if 'Color' in tex.outputs and 'Color' in sep_color.inputs:
        links.new(tex.outputs['Color'], sep_color.inputs['Color'])

    # Curve Driver (TIME) -> Connects to all curves (Value / X Axis)
    curve_val_out = get_socket(curve_driver, "Value", is_output=True)
    if curve_val_out:
        links.new(curve_val_out, r_curve.inputs['Value'])
        links.new(curve_val_out, g_curve.inputs['Value'])
        links.new(curve_val_out, b_curve.inputs['Value'])
        links.new(curve_val_out, alpha_curve.inputs['Value'])

    # Math (Multiply) nodes to multiply curve value with Texture color
    math_r = nodes.new('ShaderNodeMath'); math_r.operation = 'MULTIPLY'; math_r.location = (250, 600)
    math_g = nodes.new('ShaderNodeMath'); math_g.operation = 'MULTIPLY'; math_g.location = (250, 400)
    math_b = nodes.new('ShaderNodeMath'); math_b.operation = 'MULTIPLY'; math_b.location = (250, 200)

    # MULTIPLY Texture Color (RGB) with Curve Outputs
    links.new(sep_color.outputs['Red'], math_r.inputs[0])
    links.new(r_curve.outputs['Value'], math_r.inputs[1])

    links.new(sep_color.outputs['Green'], math_g.inputs[0])
    links.new(g_curve.outputs['Value'], math_g.inputs[1])

    links.new(sep_color.outputs['Blue'], math_b.inputs[0])
    links.new(b_curve.outputs['Value'], math_b.inputs[1])

    # Link Multiply Results -> Combine Color
    links.new(math_r.outputs[0], comb_color.inputs['Red'])
    links.new(math_g.outputs[0], comb_color.inputs['Green'])
    links.new(math_b.outputs[0], comb_color.inputs['Blue'])

    # Combined Color -> BSDF Base Color and Emission Color
    if 'Color' in comb_color.outputs:
        if 'Base Color' in bsdf.inputs:
            links.new(comb_color.outputs['Color'], bsdf.inputs['Base Color'])
        if 'Emission Color' in bsdf.inputs:
            links.new(comb_color.outputs['Color'], bsdf.inputs['Emission Color'])

    if 'Alpha' in tex.outputs and get_socket(alpha_calc, "Alpha in", is_output=False):
        links.new(tex.outputs['Alpha'], get_socket(alpha_calc, "Alpha in", is_output=False))
    
    alpha_val_out = get_socket(alpha_curve, "Value", is_output=True)
    alpha_curve_sock = get_socket(alpha_calc, "Alpha Curve", is_output=False)
    if alpha_val_out and alpha_curve_sock:
        links.new(alpha_val_out, alpha_curve_sock)

    # Strength: Direct mapping from XML
    bsdf.inputs['Emission Strength'].default_value = block_info.get('base_emission', 1.0)
    
    alpha_out_sock = get_socket(alpha_calc, "Alpha", is_output=True)
    if alpha_out_sock and 'Alpha' in bsdf.inputs:
        links.new(alpha_out_sock, bsdf.inputs['Alpha'])
        
    if 'BSDF' in bsdf.outputs and 'Surface' in out.inputs:
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
       
    mat.blend_method = 'BLEND'
    mat.show_transparent_back = True  # Enables Transparent Overlap
    return mat

# --- HELPERS ---
def get_xml_val(layer_node, param_name, default_val=0.0, is_int=False, is_str=False):
    known = layer_node.find("Known_Parameters")
    if known is None: return default_val
    
    elem = known.find(param_name)
    if elem is None:
        for sub_group in known:
            if len(list(sub_group)) > 0:
                elem = sub_group.find(param_name)
                if elem is not None: break
                
    if elem is None or elem.text is None:
        return "" if is_str else (0 if is_int else default_val)
        
    if is_str: return str(elem.text)
    if is_int: return int(float(elem.text))
    return float(elem.text)

# --- CURVE HELPERS ---
def get_curve_points(layer_node, curve_name):
    """Reads curve points from XML."""
    curves_node = layer_node.find("Curves")
    if curves_node is None: return None
    
    curve_elem = curves_node.find(curve_name)
    if curve_elem is None: return None
    
    points = []
    for pt in curve_elem.findall("Point"):
        t = float(pt.get("time", 0.0))
        v = float(pt.get("value", 0.0))
        points.append((t, v))
    return points

def apply_points_to_curve_node(curve_node, points):
    """Applies read points to Blender Float Curve node."""
    if not points: 
        return # If no curve in XML, keep defaults

    # 1. CALCULATE Y-AXIS LIMITS
    # Find min/max values (ensure standard 0.0 - 1.0 boundary)
    max_y = max(max([v for t, v in points]), 1.0)
    min_y = min(min([v for t, v in points]), 0.0)

    # 2. UPDATE CURVE CLIPPING
    # Prevents clipping for values > 1.0 (e.g., 10.0)
    curve_node.mapping.clip_max_y = max_y
    curve_node.mapping.clip_min_y = min_y

    curve_map = curve_node.mapping.curves[0]
    
    # 3. Adjust required point count
    while len(curve_map.points) < len(points):
        curve_map.points.new(0.0, 0.0)
    while len(curve_map.points) > len(points):
        curve_map.points.remove(curve_map.points[-1])
        
    # 4. Assign point values
    for i, (t, v) in enumerate(points):
        curve_map.points[i].location = (t, v)
        curve_map.points[i].handle_type = 'AUTO' # Enables smooth interpolation
        
    curve_node.mapping.update()

# Allow custom UV bounds during plane creation
def create_plane(name, size_x=1.0, size_y=1.0, uv_bounds=(0.0, 0.0, 1.0, 1.0)):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    
    hx, hy = size_x / 2.0, size_y / 2.0
    mesh.from_pydata([(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0)], [], [(0,1,2,3)])
    
    uv_layer = mesh.uv_layers.new(name="UVMap")
    u_min, v_min, u_max, v_max = uv_bounds
    
    uv_layer.data[0].uv = (u_min, v_min)
    uv_layer.data[1].uv = (u_max, v_min)
    uv_layer.data[2].uv = (u_max, v_max)
    uv_layer.data[3].uv = (u_min, v_max)
    return obj

# --- SMART LINKING SYSTEM (Index, Typo & Multi-Seed Protected) ---
def safe_link(tree, n1, out_name, n2, in_name, in_index=0):
    def match_name(name, target):
        n = name.lower().replace("ı", "i").replace("lenght", "length").replace("velocitiy", "velocity").replace("gravitiy", "gravity")
        t = target.lower().replace("ı", "i").replace("lenght", "length").replace("velocitiy", "velocity").replace("gravitiy", "gravity")
        return n == t

    out_sock = next((s for s in n1.outputs if match_name(s.name, out_name)), None)
    matching_in_sockets = [s for s in n2.inputs if match_name(s.name, in_name)]
    
    if out_sock and matching_in_sockets:
        # If index is -1, link to all matching sockets (for Seed)
        if in_index == -1:
            for sock in matching_in_sockets:
                tree.links.new(out_sock, sock)
        elif in_index < len(matching_in_sockets):
            in_sock = matching_in_sockets[in_index]
            tree.links.new(out_sock, in_sock)
        else:
            log(f"WARNING: Socket '{in_name}' index {in_index} not found!")
    else:
        log(f"WARNING: Link failed! '{out_name}' -> '{in_name}' (Socket not found).")

def ensure_compositor_glare():
    scene = bpy.context.scene
    scene.display_settings.display_device = 'sRGB'
    scene.view_settings.view_transform = 'Standard' # Switch from Filmic to Standard
    scene.view_settings.look = 'None'
    # Enable Compositor nodes
    if not scene.use_nodes:
        scene.use_nodes = True
    
    tree = scene.node_tree
    nodes = tree.nodes
    links = tree.links

    # Skip if Glare node already exists
    if any(n.type == 'GLARE' for n in nodes):
        return

    # Find or create base nodes
    rl_node = nodes.get("Render Layers") or nodes.new('CompositorNodeRLayers')
    comp_node = nodes.get("Composite") or nodes.new('CompositorNodeComposite')
    
    # 1. Create and setup Glare Node
    glare = nodes.new('CompositorNodeGlare')
    glare.glare_type = 'FOG_GLOW' # FOG_GLOW gives the most natural bloom effect
    glare.mix = 0.0
    glare.threshold = 0.1
    glare.size = 9
    glare.location = (300, 0)

    # 2. Viewer Node
    viewer = nodes.new('CompositorNodeViewer')
    viewer.location = (600, -200)

    # 3. Establish Links
    links.new(rl_node.outputs[0], glare.inputs[0])
    # Glare -> Composite (For Final Render)
    links.new(glare.outputs[0], comp_node.inputs[0])
    # Glare -> Viewer (For Node Editor preview)
    links.new(glare.outputs[0], viewer.inputs[0])

    # 4. Set Viewport Shading to "Camera" (Real-time Compositor)
    # Applicable for Blender 3.5+
    if hasattr(scene.display, "compositor"):
        scene.display.compositor = 'CAMERA'

    log("Compositor: Glare structure and Real-time settings successfully established.")

# --- MAIN PIPELINE ---
def load_vfx_pipeline(filepath, parent_gn_tree=None):
    if parent_gn_tree is None:
        # Execute only if main effect
        ensure_compositor_glare()
        init_log(filepath)
    
    log(f"Extracting XML: {filepath}")
    xml_path = unpack_vfxbin_to_xml(filepath)
    if not xml_path or not os.path.exists(xml_path):
        log("ERROR: Failed to create XML! Aborting.")
        return

    tree = ET.parse(xml_path)
    root = tree.getroot()
    dir_path = os.path.dirname(filepath)

    # 1. PREPARE COMMON OBJECTS (CAMERA & WIND)
    if parent_gn_tree is None:
        cam_target = bpy.context.scene.camera
        if not cam_target:
            cam_data = bpy.data.cameras.new("Auto_VFX_Cam")
            cam_target = bpy.data.objects.new("Auto_VFX_Cam", cam_data)
            bpy.context.collection.objects.link(cam_target)
            cam_target.location = (0, -20, 5)
            cam_target.rotation_euler = (math.radians(75), 0, 0)
            bpy.context.scene.camera = cam_target

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
    else:
        cam_target = bpy.context.scene.camera
        wind_col = bpy.data.collections.get("Wind")

    # 2. LOOP THROUGH XML EFFECTS
    for layer in root.findall("Layer"):
        layer_name = layer.get("name")
        log(f"Processing: {layer_name}")

        info = {
            'name': layer_name,
            'base_emission': get_xml_val(layer, "Base_Emission", 1.0),
            'rate': get_xml_val(layer, "Animation_Speed", 1.0),
            'v_max': get_xml_val(layer, "V_Max", 1.0),
            'u_min': get_xml_val(layer, "U_Min", 0.0),
            'v_min': get_xml_val(layer, "V_Min", 0.0),
            'u_max': get_xml_val(layer, "U_Max", 1.0),
            'cols': get_xml_val(layer, "Cols", 1, is_int=True) or 1,
            'rows': get_xml_val(layer, "Rows", 1, is_int=True) or 1,
            'alpha_ref': get_xml_val(layer, "Alpha_Offset", 1.0),
            # NEW CURVE DATA
            'curve_scale': get_curve_points(layer, "Curve_Scale"),
            'curve_r': get_curve_points(layer, "Curve_Color_R"),
            'curve_g': get_curve_points(layer, "Curve_Color_G"),
            'curve_b': get_curve_points(layer, "Curve_Color_B"),
            'curve_a': get_curve_points(layer, "Curve_Alpha_A"),
            'life_time_avg': (get_xml_val(layer, "Life_Time_Min", 1.0) + get_xml_val(layer, "Life_Time_Max", 1.0)) / 2.0,
            'tex_path': None
        }

        raw_tex_path = get_xml_val(layer, "Texture_Path", "", is_str=True)
        if raw_tex_path:
            info['tex_path'] = find_texture_smart(dir_path, raw_tex_path)

        # A. EMITTER OBJECT
        size_x = max(get_xml_val(layer, "Size_X", 1.0), 0.01)
        size_y = max(get_xml_val(layer, "Size_Y", 1.0), 0.01)
        emitter_obj = create_plane(f"{layer_name}_Emitter", size_x, size_y)

        # B. INSTANCED OBJECT (MESH or ANIMATED PLANE)
        mesh_path_raw = get_xml_val(layer, "Mesh_Path", "", is_str=True).strip()
        use_mesh = False
        anim_obj = None

        # 1. IF MESH PATH EXISTS, IMPORT 3D MODEL
        if mesh_path_raw and mesh_path_raw.lower() != "none":
            # BigWorld XML points to .visual, but disk has .model or _processed files.
            # Try all possible actual extensions:
            base_mesh_path = os.path.splitext(mesh_path_raw)[0]
            possible_exts = [".model", ".visual_processed", ".primitives_processed", ".visual"]
            
            actual_mesh_path = None
            for ext in possible_exts:
                test_path = base_mesh_path + ext
                actual_mesh_path = find_texture_smart(dir_path, test_path)
                if actual_mesh_path:
                    break  # Break loop once file is found
                    
            if actual_mesh_path and os.path.exists(actual_mesh_path):
                log(f"Custom 3D Mesh found and importing: {actual_mesh_path}")
                
                # Store existing objects to catch the newly imported ones
                existing_objs = set(bpy.context.scene.objects)
                col = bpy.context.view_layer.active_layer_collection.collection
                
                try:
                    # Request mesh directly instead of empty root by passing import_empty=False
                    load_bw_primitive_textured(col, Path(actual_mesh_path), True)
                    
                    # Filter newly imported objects
                    new_objs = list(set(bpy.context.scene.objects) - existing_objs)
                    
                    if new_objs:
                        # Select the most appropriate MESH type object for GeoNodes
                        mesh_objs = [o for o in new_objs if o.type == 'MESH']
                        anim_obj = mesh_objs[0] if mesh_objs else new_objs[0]
                        
                        # Rename object to match old system structure
                        anim_obj.name = f"{layer_name}_mesh_instance"
                        
                        # --- NEW: STAMP ORIGINAL FILE PATH TO OBJECT ---
                        # Write actual .visual path to Custom Properties
                        anim_obj["Original_Visual_Path"] = mesh_path_raw
                        
                        # Hide to prevent viewport clutter
                        for o in new_objs:
                            o.hide_render = True
                            o.hide_viewport = True
                            
                        use_mesh = True
                        log(f"Mesh successfully instanced: {anim_obj.name}")

                        # --- NEW: CONVERT MESH MATERIALS TO VFX SYSTEM (EMISSION) ---
                        # Iterate through standard materials on the mesh
                        for i, slot in enumerate(anim_obj.material_slots):
                            old_mat = slot.material
                            existing_img = None
                            
                            # Extract the actual Texture node from the primitive imported material
                            if old_mat and old_mat.use_nodes:
                                tex_node = next((n for n in old_mat.node_tree.nodes if n.type == 'TEX_IMAGE'), None)
                                if tex_node and tex_node.image:
                                    existing_img = tex_node.image
                                    
                            # Add extracted image to dict so material_slicing can merge it with Emission
                            info['existing_image'] = existing_img
                            
                            # Create advanced VFX material (Emission, Curves, etc.)
                            new_mat = create_material_slicing(info)
                            new_mat.name = f"{old_mat.name}_VFX" if old_mat else f"{layer_name}_MeshMat_{i}"
                            
                            # Replace old standard material with new VFX material
                            anim_obj.material_slots[i].material = new_mat
                            
                        # Fallback if mesh has no materials
                        if len(anim_obj.material_slots) == 0:
                            new_mat = create_material_slicing(info)
                            anim_obj.data.materials.append(new_mat)

                except Exception as e:
                    log(f"Mesh import error (Falling back to Plane): {e}")
            else:
                log(f"WARNING: Mesh file not found on disk ({mesh_path_raw}). Creating Standard Plane.")

        # 2. IF MESH IS MISSING/NOT FOUND (GENERATE STANDARD PLANE AND MAT)
        if not use_mesh or anim_obj is None:
            uv_bounds = (info['u_min'], info['v_min'], info['u_max'], info['v_max'])
            anim_obj = create_plane(f"{layer_name}_anim_instance", 1.0, 1.0, uv_bounds)
            mat = create_material_slicing(info)
            anim_obj.data.materials.append(mat)
            anim_obj.location = (0, 0, -50) 
            anim_obj.hide_render = True

        # C. SETTINGS OBJECT
        settings_obj = create_plane(f"{layer_name}_emitter_settings", 1.0, 1.0)
        settings_obj["Original_Texture_Path"] = raw_tex_path
        
        # --- NEW: EMBED ORIGINAL EFFECT DNA (Unknowns & Header) INTO BLENDER! ---
        unknowns = layer.find("Unknown_Parameters")
        if unknowns is not None:
            settings_obj["Unknown_Params_XML"] = ET.tostring(unknowns, encoding="unicode")
        
        # --- NEW: CHILD EFFECT STAMP AND ORIGINAL ALPHA ---
        if parent_gn_tree is not None:
            settings_obj["Is_Child_Effect"] = True
            settings_obj["Child_Source_File"] = os.path.basename(filepath)
            
        # Save Original Alpha Offset safely for export
        settings_obj["Original_Alpha_Offset"] = info.get('alpha_ref', 1.0)
        
        # GeoNodes Setup
        gn_mod = settings_obj.modifiers.new(name="VFX_WoT_Controller", type='NODES')
        new_gn_tree = bpy.data.node_groups.new(name=f"GN_{layer_name}", type='GeometryNodeTree')
        gn_mod.node_group = new_gn_tree
        
        # Prepare Output Node and Sockets
        new_gn_tree.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
        # ALL trees must output "Point Clean Geometry" for child effects to process!
        new_gn_tree.interface.new_socket(name="Point Clean Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
        
        out_node = new_gn_tree.nodes.new('NodeGroupOutput')
        out_node.location = (800, 0)
        
        wot_gn_tree = bpy.data.node_groups.get("Wot .vfxbin to blender")
        master_gn_tree = bpy.data.node_groups.get("GeoSpritesV2+WoT by wotcuk MASTER NODE")
        
        if wot_gn_tree and master_gn_tree:
            # 1. Add WOT Data Node
            wot_node = new_gn_tree.nodes.new('GeometryNodeGroup')
            wot_node.node_tree = wot_gn_tree
            wot_node.name = "Wot .vfxbin to blender"
            wot_node.location = (-400, 0)
            wot_node.width = 250
            
            # 2. Add MASTER Node
            master_node = new_gn_tree.nodes.new('GeometryNodeGroup')
            master_node.node_tree = master_gn_tree
            master_node.name = "GeoSpritesV2+WoT by wotcuk MASTER NODE"
            master_node.location = (200, 0)
            master_node.width = 300
            
            # Link Master's "Point Clean Geometry" to Output
            safe_link(new_gn_tree, master_node, "Point Clean Geometry", out_node, "Point Clean Geometry", 0)

            # FIX: DEFINE FUNCTION HERE BEFORE OPERATIONS
            def set_node_input(node, input_name, value):
                # Ignore case and common typos like 'lenght'
                t_name = input_name.lower().replace("ı", "i").replace("lenght", "length")
                for s in node.inputs:
                    if s.name.lower().replace("ı", "i").replace("lenght", "length") == t_name:
                        try:
                            # Force data to correct format (Bool/Int) based on socket type
                            if s.type == 'BOOLEAN':
                                s.default_value = bool(value)
                            elif s.type == 'INT':
                                s.default_value = int(value)
                            else:
                                s.default_value = value
                        except: pass
                        return

            # NEW ARCHITECTURE: EXECUTE IF THIS IS A CHILD EFFECT
            if parent_gn_tree is not None:
                log(f"-> {layer_name} processed as a child effect. Linking Parent node...")
                
                # FIX: Disable checkbox on MASTER NODE, not wot_node!
                set_node_input(master_node, "Use object as emitter", False)
                
                # Force disconnect Emitter object
                sock_emitter = next((s for s in wot_node.inputs if s.name == "Emitter Object"), None)
                if sock_emitter and sock_emitter.is_linked:
                    new_gn_tree.links.remove(sock_emitter.links[0])
                
                # Import Parent's GeoNodes Tree (To the left)
                parent_inst_node = new_gn_tree.nodes.new('GeometryNodeGroup')
                parent_inst_node.node_tree = parent_gn_tree
                parent_inst_node.name = f"Parent_{parent_gn_tree.name}"
                parent_inst_node.location = (master_node.location.x - 400, master_node.location.y + 300)
                
                # Link Parent's "Point Clean Geometry" to Master Node's "Geometry"
                safe_link(new_gn_tree, parent_inst_node, "Point Clean Geometry", master_node, "Geometry", 0)
                parent_inst_node.node_tree = parent_gn_tree
                parent_inst_node.name = f"Parent_{parent_gn_tree.name}"
                parent_inst_node.location = (master_node.location.x - 400, master_node.location.y + 300)
                
                # Link Parent's "Point Clean Geometry" to Master Node's "Geometry"
                safe_link(new_gn_tree, parent_inst_node, "Point Clean Geometry", master_node, "Geometry", 0)
            
            # If Main Effect (Parent), assign Emitter Object normally
            else:
                def set_node_input(node, input_name, value):
                    possible_names = [input_name, input_name.replace("ı", "i"), input_name.replace("i", "ı")]
                    sock = next((s for s in node.inputs if s.name in possible_names), None)
                    if sock: sock.default_value = value
                
                set_node_input(wot_node, "Emitter Object", emitter_obj)

            # --- SCALE CURVES AND SCALE FROM CURVE GROUP ---
            x_curve_node = new_gn_tree.nodes.new('ShaderNodeFloatCurve')
            x_curve_node.name = "X Scale Curve"
            x_curve_node.location = (-100, 200)
            apply_points_to_curve_node(x_curve_node, info.get('curve_scale'))

            y_curve_node = new_gn_tree.nodes.new('ShaderNodeFloatCurve')
            y_curve_node.name = "Y Scale Curve"
            y_curve_node.location = (-100, -50)
            apply_points_to_curve_node(y_curve_node, info.get('curve_scale'))
            
            scale_node = new_gn_tree.nodes.new('GeometryNodeGroup')
            scale_node.node_tree = bpy.data.node_groups.get("Scale From Curve")
            scale_node.name = "Scale From Curve"
            scale_node.location = (550, 0)
            
            safe_link(new_gn_tree, wot_node, "Curve Driver", x_curve_node, "Value", 0)
            safe_link(new_gn_tree, wot_node, "Curve Driver", y_curve_node, "Value", 0)
            safe_link(new_gn_tree, master_node, "Geometry", scale_node, "Geometry", 0)
            safe_link(new_gn_tree, x_curve_node, "Value", scale_node, "X Scale Curve", 0)
            safe_link(new_gn_tree, y_curve_node, "Value", scale_node, "Y Scale Curve", 0)
            safe_link(new_gn_tree, scale_node, "Geometry", out_node, "Geometry", 0)
            
            # --- ESTABLISH OTHER MAIN LINKS ---
            link_pairs = [
                ("Emitter Object", "EMITTER OBJECT", 0),
                ("Count", "Count", 0),
                ("Lifetime Max", "Lifetime Max", 0),
                ("Lifetime Min", "Lifetime Min", 0),
                ("Normal Velocity Max", "Normal Velocity Max", 0),
                ("Normal Velocity Min", "Normal Velocity Min", 0),
                ("Distribution ratio (cone)", "Distribution ratio (cone)", 0),
                ("Global Gravitiy Max", "Global Gravitiy Max", 0),
                ("Global Gravitiy Min", "Global Gravitiy Min", 0),
                ("Object to Instance", "Object to Instance", 0),
                
                ("Base X Scale Max", "Max", 0),
                ("Base X Scale Min", "Min", 0),
                
                ("Base Y Scale Max", "Max", 1),
                ("Base Y Scale Min", "Min", 1),
                
                ("Camera", "Select Camera", 0),
                ("Camera Track Mode", "Cam Tracking Mode info from other group (negative)", 0),
                
                ("Inital Angle Max", "Max", 2),
                ("Inital Angle Min", "Min", 2),
                
                ("Rotation Speed Max", "Max", 3),
                ("Rotation Speed Min", "Min", 3),
                ("x first rotation value", "x first rotation value", 0),
                ("y first rotation value", "y first rotation value", 0),
                ("z first rotation value", "z first rotation value", 0),
                ("x rotation speed max", "x rotation speed max", 0),
                ("x rotation speed min", "x rotation speed min", 0),
                ("y rotation speed max", "y rotation speed max", 0),
                ("y rotation speed min", "y rotation speed min", 0),
                ("z rotation speed max", "z rotation speed max", 0),
                ("z rotation speed min", "z rotation speed min", 0),
                # SEED LINK: Connect to ALL Seed inputs in Master Node using -1
                ("Seed", "Seed", -1), 
                ("Wind Collection", "Wind Collection", 0),
                ("Wind Max", "Wind Max", 0),
                ("Wind Min", "Wind Min", 0)
            ]
            
            # Link all via loop
            for wot_out, master_in, in_idx in link_pairs:
                safe_link(new_gn_tree, wot_node, wot_out, master_node, master_in, in_index=in_idx)
                
            # NEW: LOOP LENGTH LOGIC
            if parent_gn_tree is None:
                # If MAIN EFFECT, link normally
                safe_link(new_gn_tree, wot_node, "Loop Lenght", master_node, "Loop Lenght", 0)
            else:
                # If CHILD EFFECT, skip link and set value to 1!
                set_node_input(master_node, "Loop Lenght", 1)
                set_node_input(wot_node, "Loop Lenght", 1)

            # Link Scale Group -> Output Node
            safe_link(new_gn_tree, scale_node, "Geometry", out_node, "Geometry", 0)
            
            set_node_input(wot_node, "Life Time Max", get_xml_val(layer, "Life_Time_Max"))
            set_node_input(wot_node, "Life Time Min", get_xml_val(layer, "Life_Time_Min"))
            set_node_input(wot_node, "Emitter Object", emitter_obj)
            set_node_input(wot_node, "Count", int(get_xml_val(layer, "Particle_Count")))
            set_node_input(wot_node, "Vertical Speed Max", get_xml_val(layer, "Init_Vertical_Speed_Max"))
            set_node_input(wot_node, "Vertical Speed Min", get_xml_val(layer, "Init_Vertical_Speed_Min"))
            # --- NEW: DISTRIBUTION RATIO ---
            set_node_input(wot_node, "Distribution ratio (cone)", get_xml_val(layer, "Cone_Radius_Multiplier"))
            set_node_input(wot_node, "Acc Max", get_xml_val(layer, "Acceleration_Max"))
            set_node_input(wot_node, "Acc Min", get_xml_val(layer, "Acceleration_Min"))
            
            set_node_input(wot_node, "Object to Instance", anim_obj)
            
            # --- SCALE ASSIGNMENTS ---
            # Read Width and Length values once
            width_max = get_xml_val(layer, "Width_Max")
            width_min = get_xml_val(layer, "Width_Min")
            length_max = get_xml_val(layer, "Length_Max")
            length_min = get_xml_val(layer, "Length_Min")

            # X axis (Width) remains the same in both cases
            set_node_input(wot_node, "Base X Scale Max", width_max)
            set_node_input(wot_node, "Base X Scale Min", width_min)
            
            if use_mesh:
                # If Mesh: Copy X axis values to Y axis (Uniform Scale)
                set_node_input(wot_node, "Base Y Scale Max", width_max)
                set_node_input(wot_node, "Base Y Scale Min", width_min)
            else:
                # If Plane: Use its original Y axis (Length) values
                set_node_input(wot_node, "Base Y Scale Max", length_max)
                set_node_input(wot_node, "Base Y Scale Min", length_min)
            
            set_node_input(wot_node, "FX file location", get_xml_val(layer, "Shader_Path", "default.fx", is_str=True))
            set_node_input(wot_node, "Camera", cam_target)
            
            angle_max = math.degrees(get_xml_val(layer, "Initial_Angle_Max"))
            set_node_input(wot_node, "Inital Angle Max", angle_max)
            set_node_input(wot_node, "Inital Angle Min", -angle_max)
            
            rot_max = math.degrees(get_xml_val(layer, "Rotation_Speed_Max"))
            rot_min = math.degrees(get_xml_val(layer, "Rotation_Speed_Min"))
            set_node_input(wot_node, "Rotation Speed Max", rot_max)
            set_node_input(wot_node, "Rotation Speed Min", rot_min)
            
            set_node_input(wot_node, "Seed", random.randint(0, 10000))
            # --- NEW: INITIAL ROTATION ANGLES (RADIANS) ---
            set_node_input(wot_node, "x first rotation value", get_xml_val(layer, "Init_Rot_Range_X_Rad"))
            set_node_input(wot_node, "y first rotation value", get_xml_val(layer, "Init_Rot_Range_Y_Rad"))
            set_node_input(wot_node, "z first rotation value", get_xml_val(layer, "Init_Rot_Range_Z_Rad"))
            
            # --- NEW: AXIAL ROTATION SPEEDS ---
            set_node_input(wot_node, "x rotation speed max", get_xml_val(layer, "Rot_Speed_X_Max"))
            set_node_input(wot_node, "x rotation speed min", get_xml_val(layer, "Rot_Speed_X_Min"))
            
            set_node_input(wot_node, "y rotation speed max", get_xml_val(layer, "Rot_Speed_Y_Max"))
            set_node_input(wot_node, "y rotation speed min", get_xml_val(layer, "Rot_Speed_Y_Min"))
            
            set_node_input(wot_node, "z rotation speed max", get_xml_val(layer, "Rot_Speed_Z_Max"))
            set_node_input(wot_node, "z rotation speed min", get_xml_val(layer, "Rot_Speed_Z_Min"))

            set_node_input(wot_node, "Wind Collection", wind_col)
            set_node_input(wot_node, "Wind Max", get_xml_val(layer, "Wind_Multiplier_Max"))
            set_node_input(wot_node, "Wind Min", get_xml_val(layer, "Wind_Multiplier_Min"))

            # NEW ARCHITECTURE: DETECT AND TRIGGER CHILD VFX
            # If the Texture path read is actually a VFX file:
            if raw_tex_path and raw_tex_path.lower().endswith(('.vfx', '.vfxbin')):
                child_vfx_path = find_texture_smart(dir_path, raw_tex_path)
                if child_vfx_path and os.path.exists(child_vfx_path):
                    log(f"\n[WARNING] NESTED EFFECT FOUND! Calling child effect: {child_vfx_path}")
                    # Stamp object so Export code knows it has a child effect:
                    settings_obj["Child_VFX_Path"] = raw_tex_path
                    # Call ourselves again! (Recursive Import)
                    load_vfx_pipeline(child_vfx_path, parent_gn_tree=new_gn_tree)
                    
        else:
            log("WARNING: Required node groups not found! Setup aborted.")

    # If this is a main process (Not Parent), print finish message
    if parent_gn_tree is None:
        log("=== FINISHED (XML & GeoNodes Transfer Completed) ===")