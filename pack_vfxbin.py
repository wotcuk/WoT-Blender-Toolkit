import struct
import os
import xml.etree.ElementTree as ET

# Empty header to avoid byte shift. Original header can be added later as hex.
MANUAL_HEADER = b"" 

# Hardcoded footer block placed immediately after curves
LAYER_FOOTER = bytes.fromhex("E9 03 00 00 10 07 00 00 E4 05 00 00 E9 03 00 00 05 00 00 00 00 0C 00 00")
# Separator placed ONLY between effects
LAYER_SEPARATOR = bytes.fromhex("FF FF FF FF")

def pack_float(val):
    return struct.pack('<f', float(val))

def pack_int(val):
    return struct.pack('<I', int(float(val)))

def pack_byte(val):
    return struct.pack('<B', int(float(val)))

def pack_hex(val_str):
    clean_hex = val_str.replace(" ", "").strip()
    return bytes.fromhex(clean_hex)

def pack_string(val_str, total_length):
    str_bytes = val_str.encode('utf-8', 'ignore')
    if len(str_bytes) > total_length - 1:
        str_bytes = str_bytes[:total_length - 1]
    return str_bytes + b'\x00' * (total_length - len(str_bytes))

def determine_pack_type(tag_name):
    tag = tag_name.lower()
    if tag in ["cols", "rows", "emitter_type_or_size_z"]:
        return "int"
    elif tag in ["animation_mode", "flip_visual_180", "axis_orientation"]:
        return "byte"
    elif "ffff" in tag or "unknown_flag" in tag:
        return "hex"
    elif tag in ["texture_path", "shader_path", "mesh_path", "info_string"]:
        return "string"
    else:
        return "float"

