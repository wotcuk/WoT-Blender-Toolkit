"""SkepticalFox 2015-2024 - Tam Kapsamlı Debug Sürümü"""

# imports
import logging
import os
import traceback
from pathlib import Path
from xml.etree import ElementTree as ET

# blender imports
import bpy  # type: ignore
from bpy_extras.io_utils import unpack_list  # type: ignore
from mathutils import Vector  # type: ignore

# local imports
from .common.XmlUnpacker import XmlUnpacker
from .common import utils_AsVector
from .common.consts import visual_property_descr_dict, VERBOSE_VALIDATE
from .loaddatamesh import LoadDataMesh

logger = logging.getLogger(__name__)

def write_to_blender_text(content, clear=False):
    """Blender içindeki Text Editor'e (BW_Import_Debug_Log) mesaj yazar."""
    text_name = "BW_Import_Debug_Log"
    txt = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    if clear:
        txt.clear()
    txt.write(content + "\n")

from mathutils import Matrix

def get_empty_by_nodes(col: bpy.types.Collection, elem: ET.Element, empty_obj=None):
    if (elem.find("identifier") is None) or (elem.find("transform") is None):
        return None

    identifier = elem.findtext("identifier").strip()
    
    # 1. BigWorld XML verilerini oku
    r0 = utils_AsVector(elem.findtext("transform/row0"))
    r1 = utils_AsVector(elem.findtext("transform/row1"))
    r2 = utils_AsVector(elem.findtext("transform/row2"))
    r3 = utils_AsVector(elem.findtext("transform/row3"))

    # 2. Blender Matrisini olustur
    # KRITIK: BigWorld satirlarini Blender'in SUTUNLARINA (Column) esliyoruz.
    # Bu islem koordinatlarin kaybolmasini engeller.
    mtx = Matrix()
    mtx.col[0] = [*r0, 0] # Lokal X Ekseni (Rotasyon + Scale)
    mtx.col[1] = [*r1, 0] # Lokal Y Ekseni
    mtx.col[2] = [*r2, 0] # Lokal Z Ekseni
    mtx.col[3] = [*r3, 1] # KOORDINATLAR (Translation) - Burasi artik 0 degil!

    # 3. Koordinat Sistemi Donusumu (BW Y-up -> Blender Z-up)
    # Senin orijinal .xzy (X->X, Y->Z, Z->Y) mantigini tum matrise uyguluyoruz.
    C = Matrix([
        [1, 0, 0, 0],
        [0, 0, 1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1]
    ])
    
    # Matris donusumu: Hem aciyi hem yeri ayni anda dondurur
    final_mtx = C @ mtx @ C

    # 4. Obje olustur ve hiyerarsiyi kur
    ob = bpy.data.objects.new(identifier, None)
    col.objects.link(ob)
    
    if empty_obj is not None:
        ob.parent = empty_obj # Once ebeveyne bagla
        
    # 5. Matrisi lokal transform (matrix_basis) olarak ata
    # Artik hem koordinat hem de menteşe egimi (rotation) Blender'da gorunur olacak.
    ob.matrix_basis = final_mtx

    # Alt nodelara devam et
    for node in elem.iterfind("node"):
        get_empty_by_nodes(col, node, ob)

    return ob

# YENI EKLENEN FONKSIYON: Texture Bulucu
def find_and_assign_texture(mat, prop_name, base_path, is_data=False):
    # XML'den gelen ham degeri al (Örn: "diffuseMapparticles/../wood_am.dds" gibi bozuk veya duzgun)
    raw_path = mat.get(f"BigWorld_{prop_name}")
    if not raw_path:
        return

    # Dosya adini temizle ve al
    # Windows/Linux slash farkini duzelt
    clean_path = raw_path.replace("\\", "/").strip("/")
    filename = os.path.basename(clean_path)

    # 1. Strateji: Ayni klasorde ara (Dosya adiyla)
    search_path_local = base_path / filename
    
    # 2. Strateji: Tam klasor yapisinda ara (Goreceli yol)
    # Eger raw_path "vehicles/..." gibi basliyorsa base_path'in ustlerine bakmak gerekir.
    # Ancak burada basitlestirilmis olarak: base_path + clean_path deniyoruz.
    search_path_full = base_path / clean_path

    final_image_path = None

    if search_path_local.is_file():
        final_image_path = str(search_path_local)
    elif search_path_full.is_file():
        final_image_path = str(search_path_full)
    
    if final_image_path:
        # Texture'i Blender'a yukle
        try:
            img_name = os.path.basename(final_image_path)
            if img_name in bpy.data.images:
                image = bpy.data.images[img_name]
            else:
                image = bpy.data.images.load(final_image_path)
            
            if is_data:
                image.colorspace_settings.name = 'Non-Color'

            # Node Kurulumu
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            # Principled BSDF'i bul veya yarat
            bsdf = None
            for n in nodes:
                if n.type == 'BSDF_PRINCIPLED':
                    bsdf = n
                    break
            if not bsdf:
                nodes.clear() # Temizle
                bsdf = nodes.new('ShaderNodeBsdfPrincipled')
                out = nodes.new('ShaderNodeOutputMaterial')
                links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

            # Texture Node
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = image
            
            if prop_name == "diffuseMap":
                tex_node.location = (-300, 200)
                links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
                if image.alpha_mode != 'NONE':
                    links.new(tex_node.outputs['Alpha'], bsdf.inputs['Alpha'])
            elif prop_name == "normalMap":
                tex_node.location = (-300, -100)
                norm_node = nodes.new('ShaderNodeNormalMap')
                norm_node.location = (-150, -100)
                links.new(tex_node.outputs['Color'], norm_node.inputs['Color'])
                links.new(norm_node.outputs['Normal'], bsdf.inputs['Normal'])

        except Exception as e:
            logger.error(f"Texture yuklenirken hata: {e}")
            raise Exception(f"Texture dosyasi bozuk veya acilamiyor: {final_image_path}")
    else:
        # Texture bulunamadiysa HATA FIRLAT
        err_msg = f"Texture Bulunamadi!\nAranan 1: {search_path_local}\nAranan 2: {search_path_full}"
        logger.error(err_msg)
        raise Exception(err_msg)

