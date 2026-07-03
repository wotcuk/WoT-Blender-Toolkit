# -*- coding: utf-8 -*-
import bpy
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom

def log(msg):
    print(f"[VFX EXPORT] {msg}")
def prettify_wot_xml(elem):
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="\t")
    
    lines = pretty_xml.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip() == "": continue
        if line.startswith("<?xml"): continue 
        if "><" not in line and "</" in line:
            parts = line.split('>', 1)
            if len(parts) == 2 and '<' in parts[1]:
                text_parts = parts[1].split('<', 1)
                inner_text = text_parts[0].strip()
                if inner_text:
                    line = f"{parts[0]}> {inner_text} <{text_parts[1]}"
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines)
# ==============================================================================
# --- CURVE (TIMELINE) HELPERS ---
# ==============================================================================
def get_curve_points(curve_node):
    """Blender Float Curve nodundan noktaları (time, value) olarak çeker"""
    if not curve_node or not hasattr(curve_node, 'mapping'): return []
    return [(p.location.x, p.location.y) for p in curve_node.mapping.curves[0].points]

def interpolate_curve(points, time):
    """Belirli bir zaman için curve üzerindeki değeri hesaplar (Lineer Interpolation)"""
    if not points: return 1.0
    if time <= points[0][0]: return points[0][1]
    if time >= points[-1][0]: return points[-1][1]
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i+1]
        if p1[0] <= time <= p2[0]:
            t = (time - p1[0]) / (p2[0] - p1[0])
            return p1[1] + t * (p2[1] - p1[1])
    return 1.0

def export_timeline(parent_xml, tag, points):
    """Standart timeline bloğunu yazar"""
    if not points: return 
    tl_xml = ET.SubElement(parent_xml, tag)
    for t, v in points:
        ET.SubElement(tl_xml, "time").text = f" {t:.6f} "
        ET.SubElement(tl_xml, "value").text = f" {v:.6f} "

def export_color_timeline(parent_xml, r_points, g_points, b_points, a_points):
    """Özel tl_Color_key bloğunu yazar (Ortak Zaman Havuzu Mantığı)"""
    tl_xml = ET.SubElement(parent_xml, "tl_Color_key")
    
    all_times = sorted(list(set([p[0] for p in r_points] + [p[0] for p in g_points] + [p[0] for p in b_points] + [p[0] for p in a_points])))
    if not all_times: all_times = [0.0, 1.0] 

    for t in all_times:
        r = interpolate_curve(r_points, t) * 255.0
        g = interpolate_curve(g_points, t) * 255.0
        b = interpolate_curve(b_points, t) * 255.0
        a = interpolate_curve(a_points, t)
        
        ET.SubElement(tl_xml, "time").text = f" {t:.6f} "
        val_rgba = ET.SubElement(tl_xml, "value_RGBA")
        val_rgba.text = f" {r:.6f} {g:.6f} {b:.6f} {a:.6f} "


def export_lod_block(lod_empty, parent_xml):
    """LOD nesnesinden verileri okuyup XML bloğuna yazar"""
    lod_xml = ET.SubElement(parent_xml, "lod")
    
    s_name = ET.SubElement(lod_xml, "s_effect_name")
    s_name.text = f" {lod_empty.name} "

    mask_props = ["ps_particle_lod_default", "ps_particle_lod_last_disableable", "ps_particle_lod_last_available"]
    if any(p in lod_empty for p in mask_props):
        mask_xml = ET.SubElement(lod_xml, "i_lod_mask")
        for p in mask_props:
            if p in lod_empty:
                bit = ET.SubElement(mask_xml, p)
                bit.text = "1" if lod_empty[p] else "0"

    for prop in ["f_near_clip", "f_far_clip", "f_Skip_time"]:
        if prop in lod_empty:
            p_xml = ET.SubElement(lod_xml, prop)
            p_xml.text = f" {float(lod_empty[prop]):.6f} "

    ET.SubElement(lod_xml, "buffer")

    if "ps_element_off" in lod_empty:
        dw_mode_xml = ET.SubElement(lod_xml, "dw_mode")
        off_xml = ET.SubElement(dw_mode_xml, "ps_element_off")
        off_xml.text = " 1 " if lod_empty["ps_element_off"] else " 0 "

    emitters = []
    instances = []
    settings = []

    for child in lod_empty.children:
        if child.type == 'MESH':
            if "_EmitterSettings" in child.name:
                settings.append(child)
            elif "_Instance" in child.name:
                instances.append(child)
            elif "_Emitter" in child.name:
                emitters.append(child)

    for e_obj in emitters:
        base_name = e_obj.name.split("_Emitter")[0]
        
        i_obj = next((i for i in instances if i.name.startswith(base_name + "_Instance")), None)
        s_obj = next((s for s in settings if s.name.startswith(base_name + "_EmitterSettings")), None)

        if i_obj: instances.remove(i_obj)
        if s_obj: settings.remove(s_obj)

        if i_obj and s_obj:
            export_emitter_block(base_name, e_obj, i_obj, s_obj, lod_xml)
        else:
            log(f"ERROR: {e_obj.name} The Instance or Settings object could not be found! It is being skipped.")



