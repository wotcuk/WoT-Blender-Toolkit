# -*- coding: utf-8 -*-
import bpy
import os
import struct
import traceback
from pathlib import Path
from mathutils import Vector, Quaternion, Matrix
try:
    from .import_bw_primitives_textured import load_bw_primitive_textured
    from .file_finder import WoTFileFinder
except ImportError:
    load_bw_primitive_textured = None
    WoTFileFinder = None
def auto_import_model(model_internal_path, anim_base_dir, finder):
    """
    Finder kullanarak sadece .model dosyasını bulur. 
    Alt dosyaları (visual/primitives) bulma işini textured importer'a bırakır.
    """
    if not model_internal_path or not load_bw_primitive_textured or not finder:
        return None
    found_model_path = finder.find(
        target_file=model_internal_path, 
        base_dir=anim_base_dir, 
        internal_path=model_internal_path
    )

    if not found_model_path:
        print(f"[LOADER] Model path reference found but file not located: {model_internal_path}")
        return None
    print(f"[LOADER] Importing referenced model: {found_model_path}")
    col = bpy.context.view_layer.active_layer_collection.collection
    pre_import_objs = set(bpy.data.objects.keys())
    context = {'last_pkg': finder.last_found_pkg}
    load_bw_primitive_textured(col, Path(found_model_path), import_empty=True, finder=finder, context=context)
    post_import_objs = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in pre_import_objs]
    for obj in post_import_objs:
        if obj.type == 'ARMATURE':
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            return obj
            
    return None