def pack_xml_to_vfxbin(xml_filepath, output_filepath):
    print(f"\n[VFX Packer] Compilation started: {xml_filepath}")
    
    try:
        tree = ET.parse(xml_filepath)
        root = tree.getroot()
    except Exception as e:
        print(f"[VFX Packer] XML read error: {e}")
        return

    # =========================================================================
    # 1. GROUP FILES (Separate Main and Child Effects)
    # =========================================================================
    out_dir = os.path.dirname(output_filepath)
    if not out_dir: out_dir = "."
    
    file_groups = {} 
    
    for layer in root.findall("Layer"):
        is_child_elem = layer.find("Is_Child_Effect")
        child_file_elem = layer.find("Child_Source_File")
        
        is_child = (is_child_elem is not None and is_child_elem.text == "True")
        child_file = child_file_elem.text if child_file_elem is not None else "None"
        
        if is_child and child_file and child_file != "None":
            if child_file.lower().endswith(".vfx"):
                child_file = child_file[:-4] + ".vfxbin"
            target_path = os.path.join(out_dir, child_file)
        else:
            target_path = output_filepath
            
        if target_path not in file_groups:
            file_groups[target_path] = []
        file_groups[target_path].append(layer)


    # =========================================================================
    # 2. PACK EACH GROUP INTO ITS OWN FILE
    # =========================================================================
    for current_filepath, layers_in_file in file_groups.items():
        print(f"\n>>> Creating file: {os.path.basename(current_filepath)} ({len(layers_in_file)} layers)")
        
        file_header_bytes = b""
        
        first_layer = layers_in_file[0]
        unknowns = first_layer.find("Unknown_Parameters")
        if unknowns is not None:
            header_elem = unknowns.find("Header_Data")
            if header_elem is not None and header_elem.text:
                file_header_bytes = pack_hex(header_elem.text)
                
        final_binary = bytearray(file_header_bytes)
        
        for idx, layer in enumerate(layers_in_file):
            layer_name = layer.get("name", "Layer_0")
            print(f"  -> Packing Layer: {layer_name}")
            
            # Plane Name Block (64 Bytes)
            final_binary.extend(pack_string(layer_name, 64))
            
            # Magic Layer Starter
            final_binary.extend(b'\xE8\x03\x00\x00')
            
            # Blank Canvas up to 0x590
            layer_buffer = bytearray(0x590) 
            
            all_params = []
            
            known = layer.find("Known_Parameters")
            if known is not None:
                for child in known:
                    if len(list(child)) > 0:
                        for sub_child in child:
                            all_params.append(sub_child)
                    else:
                        all_params.append(child)
                        
            unknowns = layer.find("Unknown_Parameters")
            if unknowns is not None:
                for child in unknowns:
                    all_params.append(child)
                    
            for param in all_params:
                if param.tag == "Header_Data":
                    continue
                    
                offset_str = param.get("offset")
                
                # Smart Offset Reader
                if not offset_str and param.tag.startswith("Offset_"):
                    offset_str = param.tag.split("_")[1]
                    
                if not offset_str:
                    continue 
                    
                try:
                    offset_addr = int(offset_str, 16)
                except: continue
                    
                val_type = param.get("type")
                if not val_type:
                    val_type = determine_pack_type(param.tag)
                    
                val_text = param.text if param.text else ""
                
                try:
                    if val_type == "int":
                        packed_data = pack_int(val_text)
                    elif val_type == "byte":
                        packed_data = pack_byte(val_text)
                    elif val_type == "hex":
                        packed_data = pack_hex(val_text)
                    elif val_type == "string":
                        length = 64
                        if offset_addr == 0xC0 or offset_addr == 0x1A0: length = 128
                        elif offset_addr == 0x490: length = 256
                        packed_data = pack_string(val_text, length)
                    else:
                        packed_data = pack_float(val_text)
                        
                    layer_buffer[offset_addr : offset_addr + len(packed_data)] = packed_data
                except Exception as e:
                    print(f"Warning: Error packing {param.tag}! ({e})")
                    
            final_binary.extend(layer_buffer)
            
            # ==========================================
            # 3. DYNAMIC CURVE WRITING
            # ==========================================
            curves = layer.find("Curves")
            if curves is not None:
                scale_points = curves.find("Curve_Scale").findall("Point") if curves.find("Curve_Scale") is not None else []
                r_pts = curves.find("Curve_Color_R").findall("Point") if curves.find("Curve_Color_R") is not None else []
                g_pts = curves.find("Curve_Color_G").findall("Point") if curves.find("Curve_Color_G") is not None else []
                b_pts = curves.find("Curve_Color_B").findall("Point") if curves.find("Curve_Color_B") is not None else []
                a_pts = curves.find("Curve_Alpha_A").findall("Point") if curves.find("Curve_Alpha_A") is not None else []
                
                for p_idx in range(8):
                    if p_idx == 0:
                        pt_count = len(scale_points)
                        final_binary.extend(pack_int(pt_count))
                        final_binary.extend(b'PPPP')
                        if pt_count > 0:
                            for pt in scale_points:
                                final_binary.extend(pack_float(pt.get("time", 0.0)))
                            for pt in scale_points:
                                final_binary.extend(pack_float(pt.get("value", 0.0)))
                    
                    elif p_idx == 6:
                        pt_count = len(r_pts)
                        
                        final_binary.extend(pack_int(pt_count))
                        final_binary.extend(b'PPPP')
                        
                        if pt_count > 0:
                            # Step 1: Write Times once
                            for pt in r_pts:
                                final_binary.extend(pack_float(pt.get("time", 0.0)))
                            
                            # Step 2: Write Values as R, G, B, A
                            for i in range(pt_count):
                                final_binary.extend(pack_float(r_pts[i].get("value", 1.0)))
                                final_binary.extend(pack_float(g_pts[i].get("value", 1.0)))
                                final_binary.extend(pack_float(b_pts[i].get("value", 1.0)))
                                final_binary.extend(pack_float(a_pts[i].get("value", 1.0)))
                    else:
                        # Create 2-point (1.0) dummy for curves 1, 2, 3, 4, 5, 7
                        if p_idx in [1, 2, 3, 4, 5, 7]:
                            final_binary.extend(pack_int(2))
                            final_binary.extend(b'PPPP')
                            
                            # Times (0.0 and 1.0)
                            final_binary.extend(pack_float(0.0))
                            final_binary.extend(pack_float(1.0))
                            
                            # Values (1.0 and 1.0)
                            final_binary.extend(pack_float(1.0))
                            final_binary.extend(pack_float(1.0))
                        else:
                            # Other curves remain empty (0)
                            final_binary.extend(pack_int(0))
                            final_binary.extend(b'PPPP')
            
            # ==========================================
            # 4. EFFECT TRANSITION AND FOOTER
            # ==========================================
            final_binary.extend(LAYER_FOOTER)
            
            # Add separator if this is not the last layer in the file
            if idx < len(layers_in_file) - 1:
                final_binary.extend(LAYER_SEPARATOR)

        # Save file for group
        with open(current_filepath, "wb") as f:
            f.write(final_binary)
            
        print(f"[VFX Packer] SUCCESS! File saved: {current_filepath}")