def export_emitter_block(emitter_base_name, e_obj, i_obj, s_obj, parent_xml):
    """3 nesneden verileri çekip kesin WoT sırasıyla yazar"""
    emitter_xml = ET.SubElement(parent_xml, "emitter")

    all_params = {}
    
    for key, val in s_obj.items():
        if key not in ["_RNA_UI", "bw_export_filename"] and " " not in key:
            all_params[key] = val

    if i_obj:
        for key, val in i_obj.items():
            if key not in ["_RNA_UI", "bw_export_filename"] and " " not in key:
                all_params[key] = val

    gn_mod = s_obj.modifiers.get("VFX_WoT_Controller")
    wot_node = gn_mod.node_group.nodes.get("Wot .vfxbin to blender") if gn_mod else None
    if wot_node:
        for inp in wot_node.inputs:
            if not inp.is_linked and inp.name and " " not in inp.name:
                all_params[inp.name] = inp.default_value

    mat = i_obj.data.materials[0] if i_obj.data.materials else None
    mat_nodes = mat.node_tree.nodes if mat else None
    
    anim_node = mat_nodes.get("VFX_WoT_Animation") if mat_nodes else None
    if anim_node:
        for inp in anim_node.inputs:
            if inp.name != "Frame" and not inp.is_linked and inp.name and " " not in inp.name:
                all_params[inp.name] = inp.default_value

    light_node = mat_nodes.get("Lighting calculator") if mat_nodes else None
    if light_node:
        for inp in light_node.inputs:
            if not inp.is_linked and inp.name and " " not in inp.name:
                all_params[inp.name] = inp.default_value

    if e_obj:
        if "vt.ui_volume_type" in e_obj:
            all_params["vt.ui_volume_type"] = e_obj["vt.ui_volume_type"]
        all_params["emitter.fa_start_pos"] = e_obj.location
        all_params["f_X_dim_volume"] = e_obj.dimensions.x
        all_params["f_Y_dim_volume"] = e_obj.dimensions.y
        all_params["f_Z_dim_volume"] = e_obj.dimensions.z
        
    all_params["i_RT_shader_num"] = -1
    
    if mat:
        if "particle.ch_fn_texture" in mat:
            all_params["particle.ch_fn_texture"] = mat["particle.ch_fn_texture"]
        if "particle.ch_fn_Shader" in mat:
            all_params["particle.ch_fn_Shader"] = mat["particle.ch_fn_Shader"]

    dw_mode_keys = [
        "ps_emitter_mode_onetime_emission", "ps_element_dead", "ps_element_particle",
        "ps_element_emitter", "ps_element_type_reserved01", "ps_element_found_external_data",
        "ps_element_not_active", "ps_element_inconsumable", "ps_element_no_gravity",
        "ps_element_destructed", "ps_element_not_used", "ps_element_use_size_timeline",
        "ps_element_use_color_timeline", "ps_emitter_use_rate_timeline", "ps_emitter_use_gravity_timeline",
        "ps_emitter_use_tangent_speed_timeline", "ps_emitter_use_angle_speed_timeline", "ps_emitter_use_speed_timeline",
        "ps_emitter_use_color_op_timeline", "ps_element_use_timeline_9", "ps_element_use_timeline_10",
        "ps_element_not_render", "ps_element_use_tangent_speed", "ps_element_off",
        "ps_emitter_off", "ps_element_r_type_dx", "ps_element_r_type_shader",
        "ps_element_world_offset", "ps_element_y_emission", "ps_element_x_emission",
        "ps_element_epicentr_emission"
    ]

    dw_ext_mode_keys = [
        "ps_emitter_ext_ignore_camera_factor",
        "ps_emitter_ext_mode_reserved", "ps_emitter_ext_mode_eee_slave", 
        "ps_emitter_ext_mode_model_emission", "ps_emitter_ext_mode_model_reserved", 
        "ps_emitter_ext_mode_model_hmap_lim", "ps_emitter_ext_mode_havok_disable",
        "ps_emitter_ext_mode_length_depends_on_size", "ps_emitter_ext_mode_accept_tint"
    ]

    particle_dw_mode_keys = [
        "ps_particle_use_frames", "ps_particle_random_frame", "ps_particle_local",
        "ps_particle_horizont", "ps_particle_soft", "ps_particle_water_level",
        "ps_particle_stop_on_last_frame", "ps_particle_do_not_blend", "ps_particle_use_direction_for_angle",
        "ps_element_directional", "ps_element_speed_oriented"
    ]
    
    transition_order = [
        "coordinate_system", "fa_epicenter_pos", "fa_epicenter_box", "Ex_Filename",
        "f_solidThreshold", "QUALITY_MIN", "QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH",
        "QUALITY_ULTRA", "m_supportedQualityMask", "m_supportedPassMask", "m_supportedSniperPassMask",
        "f_fadeInOffsetFrom", "f_fadeInOffsetTo", "f_dir_length_max", "f_slopeFadeCoeff",
        "particle_ex.YPR_start", "particle_ex.YPR_start_spread", "particle_ex.f_soft_factor",
        "particle_ex.f_ground_height_offset", "particle_ex.deffered_color_mult"
    ]

    all_dw_keys = set(dw_mode_keys + dw_ext_mode_keys + particle_dw_mode_keys)
    all_dw_keys.add("disabled_in_havok")
    all_transition_keys = set(transition_order)

    def get_bool_str(key):
        val = all_params.get(key, 0)
        if val in [True, 1, 1.0, "1", "true", "True"]: return " 1 "
        return " 0 "

    def format_value(val, tag=""):
        if tag == "disabled_in_havok":
            return "true" if str(val).strip().lower() in ["true", "1", "1.0"] else "false"
        if tag.startswith("QUALITY_"):
            return "true" if str(val).strip().lower() in ["true", "1", "1.0"] else "false"
        if (tag.startswith("m_") and "Mask" in tag) or tag in ["vt.ui_volume_type", "m_sortType", "i_RT_shader_num"]:
            try: return str(int(float(val)))
            except: return "0"
        if tag in ["particle.ui_particle_Type", "particle.i_frame_div_U", "particle.i_frame_div_V"]:
            try: return str(int(float(val)))
            except: return "1"
        if hasattr(val, '__len__') and not isinstance(val, str):
            try: return " ".join([f"{float(v):.6f}" for v in list(val)])
            except: pass
        try: return f"{float(val):.6f}"
        except: return str(val).strip()
    
    # HEADER
    ET.SubElement(emitter_xml, "s_emitter_name").text = f" {emitter_base_name} "
    ET.SubElement(emitter_xml, "type").text = f" {all_params.get('type', 'Sprites')} "
    ET.SubElement(emitter_xml, "disabled_in_havok").text = f" {format_value(all_params.get('disabled_in_havok', False), 'disabled_in_havok')} "
    
    reserved_buffer_value = str(all_params.get('reserved_buffer', "")).strip()
    if reserved_buffer_value:
        ET.SubElement(emitter_xml, "reserved_buffer").text = f" {reserved_buffer_value} "
    else:
        ET.SubElement(emitter_xml, "reserved_buffer") 
    
    reserved_value = str(all_params.get('reserved', "")).strip()
    if reserved_value:
        ET.SubElement(emitter_xml, "reserved").text = f" {reserved_value} "
    else:
        ET.SubElement(emitter_xml, "reserved") 

    dw_xml = ET.SubElement(emitter_xml, "dw_mode")
    for k in dw_mode_keys: ET.SubElement(dw_xml, k).text = get_bool_str(k)

    dw_ext_xml = ET.SubElement(emitter_xml, "dw_ext_mode")
    for k in dw_ext_mode_keys: ET.SubElement(dw_ext_xml, k).text = get_bool_str(k)

    standard_order = [
        "i_RT_shader_num", "emitter.f_life_min", "emitter.f_life_max",
        "emitter.f_delay_min", "emitter.f_delay_max", "emitter.fa_start_pos",
        "f_rate", "vt.ui_volume_type", "f_X_dim_volume", "f_Y_dim_volume", "f_Z_dim_volume",
        "f_strt_angle_min", "f_strt_angle_max", "f_strt_angle_speed_min", "f_strt_angle_speed_max",
        "f_tangent_speed_min", "f_tangent_speed_max", "f_fire_smoke", "f_wind_weight",
        "f_wind_weight_max", "f_part_tangenta", "f_Espeed_time", "f_Espeed_mult",
        "f_minDistanceBeforeEmission", "m_sortType"
    ]

    for tag in standard_order:
        if tag in all_params:
            ET.SubElement(emitter_xml, tag).text = f" {format_value(all_params[tag], tag)} "
        else:
            if tag == "vt.ui_volume_type": ET.SubElement(emitter_xml, tag).text = " 1 "
            elif tag in ["m_sortType", "i_RT_shader_num"]: ET.SubElement(emitter_xml, tag).text = " 0 "
            elif tag == "emitter.fa_start_pos": ET.SubElement(emitter_xml, tag).text = " 0.000000 0.000000 0.000000 "
            else: ET.SubElement(emitter_xml, tag).text = " 0.000000 "
            log(f"DEBUG (Fallback): '{emitter_base_name}' icinde '{tag}' bulunamadi. Varsayilan kullanildi.")

    blacklisted_export_keys = ["Seed", "type", "Frame", "Count", "Emitter Object", "Object to Instance", "Camera", "Loop Lenght", "Wind Max", "Wind Min", "reserved", "reserved_buffer"]

    for tag in sorted(all_params.keys()):
        if tag in all_dw_keys or tag in all_transition_keys or tag in standard_order: continue
        if tag.startswith("RAW_"): continue 
        if tag in blacklisted_export_keys: continue 
        if not tag.startswith(("particle.", "lighting_params.", "tl_")):
            ET.SubElement(emitter_xml, tag).text = f" {format_value(all_params[tag], tag)} "

    timeline_order = [
        "tl_size_key", "tl_rate_key", "tl_gravity_key", "tl_speed_key",
        "tl_tangent_speed_key", "tl_angle_speed_key", "tl_Color_key", "tl_color_op_key"
    ]
    for tl_name in timeline_order:
        if tl_name == "tl_Color_key":
            if mat_nodes and mat_nodes.get("R Curve"): 
                r_pts = get_curve_points(mat_nodes.get("R Curve"))
                g_pts = get_curve_points(mat_nodes.get("G Curve"))
                b_pts = get_curve_points(mat_nodes.get("B Curve"))
                a_pts = get_curve_points(mat_nodes.get("Alpha Curve"))
                export_color_timeline(emitter_xml, r_pts, g_pts, b_pts, a_pts)
            else: 
                ET.SubElement(emitter_xml, tl_name) 
                
        elif tl_name == "tl_color_op_key":
            if mat_nodes and mat_nodes.get("tl_color_op_key"): 
                export_timeline(emitter_xml, tl_name, get_curve_points(mat_nodes.get("tl_color_op_key")))
            else: 
                ET.SubElement(emitter_xml, tl_name)
                
        else:
            tl_node = gn_mod.node_group.nodes.get(tl_name) if gn_mod else None
            if tl_node:
                export_timeline(emitter_xml, tl_name, get_curve_points(tl_node))
            else:
                ET.SubElement(emitter_xml, tl_name) 

    for tag in transition_order:
        if tag == "Ex_Filename":
            val = all_params.get(tag, "")
            if val and str(val).strip():
                ET.SubElement(emitter_xml, tag).text = f" {str(val).strip()} "
            else:
                ET.SubElement(emitter_xml, tag) 
            continue
            
        if tag in all_params:
            ET.SubElement(emitter_xml, tag).text = f" {format_value(all_params[tag], tag)} "
        else:
            if tag.startswith("QUALITY_"): ET.SubElement(emitter_xml, tag).text = " false "
            elif tag in ["fa_epicenter_pos", "fa_epicenter_box", "particle_ex.YPR_start", "particle_ex.YPR_start_spread"]:
                ET.SubElement(emitter_xml, tag).text = " 0.000000 0.000000 0.000000 "
            elif tag == "coordinate_system": ET.SubElement(emitter_xml, tag).text = " World "
            else: ET.SubElement(emitter_xml, tag).text = " 0.000000 "
            log(f"DEBUG (Fallback): '{emitter_base_name}' icinde '{tag}' bulunamadi. Varsayilan kullanildi.")

    p_dw_xml = ET.SubElement(emitter_xml, "particle.dw_mode")
    for k in particle_dw_mode_keys: ET.SubElement(p_dw_xml, k).text = get_bool_str(k)

    particle_order = [
        "particle.dw_mode_Ext_inv",
        "particle.base.f_life_min", "particle.base.f_life_max",
        "particle.base.f_delay_min", "particle.base.f_delay_max",
        "particle.base.fa_start_pos", "particle.ui_particle_Type",
        "particle.f_particle_size", "particle.f_particle_size_max",
        "particle.f_part_speed_module", "particle.f_part_speed_module_max",
        "particle.UV_set.left", "particle.UV_set.up",
        "particle.UV_set.right", "particle.UV_set.down",
        "particle.i_frame_div_U", "particle.i_frame_div_V",
        "particle.f_fps", "particle.f_dir_length",
        "particle.f_K_gravity", "particle.f_K_gravity_max",
        "particle.f_YAW_min", "particle.f_YAW_max",
        "particle.f_PITCH_min", "particle.f_PITCH_max",
        "particle.f_ROLL_min", "particle.f_ROLL_max",
        "particle.f_speed_sensor", "particle.f_z_offset",
        "particle.ch_fn_texture", "particle.ch_fn_Shader"
    ]

    for tag in particle_order:
        raw_key = f"RAW_{tag}"
        if raw_key in s_obj:
            ET.SubElement(emitter_xml, tag).text = f" {s_obj[raw_key]} "
        
        elif tag in all_params:
            val = all_params[tag]
            if isinstance(val, int) and val < 0:
                val = val + 4294967296
                
            formatted_val = format_value(val, tag)
            
            if tag == "particle.ch_fn_texture" and not formatted_val.strip():
                ET.SubElement(emitter_xml, tag)
            else:
                ET.SubElement(emitter_xml, tag).text = f" {formatted_val} "
            
        else:
            if tag == "particle.ch_fn_texture":
                ET.SubElement(emitter_xml, tag).text = " particles/content_deferred/PFX_textures/eff_tex.dds "
            elif tag == "particle.ch_fn_Shader":
                ET.SubElement(emitter_xml, tag).text = r" \Data\Shaders\ps.fx "
            elif tag == "particle.dw_mode_Ext_inv":
                ET.SubElement(emitter_xml, tag).text = " 4294967295 " # <-- Gördüğün gibi eski kodda da buraya sabitlenmiş!
            elif tag == "particle.base.fa_start_pos":
                ET.SubElement(emitter_xml, tag).text = " 0.000000 0.000000 0.000000 "
            elif tag in ["particle.ui_particle_Type", "particle.i_frame_div_U", "particle.i_frame_div_V"]:
                ET.SubElement(emitter_xml, tag).text = " 1 "
            else:
                ET.SubElement(emitter_xml, tag).text = " 0.000000 "
            log(f"DEBUG (Fallback): '{emitter_base_name}' icinde '{tag}' bulunamadi. Varsayilan atandi.")

    lighting_order = [
        "lighting_params.f_diffuse_light_multiplier", "lighting_params.f_indirect_light_multiplier",
        "lighting_params.f_scattered_light_multiplier", "lighting_params.f_constant_scattered_light_ammount",
        "lighting_params.f_self_shadow_power", "lighting_params.f_halo_alpha_threshold",
        "lighting_params.f_halo_multiplier", "lighting_params.f_halo_shadow_power",
        "lighting_params.f_halo_fade_power", "lighting_params.f_self_illum",
        "lighting_params.f_normal_generation_offset", "lighting_params.f_tessellation_factor"
    ]

    for tag in lighting_order:
        if tag in all_params:
            ET.SubElement(emitter_xml, tag).text = f" {format_value(all_params[tag], tag)} "
        else:
            ET.SubElement(emitter_xml, tag).text = " 0.000000 "

