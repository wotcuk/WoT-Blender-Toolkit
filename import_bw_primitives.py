"""Uses Old import method. Will be fixed in the future"""

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
    """Writes messages to Blender's Text Editor (BW_Import_Debug_Log)."""
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
    
    # 1. Read BigWorld XML data
    r0 = utils_AsVector(elem.findtext("transform/row0"))
    r1 = utils_AsVector(elem.findtext("transform/row1"))
    r2 = utils_AsVector(elem.findtext("transform/row2"))
    r3 = utils_AsVector(elem.findtext("transform/row3"))

    # 2. Create Blender Matrix
    # CRITICAL: Map BigWorld rows to Blender columns to preserve coordinates
    mtx = Matrix()
    mtx.col[0] = [*r0, 0] # Local X Axis (Rotation + Scale)
    mtx.col[1] = [*r1, 0] # Local Y Axis
    mtx.col[2] = [*r2, 0] # Local Z Axis
    mtx.col[3] = [*r3, 1] # Translation (Coordinates)

    # 3. Coordinate System Conversion (BW Y-up -> Blender Z-up)
    C = Matrix([
        [1, 0, 0, 0],
        [0, 0, 1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1]
    ])
    
    # Matrix conversion: Rotates both angle and location simultaneously
    final_mtx = C @ mtx @ C

    # 4. Create object and establish hierarchy
    ob = bpy.data.objects.new(identifier, None)
    col.objects.link(ob)
    
    if empty_obj is not None:
        ob.parent = empty_obj
        
    # 5. Assign matrix as local transform (matrix_basis)
    ob.matrix_basis = final_mtx

    # Process child nodes
    for node in elem.iterfind("node"):
        get_empty_by_nodes(col, node, ob)

    return ob

# --- NEW: Texture Finder ---
def find_and_assign_texture(mat, prop_name, base_path, is_data=False):
    # Get raw path from XML
    raw_path = mat.get(f"BigWorld_{prop_name}")
    if not raw_path:
        return

    # Clean and extract filename
    clean_path = raw_path.replace("\\", "/").strip("/")
    filename = os.path.basename(clean_path)

    # Strategy 1: Search in the same folder by filename
    search_path_local = base_path / filename
    
    # Strategy 2: Search full relative path
    search_path_full = base_path / clean_path

    final_image_path = None

    if search_path_local.is_file():
        final_image_path = str(search_path_local)
    elif search_path_full.is_file():
        final_image_path = str(search_path_full)
    
    if final_image_path:
        # Load texture into Blender
        try:
            img_name = os.path.basename(final_image_path)
            if img_name in bpy.data.images:
                image = bpy.data.images[img_name]
            else:
                image = bpy.data.images.load(final_image_path)
            
            if is_data:
                image.colorspace_settings.name = 'Non-Color'

            # Node Setup
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            # Find or create Principled BSDF
            bsdf = None
            for n in nodes:
                if n.type == 'BSDF_PRINCIPLED':
                    bsdf = n
                    break
            if not bsdf:
                nodes.clear()
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
            logger.error(f"Error loading texture: {e}")
            raise Exception(f"Corrupted or unreadable texture file: {final_image_path}")
    else:
        # Throw error if texture is not found
        err_msg = f"Texture Not Found!\nSearched 1: {search_path_local}\nSearched 2: {search_path_full}"
        logger.error(err_msg)
        raise Exception(err_msg)

