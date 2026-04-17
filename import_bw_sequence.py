import bpy
import os
import math
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from mathutils import Vector, Euler, Quaternion

from .common.XmlUnpacker import XmlUnpacker
from .file_finder import WoTFileFinder
from .import_bw_primitives_textured import load_bw_primitive_textured

def parse_bw_vector3(val_str):
    parts = val_str.strip().split()
    if len(parts) >= 3:
        return Vector((float(parts[0]), float(parts[2]), float(parts[1])))
    return Vector((0.0, 0.0, 0.0))

def parse_bw_vector4(val_str):
    parts = val_str.strip().split()
    return [float(p) for p in parts]

def parse_bw_quaternion(val_str):
    parts = val_str.strip().split()
    if len(parts) >= 4:
        x, y, z, w = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
        return Quaternion((w, x, z, y))
    return Quaternion((1.0, 0.0, 0.0, 0.0))

class ImportReport:
    def __init__(self, seq_name):
        self.seq_name = seq_name
        self.success = []
        self.failed = []
        self.warnings = []

    def write_to_blender(self):
        text_name = f"SeqReport_{self.seq_name}.txt"
        if text_name in bpy.data.texts:
            txt = bpy.data.texts[text_name]
            txt.clear()
        else:
            txt = bpy.data.texts.new(text_name)
        
        txt.write(f"=== {self.seq_name} DETAYLI IMPORT RAPORU ===\n\n")
        txt.write("--- BASARILI YUKLENENLER ---\n")
        for s in self.success: txt.write(f"[+] {s}\n")
        txt.write("\n--- HATALI / BULUNAMAYAN DOSYALAR ---\n")
        for f in self.failed: txt.write(f"[-] {f}\n")
        txt.write("\n--- UYARILAR / DESTEKLENMEYENLER ---\n")
        for w in self.warnings: txt.write(f"[!] {w}\n")