def export_vfx_pipeline(root_obj, filepath):
    """Dışa aktarma işleminin ana başlatıcısı"""
    log(f"Export başlatılıyor: {filepath}")
    
    root_xml = ET.Element("root")
    
    if "dw_mode_lodeffect_mutable" in root_obj:
        dw_mode_lod = ET.SubElement(root_xml, "dw_mode_lod_effect")
        mut = ET.SubElement(dw_mode_lod, "dw_mode_lodeffect_mutable")
        mut.text = "1" if root_obj["dw_mode_lodeffect_mutable"] else "0"

    is_hybrid = root_obj.get("hybrid_effect", False)
    
    if is_hybrid:
        log("Hybrid effect detected. Searching for Influx/GPU subtrees...")
        for child in root_obj.children:
            if child.name == "influx":
                influx_xml = ET.SubElement(root_xml, "influx")
                for lod in child.children:
                    export_lod_block(lod, influx_xml)
            elif child.name == "gpu":
                gpu_xml = ET.SubElement(root_xml, "gpu")
                for lod in child.children:
                    export_lod_block(lod, gpu_xml)
    else:
        log("Standard effect detected.")
        for child in root_obj.children:
            if child.type == 'EMPTY':
                export_lod_block(child, root_xml)

    final_xml_string = prettify_wot_xml(root_xml)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(final_xml_string)
        
    log("Export completed!")