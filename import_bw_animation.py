# -*- coding: utf-8 -*-
import bpy
import os
import struct
from mathutils import Vector, Quaternion, Matrix

def get_value_at_time(track_list, time_val, default):
    """Finds the data at a specific time, uses the previous one (step) if not exact"""
    if not track_list: return default
    best_val = track_list[0][1]
    for t, v in track_list:
        if t <= time_val + 0.001:
            best_val = v
        else:
            break
    return best_val

def apply_animation_to_armature(anim_name, duration, tracks):
    obj = bpy.context.active_object
    if not obj or obj.type != 'ARMATURE':
        print("[ERROR] An ARMATURE must be selected in the scene to apply the animation!")
        return False
        
    if not obj.animation_data:
        obj.animation_data_create()
    action = bpy.data.actions.new(name=anim_name)
    obj.animation_data.action = action
    
    fps = bpy.context.scene.render.fps
    C = Matrix([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])

    for bone_name, data in tracks.items():
        if bone_name not in obj.pose.bones:
            continue 
            
        pbone = obj.pose.bones[bone_name]
        pbone.rotation_mode = 'QUATERNION'
        
        # Bone Rest Matrix (relative to Parent)
        if pbone.parent:
            rest_local = pbone.parent.bone.matrix_local.inverted() @ pbone.bone.matrix_local
        else:
            rest_local = pbone.bone.matrix_local
            
        rest_local_inv = rest_local.inverted()
        
        all_frames = sorted(set(
            [int(t * fps) for t, _ in data['pos']] + 
            [int(t * fps) for t, _ in data['rot']] +
            [int(t * fps) for t, _ in data['scale']]
        ))

        for frame in all_frames:
            time_val = frame / fps
            
            pos_val = get_value_at_time(data['pos'], time_val, (0,0,0))
            rot_val = get_value_at_time(data['rot'], time_val, (0,0,0,1)) 
            scl_val = get_value_at_time(data['scale'], time_val, (1,1,1))

            rx, ry, rz, rw = rot_val
            
            # Passing to Blender in W, X, Y, Z order!
            mat_bw_loc = Matrix.Translation(pos_val) @ Quaternion((rw, rx, ry, rz)).to_matrix().to_4x4()
            mat_bw_loc = mat_bw_loc @ Matrix.Diagonal((scl_val[0], scl_val[1], scl_val[2], 1.0))
            
            # Y-Up -> Z-Up Conversion
            mat_z_loc = C @ mat_bw_loc @ C

            # Convert New Animation Location to Offset (Matrix Basis)
            pbone.matrix_basis = rest_local_inv @ mat_z_loc
            
            pbone.keyframe_insert(data_path="location", frame=frame)
            pbone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            pbone.keyframe_insert(data_path="scale", frame=frame)
            
    total_frames = int(duration * fps)
    if total_frames > 0:
        bpy.context.scene.frame_start = 0
        bpy.context.scene.frame_end = total_frames
        
    print("[SUCCESS] Animation successfully applied to the armature!")
    return True

def parse_raw_animation(f, filepath):
    """ Parses .animation files (Block structured) and collects data """
    total_time = struct.unpack('<f', f.read(4))[0]
    
    len1 = struct.unpack('<I', f.read(4))[0]
    name1 = f.read(len1).decode('utf-8', errors='ignore')
    
    len2 = struct.unpack('<I', f.read(4))[0]
    name2 = f.read(len2).decode('utf-8', errors='ignore')
    
    track_count = struct.unpack('<I', f.read(4))[0]
    tracks = {}
    
    for i in range(track_count):
        flag = struct.unpack('<I', f.read(4))[0]
        bone_name_len = struct.unpack('<I', f.read(4))[0]
        bone_name = f.read(bone_name_len).decode('utf-8', errors='ignore')
        
        tracks[bone_name] = {'scale': [], 'pos': [], 'rot': []}
        
        scale_keys_count = struct.unpack('<I', f.read(4))[0]
        for _ in range(scale_keys_count):
            s_time, sx, sy, sz = struct.unpack('<4f', f.read(16))
            tracks[bone_name]['scale'].append((s_time, (sx, sy, sz)))
            
        pos_keys_count = struct.unpack('<I', f.read(4))[0]
        for _ in range(pos_keys_count):
            p_time, px, py, pz = struct.unpack('<4f', f.read(16))
            tracks[bone_name]['pos'].append((p_time, (px, py, pz)))
            
        rot_keys_count = struct.unpack('<I', f.read(4))[0]
        for _ in range(rot_keys_count):
            r_time, rx, ry, rz, rw = struct.unpack('<5f', f.read(20))
            tracks[bone_name]['rot'].append((r_time, (rx, ry, rz, rw)))
            
        extra_c1 = struct.unpack('<I', f.read(4))[0]
        extra_c2 = struct.unpack('<I', f.read(4))[0]
        extra_c3 = struct.unpack('<I', f.read(4))[0]

    apply_animation_to_armature(name1, total_time, tracks)