def apply_animation_to_armature(anim_name, duration, tracks, model_path, anim_base_dir, finder):
    obj = None
    if model_path:
        obj = auto_import_model(model_path, anim_base_dir, finder)
        if obj:
            print(f"[LOADER] Successfully imported and targeted: {obj.name}")
    if not obj:
        active_obj = bpy.context.active_object
        if active_obj and active_obj.type == 'ARMATURE':
            obj = active_obj
            print(f"[LOADER] Using CURRENTLY SELECTED armature: {obj.name}")
    if not obj and model_path:
        model_filename = os.path.basename(model_path).split('.')[0]
        for o in bpy.data.objects:
            if o.type == 'ARMATURE' and model_filename.lower() in o.name.lower():
                obj = o
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                print(f"[LOADER] Found matching armature in scene: {obj.name}")
                break
    if not obj:
        for o in bpy.data.objects:
            if o.type == 'ARMATURE':
                obj = o
                print(f"[LOADER] Fallback: Using the first armature in scene: {obj.name}")
                break

    if not obj:
        print("[ERROR] Valid Armature not found for animation.")
        return False
    if not obj.animation_data:
        obj.animation_data_create()
    action = bpy.data.actions.new(name=anim_name)
    obj.animation_data.action = action
    fps = bpy.context.scene.render.fps
    C_CONV = Matrix([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
    for bone_name, data in tracks.items():
        if bone_name not in obj.pose.bones:
            continue 
        pbone = obj.pose.bones[bone_name]
        pbone.rotation_mode = 'QUATERNION'
        if pbone.parent:
            rest_local = pbone.parent.bone.matrix_local.inverted() @ pbone.bone.matrix_local
        else:
            rest_local = pbone.bone.matrix_local
        rest_local_inv = rest_local.inverted()
        track_frames = sorted(set([int(t * fps) for t, _ in data['pos']] + 
                                  [int(t * fps) for t, _ in data['rot']] +
                                  [int(t * fps) for t, _ in data['scale']] + [0]))
        for frame in track_frames:
            time_val = frame / fps
            def find_val(track, t, default):
                if not track: return default
                res = track[0][1]
                for kt, kv in track:
                    if kt <= t + 0.001: res = kv
                    else: break
                return res
            pos = find_val(data['pos'], time_val, (0,0,0))
            rot = find_val(data['rot'], time_val, (0,0,0,1)) 
            scl = find_val(data['scale'], time_val, (1,1,1))
            quat = Quaternion((rot[3], rot[0], rot[1], rot[2]))
            quat.normalize()
            mat_loc = Matrix.Translation(pos) @ quat.to_matrix().to_4x4() @ Matrix.Diagonal((scl[0], scl[1], scl[2], 1.0))
            mat_final = C_CONV @ mat_loc @ C_CONV
            pbone.matrix_basis = rest_local_inv @ mat_final
            pbone.keyframe_insert(data_path="location", frame=frame)
            pbone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            pbone.keyframe_insert(data_path="scale", frame=frame)
    for fcurve in action.fcurves:
        for kp in fcurve.keyframe_points:
            kp.interpolation = 'LINEAR'
    bpy.context.scene.frame_end = int(duration * fps)
    print(f"[SUCCESS] Animation applied to {obj.name}")
    return True
def parse_processed_animation(filepath):
    finder = WoTFileFinder()
    anim_base_dir = os.path.dirname(filepath)
    with open(filepath, "rb") as f:
        f.seek(27)
        path_len = struct.unpack('<I', f.read(4))[0]
        model_path = f.read(path_len).decode('utf-8', errors='ignore') if path_len > 0 else ""
        bone_count = struct.unpack('<I', f.read(4))[0]
        bone_names = []
        for _ in range(bone_count):
            n_len = struct.unpack('<I', f.read(4))[0]
            bone_names.append(f.read(n_len).decode('utf-8', errors='ignore'))
        flag = struct.unpack('<I', f.read(4))[0]
        f.read(4) 
        tracks = {n: {'pos': [], 'rot': [], 'scale': []} for n in bone_names}
        max_duration = 0.0
        def deq(v, mi, ma): return mi + (v / 65535.0) * (ma - mi)
        # --- FLAG 00 / 02 / 01 / 03 
        if flag == 0:
            frame_count, bone_count_check, anim_fps = struct.unpack('<IIf', f.read(12))
            max_duration = (frame_count - 1) / anim_fps if anim_fps > 0 else 0.0
            for f_idx in range(frame_count):
                time_val = f_idx / anim_fps if anim_fps > 0 else 0.0
                for b_idx in range(bone_count_check):
                    raw = struct.unpack('<10f', f.read(40))
                    if b_idx < bone_count:
                        bn = bone_names[b_idx]
                        tracks[bn]['pos'].append((time_val, (raw[0], raw[1], raw[2])))
                        tracks[bn]['rot'].append((time_val, (raw[3], raw[4], raw[5], raw[6])))
                        tracks[bn]['scale'].append((time_val, (raw[7], raw[8], raw[9])))
        elif flag == 2:
            frame_count, bone_count_check, anim_fps = struct.unpack('<IIf', f.read(12))
            bounds = struct.unpack('<20f', f.read(80))
            max_duration = (frame_count - 1) / anim_fps if anim_fps > 0 else 0.0
            for f_idx in range(frame_count):
                time_val = f_idx / anim_fps if anim_fps > 0 else 0.0
                for b_idx in range(bone_count_check):
                    r = struct.unpack('<10H', f.read(20))
                    if b_idx < bone_count:
                        bn = bone_names[b_idx]
                        pos = (deq(r[0], bounds[0], bounds[1]), deq(r[1], bounds[2], bounds[3]), deq(r[2], bounds[4], bounds[5]))
                        rot = (deq(r[3], bounds[12], bounds[13]), deq(r[4], bounds[14], bounds[15]), deq(r[5], bounds[16], bounds[17]), deq(r[6], bounds[18], bounds[19]))
                        scl = (deq(r[7], bounds[6], bounds[7]), deq(r[8], bounds[8], bounds[9]), deq(r[9], bounds[10], bounds[11]))
                        tracks[bn]['pos'].append((time_val, pos))
                        tracks[bn]['rot'].append((time_val, rot))
                        tracks[bn]['scale'].append((time_val, scl))
        elif flag in [1, 3]:
            start = f.tell()
            f.seek(start + 16); off1 = struct.unpack('<I', f.read(4))[0]
            f.seek(start + 24); off2 = struct.unpack('<I', f.read(4))[0]
            f.seek(start + 28); b = struct.unpack('<20f', f.read(80)) if flag == 3 else [0.0]*20
            f.seek(start + 28 + (80 if flag == 3 else 0))
            t1c, t1o = struct.unpack('<I', f.read(4))[0], []
            t1o = [struct.unpack('<I', f.read(4))[0] for _ in range(t1c)]
            t2c, t2o = struct.unpack('<I', f.read(4))[0], []
            t2o = [struct.unpack('<I', f.read(4))[0] for _ in range(t2c)]
            for o in [start+off1+x for x in t1o]:
                f.seek(o); tid, bidx, k = struct.unpack('<BII', f.read(9))
                if bidx >= bone_count: continue
                ts = struct.unpack(f'<{k}f', f.read(k*4))
                nc = 4 if tid==1 else 3
                raw = struct.unpack(f'<{k*nc}{"f" if flag==1 else "H"}', f.read(k*nc*(4 if flag==1 else 2)))
                for i in range(k):
                    if ts[i] > max_duration: max_duration = ts[i]
                    c = raw[i*nc : (i+1)*nc]
                    if flag == 3:
                        if tid == 0: val = (deq(c[0],b[0],b[1]), deq(c[1],b[2],b[3]), deq(c[2],b[4],b[5]))
                        elif tid == 1: val = (deq(c[0],b[12],b[13]), deq(c[1],b[14],b[15]), deq(c[2],b[16],b[17]), deq(c[3],b[18],b[19]))
                        else: val = (deq(c[0],b[6],b[7]), deq(c[1],b[8],b[9]), deq(c[2],b[10],b[11]))
                    else: val = c
                    tracks[bone_names[bidx]][['pos','rot','scale'][tid]].append((ts[i], val))
            for o in [start+off2+x for x in t2o]:
                f.seek(o); tid, bidx = struct.unpack('<BI', f.read(5))
                if bidx >= bone_count: continue
                nc = 4 if tid==1 else 3
                c = struct.unpack(f'<{nc}{"f" if flag==1 else "H"}', f.read(nc*(4 if flag==1 else 2)))
                if flag == 3:
                    if tid == 0: val = (deq(c[0],b[0],b[1]), deq(c[1],b[2],b[3]), deq(c[2],b[4],b[5]))
                    elif tid == 1: val = (deq(c[0],b[12],b[13]), deq(c[1],b[14],b[15]), deq(c[2],b[16],b[17]), deq(c[3],b[18],b[19]))
                    else: val = (deq(c[0],b[6],b[7]), deq(c[1],b[8],b[9]), deq(c[2],b[10],b[11]))
                else: val = c
                tracks[bone_names[bidx]][['pos','rot','scale'][tid]].append((0.0, val))
        apply_animation_to_armature(os.path.basename(filepath), max_duration, tracks, model_path, anim_base_dir, finder)
def load_bw_animation(filepath):
    try:
        if filepath.lower().endswith('.anim_processed'):
            parse_processed_animation(filepath)
    except Exception as e:
        print(f"[LOADER] Critical Error: {e}")
        traceback.print_exc()