def fake_visual_from_primitives(primitives_filepath: Path):
    write_to_blender_text("DEBUG: .visual file missing, faking groups from primitives...")
    root = ET.Element("root")
    dataMesh = LoadDataMesh(primitives_filepath)
    for name in dataMesh.packed_groups:
        if name.endswith("vertices"):
            write_to_blender_text(f"DEBUG: Group found: {name}")
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
    write_to_blender_text("=== BIGWORLD IMPORT STARTED ===", clear=True)
    write_to_blender_text(f"File: {model_filepath}")
    
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
            write_to_blender_text(f"ERROR: Primitives file not found: {primitives_filepath}")
            raise Exception("There is no primitives file in the directory!")

        has_visual = visual_filepath.is_file()
        if not has_visual:
            import_empty = False
            write_to_blender_text("WARNING: .visual file missing, loading geometry only.")

        if has_visual:
            write_to_blender_text(f"DEBUG: Reading Visual XML: {visual_filepath}")
            with visual_filepath.open("rb") as f:
                visual = XmlUnpacker().read(f)
        else:
            visual = fake_visual_from_primitives(primitives_filepath)

        if visual.find("renderSet") is None:
            write_to_blender_text("ERROR: 'renderSet' not found in XML.")
            return

        root_empty_ob = None
        for rs_idx, renderSet in enumerate(visual.findall("renderSet")):
            vres_name = renderSet.findtext("geometry/vertices").strip()
            pres_name = renderSet.findtext("geometry/primitive").strip()
            write_to_blender_text(f"DEBUG: Processing RenderSet {rs_idx} (V: {vres_name}, I: {pres_name})")
            
            mesh_name = os.path.splitext(vres_name)[0]
            bmesh = bpy.data.meshes.new(mesh_name)

            # --- NEW: Dynamic Stream Scanner ---
            uv2_name = ""
            colour_name = ""
            
            # Find all <stream> tags and identify them
            for stream_node in renderSet.findall("geometry/stream"):
                stream_res_name = stream_node.text.strip()
                if "uv2" in stream_res_name:
                    uv2_name = stream_res_name
                elif "colour" in stream_res_name:
                    colour_name = stream_res_name

            write_to_blender_text(f"DEBUG: LoadDataMesh pulling data... (Expected -> UV2: {bool(uv2_name)}, Colour: {bool(colour_name)})")
            dataMesh = LoadDataMesh(primitives_filepath, vres_name, pres_name, uv2_name, colour_name)
            write_to_blender_text(f"   Result: {len(dataMesh.vertices)} vertices, {len(dataMesh.indices)} faces found.")

            if len(dataMesh.vertices) == 0:
                write_to_blender_text("CRITICAL ERROR: Vertex count is 0! Primitives file is corrupted or export failed.")
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

            # UV Operations
            uv2_layer = None
            if uv2_name:
                if dataMesh.uv2_list:
                    uv2_layer = bmesh.uv_layers.new(name="uv2")
                    write_to_blender_text("DEBUG: Added uv2 layer.")
                else:
                    uv2_name = ""

            if dataMesh.uv_list:
                uv_layer = bmesh.uv_layers.new(name="uv1")
                uv_layer.active = True
                write_to_blender_text("DEBUG: Mapping UV coordinates...")
                
                uv_layer_data = uv_layer.data
                uv2_layer_data = uv2_layer.data if uv2_layer else None

                for poly in bmesh.polygons:
                    for li in poly.loop_indices:
                        vi = bmesh.loops[li].vertex_index
                        uv_layer_data[li].uv = dataMesh.uv_list[vi]
                        if uv2_name:
                            uv2_layer_data[li].uv = dataMesh.uv2_list[vi]
            else:
                write_to_blender_text("WARNING: No UV data found in model.")

            # --- NEW: COLOR (Vertex Paint) OPERATIONS ---
            if hasattr(dataMesh, "colour_list") and dataMesh.colour_list:
                write_to_blender_text("DEBUG: BPVScolour (Vertex Color) found, adding...")
                # Blender 3.2+ compatible Vertex Color layer
                color_attr = bmesh.color_attributes.new(name="BPVScolour", type='BYTE_COLOR', domain='POINT')
                for v_idx, c_bytes in enumerate(dataMesh.colour_list):
                    # Convert BigWorld RGBA bytes to Blender floats
                    r, g, b, a = c_bytes[0]/255.0, c_bytes[1]/255.0, c_bytes[2]/255.0, c_bytes[3]/255.0
                    color_attr.data[v_idx].color = (r, g, b, a)
            else:
                write_to_blender_text("DEBUG: No BPVScolour data found.")

            # Material and Group Operations
            primitiveGroupInfo = {}
            for primitiveGroup in renderSet.findall("geometry/primitiveGroup"):
                primitiveGroupInfo[int(primitiveGroup.text)] = {
                    "identifier": primitiveGroup.findtext("material/identifier").strip(),
                    "material_fx": primitiveGroup.findtext("material/fx"),
                    "material_props": primitiveGroup.findall("material/property"),
                    "groupOrigin": primitiveGroup.findtext("groupOrigin"),
                }

            write_to_blender_text(f"DEBUG: Creating {len(dataMesh.PrimitiveGroups)} material groups...")
            for i, pg in enumerate(dataMesh.PrimitiveGroups):
                pgVisual = primitiveGroupInfo.get(i)
                mat_name = pgVisual["identifier"] if pgVisual else f"mat_{i}"
                material = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
                bmesh.materials.append(material)

                # --- NEW: Automatic Vertex Color Visualization ---
                if hasattr(dataMesh, "colour_list") and dataMesh.colour_list:
                    material.use_nodes = True
                    nodes = material.node_tree.nodes
                    links = material.node_tree.links
                    
                    # Find or create Principled BSDF
                    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
                    if not bsdf:
                        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
                        bsdf.location = (0, 0)
                    
                    # Add Attribute node for Vertex Color
                    attr_node = nodes.new('ShaderNodeAttribute')
                    attr_node.attribute_name = "BPVScolour"
                    attr_node.location = (-400, 200)
                    
                    links.new(attr_node.outputs['Alpha'], bsdf.inputs['Alpha'])
                    material.blend_method = 'BLEND'
                    material.show_transparent_back = True

                startIndex = pg["startIndex"] // 3
                count = pg["nPrimitives"]
                for fidx in range(startIndex, startIndex + count):
                    if fidx < len(bmesh.polygons):
                        bmesh.polygons[fidx].material_index = i

            write_to_blender_text("DEBUG: Validating BMesh...")
            bmesh.validate(verbose=VERBOSE_VALIDATE)
            bmesh.update()

            ob = bpy.data.objects.new(mesh_name, bmesh)

            # Bone Weights (Skinning)
            if "true" in renderSet.findtext("treatAsWorldSpaceObject").lower():
                write_to_blender_text("DEBUG: Processing skinning data...")
                if dataMesh.bones_info:
                    bone_nodes = renderSet.findall("node")
                    bone_arr = []
                    for node in bone_nodes:
                        bn = node.text.strip()
                        bone_arr.append({"name": bn, "group": ob.vertex_groups.new(name=bn)})

                    for vert_idx, iiiww in enumerate(dataMesh.bones_info):
                        # Dictionary to accumulate weights for the same bone
                        weights_sum_map = {}
                        
                        # --- NEW GEN (8-BYTE) iiiww STRUCTURE ---
                        if len(iiiww) == 8: 
                            mapping = [
                                (iiiww[0], iiiww[7]), 
                                (iiiww[1], iiiww[5]), 
                                (iiiww[2], iiiww[6])  
                            ]
                        
                        # --- OLD GEN (5-BYTE) iiiww STRUCTURE ---
                        elif len(iiiww) == 5:
                            w1, w2 = iiiww[3], iiiww[4]
                            w3 = max(0, 255 - (w1 + w2))
                            mapping = [
                                (iiiww[0], w1),
                                (iiiww[1], w2),
                                (iiiww[2], w3)
                            ]
                        else:
                            continue
                            
                        # Accumulate weights and map bone IDs
                        for raw_idx, weight_val in mapping:
                            if weight_val > 0:
                                bone_id = raw_idx // 3
                                norm_weight = weight_val / 255.0
                                # Cumulative addition
                                weights_sum_map[bone_id] = weights_sum_map.get(bone_id, 0.0) + norm_weight

                        # Apply to Blender Vertex Group
                        for b_id, final_w in weights_sum_map.items():
                            if b_id < len(bone_arr) and final_w > 0.0001:
                                bone_arr[b_id]["group"].add([vert_idx], final_w, "ADD")

            ob.scale = Vector((1.0, 1.0, 1.0))
            col.objects.link(ob)

            if import_empty and visual.find("node") is not None:
                if root_empty_ob is None:
                    root_empty_ob = get_empty_by_nodes(col, visual.findall("node")[0])
                if root_empty_ob: ob.parent = root_empty_ob

            write_to_blender_text(f"SUCCESS: {mesh_name} added to scene.")

        write_to_blender_text("=== IMPORT COMPLETED ===")

    except Exception as e:
        msg = f"\n!!! IMPORT ERROR !!!\n{str(e)}\n\n{traceback.format_exc()}"
        write_to_blender_text(msg)
        print(msg)