def parse_processed_animation(f, filepath):
    """ BigWorld .anim_processed - Smart Mathematical Solver """
    print("\n[INFO] Format: PROCESSED (.anim_processed) - Stable Solver Active")
    
    f.seek(0)
    f.read(31)

    # Bone Names
    bone_count = struct.unpack('<I', f.read(4))[0]
    bone_names = []
    for i in range(bone_count):
        name_len = struct.unpack('<I', f.read(4))[0]
        bone_name = f.read(name_len).decode('utf-8', errors='ignore')
        bone_names.append(bone_name)

    # Flag
    struct.unpack('<I', f.read(4))[0]
    struct.unpack('<I', f.read(4))[0]

    block_start = f.tell()

    # Offsets
    f.seek(block_start + 16)
    base_offset_1 = struct.unpack('<I', f.read(4))[0]
    f.seek(block_start + 24)
    base_offset_2 = struct.unpack('<I', f.read(4))[0]

    f.seek(block_start + 28)
    type1_count = struct.unpack('<I', f.read(4))[0]
    type1_offsets = [struct.unpack('<I', f.read(4))[0] for _ in range(type1_count)]

    type2_count = struct.unpack('<I', f.read(4))[0]
    type2_offsets = [struct.unpack('<I', f.read(4))[0] for _ in range(type2_count)]

    type1_abs_offsets = [block_start + base_offset_1 + off for off in type1_offsets]
    type2_abs_offsets = [block_start + base_offset_2 + off for off in type2_offsets]

    # Blender tracks dictionary
    tracks = {name: {'pos': [], 'rot': [], 'scale': []} for name in bone_names}
    type_keys = {0: 'pos', 1: 'rot', 2: 'scale'}
    comp_counts = {0: 3, 1: 4, 2: 3}
    max_time = 0.0

    # TYPE 1: Dynamic Packets
    for abs_offset in type1_abs_offsets:
        f.seek(abs_offset)
        header = f.read(9)
        if len(header) < 9: continue
        
        type_id, bone_idx, key_count = struct.unpack('<BII', header)
        if bone_idx >= bone_count: continue
        
        bone_name = bone_names[bone_idx]
        track_key = type_keys.get(type_id)
        if not track_key: continue
        
        num_comps = comp_counts[type_id]
        times = struct.unpack(f'<{key_count}f', f.read(4 * key_count))
        
        total_floats = key_count * num_comps
        values = struct.unpack(f'<{total_floats}f', f.read(4 * total_floats))
        
        for k in range(key_count):
            t = times[k]
            if t > max_time: max_time = t
            val_tuple = tuple(values[k*num_comps : (k+1)*num_comps])
            tracks[bone_name][track_key].append((t, val_tuple))

    # TYPE 2: Static Packets
    for abs_offset in type2_abs_offsets:
        f.seek(abs_offset)
        header = f.read(5)
        if len(header) < 5: continue
        
        type_id, bone_idx = struct.unpack('<BI', header)
        if bone_idx >= bone_count: continue
        
        bone_name = bone_names[bone_idx]
        track_key = type_keys.get(type_id)
        if not track_key: continue
        
        num_comps = comp_counts[type_id]
        values = struct.unpack(f'<{num_comps}f', f.read(4 * num_comps))
        tracks[bone_name][track_key].append((0.0, tuple(values)))

    # Assign Identity to missing channels
    for bone in bone_names:
        if not tracks[bone]['pos']: tracks[bone]['pos'].append((0.0, (0.0, 0.0, 0.0)))
        if not tracks[bone]['rot']: tracks[bone]['rot'].append((0.0, (0.0, 0.0, 0.0, 1.0)))
        if not tracks[bone]['scale']: tracks[bone]['scale'].append((0.0, (1.0, 1.0, 1.0)))

    anim_name = os.path.splitext(os.path.basename(filepath))[0]
    if max_time <= 0.0: max_time = 1.0

    print(f"[INFO] Animation (Processed) collected (Duration: {max_time:.2f}s), sending to Armature...")
    apply_animation_to_armature(anim_name, max_time, tracks)

def load_bw_animation(filepath):
    print(f"\n=== ANIMATION IMPORT: {os.path.basename(filepath)} ===")
    
    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        return False

    try:
        with open(filepath, "rb") as f:
            if filepath.lower().endswith('.anim_processed'):
                parse_processed_animation(f, filepath)
            else:
                parse_raw_animation(f, filepath)
                
        print("=== ANIMATION IMPORT SUCCESSFUL ===\n")
        return True

    except Exception as e:
        print(f"[CRITICAL ERROR] Crashed while reading animation: {e}")
        import traceback
        traceback.print_exc()
        return False