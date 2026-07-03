import os
import struct

def read_string(data, offset, length):
    raw = data[offset : offset+length]
    if all(b == 0 for b in raw):
        return None
    return raw.split(b'\x00')[0].decode('utf-8', errors='ignore')

# --- FONKSİYONA PARAMETRE EKLENDİ ---
def unpack_vfxbin_files(input_dir, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    vfxbin_files = [f for f in os.listdir(input_dir) if f.endswith('.vfxbin')]
    print(f"--- UNPACK İŞLEMİ BAŞLADI ({len(vfxbin_files)} Dosya) ---")

    for filename in vfxbin_files:
        filepath = os.path.join(input_dir, filename)
        
        with open(filepath, 'rb') as f:
            data = f.read()

        if len(data) < 80 or data[0:4] != b'\xEC\x03\x00\x00':
            print(f"[ATLANDI] {filename} (Hibrit veya geçersiz header)")
            continue
            
        print(f"[İŞLENİYOR] {filename}")

        total_size = struct.unpack_from('<I', data, 0x04)[0]
        lod_count = struct.unpack_from('<I', data, 0x0C)[0]
        dw_mode_lodeffect_mutable = data[0x32] 

        xml_lines = []
        xml_lines.append("<root>")
        xml_lines.append("\t<dw_mode_lod_effect>")
        xml_lines.append(f"\t\t<dw_mode_lodeffect_mutable> {dw_mode_lodeffect_mutable} </dw_mode_lodeffect_mutable>")
        xml_lines.append("\t</dw_mode_lod_effect>")

        current_offset = 80 
        
        for lod_index in range(lod_count):
            if current_offset + 160 > len(data) or data[current_offset : current_offset+4] != b'\xEB\x03\x00\x00':
                break

            lod_size = struct.unpack_from('<I', data, current_offset + 0x04)[0]
            emitter_count = struct.unpack_from('<I', data, current_offset + 0x0C)[0]
            
            dw_mode_mask = struct.unpack_from('<I', data, current_offset + 0x1C)[0]
            effect_name = read_string(data, current_offset + 0x20, 64)
            i_lod_mask = struct.unpack_from('<I', data, current_offset + 0x6C)[0]
            
            f_near_clip = struct.unpack_from('<f', data, current_offset + 0x60)[0]
            f_far_clip = struct.unpack_from('<f', data, current_offset + 0x64)[0]
            f_Skip_time = struct.unpack_from('<f', data, current_offset + 0x68)[0]
            buffer_val = read_string(data, current_offset + 0x70, 40)

            xml_lines.append("\t<lod>")
            xml_lines.append(f"\t\t<s_effect_name> {effect_name} </s_effect_name>")
            xml_lines.append("\t\t<i_lod_mask>")
            xml_lines.append(f"\t\t\t<ps_particle_lod_default> {1 if (i_lod_mask & 0x00010000) else 0} </ps_particle_lod_default>")
            xml_lines.append(f"\t\t\t<ps_particle_lod_last_disableable> {1 if (i_lod_mask & 0x01000000) else 0} </ps_particle_lod_last_disableable>")
            xml_lines.append(f"\t\t\t<ps_particle_lod_last_available> {1 if (i_lod_mask & 0x80000000) else 0} </ps_particle_lod_last_available>")
            xml_lines.append("\t\t</i_lod_mask>")
            xml_lines.append(f"\t\t<f_near_clip> {f_near_clip:.6f} </f_near_clip>")
            xml_lines.append(f"\t\t<f_far_clip> {f_far_clip:.6f} </f_far_clip>")
            xml_lines.append(f"\t\t<f_Skip_time> {f_Skip_time:.6f} </f_Skip_time>")
            
            if buffer_val is None: xml_lines.append("\t\t<buffer/>")
            else: xml_lines.append(f"\t\t<buffer> {buffer_val} </buffer>")
                
            xml_lines.append("\t\t<dw_mode>")
            xml_lines.append(f"\t\t\t<ps_element_off> {1 if (dw_mode_mask & 0x00400000) else 0} </ps_element_off>")
            xml_lines.append("\t\t</dw_mode>")
            
            first_emitter_distance = struct.unpack_from('<I', data, current_offset + 0x10)[0]
            e_pos = current_offset + 0x14 + first_emitter_distance

            for _ in range(emitter_count):
                if e_pos + 8 > len(data): break
                e_size = struct.unpack_from('<I', data, e_pos + 0x04)[0]

                e_name = read_string(data, e_pos + 0x1C, 64)
                xml_lines.append("\t\t<emitter>")
                xml_lines.append(f"\t\t\t<s_emitter_name> {e_name} </s_emitter_name>")
                
                p_shader_raw = read_string(data, e_pos + 0x200, 128)
                shader_name = ""
                if p_shader_raw:
                    # Dosya yolunu (particles/shaders/ps.fx) temizleyip sadece ps.fx kısmını alıyoruz
                    shader_name = p_shader_raw.split('\\')[-1].split('/')[-1].lower()

                if shader_name == "pbs_mesh_particles.fx":
                    # Mesh ve Particle Emitter aynı shader'ı kullanır. Ayırmak için dw_mode (0x14) okuyoruz.
                    temp_dm = struct.unpack_from('<I', data, e_pos + 0x14)[0]
                    if temp_dm & 0x04: # ps_element_emitter bayrağı aktif mi?
                        xml_type = "Particle Emitter"
                    else:
                        xml_type = "Mesh"
                elif shader_name == "ps_long.fx": xml_type = "Directional Sprites"
                elif shader_name == "ps_solid.fx": xml_type = "Solid particles"
                elif shader_name == "ps_shimmer.fx": xml_type = "Distortion particles"
                elif shader_name == "ps_water.fx": xml_type = "World Space Sprites"
                elif shader_name == "ps_water_displacement.fx": xml_type = "Water displacement particles"
                elif shader_name == "ps_force_fields.fx": xml_type = "Force field particles"
                elif shader_name == "ps_foam.fx": xml_type = "Water foam particle"
                elif shader_name == "ps_under_water.fx": xml_type = "Under water particles"
                else: xml_type = "Sprites" # Varsayılan (ps.fx veya bilinmeyen için)

                xml_lines.append(f"\t\t\t<type> {xml_type} </type>")
                # 0x00B8 offsetinden 4 byte'lık (32-bit Unsigned Integer) bayrak değerini okuyoruz
                havok_flag = struct.unpack_from('<I', data, e_pos + 0x00B8)[0]
                
                # 0x4000 biti 1 ise true, 0 ise false yazdırıyoruz
                is_havok_disabled = 'true' if (havok_flag & 0x4000) else 'false'
                xml_lines.append(f"\t\t\t<disabled_in_havok> {is_havok_disabled} </disabled_in_havok>")
                
                # DOĞRU KISIM (Hem 0x00CC hem de 0x03B0 okunuyor)
                res_buffer = read_string(data, e_pos + 0x00CC, 36)
                if res_buffer:
                    xml_lines.append(f"\t\t\t<reserved_buffer> {res_buffer} </reserved_buffer>")
                else:
                    xml_lines.append("\t\t\t<reserved_buffer/>")

                res_str = read_string(data, e_pos + 0x03B0, 64)
                if res_str:
                    xml_lines.append(f"\t\t\t<reserved> {res_str} </reserved>")
                else:
                    xml_lines.append("\t\t\t<reserved/>")

                dm = struct.unpack_from('<I', data, e_pos + 0x14)[0]
                xml_lines.append("\t\t\t<dw_mode>")
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
                for f_name, f_val in dm_flags:
                    xml_lines.append(f"\t\t\t\t<{f_name}> {1 if (dm & f_val) else 0} </{f_name}>")
                xml_lines.append("\t\t\t</dw_mode>")

                em = data[e_pos + 0xB9]
                xml_lines.append("\t\t\t<dw_ext_mode>")
                em_flags = [
                    ("ps_emitter_ext_ignore_camera_factor", 0x02), ("ps_emitter_ext_mode_eee_slave", 0x04),
                    ("ps_emitter_ext_mode_model_emission", 0x08), ("ps_emitter_ext_mode_model_reserved", 0x10),
                    ("ps_emitter_ext_mode_model_hmap_lim", 0x20), ("ps_emitter_ext_mode_havok_disable", 0x40),
                    ("ps_emitter_ext_mode_length_depends_on_size", 0x80), ("ps_emitter_ext_mode_accept_tint", 0x80)
                ]
                for f_name, f_val in em_flags:
                    xml_lines.append(f"\t\t\t\t<{f_name}> {1 if (em & f_val) else 0} </{f_name}>")
                xml_lines.append("\t\t\t</dw_ext_mode>")

                i_rt = struct.unpack_from('<i', data, e_pos + 0x18)[0]
                xml_lines.append(f"\t\t\t<i_RT_shader_num> {i_rt} </i_RT_shader_num>")
                
                def get_f(offset): return struct.unpack_from('<f', data, e_pos + offset)[0]
                def get_v3(offset): return (get_f(offset), get_f(offset+4), get_f(offset+8))
                
                xml_lines.append(f"\t\t\t<emitter.f_life_min> {get_f(0x64):.6f} </emitter.f_life_min>")
                xml_lines.append(f"\t\t\t<emitter.f_life_max> {get_f(0x68):.6f} </emitter.f_life_max>")
                xml_lines.append(f"\t\t\t<emitter.f_delay_min> {get_f(0x6C):.6f} </emitter.f_delay_min>")
                xml_lines.append(f"\t\t\t<emitter.f_delay_max> {get_f(0x70):.6f} </emitter.f_delay_max>")
                
                sp = get_v3(0x74)
                xml_lines.append(f"\t\t\t<emitter.fa_start_pos> {sp[0]:.6f} {sp[1]:.6f} {sp[2]:.6f} </emitter.fa_start_pos>")
                xml_lines.append(f"\t\t\t<f_rate> {get_f(0x80):.6f} </f_rate>")
                
                vol_type = struct.unpack_from('<I', data, e_pos + 0x84)[0]
                xml_lines.append(f"\t\t\t<vt.ui_volume_type> {vol_type} </vt.ui_volume_type>")
                xml_lines.append(f"\t\t\t<f_X_dim_volume> {get_f(0x88):.6f} </f_X_dim_volume>")
                xml_lines.append(f"\t\t\t<f_Y_dim_volume> {get_f(0x8C):.6f} </f_Y_dim_volume>")
                xml_lines.append(f"\t\t\t<f_Z_dim_volume> {get_f(0x90):.6f} </f_Z_dim_volume>")
                xml_lines.append(f"\t\t\t<f_strt_angle_min> {get_f(0x94):.6f} </f_strt_angle_min>")
                xml_lines.append(f"\t\t\t<f_strt_angle_max> {get_f(0x98):.6f} </f_strt_angle_max>")
                xml_lines.append(f"\t\t\t<f_strt_angle_speed_min> {get_f(0x9C):.6f} </f_strt_angle_speed_min>")
                xml_lines.append(f"\t\t\t<f_strt_angle_speed_max> {get_f(0xA0):.6f} </f_strt_angle_speed_max>")
                xml_lines.append(f"\t\t\t<f_tangent_speed_min> {get_f(0xA4):.6f} </f_tangent_speed_min>")
                xml_lines.append(f"\t\t\t<f_tangent_speed_max> {get_f(0xA8):.6f} </f_tangent_speed_max>")
                xml_lines.append(f"\t\t\t<f_fire_smoke> {get_f(0xAC):.6f} </f_fire_smoke>")
                xml_lines.append(f"\t\t\t<f_wind_weight> {get_f(0xB0):.6f} </f_wind_weight>")
                xml_lines.append(f"\t\t\t<f_wind_weight_max> {get_f(0xB4):.6f} </f_wind_weight_max>")
                xml_lines.append(f"\t\t\t<f_part_tangenta> {get_f(0x280):.6f} </f_part_tangenta>")
                xml_lines.append(f"\t\t\t<f_Espeed_time> {get_f(0xC0):.6f} </f_Espeed_time>")
                xml_lines.append(f"\t\t\t<f_Espeed_mult> {get_f(0xC4):.6f} </f_Espeed_mult>")
                xml_lines.append(f"\t\t\t<f_minDistanceBeforeEmission> {get_f(0xC8):.6f} </f_minDistanceBeforeEmission>")
                
                m_sort = data[e_pos + 0x475]
                xml_lines.append(f"\t\t\t<m_sortType> {m_sort} </m_sortType>")

                curve_offset = e_pos + 0x5F0
                curve_names = [
                    "tl_size_key", "tl_rate_key", "tl_gravity_key", "tl_speed_key",
                    "tl_tangent_speed_key", "tl_angle_speed_key", "tl_Color_key", "tl_color_op_key"
                ]

                for c_name in curve_names:
                    num_points = struct.unpack_from('<I', data, curve_offset)[0]
                    curve_offset += 4
                    
                    if num_points == 0:
                        curve_offset += 4 
                        xml_lines.append(f"\t\t\t<{c_name}/>")
                    else:
                        curve_offset += 4 
                        xml_lines.append(f"\t\t\t<{c_name}>")
                        
                        times = []
                        for _ in range(num_points):
                            times.append(struct.unpack_from('<f', data, curve_offset)[0])
                            curve_offset += 4
                            
                        if c_name == "tl_Color_key":
                            for i in range(num_points):
                                r = struct.unpack_from('<f', data, curve_offset)[0] * 255.0
                                g = struct.unpack_from('<f', data, curve_offset+4)[0] * 255.0
                                b = struct.unpack_from('<f', data, curve_offset+8)[0] * 255.0
                                a = struct.unpack_from('<f', data, curve_offset+12)[0]
                                curve_offset += 16
                                xml_lines.append(f"\t\t\t\t<time> {times[i]:.6f} </time>")
                                xml_lines.append(f"\t\t\t\t<value_RGBA> {r:.6f} {g:.6f} {b:.6f} {a:.6f} </value_RGBA>")
                        else:
                            for i in range(num_points):
                                val = struct.unpack_from('<f', data, curve_offset)[0]
                                curve_offset += 4
                                xml_lines.append(f"\t\t\t\t<time> {times[i]:.6f} </time>")
                                xml_lines.append(f"\t\t\t\t<value> {val:.6f} </value>")
                                
                        xml_lines.append(f"\t\t\t</{c_name}>")

                coord_flags = data[e_pos + 0x1C8]
                
                # 0x04 biti 1 ise Local, 0 ise World
                if coord_flags & 0x04:
                    coord_sys = "Local"
                else:
                    coord_sys = "World"
                    
                xml_lines.append(f"\t\t\t<coordinate_system> {coord_sys} </coordinate_system>")
                
                ep = get_v3(0x3F0)
                eb = get_v3(0x3FC)
                xml_lines.append(f"\t\t\t<fa_epicenter_pos> {ep[0]:.6f} {ep[1]:.6f} {ep[2]:.6f} </fa_epicenter_pos>")
                xml_lines.append(f"\t\t\t<fa_epicenter_box> {eb[0]:.6f} {eb[1]:.6f} {eb[2]:.6f} </fa_epicenter_box>")
                
                ex_file = read_string(data, e_pos + 0x4F0, 256)
                if ex_file: xml_lines.append(f"\t\t\t<Ex_Filename> {ex_file} </Ex_Filename>")
                else: xml_lines.append("\t\t\t<Ex_Filename/>")
                
                xml_lines.append(f"\t\t\t<f_solidThreshold> {get_f(0x470):.6f} </f_solidThreshold>")
                
                q_mask = data[e_pos + 0x474]
                p_mask = struct.unpack_from('<i', data, e_pos + 0x478)[0] # -1 hatası için küçük 'i' yapıldı
                s_mask = struct.unpack_from('<i', data, e_pos + 0x47C)[0] # -1 hatası için küçük 'i' yapıldı

                # q_mask byte'ından bitleri okuyup true/false olarak XML'e yazdırıyoruz
                xml_lines.append(f"\t\t\t<QUALITY_MIN> {'true' if (q_mask & 0x01) else 'false'} </QUALITY_MIN>")
                xml_lines.append(f"\t\t\t<QUALITY_LOW> {'true' if (q_mask & 0x02) else 'false'} </QUALITY_LOW>")
                xml_lines.append(f"\t\t\t<QUALITY_MEDIUM> {'true' if (q_mask & 0x04) else 'false'} </QUALITY_MEDIUM>")
                xml_lines.append(f"\t\t\t<QUALITY_HIGH> {'true' if (q_mask & 0x08) else 'false'} </QUALITY_HIGH>")
                xml_lines.append(f"\t\t\t<QUALITY_ULTRA> {'true' if (q_mask & 0x10) else 'false'} </QUALITY_ULTRA>")

                # Maskelerin orijinal decimal değerlerini de dosyaya ekliyoruz
                xml_lines.append(f"\t\t\t<m_supportedQualityMask> {q_mask} </m_supportedQualityMask>")
                xml_lines.append(f"\t\t\t<m_supportedPassMask> {p_mask} </m_supportedPassMask>")
                xml_lines.append(f"\t\t\t<m_supportedSniperPassMask> {s_mask} </m_supportedSniperPassMask>")
                # -----------------------------
                
                xml_lines.append(f"\t\t\t<f_fadeInOffsetFrom> {get_f(0x480):.6f} </f_fadeInOffsetFrom>")
                xml_lines.append(f"\t\t\t<f_fadeInOffsetTo> {get_f(0x484):.6f} </f_fadeInOffsetTo>")
                xml_lines.append(f"\t\t\t<f_dir_length_max> {get_f(0x488):.6f} </f_dir_length_max>")
                xml_lines.append(f"\t\t\t<f_slopeFadeCoeff> {get_f(0x48C):.6f} </f_slopeFadeCoeff>")
                
                ypr_s = get_v3(0x410)
                ypr_sp = get_v3(0x41C)
                xml_lines.append(f"\t\t\t<particle_ex.YPR_start> {ypr_s[0]:.6f} {ypr_s[1]:.6f} {ypr_s[2]:.6f} </particle_ex.YPR_start>")
                xml_lines.append(f"\t\t\t<particle_ex.YPR_start_spread> {ypr_sp[0]:.6f} {ypr_sp[1]:.6f} {ypr_sp[2]:.6f} </particle_ex.YPR_start_spread>")
                xml_lines.append(f"\t\t\t<particle_ex.f_soft_factor> {get_f(0x428):.6f} </particle_ex.f_soft_factor>")
                xml_lines.append(f"\t\t\t<particle_ex.f_ground_height_offset> {get_f(0x42C):.6f} </particle_ex.f_ground_height_offset>")
                xml_lines.append(f"\t\t\t<particle_ex.deffered_color_mult> {get_f(0x43C):.6f} </particle_ex.deffered_color_mult>")

                pm = struct.unpack_from('<I', data, e_pos + 0x1C8)[0]
                xml_lines.append("\t\t\t<particle.dw_mode>")
                pm_flags = [
                    ("ps_particle_use_frames", 0x00000001), ("ps_particle_random_frame", 0x00000002),
                    ("ps_particle_local", 0x00000004), ("ps_particle_horizont", 0x00000008),
                    ("ps_particle_soft", 0x00000010), ("ps_particle_water_level", 0x00000020),
                    ("ps_particle_stop_on_last_frame", 0x00000040), ("ps_particle_do_not_blend", 0x00000080),
                    ("ps_particle_use_direction_for_angle", 0x00000100), ("ps_element_directional", 0x04000000),
                    ("ps_element_speed_oriented", 0x08000000)
                ]
                for f_name, f_val in pm_flags:
                    xml_lines.append(f"\t\t\t\t<{f_name}> {1 if (pm & f_val) else 0} </{f_name}>")
                xml_lines.append("\t\t\t</particle.dw_mode>")

                p_ext_inv = struct.unpack_from('<I', data, e_pos + 0x1C0)[0]
                xml_lines.append(f"\t\t\t<particle.dw_mode_Ext_inv> {p_ext_inv} </particle.dw_mode_Ext_inv>")
                
                xml_lines.append(f"\t\t\t<particle.base.f_life_min> {get_f(0x100):.6f} </particle.base.f_life_min>")
                xml_lines.append(f"\t\t\t<particle.base.f_life_max> {get_f(0x104):.6f} </particle.base.f_life_max>")
                xml_lines.append(f"\t\t\t<particle.base.f_delay_min> {get_f(0x108):.6f} </particle.base.f_delay_min>")
                xml_lines.append(f"\t\t\t<particle.base.f_delay_max> {get_f(0x10C):.6f} </particle.base.f_delay_max>")
                
                p_sp = get_v3(0x110)
                xml_lines.append(f"\t\t\t<particle.base.fa_start_pos> {p_sp[0]:.6f} {p_sp[1]:.6f} {p_sp[2]:.6f} </particle.base.fa_start_pos>")
                
                p_type = struct.unpack_from('<I', data, e_pos + 0x11C)[0]
                xml_lines.append(f"\t\t\t<particle.ui_particle_Type> {p_type} </particle.ui_particle_Type>")
                xml_lines.append(f"\t\t\t<particle.f_particle_size> {get_f(0x1A0):.6f} </particle.f_particle_size>")
                xml_lines.append(f"\t\t\t<particle.f_particle_size_max> {get_f(0x1A4):.6f} </particle.f_particle_size_max>")
                xml_lines.append(f"\t\t\t<particle.f_part_speed_module> {get_f(0x1A8):.6f} </particle.f_part_speed_module>")
                xml_lines.append(f"\t\t\t<particle.f_part_speed_module_max> {get_f(0x1AC):.6f} </particle.f_part_speed_module_max>")
                xml_lines.append(f"\t\t\t<particle.UV_set.left> {get_f(0x1B4):.6f} </particle.UV_set.left>")
                xml_lines.append(f"\t\t\t<particle.UV_set.up> {get_f(0x1B0):.6f} </particle.UV_set.up>")
                xml_lines.append(f"\t\t\t<particle.UV_set.right> {get_f(0x1BC):.6f} </particle.UV_set.right>")
                xml_lines.append(f"\t\t\t<particle.UV_set.down> {get_f(0x1B8):.6f} </particle.UV_set.down>")
                
                p_div_u = struct.unpack_from('<i', data, e_pos + 0x1CC)[0]
                p_div_v = struct.unpack_from('<i', data, e_pos + 0x1D0)[0]
                xml_lines.append(f"\t\t\t<particle.i_frame_div_U> {p_div_u} </particle.i_frame_div_U>")
                xml_lines.append(f"\t\t\t<particle.i_frame_div_V> {p_div_v} </particle.i_frame_div_V>")
                
                xml_lines.append(f"\t\t\t<particle.f_fps> {get_f(0x1D4):.6f} </particle.f_fps>")
                xml_lines.append(f"\t\t\t<particle.f_dir_length> {get_f(0x1D8):.6f} </particle.f_dir_length>")
                xml_lines.append(f"\t\t\t<particle.f_K_gravity> {get_f(0x1C4):.6f} </particle.f_K_gravity>")
                xml_lines.append(f"\t\t\t<particle.f_K_gravity_max> {get_f(0x1DC):.6f} </particle.f_K_gravity_max>")
                xml_lines.append(f"\t\t\t<particle.f_YAW_min> {get_f(0x1E0):.6f} </particle.f_YAW_min>")
                xml_lines.append(f"\t\t\t<particle.f_YAW_max> {get_f(0x1E4):.6f} </particle.f_YAW_max>")
                xml_lines.append(f"\t\t\t<particle.f_PITCH_min> {get_f(0x1E8):.6f} </particle.f_PITCH_min>")
                xml_lines.append(f"\t\t\t<particle.f_PITCH_max> {get_f(0x1EC):.6f} </particle.f_PITCH_max>")
                xml_lines.append(f"\t\t\t<particle.f_ROLL_min> {get_f(0x1F0):.6f} </particle.f_ROLL_min>")
                xml_lines.append(f"\t\t\t<particle.f_ROLL_max> {get_f(0x1F4):.6f} </particle.f_ROLL_max>")
                xml_lines.append(f"\t\t\t<particle.f_speed_sensor> {get_f(0x1F8):.6f} </particle.f_speed_sensor>")
                xml_lines.append(f"\t\t\t<particle.f_z_offset> {get_f(0x1FC):.6f} </particle.f_z_offset>")
                
                p_tex = read_string(data, e_pos + 0x120, 128)
                if p_tex: 
                    xml_lines.append(f"\t\t\t<particle.ch_fn_texture> {p_tex} </particle.ch_fn_texture>")
                else:
                    xml_lines.append("\t\t\t<particle.ch_fn_texture/>")
                
                p_shader = read_string(data, e_pos + 0x200, 128)
                if p_shader: xml_lines.append(f"\t\t\t<particle.ch_fn_Shader> {p_shader} </particle.ch_fn_Shader>")

                xml_lines.append(f"\t\t\t<lighting_params.f_diffuse_light_multiplier> {get_f(0x440):.6f} </lighting_params.f_diffuse_light_multiplier>")
                xml_lines.append(f"\t\t\t<lighting_params.f_indirect_light_multiplier> {get_f(0x444):.6f} </lighting_params.f_indirect_light_multiplier>")
                xml_lines.append(f"\t\t\t<lighting_params.f_scattered_light_multiplier> {get_f(0x448):.6f} </lighting_params.f_scattered_light_multiplier>")
                xml_lines.append(f"\t\t\t<lighting_params.f_constant_scattered_light_ammount> {get_f(0x44C):.6f} </lighting_params.f_constant_scattered_light_ammount>")
                xml_lines.append(f"\t\t\t<lighting_params.f_self_shadow_power> {get_f(0x450):.6f} </lighting_params.f_self_shadow_power>")
                xml_lines.append(f"\t\t\t<lighting_params.f_halo_alpha_threshold> {get_f(0x454):.6f} </lighting_params.f_halo_alpha_threshold>")
                xml_lines.append(f"\t\t\t<lighting_params.f_halo_multiplier> {get_f(0x458):.6f} </lighting_params.f_halo_multiplier>")
                xml_lines.append(f"\t\t\t<lighting_params.f_halo_shadow_power> {get_f(0x45C):.6f} </lighting_params.f_halo_shadow_power>")
                xml_lines.append(f"\t\t\t<lighting_params.f_halo_fade_power> {get_f(0x460):.6f} </lighting_params.f_halo_fade_power>")
                xml_lines.append(f"\t\t\t<lighting_params.f_self_illum> {get_f(0x464):.6f} </lighting_params.f_self_illum>")
                xml_lines.append(f"\t\t\t<lighting_params.f_normal_generation_offset> {get_f(0x468):.6f} </lighting_params.f_normal_generation_offset>")
                xml_lines.append(f"\t\t\t<lighting_params.f_tessellation_factor> {get_f(0x46C):.6f} </lighting_params.f_tessellation_factor>")

                xml_lines.append("\t\t</emitter>")
                e_pos += e_size

            current_offset += lod_size 
            xml_lines.append("\t</lod>")
        xml_lines.append("</root>")

        output_filepath = os.path.join(output_dir, filename.replace('.vfxbin', '.vfx'))
        with open(output_filepath, 'w', encoding='utf-8') as out_f:
            out_f.write("\n".join(xml_lines))

    print(f"\n--- İŞLEM TAMAMLANDI ---")

def unpack_single_vfxbin(filepath, output_filepath=None):
    """Blender'dan tek bir dosya seçildiğinde çalışacak fonksiyon"""
    if not output_filepath:
        output_filepath = filepath.replace('.vfxbin', '.vfx')
        
    with open(filepath, 'rb') as f:
        data = f.read()

    if len(data) < 80 or data[0:4] != b'\xEC\x03\x00\x00':
        raise ValueError("Geçersiz vfxbin dosyası veya hibrit/eski sürüm header.")
    
    input_dir = os.path.dirname(filepath)
    temp_out_dir = os.path.dirname(output_filepath)
    
    # Asıl unpacker'ı çağır
    unpack_vfxbin_files(input_dir, temp_out_dir)
    return output_filepath