def load_bw_sequence(filepath):
    seq_name = os.path.basename(filepath).split('.')[0]
    report = ImportReport(seq_name)
    fps = bpy.context.scene.render.fps

    try:
        try:
            tree = ET.parse(filepath)
            xml_root = tree.getroot()
        except ET.ParseError:
            unpacker = XmlUnpacker()
            unpacker.read(filepath)
            xml_root = ET.fromstring(unpacker.xml_string)

        seq_dir = os.path.dirname(filepath)
        finder = WoTFileFinder()
        context_dict = {'last_pkg': None}

        main_empty = bpy.data.objects.new(f"SEQ_{seq_name}", None)
        main_empty.empty_display_type = 'ARROWS'
        main_empty.empty_display_size = 2.0
        bpy.context.collection.objects.link(main_empty)

        created_objs = {}

        for seq_obj in xml_root.findall('sequenceObject'):
            obj_name = (seq_obj.findtext('name') or "Unnamed").strip()
            obj_type = (seq_obj.findtext('type') or "").strip().lower()
            resource = (seq_obj.findtext('resource') or "").strip()
            
            target_ob = None

            if obj_type == 'model' and resource:
                full_model_path = finder.find(resource, seq_dir, resource)
                if full_model_path:
                    pre_import_objs = set(bpy.data.objects[:])
                    try:
                        load_bw_primitive_textured(
                            col=bpy.context.collection, 
                            model_filepath=Path(full_model_path), 
                            import_empty=True, finder=finder, context=context_dict
                        )
                        report.success.append(f"Model: {obj_name}")
                    except Exception as e:
                        report.failed.append(f"Model Import Hatasi: {obj_name}")
                    
                    new_objs = set(bpy.data.objects[:]) - pre_import_objs
                    roots = [o for o in new_objs if o.parent is None]
                    if roots:
                        target_ob = roots[0]
                        target_ob.name = obj_name
                    elif new_objs:
                        target_ob = list(new_objs)[0]
                        target_ob.name = obj_name
                else:
                    report.failed.append(f"Bulunamadi: {resource}")

            elif obj_type == 'light':
                light_type_str = (seq_obj.findtext('lightType') or "omnilight").strip().lower()
                b_light_type = 'SPOT' if light_type_str == 'spotlight' else 'POINT'
                
                light_data = bpy.data.lights.new(name=f"LData_{obj_name}", type=b_light_type)
                target_ob = bpy.data.objects.new(name=obj_name, object_data=light_data)
                bpy.context.collection.objects.link(target_ob)
                report.success.append(f"Isik ({b_light_type}): {obj_name}")

            if target_ob is None:
                target_ob = bpy.data.objects.new(obj_name, None)
                if obj_type == 'particle':
                    target_ob.empty_display_type = 'SPHERE'
                    target_ob["bw_particle"] = resource
                elif obj_type == 'sound':
                    target_ob.empty_display_type = 'CONE'
                else:
                    target_ob.empty_display_type = 'PLAIN_AXES'
                target_ob.empty_display_size = 0.5
                bpy.context.collection.objects.link(target_ob)

            created_objs[obj_name] = target_ob

            for track in seq_obj.findall('track'):
                track_name = (track.findtext('name') or "").strip()
                track_type = (track.findtext('type') or "").strip().lower()
                identifier = (track.findtext('identifier') or "").strip()
                prop = (track.findtext('property') or "").strip()

                for frame in track.findall('frame'):
                    start_time = float(frame.findtext('startTime') or "0.0")
                    val_str = (frame.findtext('value') or "").strip()
                    if not val_str: continue

                    b_frame = int(round(start_time * fps))

                    try:
                        if track_name == 'position':
                            target_ob.location = parse_bw_vector3(val_str)
                            target_ob.keyframe_insert(data_path="location", frame=b_frame)

                        elif track_name == 'rotationEuler':
                            target_ob.rotation_mode = 'XYZ'
                            rot = parse_bw_vector3(val_str)
                            pitch_offset = 90 if target_ob.type == 'LIGHT' else 0
                            
                            target_ob.rotation_euler = Euler((
                                math.radians(rot.x + pitch_offset), 
                                math.radians(rot.y), 
                                math.radians(rot.z)
                            ), 'XYZ')
                            
                            target_ob.keyframe_insert(data_path="rotation_euler", frame=b_frame)

                        elif track_name == 'rotation' and track_type == 'quaternion':
                            target_ob.rotation_mode = 'QUATERNION'
                            target_ob.rotation_quaternion = parse_bw_quaternion(val_str)
                            target_ob.keyframe_insert(data_path="rotation_quaternion", frame=b_frame)

                        elif track_name == 'scale':
                            parts = val_str.split()
                            if len(parts) >= 3:
                                target_ob.scale = Vector((float(parts[0]), float(parts[2]), float(parts[1])))
                                target_ob.keyframe_insert(data_path="scale", frame=b_frame)
                        
                        elif target_ob.type == 'LIGHT':
                            if track_name == 'multiplier':
                                target_ob.data.energy = float(val_str) * 10.0
                                target_ob.data.keyframe_insert(data_path="energy", frame=b_frame)
                            elif track_name == 'color':
                                col = parse_bw_vector4(val_str)
                                target_ob.data.color = (col[0]/255.0 if col[0]>1 else col[0], col[1]/255.0 if col[1]>1 else col[1], col[2]/255.0 if col[2]>1 else col[2])
                                target_ob.data.keyframe_insert(data_path="color", frame=b_frame)
                            elif track_name == 'coneAngle' and target_ob.data.type == 'SPOT':
                                target_ob.data.spot_size = math.radians(float(val_str))
                                target_ob.data.keyframe_insert(data_path="spot_size", frame=b_frame)
                            elif track_name == 'castShadow':
                                target_ob.data.use_shadow = (val_str.lower() == 'true')
                            elif track_name in ['outerRadius', 'innerRadius']:
                                target_ob.data[track_name] = float(val_str) 

                        else:
                            prop_key = f"{identifier}_{prop}" if (identifier and prop) else track_name
                            
                            if track_type in ['float', 'bool', 'rtpc_value']:
                                if val_str.lower() == 'true': val_float = 1.0
                                elif val_str.lower() == 'false': val_float = 0.0
                                else: val_float = float(val_str)
                                
                                target_ob[prop_key] = val_float
                                target_ob.keyframe_insert(data_path=f'["{prop_key}"]', frame=b_frame)
                            elif 'vector' in track_type:
                                target_ob[prop_key] = parse_bw_vector4(val_str)

                    except Exception as e:
                        report.warnings.append(f"Keyframe hatasi ({obj_name} -> {track_name}): {str(e)}")

        root_node = created_objs.get("Root") or created_objs.get("root")
        if root_node:
            root_node.parent = main_empty
            for obj in created_objs.values():
                if obj != root_node:
                    obj.parent = root_node
        else:
            for obj in created_objs.values():
                if obj.parent is None:
                    obj.parent = main_empty

        report.write_to_blender()
        return {"FINISHED"}

    except Exception as e:
        print(f"[WOT Sequence Error] {traceback.format_exc()}")
        return {"CANCELLED"}