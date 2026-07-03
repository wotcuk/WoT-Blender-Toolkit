import os
import struct
import xml.etree.ElementTree as ET

def write_string(buffer, offset, text, length):
    """Writes the text to a byte array of the specified length, filling the rest with null (0x00)."""
    if text is None:
        text = ""
    encoded = text.encode('utf-8')[:length - 1]
    buffer[offset : offset + len(encoded)] = encoded
    # Since the buffer is created as a bytearray, the remaining parts will already remain 0x00.

def parse_bool(text):
    if text is None: return False
    return text.strip().lower() in ['true', '1']

def pack_vfx_to_vfxbin(input_xml_path, output_bin_path):
    tree = ET.parse(input_xml_path)
    root = tree.getroot()

    # --- HEADER CREATION (80 Bytes) ---
    header_data = bytearray(80)
    header_data[0:4] = b'\xEC\x03\x00\x00' # Magic Number
    write_string(header_data, 0x10, "lod_effect_f", 13)
    
    mut_val = root.find('.//dw_mode_lodeffect_mutable')
    if mut_val is not None:
        header_data[0x32] = int(mut_val.text.strip())
        
    lods = root.findall('lod')
    struct.pack_into('<I', header_data, 0x0C, len(lods))

    vfxbin_data = bytearray()
    vfxbin_data.extend(header_data)

    # --- LOD LOOP ---
    for lod in lods:
        lod_start_idx = len(vfxbin_data)
        lod_header = bytearray(160) # Standard LOD size
        lod_header[0:4] = b'\xEB\x03\x00\x00'
        lod_header[0x08:0x0C] = b'\x02\x00\x00\x00' # Unknown constant
        lod_header[0x14:0x18] = b'\xEB\x03\x00\x00'
        lod_header[0x18:0x1C] = b'\x02\x00\x00\x00' # Unknown constant

        emitters = lod.findall('emitter')
        struct.pack_into('<I', lod_header, 0x0C, len(emitters))
        struct.pack_into('<I', lod_header, 0x10, 140) # 0x8C Distance to the first emitter
        
        write_string(lod_header, 0x20, lod.find('s_effect_name').text.strip(), 64)
        
        struct.pack_into('<f', lod_header, 0x60, float(lod.find('f_near_clip').text))
        struct.pack_into('<f', lod_header, 0x64, float(lod.find('f_far_clip').text))
        struct.pack_into('<f', lod_header, 0x68, float(lod.find('f_Skip_time').text))
        
        buffer_val = lod.find('buffer').text
        if buffer_val and buffer_val.strip():
            write_string(lod_header, 0x70, buffer_val.strip(), 40)

        # LOD Masks
        i_lod_mask = 0
        i_lod_node = lod.find('i_lod_mask')
        if i_lod_node is not None:
            if parse_bool(i_lod_node.find('ps_particle_lod_default').text): i_lod_mask |= 0x00010000
            if parse_bool(i_lod_node.find('ps_particle_lod_last_disableable').text): i_lod_mask |= 0x01000000
            if parse_bool(i_lod_node.find('ps_particle_lod_last_available').text): i_lod_mask |= 0x80000000
        struct.pack_into('<I', lod_header, 0x6C, i_lod_mask)

        lod_dw_mask = 0
        if parse_bool(lod.find('.//ps_element_off').text): lod_dw_mask |= 0x00400000
        struct.pack_into('<I', lod_header, 0x1C, lod_dw_mask)

        vfxbin_data.extend(lod_header)

        # --- EMITTER LOOP ---
        for emitter in emitters:
            e_start_idx = len(vfxbin_data)
            
            # Fixed area where curves start
            curve_start_offset = 0x5F0 
            e_data = bytearray(curve_start_offset) 
            
            e_data[0:4] = b'\xE9\x03\x00\x00'
            
            # FIX FOR SIZE CALCULATION ERROR: 
            # Dynamically calculate the distance from 0x0C to 0x5F0 where the curves start
            distance_to_curves = curve_start_offset - 0x0C # Result: 1508 (0x5E4)
            struct.pack_into('<I', e_data, 0x08, distance_to_curves) 
            
            e_data[0x0C:0x10] = b'\xE9\x03\x00\x00'
            
            # NEW DISCOVERY: Offset 0x10 is always 5 (05 00 00 00)
            e_data[0x10:0x14] = b'\x05\x00\x00\x00'
            
            e_data[0x5C:0x60] = b'\xE8\x03\x00\x00'
            e_data[0x60:0x64] = b'\x02\x00\x00\x00'
            
            e_data[0x00BC:0x00C0] = b'\xFF\xFF\xFF\xFF'
            e_data[0x00F0:0x0100] = b'\xE7\x03\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            
            # NEW DISCOVERY: The mysterious 8 Bytes at offset 0x0408 is always 1005 (ED 03 00 00 + 4 zero bytes)
            e_data[0x0408:0x0410] = b'\xED\x03\x00\x00\x00\x00\x00\x00'

            for i in range(0x0490, 0x04F0, 4):
                e_data[i:i+4] = b'\x00\x00\x00\x00'

            write_string(e_data, 0x1C, emitter.find('s_emitter_name').text.strip(), 64)
            
            # Shader and Texture
            ch_fn_shader = emitter.find('particle.ch_fn_Shader')
            if ch_fn_shader is not None and ch_fn_shader.text:
                write_string(e_data, 0x200, ch_fn_shader.text.strip(), 128)
                
            ch_fn_tex = emitter.find('particle.ch_fn_texture')
            if ch_fn_tex is not None and ch_fn_tex.text:
                write_string(e_data, 0x120, ch_fn_tex.text.strip(), 128)

            ex_file = emitter.find('Ex_Filename')
            if ex_file is not None and ex_file.text:
                write_string(e_data, 0x4F0, ex_file.text.strip(), 256)

            res_buf = emitter.find('reserved_buffer')
            if res_buf is not None and res_buf.text:
                write_string(e_data, 0x00CC, res_buf.text.strip(), 36)
                
            res_str = emitter.find('reserved')
            if res_str is not None and res_str.text:
                write_string(e_data, 0x03B0, res_str.text.strip(), 64)

            # CRITICAL INTEGER VALUES PREVENTING CRASHES
            struct.pack_into('<i', e_data, 0x18, int(emitter.find('i_RT_shader_num').text))
            struct.pack_into('<i', e_data, 0x1CC, int(emitter.find('particle.i_frame_div_U').text))
            struct.pack_into('<i', e_data, 0x1D0, int(emitter.find('particle.i_frame_div_V').text))
            
            # Masks (Quality, Support)
            q_mask_val = int(emitter.find('m_supportedQualityMask').text)
            e_data[0x474] = q_mask_val & 0xFF
            
            m_sort_val = int(emitter.find('m_sortType').text)
            e_data[0x475] = m_sort_val & 0xFF
            
            struct.pack_into('<i', e_data, 0x478, int(emitter.find('m_supportedPassMask').text))
            struct.pack_into('<i', e_data, 0x47C, int(emitter.find('m_supportedSniperPassMask').text))
            struct.pack_into('<I', e_data, 0x1C0, int(emitter.find('particle.dw_mode_Ext_inv').text))
            struct.pack_into('<I', e_data, 0x84, int(emitter.find('vt.ui_volume_type').text))
            struct.pack_into('<I', e_data, 0x11C, int(emitter.find('particle.ui_particle_Type').text))

            # Bitmask - dw_mode
            dm = 0
            dm_flags = [
                ("ps_emitter_mode_onetime_emission", 0x00000100), ("ps_element_dead", 0x00000001),
                ("ps_element_particle", 0x00000002), ("ps_element_emitter", 0x00000004),
                ("ps_element_type_reserved01", 0x00000008), ("ps_element_found_external_data", 0x00000010),
                ("ps_element_not_active", 0x00000020), ("ps_element_inconsumable", 0x00000040),
                ("ps_element_no_gravity", 0x00000080), ("ps_element_destructed", 0x00000100),
                ("ps_element_not_used", 0x00000200), ("ps_element_use_size_timeline", 0x00000400),
                ("ps_element_use_color_timeline", 0x00000800), ("ps_emitter_use_rate_timeline", 0x00001000),
                ("ps_emitter_use_gravity_timeline", 0x00002000), ("ps_emitter_use_tangent_speed_timeline", 0x00004000),
                ("ps_emitter_use_angle_speed_timeline", 0x00008000), ("ps_emitter_use_speed_timeline", 0x00010000),
                ("ps_emitter_use_color_op_timeline", 0x00020000), ("ps_element_use_timeline_9", 0x00040000),
                ("ps_element_use_timeline_10", 0x00080000), ("ps_element_not_render", 0x00100000),
                ("ps_element_use_tangent_speed", 0x00200000), ("ps_element_off", 0x00400000),
                ("ps_emitter_off", 0x00800000), ("ps_element_r_type_dx", 0x01000000),
                ("ps_element_r_type_shader", 0x02000000), ("ps_element_world_offset", 0x10000000),
                ("ps_element_y_emission", 0x20000000), ("ps_element_x_emission", 0x40000000),
                ("ps_element_epicentr_emission", 0x80000000)
            ]
            dw_node = emitter.find('dw_mode')
            for f_name, f_val in dm_flags:
                if dw_node.find(f_name) is not None and parse_bool(dw_node.find(f_name).text):
                    dm |= f_val
            struct.pack_into('<I', e_data, 0x14, dm)

            # --- FIXED HAVOK AND EXT_MODE START ---
            # 1. First, Havok Flag is written (overwrites 4 bytes starting from 0xB8)
            havok_flag = 0
            if parse_bool(emitter.find('disabled_in_havok').text):
                havok_flag |= 0x4000
            struct.pack_into('<I', e_data, 0x00B8, havok_flag)

            # 2. Then, dw_ext_mode flags are accumulated
            em = 0
            em_flags = [
                ("ps_emitter_ext_ignore_camera_factor", 0x02), ("ps_emitter_ext_mode_eee_slave", 0x04),
                ("ps_emitter_ext_mode_model_emission", 0x08), ("ps_emitter_ext_mode_model_reserved", 0x10),
                ("ps_emitter_ext_mode_model_hmap_lim", 0x20),
                ("ps_emitter_ext_mode_length_depends_on_size", 0x80), ("ps_emitter_ext_mode_accept_tint", 0x80)
            ]
            ext_node = emitter.find('dw_ext_mode')
            if ext_node is not None:
                for f_name, f_val in em_flags:
                    if ext_node.find(f_name) is not None and parse_bool(ext_node.find(f_name).text):
                        em |= f_val
            
            # 3. Using (|=) instead of (=) adds it on top of the existing data, preventing Havok data corruption!
            e_data[0xB9] |= em
            # --- FIXED HAVOK AND EXT_MODE END ---

            # Bitmask - particle.dw_mode
            pm = 0
            pm_flags = [
                ("ps_particle_use_frames", 0x00000001), ("ps_particle_random_frame", 0x00000002),
                ("ps_particle_local", 0x00000004), ("ps_particle_horizont", 0x00000008),
                ("ps_particle_soft", 0x00000010), ("ps_particle_water_level", 0x00000020),
                ("ps_particle_stop_on_last_frame", 0x00000040), ("ps_particle_do_not_blend", 0x00000080),
                ("ps_particle_use_direction_for_angle", 0x00000100), ("ps_element_directional", 0x04000000),
                ("ps_element_speed_oriented", 0x08000000)
            ]
            pm_node = emitter.find('particle.dw_mode')
            for f_name, f_val in pm_flags:
                if pm_node.find(f_name) is not None and parse_bool(pm_node.find(f_name).text):
                    pm |= f_val
            struct.pack_into('<I', e_data, 0x1C8, pm)
            
            # Coordinate System Control (overwrites the 0x04 bit)
            coord = emitter.find('coordinate_system').text.strip()
            if coord == "Local":
                e_data[0x1C8] |= 0x04 
            else:
                e_data[0x1C8] &= ~0x04

            # --- FLOAT PARAMETERS (All) ---
            def set_f(tag_name, offset):
                node = emitter.find(tag_name)
                if node is not None:
                    struct.pack_into('<f', e_data, offset, float(node.text))

            def set_v3(tag_name, offset):
                node = emitter.find(tag_name)
                if node is not None:
                    vals = list(map(float, node.text.strip().split()))
                    struct.pack_into('<fff', e_data, offset, vals[0], vals[1], vals[2])

            set_f('emitter.f_life_min', 0x64); set_f('emitter.f_life_max', 0x68)
            set_f('emitter.f_delay_min', 0x6C); set_f('emitter.f_delay_max', 0x70)
            set_v3('emitter.fa_start_pos', 0x74); set_f('f_rate', 0x80)
            set_f('f_X_dim_volume', 0x88); set_f('f_Y_dim_volume', 0x8C); set_f('f_Z_dim_volume', 0x90)
            set_f('f_strt_angle_min', 0x94); set_f('f_strt_angle_max', 0x98)
            set_f('f_strt_angle_speed_min', 0x9C); set_f('f_strt_angle_speed_max', 0xA0)
            set_f('f_tangent_speed_min', 0xA4); set_f('f_tangent_speed_max', 0xA8)
            set_f('f_fire_smoke', 0xAC); set_f('f_wind_weight', 0xB0); set_f('f_wind_weight_max', 0xB4)
            set_f('f_Espeed_time', 0xC0); set_f('f_Espeed_mult', 0xC4); set_f('f_minDistanceBeforeEmission', 0xC8)
            
            set_f('particle.base.f_life_min', 0x100); set_f('particle.base.f_life_max', 0x104)
            set_f('particle.base.f_delay_min', 0x108); set_f('particle.base.f_delay_max', 0x10C)
            set_v3('particle.base.fa_start_pos', 0x110)
            
            set_f('particle.f_particle_size', 0x1A0); set_f('particle.f_particle_size_max', 0x1A4)
            set_f('particle.f_part_speed_module', 0x1A8); set_f('particle.f_part_speed_module_max', 0x1AC)
            set_f('particle.UV_set.up', 0x1B0); set_f('particle.UV_set.left', 0x1B4)
            set_f('particle.UV_set.down', 0x1B8); set_f('particle.UV_set.right', 0x1BC)
            
            set_f('particle.f_K_gravity', 0x1C4); set_f('particle.f_fps', 0x1D4)
            set_f('particle.f_dir_length', 0x1D8); set_f('particle.f_K_gravity_max', 0x1DC)
            set_f('particle.f_YAW_min', 0x1E0); set_f('particle.f_YAW_max', 0x1E4)
            set_f('particle.f_PITCH_min', 0x1E8); set_f('particle.f_PITCH_max', 0x1EC)
            set_f('particle.f_ROLL_min', 0x1F0); set_f('particle.f_ROLL_max', 0x1F4)
            set_f('particle.f_speed_sensor', 0x1F8); set_f('particle.f_z_offset', 0x1FC)
            
            set_f('f_part_tangenta', 0x280)
            set_v3('fa_epicenter_pos', 0x3F0); set_v3('fa_epicenter_box', 0x3FC)
            set_v3('particle_ex.YPR_start', 0x410); set_v3('particle_ex.YPR_start_spread', 0x41C)
            
            set_f('particle_ex.f_soft_factor', 0x428); set_f('particle_ex.f_ground_height_offset', 0x42C)
            set_f('particle_ex.deffered_color_mult', 0x43C)
            
            set_f('lighting_params.f_diffuse_light_multiplier', 0x440)
            set_f('lighting_params.f_indirect_light_multiplier', 0x444)
            set_f('lighting_params.f_scattered_light_multiplier', 0x448)
            set_f('lighting_params.f_constant_scattered_light_ammount', 0x44C)
            set_f('lighting_params.f_self_shadow_power', 0x450)
            set_f('lighting_params.f_halo_alpha_threshold', 0x454)
            set_f('lighting_params.f_halo_multiplier', 0x458)
            set_f('lighting_params.f_halo_shadow_power', 0x45C)
            set_f('lighting_params.f_halo_fade_power', 0x460)
            set_f('lighting_params.f_self_illum', 0x464)
            set_f('lighting_params.f_normal_generation_offset', 0x468)
            set_f('lighting_params.f_tessellation_factor', 0x46C)
            
            set_f('f_solidThreshold', 0x470)
            set_f('f_fadeInOffsetFrom', 0x480); set_f('f_fadeInOffsetTo', 0x484)
            set_f('f_dir_length_max', 0x488); set_f('f_slopeFadeCoeff', 0x48C)

            # Set the distance right before the curves (Curve Offset)
            curve_dist = 0x5F0

            vfxbin_data.extend(e_data)

            # --- WRITING CURVES ---
            curve_names = [
                "tl_size_key", "tl_rate_key", "tl_gravity_key", "tl_speed_key",
                "tl_tangent_speed_key", "tl_angle_speed_key", "tl_Color_key", "tl_color_op_key"
            ]
            
            for c_name in curve_names:
                c_node = emitter.find(c_name)
                if c_node is None or len(c_node.findall('time')) == 0:
                    vfxbin_data.extend(struct.pack('<I', 0))
                    vfxbin_data.extend(b'\x50\x50\x50\x50')
                else:
                    times = c_node.findall('time')
                    vfxbin_data.extend(struct.pack('<I', len(times)))
                    vfxbin_data.extend(b'\x50\x50\x50\x50')
                    
                    if c_name == "tl_Color_key":
                        values = c_node.findall('value_RGBA')
                        for t in times:
                            vfxbin_data.extend(struct.pack('<f', float(t.text)))
                            
                        # Mimicking the game engine's C++ Float32 "Multiplication" optimization
                        # Forcing 1.0 / 255.0 operation into a 32-bit float and fixing it
                        inv_255 = struct.unpack('<f', struct.pack('<f', 1.0 / 255.0))[0]
                        
                        for v in values:
                            r, g, b, a = map(float, v.text.strip().split())
                            vfxbin_data.extend(struct.pack('<ffff', r * inv_255, g * inv_255, b * inv_255, a))
                    else:
                        values = c_node.findall('value')
                        for t in times:
                            vfxbin_data.extend(struct.pack('<f', float(t.text)))
                        for v in values:
                            vfxbin_data.extend(struct.pack('<f', float(v.text)))

            # Update Total Emitter Size
            e_size = len(vfxbin_data) - e_start_idx
            struct.pack_into('<I', vfxbin_data, e_start_idx + 0x04, e_size)

        # Update Total LOD Size
        lod_size = len(vfxbin_data) - lod_start_idx
        struct.pack_into('<I', vfxbin_data, lod_start_idx + 0x04, lod_size)

    # Update General File Size
    struct.pack_into('<I', vfxbin_data, 0x04, len(vfxbin_data))

    # Save File
    with open(output_bin_path, 'wb') as f:
        f.write(vfxbin_data)
        
    print(f"Packer process completed: {output_bin_path} ({len(vfxbin_data)} Bytes)")