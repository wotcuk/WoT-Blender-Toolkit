import struct
import re
import os
import math
import xml.etree.ElementTree as ET
from xml.dom import minidom

def safe_float(data, offset):
    if offset + 4 > len(data): return 0.0
    try: return round(struct.unpack('<f', data[offset:offset+4])[0], 4)
    except: return 0.0

def safe_int(data, offset):
    if offset + 4 > len(data): return 0
    try: return struct.unpack('<I', data[offset:offset+4])[0]
    except: return 0

def safe_byte(data, offset):
    if offset + 1 > len(data): return 0
    try: return struct.unpack('<B', data[offset:offset+1])[0]
    except: return 0

def safe_hex(data, offset, length=4):
    if offset + length > len(data): return ""
    return " ".join(f"{b:02X}" for b in data[offset:offset+length])

def safe_string(data, offset, length):
    if offset + length > len(data): return ""
    try:
        raw = data[offset:offset+length].split(b'\x00')[0]
        return "".join(c for c in raw.decode('utf-8', 'ignore') if c.isprintable())
    except: return ""

def guess_type_and_value(data, offset):
    raw = data[offset:offset+4]
    if len(raw) < 4: return "hex", safe_hex(data, offset, len(raw))
    
    i_val = struct.unpack('<I', raw)[0]
    i_signed = struct.unpack('<i', raw)[0]
    f_val = struct.unpack('<f', raw)[0]
    
    # 1. Tam sıfırsa Float 0.0 olarak kalsın (XML temiz görünür)
    if i_val == 0: return "float", 0.0
        
    # 2. Özel Hex blokları (Örn: -1 yani FF FF FF FF)
    if i_val == 0xFFFFFFFF: return "hex", "FF FF FF FF"
        
    # 3. Mantıklı Küçük Tam Sayılar (1'den 1 Milyona kadar) -> INT'tir!
    if 0 < i_val < 1000000: return "int", i_val
    if -1000000 < i_signed < 0: return "int", i_signed
        
    # 4. Mantıklı Ondalık Sayılar -> FLOAT'tır!
    if not math.isnan(f_val) and not math.isinf(f_val):
        if 1e-6 <= abs(f_val) <= 1e7:
            return "float", round(f_val, 6)
            
    # 5. Hiçbirine uymuyorsa (Memory adresi veya saf byte ise) -> RAW HEX
    return "hex", safe_hex(data, offset, 4)