def fake_visual_from_primitives(primitives_filepath: Path):
    write_to_blender_text("DEBUG: .visual dosyası yok, primitives içinden gruplar taklit ediliyor...")
    root = ET.Element("root")
    dataMesh = LoadDataMesh(primitives_filepath)
    for name in dataMesh.packed_groups:
        if name.endswith("vertices"):
            write_to_blender_text(f"DEBUG: Grup bulundu: {name}")
            renderSet_node = ET.SubElement(root, "renderSet")
            ET.SubElement(renderSet_node, "treatAsWorldSpaceObject").text = "false"
            geometry_node = ET.SubElement(renderSet_node, "geometry")
            ET.SubElement(geometry_node, "vertices").text = name
            ET.SubElement(geometry_node, "primitive").text = name.rpartition("vertices")[0] + "indices"
            uv2 = name.rpartition("vertices")[0] + "uv2"
            if uv2 in dataMesh.packed_groups:
                ET.SubElement(geometry_node, "stream").text = uv2
    return root

def load_bw_primitive_from_file(col: bpy.types.Collection, model_filepath: Path, import_empty: bool = False):
    write_to_blender_text("=== BIGWORLD IMPORT BASLADI ===", clear=True)
    write_to_blender_text(f"Dosya: {model_filepath}")
    
    try:
        visual_filepath = model_filepath.with_suffix(".visual_processed")
        visual_filepath_old = model_filepath.with_suffix(".visual")
        primitives_filepath = model_filepath.with_suffix(".primitives_processed")
        primitives_filepath_old = model_filepath.with_suffix(".primitives")

        is_processed = primitives_filepath.is_file()
        if not is_processed:
            visual_filepath = visual_filepath_old
            primitives_filepath = primitives_filepath_old

        if not primitives_filepath.is_file():
            write_to_blender_text(f"HATA: Primitives dosyası bulunamadı: {primitives_filepath}")
            raise Exception("There is no primitives file in the directory!")

        has_visual = visual_filepath.is_file()
        if not has_visual:
            import_empty = False
            write_to_blender_text("UYARI: .visual dosyası yok, sadece geometri yüklenecek.")

        if has_visual:
            write_to_blender_text(f"DEBUG: Visual XML okunuyor: {visual_filepath}")
            with visual_filepath.open("rb") as f:
                visual = XmlUnpacker().read(f)
        else:
            visual = fake_visual_from_primitives(primitives_filepath)

        if visual.find("renderSet") is None:
            write_to_blender_text("HATA: XML içinde 'renderSet' bulunamadı.")
            return

        root_empty_ob = None
        for rs_idx, renderSet in enumerate(visual.findall("renderSet")):
            vres_name = renderSet.findtext("geometry/vertices").strip()
            pres_name = renderSet.findtext("geometry/primitive").strip()
            write_to_blender_text(f"DEBUG: RenderSet {rs_idx} işleniyor (V: {vres_name}, I: {pres_name})")
            
            mesh_name = os.path.splitext(vres_name)[0]
            bmesh = bpy.data.meshes.new(mesh_name)

            # --- YENİ EKLENEN: Dinamik Stream (Veri Akışı) Tarayıcı ---
            uv2_name = ""
            colour_name = ""
            
            # Tüm <stream> etiketlerini bul ve ne olduklarını anla
            for stream_node in renderSet.findall("geometry/stream"):
                stream_res_name = stream_node.text.strip()
                if "uv2" in stream_res_name:
                    uv2_name = stream_res_name
                elif "colour" in stream_res_name:
                    colour_name = stream_res_name

            # LoadDataMesh ÇAĞRISI (Artık colour beklentisini de iletiyoruz)
            write_to_blender_text(f"DEBUG: LoadDataMesh veriyi çekiyor... (Beklenenler -> UV2: {bool(uv2_name)}, Colour: {bool(colour_name)})")
            dataMesh = LoadDataMesh(primitives_filepath, vres_name, pres_name, uv2_name, colour_name)
            # -----------------------------------------------------------
            write_to_blender_text(f"   Sonuç: {len(dataMesh.vertices)} vertex, {len(dataMesh.indices)} yüzey bulundu.")

            if len(dataMesh.vertices) == 0:
                write_to_blender_text("KRITIK HATA: Vertex sayısı 0! Primitives dosyası bozuk veya export hatası var.")
                continue

            bmesh.vertices.add(len(dataMesh.vertices))
            bmesh.vertices.foreach_set("co", unpack_list(dataMesh.vertices))

            nbr_faces = len(dataMesh.indices)
            bmesh.polygons.add(nbr_faces)
            bmesh.polygons.foreach_set("loop_start", range(0, nbr_faces * 3, 3))
            bmesh.polygons.foreach_set("loop_total", (3,) * nbr_faces)

            bmesh.loops.add(nbr_faces * 3)
            bmesh.loops.foreach_set("vertex_index", unpack_list(dataMesh.indices))
            bmesh.polygons.foreach_set("use_smooth", [True] * nbr_faces)

            # UV İşlemleri
            uv2_layer = None
            if uv2_name:
                if dataMesh.uv2_list:
                    uv2_layer = bmesh.uv_layers.new(name="uv2")
                    write_to_blender_text("DEBUG: uv2 katmanı eklendi.")
                else:
                    uv2_name = ""

            if dataMesh.uv_list:
                uv_layer = bmesh.uv_layers.new(name="uv1")
                uv_layer.active = True
                write_to_blender_text("DEBUG: UV koordinatları eşleniyor...")
                
                uv_layer_data = uv_layer.data
                uv2_layer_data = uv2_layer.data if uv2_layer else None

                for poly in bmesh.polygons:
                    for li in poly.loop_indices:
                        vi = bmesh.loops[li].vertex_index
                        uv_layer_data[li].uv = dataMesh.uv_list[vi]
                        if uv2_name:
                            uv2_layer_data[li].uv = dataMesh.uv2_list[vi]
            else:
                write_to_blender_text("UYARI: Modelde UV verisi bulunamadı.")

            # --- YENİ EKLENEN: COLOR (Vertex Paint) İŞLEMLERİ ---
            if hasattr(dataMesh, "colour_list") and dataMesh.colour_list:
                write_to_blender_text("DEBUG: BPVScolour (Vertex Color) bulundu, ekleniyor...")
                # Blender 3.2+ uyumlu Vertex Color katmanı (Domain: POINT yani Vertex başına)
                color_attr = bmesh.color_attributes.new(name="BPVScolour", type='BYTE_COLOR', domain='POINT')
                for v_idx, c_bytes in enumerate(dataMesh.colour_list):
                    # BigWorld RGBA baytlarını (0-255) Blender'ın 0.0-1.0 float aralığına çeviriyoruz
                    r, g, b, a = c_bytes[0]/255.0, c_bytes[1]/255.0, c_bytes[2]/255.0, c_bytes[3]/255.0
                    color_attr.data[v_idx].color = (r, g, b, a)
            else:
                write_to_blender_text("DEBUG: BPVScolour verisi yok (Modelde renk geçişi yok).")
            # -----------------------------------------------------

            # Materyal ve Grup İşlemleri
            primitiveGroupInfo = {}
            for primitiveGroup in renderSet.findall("geometry/primitiveGroup"):
                primitiveGroupInfo[int(primitiveGroup.text)] = {
                    "identifier": primitiveGroup.findtext("material/identifier").strip(),
                    "material_fx": primitiveGroup.findtext("material/fx"),
                    "material_props": primitiveGroup.findall("material/property"),
                    "groupOrigin": primitiveGroup.findtext("groupOrigin"),
                }

            write_to_blender_text(f"DEBUG: {len(dataMesh.PrimitiveGroups)} materyal grubu oluşturuluyor...")
            for i, pg in enumerate(dataMesh.PrimitiveGroups):
                pgVisual = primitiveGroupInfo.get(i)
                mat_name = pgVisual["identifier"] if pgVisual else f"mat_{i}"
                material = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
                bmesh.materials.append(material)

                # --- YENİ EKLENEN: Otomatik Vertex Color Görselleştirme ---
                if hasattr(dataMesh, "colour_list") and dataMesh.colour_list:
                    material.use_nodes = True
                    nodes = material.node_tree.nodes
                    links = material.node_tree.links
                    
                    # Varsa Principled BSDF'i bul, yoksa yarat
                    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
                    if not bsdf:
                        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
                        bsdf.location = (0, 0)
                    
                    # Attribute (BPVScolour) nodunu ekle
                    attr_node = nodes.new('ShaderNodeAttribute')
                    attr_node.attribute_name = "BPVScolour"
                    attr_node.location = (-400, 200)
                    
                    links.new(attr_node.outputs['Alpha'], bsdf.inputs['Alpha'])
                    material.blend_method = 'BLEND'   # Kumlanmayı bitirir, pürüzsüz geçiş sağlar
                    material.show_transparent_back = True # Arkadaki poligonların görünmesini sağlar
                # -----------------------------------------------------------

                startIndex = pg["startIndex"] // 3
                count = pg["nPrimitives"]
                for fidx in range(startIndex, startIndex + count):
                    if fidx < len(bmesh.polygons):
                        bmesh.polygons[fidx].material_index = i

            write_to_blender_text("DEBUG: BMesh valide ediliyor...")
            bmesh.validate(verbose=VERBOSE_VALIDATE)
            bmesh.update()

            ob = bpy.data.objects.new(mesh_name, bmesh)

            # Kemik Ağırlıkları (Skinning)
            if "true" in renderSet.findtext("treatAsWorldSpaceObject").lower():
                write_to_blender_text("DEBUG: Skinning (Kemik) verileri işleniyor...")
                if dataMesh.bones_info:
                    bone_nodes = renderSet.findall("node")
                    bone_arr = []
                    for node in bone_nodes:
                        bn = node.text.strip()
                        bone_arr.append({"name": bn, "group": ob.vertex_groups.new(name=bn)})

                    for vert_idx, iiiww in enumerate(dataMesh.bones_info):
                        # Aynı kemik gelirse ağırlıkları toplayacak depo
                        weights_sum_map = {}
                        
                        # --- YENI NESIL (8-BAYT) iiiww YAPISI ---
                        if len(iiiww) == 8: 
                            # iiiww dizilimi: [0:i1] [1:i2] [2:i3] [3:p1] [4:p2] [5:w2] [6:w3] [7:w1]
                            # Eşleşme: i1<->w1(B7), i2<->w2(B5), i3<->w3(B6)
                            mapping = [
                                (iiiww[0], iiiww[7]), # i1 <-> w1
                                (iiiww[1], iiiww[5]), # i2 <-> w2
                                (iiiww[2], iiiww[6])  # i3 <-> w3
                            ]
                        
                        # --- ESKI NESIL (5-BAYT) iiiww YAPISI ---
                        elif len(iiiww) == 5:
                            # iiiww dizilimi: [0:i1] [1:i2] [2:i3] [3:w1] [4:w2]
                            w1, w2 = iiiww[3], iiiww[4]
                            w3 = max(0, 255 - (w1 + w2)) # Kalan ağırlık i3'e
                            mapping = [
                                (iiiww[0], w1),
                                (iiiww[1], w2),
                                (iiiww[2], w3)
                            ]
                        else:
                            continue
                        # Ağırlıkları topla ve kemik ID'lerini (idx//3) eşle
                        for raw_idx, weight_val in mapping:
                            if weight_val > 0:
                                bone_id = raw_idx // 3
                                norm_weight = weight_val / 255.0
                                # Kümülatif toplama: Aynı kemik geldiyse üstüne ekle
                                weights_sum_map[bone_id] = weights_sum_map.get(bone_id, 0.0) + norm_weight

                        # Blender Vertex Grubuna Uygula
                        for b_id, final_w in weights_sum_map.items():
                            if b_id < len(bone_arr) and final_w > 0.0001:
                                bone_arr[b_id]["group"].add([vert_idx], final_w, "ADD")

            ob.scale = Vector((1.0, 1.0, 1.0))
            col.objects.link(ob)

            if import_empty and visual.find("node") is not None:
                if root_empty_ob is None:
                    root_empty_ob = get_empty_by_nodes(col, visual.findall("node")[0])
                if root_empty_ob: ob.parent = root_empty_ob

            write_to_blender_text(f"BASARILI: {mesh_name} sahneye eklendi.")

        write_to_blender_text("=== IMPORT TAMAMLANDI ===")

    except Exception as e:
        msg = f"\n!!! IMPORT HATASI !!!\n{str(e)}\n\n{traceback.format_exc()}"
        write_to_blender_text(msg)
        print(msg)