def unpack_vfxbin_to_xml(filepath):
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except Exception as e:
        print(f"[VFX Unpacker] Dosya okuma hatası: {e}")
        return None

    # E8 03 00 00 sihirli sayısını bul
    sig = b'\xE8\x03\x00\x00'
    offsets = [m.start() for m in re.finditer(re.escape(sig), data)]
    
    if not offsets:
        print("[VFX Unpacker] Sihirli sayı bulunamadı.")
        return None

    # --- YENİ: İLK KATMANIN İSMİNİ (SİHİRLİ SAYIDAN ÖNCEKİ 64 BYTE) HEADER'DAN ÇIKARTIYORUZ ---
    if offsets:
        header_end = max(0, offsets[0] - 0x40) # 0x40 = 64 Byte
        header_hex = safe_hex(data, 0, header_end)
    else:
        header_hex = ""
    # -----------------------------------------------------------------------------------------
    
    root = ET.Element("VFX_Data")
    root.set("source_file", os.path.basename(filepath))

    for idx, sig_index in enumerate(offsets):
        layer_elem = ET.SubElement(root, "Layer")
        layer_elem.set("id", str(idx))
        # --- BURAYI EKLE (Sınır belirleyici) ---
        layer_end = offsets[idx+1] if idx + 1 < len(offsets) else len(data)
        layer_data = data[sig_index:layer_end]
        
        # Plane ismi önceki 64 byte
        name_start = max(0, sig_index - 0x40)
        plane_name = safe_string(data, name_start, 64)
        if not plane_name: plane_name = f"Layer_{idx}"
        layer_elem.set("name", plane_name)

        off = sig_index + 4 # Sihirli sayıdan sonraki 0x0 noktası
        
        known_data = ET.SubElement(layer_elem, "Known_Parameters")
        
        def add_param(parent, name, val_type, offset, length=4):
            elem = ET.SubElement(parent, name)
            if val_type == "float": val = safe_float(data, off + offset)
            elif val_type == "int": val = safe_int(data, off + offset)
            elif val_type == "byte": val = safe_byte(data, off + offset)
            elif val_type == "hex": val = safe_hex(data, off + offset, length)
            elif val_type == "string": val = safe_string(data, off + offset, length)
            elem.text = str(val)
            elem.set("offset", hex(offset))

        # --- YENİ EKLENEN VEKTÖR VE GENEL BİLGİLER ---
        add_param(known_data, "Orientation_Vector_X", "float", 0x14)
        add_param(known_data, "Orientation_Vector_Y", "float", 0x18)
        add_param(known_data, "Orientation_Vector_Z", "float", 0x1C)
        add_param(known_data, "Particle_Count", "float", 0x20)
        
        # Oluşma Bölgesi ve Yayılım (Spread)
        spawn = ET.SubElement(known_data, "Spawn_Area")
        add_param(spawn, "Size_X", "float", 0x28)
        add_param(spawn, "Emitter_Type_or_Size_Z", "int", 0x2C) # Koni/Kutu Flag şüphelisi (Tam Sayı)
        add_param(spawn, "Size_Y", "float", 0x30)
        add_param(spawn, "Spread_Angle_or_Radius", "float", 0x34) # 0x34 deki şüpheli yayılım açısı
        
        # Açılar ve Dönüş
        add_param(known_data, "Initial_Angle_Max", "float", 0x38)
        add_param(known_data, "Rotation_Speed_Max", "float", 0x3C)
        add_param(known_data, "Rotation_Speed_Min", "float", 0x40)
        
        # Efekt Çarpanları
        add_param(known_data, "Alpha_Offset", "float", 0x4C)
        add_param(known_data, "Wind_Multiplier_Min", "float", 0x50)
        add_param(known_data, "Wind_Multiplier_Max", "float", 0x54)

        # FFFF ve Özel Flag Blokları
        add_param(known_data, "FFFF_Block_0x5C", "hex", 0x5C)
        add_param(known_data, "Unknown_Flag_0x94", "hex", 0x94) # 02 00 00 00 alınmalı dediğin
        add_param(known_data, "Unknown_Flag_0xBC", "hex", 0xBC) # 01 00 00 00 alınmalı dediğin
        add_param(known_data, "FFFF_Block_0x160", "hex", 0x160)
        
        # Zamanlama
        add_param(known_data, "Life_Time_Min", "float", 0xA0)
        add_param(known_data, "Life_Time_Max", "float", 0xA4)
        add_param(known_data, "Trigger_Delay_Min", "float", 0xA8)
        add_param(known_data, "Trigger_Delay_Max", "float", 0xAC)

        # Dosya Yolları
        add_param(known_data, "Texture_Path", "string", 0xC0, length=128)
        add_param(known_data, "Shader_Path", "string", 0x1A0, length=128)
        add_param(known_data, "Mesh_Path", "string", 0x490, length=256)
        # --- YENİ MİMARİ: GENİŞLİĞİN UZUNLUĞU KONTROL ETTİĞİ SHADERLAR ---
        shader_val = safe_string(data, off + 0x1A0, 128).lower()
        
        # Bu shaderlarda 0x178 ve 0x424 offsetleri uzunluk (Length) DEĞİLDİR!
        UNIFORM_SHADERS = ["pbs_mesh_particles.fx","ps_long.fx"] # Buraya virgülle diğerlerini ekleyebilirsin
        is_uniform_scale = any(s in shader_val for s in UNIFORM_SHADERS)
        # Boyut ve Hızlar
        add_param(known_data, "Width_Min", "float", 0x140)
        add_param(known_data, "Width_Max", "float", 0x144)
        add_param(known_data, "Init_Vertical_Speed_Min", "float", 0x148)
        add_param(known_data, "Init_Vertical_Speed_Max", "float", 0x14C)
        add_param(known_data, "V_Max", "float", 0x150)
        add_param(known_data, "U_Max", "float", 0x15C)
        add_param(known_data, "V_Min", "float", 0x158)
        add_param(known_data, "U_Min", "float", 0x154)
        
        # Fizik
        add_param(known_data, "Acceleration_Min", "float", 0x164)
        add_param(known_data, "Acceleration_Max", "float", 0x17C)
        # --- UZUNLUK (LENGTH) MANTIĞI ---
        if is_uniform_scale:
            # Genişlik (Width) değerini Blender için Uzunluğa da kopyalıyoruz.
            # DİKKAT: offset="" YAZMIYORUZ! (Çünkü bu değerler aslında 0x140 ve 0x144'ten geliyor)
            ET.SubElement(known_data, "Length_Max").text = str(safe_float(data, off + 0x144))
            ET.SubElement(known_data, "Length_Min").text = str(safe_float(data, off + 0x140))
        else:
            # Normal bir shader ise kendi offsetinden okumaya devam et
            add_param(known_data, "Length_Max", "float", 0x178)
        add_param(known_data, "Z_Bias", "float", 0x19C)

        # Bayraklar (1 Byte)
        flags = ET.SubElement(known_data, "Flags")
        add_param(flags, "Animation_Mode", "byte", 0x168)
        add_param(flags, "Flip_Visual_180", "byte", 0x169)
        add_param(flags, "Axis_Orientation", "byte", 0x16B)
        
        # Atlas ve Animasyon
        add_param(known_data, "Cols", "int", 0x16C)
        add_param(known_data, "Rows", "int", 0x170)
        add_param(known_data, "Animation_Speed", "float", 0x174)

        # Dönüş Hızları (Eksenel)
        add_param(known_data, "Rot_Speed_Z_Max", "float", 0x180)
        add_param(known_data, "Rot_Speed_Z_Min", "float", 0x184)
        add_param(known_data, "Rot_Speed_X_Max", "float", 0x188)
        add_param(known_data, "Rot_Speed_X_Min", "float", 0x18C)
        add_param(known_data, "Rot_Speed_Y_Max", "float", 0x190)
        add_param(known_data, "Rot_Speed_Y_Min", "float", 0x194)
        add_param(known_data, "Unknown_Deflection_0x198", "float", 0x198) # Etkisiz sanılan değer
        add_param(spawn, "Cone_Radius_Multiplier", "float", 0x220)
        add_param(known_data, "Info_String", "string", 0x350, length=64)

        # --- YENİ EKLENEN: AÇILAR (RADYAN) ---
        add_param(known_data, "Init_Rot_Range_Z_Rad", "float", 0x3BC)
        add_param(known_data, "Init_Rot_Range_X_Rad", "float", 0x3C0)
        add_param(known_data, "Init_Rot_Range_Y_Rad", "float", 0x3C4)

        # --- YENİ EKLENEN: IŞIK VE PARLAMA ---
        glow = ET.SubElement(known_data, "Lighting_and_Glow")
        add_param(glow, "Base_Emission", "float", 0x3DC)
        
        # ==========================================
        # --- YENİ EKLENEN: EĞRİLERİ (CURVES) ÇÖZME ---
        # ==========================================
        curves_elem = ET.SubElement(layer_elem, "Curves")
        
        # Bu Layer'ın içindeki PPPP bloklarını bul
        pppp_offsets = [m.start() for m in re.finditer(b'PPPP', layer_data)]
        
        # 1. Eğri Bloğu: SCALE CURVE (Index 0)
        if len(pppp_offsets) > 0:
            scale_pppp_abs = sig_index + pppp_offsets[0]
            
            # Nokta sayısı PPPP'den TAM OLARAK 4 byte önce
            pt_count = safe_int(data, scale_pppp_abs - 4) 
            scale_off_rel = (scale_pppp_abs - 4) - off
            
            scale_curve = ET.SubElement(curves_elem, "Curve_Scale")
            scale_curve.set("points", str(pt_count))
            scale_curve.set("offset", hex(scale_off_rel))
            
            curr = scale_pppp_abs + 4 
            if pt_count > 0 and curr + (pt_count * 8) <= layer_end:
                # Önce Tümü Zaman (Time) Değerleri
                times = struct.unpack(f'<{pt_count}f', data[curr : curr + pt_count*4])
                
                # Hemen ardından Tümü Değer (Value) Floatları
                vals_curr = curr + pt_count*4
                vals = struct.unpack(f'<{pt_count}f', data[vals_curr : vals_curr + pt_count*4])
                
                for i in range(pt_count):
                    pt = ET.SubElement(scale_curve, "Point")
                    pt.set("time", str(round(times[i], 4)))
                    pt.set("value", str(round(vals[i], 4)))

        # 7. Eğri Bloğu: RGBA CURVE (Index 6)
        if len(pppp_offsets) > 6:
            rgba_pppp_abs = sig_index + pppp_offsets[6]
            
            pt_count = safe_int(data, rgba_pppp_abs - 4)
            rgba_off_rel = (rgba_pppp_abs - 4) - off
            
            # Ana kapsayıcıları oluştur ve hepsine nokta sayısı / offset bilgilerini gir
            r_curve = ET.SubElement(curves_elem, "Curve_Color_R")
            r_curve.set("points", str(pt_count))
            r_curve.set("offset", hex(rgba_off_rel))
            
            g_curve = ET.SubElement(curves_elem, "Curve_Color_G")
            g_curve.set("points", str(pt_count))
            g_curve.set("offset", hex(rgba_off_rel))
            
            b_curve = ET.SubElement(curves_elem, "Curve_Color_B")
            b_curve.set("points", str(pt_count))
            b_curve.set("offset", hex(rgba_off_rel))
            
            a_curve = ET.SubElement(curves_elem, "Curve_Alpha_A")
            a_curve.set("points", str(pt_count))
            a_curve.set("offset", hex(rgba_off_rel))
            
            curr = rgba_pppp_abs + 4
            if pt_count > 0 and curr + (pt_count * 20) <= layer_end:
                # Önce 4 adet Zaman (Time) Floatı
                times = struct.unpack(f'<{pt_count}f', data[curr : curr + pt_count*4])
                
                # Ardından Vector4'ler (Her nokta için 16 Byte: R, G, B, A)
                vals_curr = curr + pt_count*4
                
                for i in range(pt_count):
                    offset = vals_curr + (i * 16)
                    r, g, b, a = struct.unpack('<ffff', data[offset : offset+16])
                    
                    ET.SubElement(r_curve, "Point").set("time", str(round(times[i], 4))); list(r_curve)[-1].set("value", str(round(r, 4)))
                    ET.SubElement(g_curve, "Point").set("time", str(round(times[i], 4))); list(g_curve)[-1].set("value", str(round(g, 4)))
                    ET.SubElement(b_curve, "Point").set("time", str(round(times[i], 4))); list(b_curve)[-1].set("value", str(round(b, 4)))
                    ET.SubElement(a_curve, "Point").set("time", str(round(times[i], 4))); list(a_curve)[-1].set("value", str(round(a, 4)))
        # ==========================================

        # --- BİLİNMEYEN OFFSETLERİ ÇEKME (Tarama) ---
        unknown_data = ET.SubElement(layer_elem, "Unknown_Parameters")
        
        if idx == 0 and header_hex:
            elem = ET.SubElement(unknown_data, "Header_Data")
            elem.text = header_hex
            elem.set("type", "hex")
            
        if is_uniform_scale:
            # Gizli offsetleri (0x178, 0x424) akıllı okuyucuyla okuyup türünü damgalıyoruz
            for hidden_off in [0x178]:
                g_type, g_val = guess_type_and_value(data, off + hidden_off)
                elem = ET.SubElement(unknown_data, f"Offset_{hex(hidden_off)}")
                elem.text = str(g_val)
                elem.set("type", g_type) # <-- XML'e "Ben bir int/float/hex'im!" damgası vuruluyor
            
        scan_ranges = [
            (0x00, 0x14), (0x24, 0x28), (0x44, 0x4C), (0x58, 0x5C), 
            (0x60, 0x94), (0x98, 0xA0), (0xB0, 0xBC), (0x224, 0x350), 
            (0x390, 0x3BC), (0x3C8, 0x3DC), (0x3E0, 0x428), (0x428, 0x490)
        ]

        for start_hex, end_hex in scan_ranges:
            for curr_offset in range(start_hex, end_hex, 4):
                g_type, g_val = guess_type_and_value(data, off + curr_offset)
                elem = ET.SubElement(unknown_data, f"Offset_{hex(curr_offset)}")
                elem.text = str(g_val)
                elem.set("type", g_type) # <-- Damgalama işlemi

    # XML'i formatla ve kaydet
    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="    ")
    
    base_name, _ = os.path.splitext(filepath)
    out_path = base_name + ".vfxxml"
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    
    print(f"[VFX Unpacker] Veriler başarıyla çıkartıldı: {out_path}")
    return out_path