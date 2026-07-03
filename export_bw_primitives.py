import os
import subprocess
from struct import pack
from xml.dom.minidom import getDOMImplementation
from .exportdatamesh import ExportDataMesh 
import bpy
import math
from mathutils import Vector, Matrix, Euler
VERTEX_SHADER_MAP = {
    "set3/xyznuviiiwwpc": [
        "shaders/std_effects/lightonly_skinned.fx",
    ],
    "set3/xyznuviiiwwtbpc": [
        "shaders/custom/volumetric_effect_vtx_skinned.fx",
        "shaders/std_effects/PBS_ext.fx",
        "shaders/std_effects/PBS_ext_dissolve_skinned_dual.fx",
        "shaders/std_effects/PBS_ext_dual_skinned.fx",
        "shaders/std_effects/PBS_ext_repaint_skinned.fx",
        "shaders/std_effects/PBS_ext_skinned.fx",
        "shaders/std_effects/PBS_ext_skinned_dual.fx",
        "shaders/std_effects/PBS_ext_skinned_repaint.fx",
        "shaders/std_effects/PBS_flag_skinned.fx",
        "shaders/std_effects/PBS_glass_skinned.fx",
        "shaders/std_effects/PBS_sss_skinned.fx",
        "shaders/std_effects/PBS_tank.fx",
        "shaders/std_effects/PBS_tank_skinned.fx",
        "shaders/std_effects/PBS_tank_skinned_ao.fx",
        "shaders/std_effects/PBS_tank_skinned_crash.fx",
        "shaders/std_effects/PBS_tank_uvtransform_skinned_ao.fx",
        "shaders/std_effects/PBS_tiled_global_skinned.fx",
        "shaders/std_effects/PBS_tiled_skinned.fx",
        "shaders/std_effects/PBS_wheel_skinned.fx",
        "shaders/std_effects/PBS_wheel_skinned_crash.fx",
        "shaders/std_effects/fur_skinned.fx",
        "shaders/std_effects/lightonly_skinned.fx",
        "shaders/std_effects/pbs_tank_skinned.fx",
    ],
    "set3/xyznuvitbpc": [
        "shaders/std_effects/PBS_ext_detail_repaint_rigid_skinned.fx",
        "shaders/std_effects/PBS_ext_detail_rigid_skinned.fx",
        "shaders/std_effects/PBS_ext_repaint_rigid_skinned.fx",
        "shaders/std_effects/PBS_ext_rigid_skinned.fx",
        "shaders/std_effects/PBS_ext_rigid_skinned_dual.fx",
        "shaders/std_effects/PBS_glass_rigid_skinned.fx",
        "shaders/std_effects/PBS_tiled_rigid_skinned.fx",
    ],
    "set3/xyznuvpc": [
        "shaders/controlPoint/wg_controlPointRadius.fx",
        "shaders/custom/emissive.fx",
        "shaders/custom/emissive_angle_falloff.fx",
        "shaders/custom/emissive_playground.fx",
        "shaders/custom/env_color_mask.fx",
        "shaders/custom/intersection_sphere.fx",
        "shaders/custom/vector_animation.fx",
        "shaders/custom/vector_animation_2.fx",
        "shaders/custom/volumetric_effect_layer_vtx.fx",
        "shaders/custom/volumetric_effect_vtx.fx",
        "shaders/environment/light_flare.fx",
        "shaders/particles/wg_particles.fx",
        "shaders/std_effects/glow.fx",
        "shaders/std_effects/glow_tone_mapping_compensation.fx",
        "shaders/std_effects/lightonly.fx",
        "shaders/std_effects/lightonly_add.fx",
        "shaders/std_effects/lightonly_alpha.fx",
        "shaders/wg_particles/pbs_mesh_particles.fx",
    ],
    "set3/xyznuvtbpc": [
        "shaders/controlPoint/wg_controlPointRadius.fx",
        "shaders/custom/VAT.fx",
        "shaders/custom/coloronly_alpha.fx",
        "shaders/custom/emissive.fx",
        "shaders/custom/emissive_angle_falloff.fx",
        "shaders/custom/emissive_playground.fx",
        "shaders/custom/hw_volumetric_effect_vtx.fx",
        "shaders/custom/interior_mapping.fx",
        "shaders/custom/shield_shimmer.fx",
        "shaders/custom/ui_3D.fx",
        "shaders/custom/vector_animation.fx",
        "shaders/custom/vector_animation_2.fx",
        "shaders/custom/volumetric_effect.fx",
        "shaders/custom/volumetric_effect_freshnel_invert.fx",
        "shaders/custom/volumetric_effect_vtx.fx",
        "shaders/decals/PBS_mesh_decal.fx",
        "shaders/environment/light_flare.fx",
        "shaders/environment/sky_box.fx",
        "shaders/environment/sky_box_HDR.fx",
        "shaders/gpu_particles/gpu_particle_pbs_ext.fx",
        "shaders/particles/wg_particles.fx",
        "shaders/std_effects/PBS_ext.fx",
        "shaders/std_effects/PBS_ext_detail.fx",
        "shaders/std_effects/PBS_ext_detail_dual.fx",
        "shaders/std_effects/PBS_ext_detail_repaint.fx",
        "shaders/std_effects/PBS_ext_dual.fx",
        "shaders/std_effects/PBS_ext_repaint.fx",
        "shaders/std_effects/PBS_ext_skinned.fx",
        "shaders/std_effects/PBS_ext_skinned_repaint.fx",
        "shaders/std_effects/PBS_flag.fx",
        "shaders/std_effects/PBS_glass.fx",
        "shaders/std_effects/PBS_glass_skinned.fx",
        "shaders/std_effects/PBS_tank.fx",
        "shaders/std_effects/PBS_tank_crash.fx",
        "shaders/std_effects/PBS_tank_damage.fx",
        "shaders/std_effects/PBS_tank_fade.fx",
        "shaders/std_effects/PBS_tank_precise_edge.fx",
        "shaders/std_effects/PBS_tank_skinned.fx",
        "shaders/std_effects/PBS_tank_tracks.fx",
        "shaders/std_effects/PBS_tiled.fx",
        "shaders/std_effects/PBS_tiled_atlas_global.fx",
        "shaders/std_effects/PBS_tiled_global.fx",
        "shaders/std_effects/PBS_tiled_skinned.fx",
        "shaders/std_effects/glow.fx",
        "shaders/std_effects/lightonly.fx",
        "shaders/std_effects/lightonly_alpha.fx",
        "shaders/std_effects/lightonly_alpha_modalpha.fx",
        "shaders/std_effects/lightonly_specmap.fx",
        "shaders/std_effects/normalmap_specmap.fx",
        "shaders/std_effects/red_wall_alpha.fx",
        "shaders/wg_particles/pbs_mesh_particles.fx",
    ],
}
SHADER_PROPERTIES_MAP = {
    "shaders/controlPoint/wg_controlPointRadius.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/VAT.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/coloronly_alpha.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/emissive.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/emissive_angle_falloff.fx": {"tawso": False, "space": "LOCAL"},
    "shaders/custom/emissive_playground.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/env_color_mask.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/hw_volumetric_effect_vtx.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/interior_mapping.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/intersection_sphere.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/shield_shimmer.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/ui_3D.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/vector_animation.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/vector_animation_2.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/volumetric_effect.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/volumetric_effect_freshnel_invert.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/volumetric_effect_layer_vtx.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/volumetric_effect_vtx.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/custom/volumetric_effect_vtx_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/decals/PBS_mesh_decal.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/environment/light_flare.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/environment/sky_box.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/environment/sky_box_HDR.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/gpu_particles/gpu_particle_pbs_ext.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/particles/wg_particles.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_ext.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_ext_detail.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_ext_detail_dual.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_ext_detail_repaint.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_ext_detail_repaint_rigid_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_detail_rigid_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_dissolve_skinned_dual.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_dual.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_ext_dual_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_repaint.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_ext_repaint_rigid_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_repaint_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_rigid_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_rigid_skinned_dual.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_skinned_dual.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_ext_skinned_repaint.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_flag.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_flag_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_glass.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_glass_rigid_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_glass_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_sss_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_tank.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_tank_crash.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_tank_damage.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_tank_fade.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_tank_precise_edge.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_tank_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_tank_skinned_ao.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_tank_skinned_crash.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_tank_tracks.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_tank_uvtransform_skinned_ao.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_tiled.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_tiled_atlas_global.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_tiled_global.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/PBS_tiled_global_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_tiled_rigid_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_tiled_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_wheel_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/PBS_wheel_skinned_crash.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/fur_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/glow.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/glow_tone_mapping_compensation.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/lightonly.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/lightonly_add.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/lightonly_alpha.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/lightonly_alpha_modalpha.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/lightonly_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/lightonly_specmap.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/normalmap_specmap.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/std_effects/pbs_tank_skinned.fx": {"tawso": True, "space": "LOCAL"},
    "shaders/std_effects/red_wall_alpha.fx": {"tawso": False, "space": "GLOBAL"},
    "shaders/wg_particles/pbs_mesh_particles.fx": {"tawso": False, "space": "GLOBAL"},
}
# --- SMART NAME AND PATH RESOLVER ---
def get_universal_config(obj, export_path, export_info):
    user_filename = os.path.splitext(os.path.basename(export_path))[0]
    
    lower_name = obj.name.lower()
    if "gun" in lower_name: part_suffix = "guns" 
    elif "turret" in lower_name: part_suffix = "turret_01"
    elif "hull" in lower_name: part_suffix = "hull"
    elif "chassis" in lower_name: part_suffix = "chassis"
    else: part_suffix = user_filename.lower()

    forced_filename = user_filename

    import re
    normalized_path = export_path.replace('\\', '/')
    game_rel_dir = ""
    
    match = re.search(r'/(vehicles|gfx|spaces|content|gui|particles|speedtree|system)/(.*)', normalized_path)
    if match:
        game_rel_dir = match.group(1) + '/' + os.path.dirname(match.group(2))
    else:
        game_rel_dir = os.path.basename(os.path.dirname(normalized_path))

    tank_base_path = game_rel_dir
    tank_pure_name = user_filename
    
    if game_rel_dir.startswith('vehicles/'):
        parts = game_rel_dir.split('/')
        if len(parts) >= 3:
            tank_base_path = f"vehicles/{parts[1]}/{parts[2]}"
            tank_pure_name = parts[2].split('_', 1)[1] if '_' in parts[2] else parts[2]

    texture_basename = f"{tank_pure_name}_{part_suffix}"
    
    return forced_filename, texture_basename, tank_base_path, game_rel_dir

ROTATION_OFFSET_X = ROTATION_OFFSET_Y = ROTATION_OFFSET_Z = 0.0    
def _strip_blender_suffix(name):
    import re
    return re.sub(r'(\.(?:dds|png|tga|bmp|jpg|jpeg|webp))\.\d{3}$', r'\1', str(name), flags=re.IGNORECASE)


def _image_name_to_dds_name(img):
    """Blender image adını güvenli şekilde .dds basename'e çevirir."""
    name = ""
    try:
        if img.filepath:
            name = os.path.basename(bpy.path.abspath(img.filepath))
    except Exception:
        pass
    if not name:
        name = getattr(img, "name", "") or ""
    name = _strip_blender_suffix(os.path.basename(name))
    root, ext = os.path.splitext(name)
    if ext.lower() in [".png", ".tga", ".bmp", ".jpg", ".jpeg", ".webp", ".dds"]:
        return root + ".dds"
    return name + ".dds" if name else ""


def _parse_bw_visual_key(key):
    """bw_* custom prop key'inden gerçek visual property adı ve tipini döndürür."""
    prefixes = [
        ("bw_tex_", "Texture"),
        ("bw_bool_", "Bool"),
        ("bw_float_", "Float"),
        ("bw_int_", "Int"),
        ("bw_vector4_", "Vector4"),
        ("bw_vector_", "Vector4"),
    ]
    for prefix, prop_type in prefixes:
        if key.startswith(prefix) and len(key) > len(prefix):
            prop_name = key[len(prefix):]
            return prop_name, prop_type
    return None, None


def _iter_bw_visual_props(mat):
    """Sadece custom property kaynaklı export edilebilir BigWorld property'leri döndürür."""
    if not mat:
        return
    seen = set()
    for key in mat.keys():
        prop_name, prop_type = _parse_bw_visual_key(str(key))
        if not prop_name or not prop_type:
            continue
        # bw_dds_format_* gibi texture export ayarları visual property değildir.
        if prop_name.startswith("dds_format_"):
            continue
        if prop_name in seen:
            continue
        seen.add(prop_name)
        yield prop_name, prop_type


def _find_visual_node(mat, prop_name):
    """
    Sadece orijinal parametre node'unu bulur.
    Sonradan shading için eklenen PBS_Tank__... / Math / Mix / Separate gibi node'lar asla export'a girmez.
    Örnek: bw_float_g_maskBias -> node adları: g_maskBias veya maskBias.
    """
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None
    nodes = mat.node_tree.nodes
    aliases = [prop_name]
    if prop_name.startswith("g_"):
        aliases.append(prop_name[2:])
    # Bazı importlarda isim label'a yazılmış olabilir.
    aliases_lower = {a.lower() for a in aliases}

    for a in aliases:
        node = nodes.get(a)
        if node:
            return node

    for node in nodes:
        if node.name.startswith("PBS_Tank__"):
            continue
        nm = (node.name or "").lower()
        lb = (getattr(node, "label", "") or "").lower()
        if nm in aliases_lower or lb in aliases_lower:
            return node
    return None


def _find_node_by_exact_name_or_label(mat, names):
    """Node name/label tam eşleşmesiyle arar. Vector4 .xyz/.w sistemi için kullanılır."""
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None

    nodes = mat.node_tree.nodes
    for name in names:
        node = nodes.get(name)
        if node:
            return node

    names_lower = {str(n).lower() for n in names}
    for node in nodes:
        # Shader preview/helper node'ları parametre sayma.
        if (node.name or "").startswith(("PBS_Tank__", "LightOnly__")):
            continue
        nm = (node.name or "").lower()
        lb = (getattr(node, "label", "") or "").lower()
        if nm in names_lower or lb in names_lower:
            return node

    return None


def _custom_vector4_default(mat, prop_name):
    """Custom property'deki orijinal Vector4 değerini liste olarak döndürür."""
    if not mat:
        return [0.0, 0.0, 0.0, 0.0]

    for key in (f"bw_vector4_{prop_name}", f"bw_vector_{prop_name}"):
        if key in mat:
            raw = mat[key]
            if isinstance(raw, str):
                parts = raw.replace(",", " ").split()
                vals = []
                for p in parts:
                    try:
                        vals.append(float(p))
                    except Exception:
                        pass
            elif isinstance(raw, (list, tuple)):
                vals = []
                for v in raw:
                    try:
                        vals.append(float(v))
                    except Exception:
                        pass
            else:
                vals = []
            while len(vals) < 4:
                vals.append(0.0)
            return vals[:4]

    return [0.0, 0.0, 0.0, 0.0]


def _read_split_vector4_nodes(mat, prop_name):
    """
    Yeni import düzenini okur:
        prop.xyz -> Combine XYZ
        prop.w   -> Value

    Örnek:
        g_detailUVTiling.xyz + g_detailUVTiling.w -> g_detailUVTiling Vector4
    """
    aliases = [prop_name]
    if prop_name.startswith("g_"):
        aliases.append(prop_name[2:])

    xyz_names = [a + ".xyz" for a in aliases]
    w_names = [a + ".w" for a in aliases]

    xyz_node = _find_node_by_exact_name_or_label(mat, xyz_names)
    w_node = _find_node_by_exact_name_or_label(mat, w_names)

    # Yeni sistem yoksa None dön; eski RGB/CustomProp yolu çalışsın.
    if not xyz_node and not w_node:
        return None

    vals = _custom_vector4_default(mat, prop_name)

    if xyz_node:
        try:
            vals[0] = float(xyz_node.inputs["X"].default_value)
            vals[1] = float(xyz_node.inputs["Y"].default_value)
            vals[2] = float(xyz_node.inputs["Z"].default_value)
        except Exception:
            # Fallback: bazı node tiplerinde Vector output default_value olabilir.
            try:
                v = xyz_node.outputs[0].default_value
                vals[0] = float(v[0])
                vals[1] = float(v[1])
                vals[2] = float(v[2])
            except Exception:
                pass

    if w_node:
        try:
            vals[3] = float(w_node.outputs[0].default_value)
        except Exception:
            try:
                vals[3] = float(w_node.inputs[0].default_value)
            except Exception:
                pass

    return vals


def _as_bool_string(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "true" if float(value) > 0.5 else "false"
    s = str(value).strip().lower()
    if s in ["true", "yes", "on"]:
        return "true"
    if s in ["false", "no", "off", ""]:
        return "false"
    try:
        return "true" if float(s) > 0.5 else "false"
    except Exception:
        return "true" if s not in ["0", "none", "null"] else "false"


def _as_float_string(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else 0.0
    try:
        return f"{float(value):.6f}"
    except Exception:
        return f"{0.0:.6f}"


def _as_int_string(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (list, tuple)):
        value = value[0] if value else 0
    try:
        return str(int(round(float(value))))
    except Exception:
        try:
            return str(int(value))
        except Exception:
            return "0"


def _as_vector4_string(value):
    if isinstance(value, str):
        parts = value.replace(",", " ").split()
        vals = []
        for p in parts:
            try:
                vals.append(float(p))
            except Exception:
                pass
    elif isinstance(value, (list, tuple)):
        vals = []
        for v in value:
            try:
                vals.append(float(v))
            except Exception:
                pass
    else:
        vals = []
    while len(vals) < 4:
        vals.append(0.0)
    return f"{vals[0]:.6f} {vals[1]:.6f} {vals[2]:.6f} {vals[3]:.6f}"


def get_visual_property_value(mat, prop_name, prop_type):
    """
    Export kuralı:
    - Property listesi custom props'tan gelir: bw_float_*, bw_bool_*, bw_tex_* ...
    - Değer önce aynı parametre node'undan okunur.
    - Vector4 için yeni import düzeni desteklenir:
          prop.xyz -> Combine XYZ
          prop.w   -> Value
      Bu iki node tekrar tek Vector4 olarak yazılır.
    - Node yoksa custom prop orijinal değeri yazılır.
    - Bool XML'e daima true/false gider; shading node 1/0 olsa bile.
    - Texture için sadece o prop'un orijinal texture node'u okunur; helper texture node'ları export edilmez.
    """

    # Yeni Vector4 sistemi: g_detailUVTiling.xyz + g_detailUVTiling.w
    # Önce bunu oku; yoksa eski RGB/custom property fallback'i çalışır.
    if prop_type == "Vector4":
        split_vec = _read_split_vector4_nodes(mat, prop_name)
        if split_vec is not None:
            return _as_vector4_string(split_vec)

    node = _find_visual_node(mat, prop_name)

    if node:
        if prop_type == "Vector4" and node.type == 'RGB':
            rgba = node.outputs[0].default_value
            return _as_vector4_string(rgba)

        if prop_type in ["Float", "Int", "Bool"] and node.type == 'VALUE':
            val = node.outputs[0].default_value
            if prop_type == "Bool":
                return _as_bool_string(val)
            if prop_type == "Int":
                return _as_int_string(val)
            return _as_float_string(val)

        if prop_type == "Texture" and node.type == 'TEX_IMAGE':
            old_path = str(mat.get(f"bw_tex_{prop_name}", "")).replace('\\', '/')
            if node.image:
                base_name = _image_name_to_dds_name(node.image)
                if old_path and "/" in old_path:
                    return os.path.join(os.path.dirname(old_path), base_name).replace('\\', '/')
                return base_name or old_path

    # Node yoksa veya tipi yanlışsa custom property'den orijinal değeri koru.
    if mat:
        custom_key = f"bw_{prop_type.lower()}_{prop_name}"
        if prop_type == "Vector4":
            custom_key_alt = f"bw_vector_{prop_name}"
            if custom_key not in mat and custom_key_alt in mat:
                custom_key = custom_key_alt
        if prop_type == "Texture":
            custom_key = f"bw_tex_{prop_name}"

        if custom_key in mat:
            raw = mat[custom_key]
            if prop_type == "Bool":
                return _as_bool_string(raw)
            if prop_type == "Float":
                return _as_float_string(raw)
            if prop_type == "Int":
                return _as_int_string(raw)
            if prop_type == "Vector4":
                return _as_vector4_string(raw)
            return str(raw).replace('\\', '/')

    return None


def collect_visual_properties_from_custom_props(mat):
    """Visual XML'e yazılacak property listesini sadece bw_* custom prop şemasından üretir."""
    props_to_write = {}
    if not mat:
        return props_to_write
    for prop_name, prop_type in _iter_bw_visual_props(mat):
        val = get_visual_property_value(mat, prop_name, prop_type)
        if val is not None:
            props_to_write[prop_name] = (prop_type, val)
    return props_to_write

# --- VISUAL PROPERTY DEFINITIONS ---
try:
    from .common.consts import visual_property_descr_dict
    from .common.export_utils import set_nodes
except ImportError:
    class VisualProp:
        def __init__(self, t): self.type = t
    visual_property_descr_dict = {
        'normalMap': VisualProp('Texture'), 'metallicGlossMap': VisualProp('Texture'),
        'diffuseMap': VisualProp('Texture'), 'doubleSided': VisualProp('Bool'),
        'alphaReference': VisualProp('Int'), 'alphaTestEnable': VisualProp('Bool'),
        'metallicDetailMap': VisualProp('Texture'), 'g_detailUVTiling': VisualProp('Vector4'),
        'g_detailParams': VisualProp('Vector4'), 'g_useDetailMetallic': VisualProp('Bool'),
        'g_heatMap': VisualProp('Texture'), 'g_heatColorGradient': VisualProp('Texture'),
        'g_heatEmissionCoefficient': VisualProp('Float'), 'colorIdMap': VisualProp('Texture'),
        'g_useNormalPackDXT1': VisualProp('Bool')
    }

def set_nodes(nodes, elem, doc):
    if not nodes: return
    from mathutils import Matrix
    for name, data in nodes.items():
        node_elem = doc.createElement('node')
        ident = doc.createElement('identifier'); ident.appendChild(doc.createTextNode(name))
        node_elem.appendChild(ident); transform = doc.createElement('transform')
        
        m_list = data.get("matrix", [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
        m = Matrix(m_list)
        
        C = Matrix((
            (1, 0, 0, 0),
            (0, 0, 1, 0),
            (0, 1, 0, 0),
            (0, 0, 0, 1)
        ))
        
        m_bw = C @ m @ C.inverted()
    
        rows = []
        for i in range(4):
            v = m_bw.col[i]
            rows.append(f"{v.x:.6f} {v.y:.6f} {v.z:.6f}")
            
        for i, row_txt in enumerate(rows):
            row = doc.createElement(f'row{i}'); row.appendChild(doc.createTextNode(row_txt))
            transform.appendChild(row)
            
        node_elem.appendChild(transform); elem.appendChild(node_elem)
        if 'children' in data: set_nodes(data['children'], node_elem, doc)

def get_real_mesh_objects(selected_objs):
    if not selected_objs: return []
    if not isinstance(selected_objs, list): selected_objs = [selected_objs]
    return [o for o in selected_objs if hasattr(o, 'type') and o.type == 'MESH']

def get_armature(mesh_objs):
    for obj in mesh_objs:
        if obj.parent and obj.parent.type == 'ARMATURE': return obj.parent
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE' and mod.object: return mod.object
    return None

def get_pose_bone_matrix(arm_obj, bone_name):
    if arm_obj and bone_name in arm_obj.pose.bones:
        return arm_obj.matrix_world @ arm_obj.pose.bones[bone_name].matrix
    return None

# --- IMAGE TO DDS CONVERTER (HYBRID) ---
def convert_to_dds(img_path, format_arg="BC1_UNORM"):
    addon_dir = os.path.dirname(__file__)
    texconv_path = os.path.join(addon_dir, "texconv.exe")
    
    if not os.path.exists(texconv_path):
        print(f"[Warning] texconv.exe not found! Leaving as original: {img_path}")
        return False
        
    try:
        subprocess.run(
            [texconv_path, "-f", format_arg, "-sepalpha", "-y", "-o", os.path.dirname(img_path), img_path],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            check=True
        )
        
        if os.path.exists(img_path):
            os.remove(img_path)
        return True
    except Exception as e:
        print(f"[Error] DDS Conversion Failed ({img_path}) ile Format: {format_arg}: {e}")
        return False

class BigWorldModelExporter:
    def export(self, export_obj, model_filepath: str, export_info: dict):
        mesh_objs = get_real_mesh_objects(export_obj)
        if not mesh_objs: raise RuntimeError("No valid Mesh found!")
        
        FORCED_FILENAME, TEXTURE_BASENAME, TANK_BASE_PATH, GAME_REL_DIR = get_universal_config(mesh_objs[0], model_filepath, export_info)
        
        all_bone_names = set()
        for o in mesh_objs:
            for vg in o.vertex_groups:
                if "blendbone" in vg.name.lower(): all_bone_names.add(vg.name)
        bone_palette = sorted(list(all_bone_names), reverse=True)

        dir_name = os.path.dirname(model_filepath)
        final_model_path, final_visual_path, final_primitives_path = [os.path.join(dir_name, FORCED_FILENAME + ext) for ext in [".model", ".visual_processed", ".primitives_processed"]]

        mesh_exporter = ExportDataMesh(final_primitives_path, FORCED_FILENAME)
        
        primary_fx_path = "shaders/std_effects/PBS_tank_skinned.fx"
        if export_info.get("use_manual_shader", False):
            primary_fx_path = export_info.get("manual_shader", primary_fx_path)
        else:
            for obj in mesh_objs:
                if obj.data.materials and len(obj.data.materials) > 0:
                    bmat = obj.data.materials[0]
                    if bmat:
                        if "bw_custom_fx" in bmat:
                            primary_fx_path = str(bmat["bw_custom_fx"])
                            break
                        elif hasattr(bmat, "BigWorld_Shader_Path") and bmat.BigWorld_Shader_Path:
                            primary_fx_path = bmat.BigWorld_Shader_Path
                            break

        exact_fx = primary_fx_path.replace("\\", "/")
        
        auto_vf = "set3/xyznuviiiwwtbpc"
        auto_space = "LOCAL"
        auto_tawso = True
        
        if exact_fx in SHADER_PROPERTIES_MAP:
            auto_tawso = SHADER_PROPERTIES_MAP[exact_fx]["tawso"]
            auto_space = SHADER_PROPERTIES_MAP[exact_fx]["space"]
            
            for v_format, supported_shaders in VERTEX_SHADER_MAP.items():
                if exact_fx in supported_shaders:
                    auto_vf = v_format
                    break
        else:
            if "skinned" not in exact_fx.lower():
                auto_vf, auto_space, auto_tawso = "set3/xyznuvtbpc", "GLOBAL", False

        if not export_info.get("use_manual_vf"):
            has_bones = False
            for obj in mesh_objs:
                for vg in obj.vertex_groups:
                    if "blendbone" in vg.name.lower():
                        has_bones = True
                        break
                if has_bones: break
                
            if has_bones:
                auto_vf = "set3/xyznuviiiwwtbpc"
                auto_space = "LOCAL"

        final_vf = export_info.get("manual_vf") if export_info.get("use_manual_vf") else auto_vf
        final_space = export_info.get("manual_space") if export_info.get("use_manual_space") else auto_space
        final_tawso = export_info.get("manual_tawso") if export_info.get("use_manual_tawso") else auto_tawso

        mesh_exporter.vertex_format = final_vf
        mesh_exporter.coordinate_mode = "LOCAL" 
        user_wants_vcolors = export_info.get("export_vcolors", True)

        mesh_groups_by_obj = {} 
        mesh_bones_by_obj = {}  
        mesh_tawso_by_obj = {}  # Import tarafindan mesh objesine yazilan bw_renderSet_tawso burada tutulur.
        global_has_colors = False
        bb_min, bb_max = Vector((99999.0, 99999.0, 99999.0)), Vector((-99999.0, -99999.0, -99999.0))

        armature_obj = get_armature(mesh_objs)
        
        import re
        used_mesh_names = set() 
        
        for obj in mesh_objs:
            base_name = re.sub(r'\.\d{3}$', '', obj.name) 
            
            final_name = base_name
            counter = 1
            while final_name in used_mesh_names:
                final_name = f"{base_name}_{counter:03d}"
                counter += 1
                
            used_mesh_names.add(final_name)
            
            mesh_exporter.add_mesh_section(final_name)
            obj_clean_name = mesh_exporter.current_mesh
            mesh_groups_by_obj[obj_clean_name] = []
            

            # Import edilen .visual renderSet'indeki treatAsWorldSpaceObject degeri varsa onu koru.
            # Yoksa None kalsin; visual export sirasinda shader listesindeki auto_tawso fallback olarak kullanilir.
            if "bw_renderSet_tawso" in obj:
                mesh_tawso_by_obj[obj_clean_name] = (_as_bool_string(obj["bw_renderSet_tawso"]) == "true")
            else:
                mesh_tawso_by_obj[obj_clean_name] = None
            obj_bones = set()
            for vg in obj.vertex_groups:
                if "blendbone" in vg.name.lower():
                    if vg.name in bone_palette:
                        obj_bones.add(vg.name)
            mesh_bones_by_obj[obj_clean_name] = [b for b in bone_palette if b in obj_bones]
            
            local_v_offset = local_i_offset = 0 
            
            vg_id_map = {vg.index: bone_palette.index(vg.name) for vg in obj.vertex_groups if vg.name in bone_palette}
            mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
            mesh.calc_loop_triangles()
            if mesh.uv_layers.active:
                try: mesh.calc_tangents()
                except: pass 
            uv_layer = mesh.uv_layers.active.data[:] if mesh.uv_layers.active else None
            
            root_matrix = export_info.get("root_matrix", Matrix())
            root_inv_matrix = root_matrix.inverted()
            
            user_rot = Euler((math.radians(ROTATION_OFFSET_X), 0, 0), 'XYZ').to_matrix().to_4x4()
            final_matrix = user_rot @ obj.matrix_world
            rotation_matrix = final_matrix.to_3x3()

            color_layer = None
            if obj.data.color_attributes and obj.data.color_attributes.active:
                color_layer = obj.data.attributes[obj.data.color_attributes.active.name]
            
            color_data_flat = []
            color_domain = 'POINT'
            
            if color_layer and user_wants_vcolors:
                global_has_colors = True
                mesh_exporter.export_vertex_colors = True
                color_domain = color_layer.domain
                count = len(obj.data.loops) if color_domain == 'CORNER' else len(obj.data.vertices)
                color_data_flat = [1.0] * (count * 4) 
                try: color_layer.data.foreach_get("color", color_data_flat)
                except: pass
            
            tris_by_mat = {}
            for tri in mesh.loop_triangles: tris_by_mat.setdefault(tri.material_index, []).append(tri)
            
            for mat_idx in sorted(tris_by_mat.keys()):
                bmat = mesh.materials[mat_idx] if mat_idx < len(mesh.materials) else None
                mat_name = bmat.name if bmat else f"mat_{mat_idx}"
                
                group_fx_path = primary_fx_path
                if not export_info.get("use_manual_shader", False):
                    if bmat:
                        if "bw_custom_fx" in bmat:
                            group_fx_path = str(bmat["bw_custom_fx"])
                        elif hasattr(bmat, "BigWorld_Shader_Path") and bmat.BigWorld_Shader_Path:
                            group_fx_path = bmat.BigWorld_Shader_Path
                
                group_data = {
                    'mat_name': mat_name,
                    'bmat': bmat, 
                    'fx': group_fx_path,
                    'indices': [], 'startVertex': local_v_offset, 'startIndex': local_i_offset, 
                    'nVertices': 0, 'nPrimitives': 0
                }
                local_v_cache = {} 
                
                for tri in tris_by_mat[mat_idx]:
                    for loop_idx in reversed(tri.loops):
                        loop_data, vert = mesh.loops[loop_idx], mesh.vertices[mesh.loops[loop_idx].vertex_index]
                        
                        world_co = final_matrix @ vert.co
                        world_n = rotation_matrix @ loop_data.normal

                        if global_has_colors and color_data_flat:
                            idx = loop_idx if color_domain == 'CORNER' else vert.index
                            base_i = idx * 4
                            r, g, b, a = color_data_flat[base_i], color_data_flat[base_i+1], color_data_flat[base_i+2], color_data_flat[base_i+3]
                            rgba = (r, g, b, a)
                        else:
                            rgba = (0, 0, 0, 0)
                        out_bones = []
                        if final_space == "GLOBAL":
                            local_co = root_inv_matrix @ world_co
                            local_n = root_inv_matrix.to_3x3() @ world_n
                        else:
                            bone_name = None
                            if vert.groups:
                                g_list = sorted(vert.groups, key=lambda g: g.weight, reverse=True)[:1]
                                if g_list and g_list[0].group in vg_id_map:
                                    bone_name = bone_palette[vg_id_map[g_list[0].group]]
                            
                            has_valid_bone = bone_name and armature_obj and (bone_name in armature_obj.pose.bones)

                            if has_valid_bone:
                                valid_groups = []
                                if vert.groups:
                                    g_list = sorted(vert.groups, key=lambda g: g.weight, reverse=True)
                                    valid_groups = [g for g in g_list if g.group in vg_id_map][:3]
                                
                                active_groups = [g for g in valid_groups if g.weight > 0.0]
                                
                                if len(active_groups) > 1:
                                    total_weight = sum(g.weight for g in active_groups)
                                    blended_mat = Matrix(((0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)))
                                    for g in active_groups:
                                        mat = get_pose_bone_matrix(armature_obj, bone_palette[vg_id_map[g.group]]) or Matrix()
                                        blended_mat += mat * (g.weight / total_weight)
                                    try: inv_m = blended_mat.inverted()
                                    except:
                                        fallback_mat = get_pose_bone_matrix(armature_obj, bone_palette[vg_id_map[active_groups[0].group]])
                                        inv_m = fallback_mat.inverted() if fallback_mat else Matrix()
                                    local_co = inv_m @ world_co
                                    local_n = inv_m.to_3x3() @ world_n
                                    if local_n.length > 0.0001: local_n.normalize()
                                        
                                else:
                                    primary_bone_name = bone_name
                                    if active_groups: primary_bone_name = bone_palette[vg_id_map[active_groups[0].group]]
                                    elif valid_groups: primary_bone_name = bone_palette[vg_id_map[valid_groups[0].group]]
                                    primary_bone_mat = get_pose_bone_matrix(armature_obj, primary_bone_name)
                                    
                                    if primary_bone_mat:
                                        inv_m = primary_bone_mat.inverted()
                                        local_co = inv_m @ world_co
                                        local_n = inv_m.to_3x3() @ world_n
                                    else:
                                        local_co = root_inv_matrix @ world_co
                                        local_n = root_inv_matrix.to_3x3() @ world_n
                                        
                                for g in valid_groups:
                                    out_bones.append((vg_id_map[g.group], g.weight))
                            else:
                                local_co = root_inv_matrix @ world_co
                                local_n = root_inv_matrix.to_3x3() @ world_n


                        # Bounding Box ve Cache
                        pos_bw = (local_co.x, local_co.z, local_co.y) 
                        for i in range(3):
                            bb_min[i], bb_max[i] = min(bb_min[i], pos_bw[i] - 0.01), max(bb_max[i], pos_bw[i] + 0.01)

                        uv = uv_layer[loop_idx].uv if uv_layer else (0.0, 0.0)
                        
                        world_tang = world_binorm = None
                        if uv_layer:
                            world_tang = rotation_matrix @ loop_data.tangent
                            world_binorm = world_n.cross(world_tang).normalized()

                        bone_cache = tuple((b[0], round(b[1], 4)) for b in out_bones)
                        v_data_for_cache = (
                            round(local_co.x, 4), round(local_co.y, 4), round(local_co.z, 4),
                            round(local_n.x, 4), round(local_n.y, 4), round(local_n.z, 4),
                            round(uv[0], 4), round(uv[1], 4),
                            bone_cache, rgba
                        )

                        if v_data_for_cache not in local_v_cache:
                            v_idx = mesh_exporter.add_vertex(
                                pos=local_co, norm=local_n, uv=uv, 
                                bones=out_bones, rgba=rgba, 
                                tang=world_tang, binorm=world_binorm
                            )
                            local_v_cache[v_data_for_cache] = v_idx
                            
                        group_data['indices'].append(local_v_cache[v_data_for_cache])

                group_data['nVertices'] = len(local_v_cache)
                group_data['nPrimitives'] = len(group_data['indices']) // 3
                
                mesh_exporter.meshes[obj_clean_name]['groups'].append(group_data)
                mesh_groups_by_obj[obj_clean_name].append(group_data)
                
                local_v_offset += group_data['nVertices']
                local_i_offset += len(group_data['indices'])

        # --- EXPORTING MODELS (.primitives, .visual, .model) ---
        if export_info.get("export_models", True):
            
            mesh_exporter.export()

            # --- EXPORT: .visual ---
            impl = getDOMImplementation()
            visual_root_tag = FORCED_FILENAME + ".visual_processed"
            doc = impl.createDocument(None, visual_root_tag, None)
            root = doc.documentElement
            
            if 'nodes' in export_info: set_nodes(export_info['nodes'], root, doc)
            for obj_clean_name, pg_list in mesh_groups_by_obj.items():
                
                if not pg_list:
                    continue
                if export_info.get("use_manual_tawso"):
                    rs_tawso = final_tawso
                else:
                    imported_tawso = mesh_tawso_by_obj.get(obj_clean_name, None)
                    rs_tawso = imported_tawso if imported_tawso is not None else auto_tawso

                rs_space = final_space if export_info.get("use_manual_space") else auto_space
                
                if not export_info.get("use_manual_space"):
                    if rs_tawso == True:
                        rs_space = "LOCAL"
                    if len(mesh_bones_by_obj.get(obj_clean_name, [])) > 0:
                        rs_space = "LOCAL"
                    
                allowed_shaders = VERTEX_SHADER_MAP.get(final_vf, [])
                
                for pg in pg_list:
                    fx_name = pg['fx'].replace("\\", "/")
                    
                    if allowed_shaders and fx_name not in allowed_shaders:
                        print(f"[Wotcuk Auto-Fix] Uyumsuz shader tespit edildi: {fx_name}")
                        print(f" -> {final_vf} formatı için {allowed_shaders[0]} olarak değiştirildi.")
                        pg['fx'] = allowed_shaders[0]

                tawso_str = 'true' if rs_tawso else 'false'

                rs = doc.createElement('renderSet'); root.appendChild(rs)
                rs.appendChild(doc.createElement('treatAsWorldSpaceObject')).appendChild(doc.createTextNode(tawso_str))
                
                if rs_space == "GLOBAL":
                    rs.appendChild(doc.createElement('node')).appendChild(doc.createTextNode('Scene Root'))
                else:
                    for bb_name in bone_palette: 
                        rs.appendChild(doc.createElement('node')).appendChild(doc.createTextNode(bb_name))
                    
                geo = doc.createElement('geometry'); rs.appendChild(geo)
                
                v_name = "vertices" if obj_clean_name == "vertices" else f"{obj_clean_name}.vertices"
                i_name = "indices" if obj_clean_name == "vertices" else f"{obj_clean_name}.indices"
                c_name = "colour" if obj_clean_name == "vertices" else f"{obj_clean_name}.colour"
                
                geo.appendChild(doc.createElement('vertices')).appendChild(doc.createTextNode(v_name))
                geo.appendChild(doc.createElement('primitive')).appendChild(doc.createTextNode(i_name))
                
                if global_has_colors and len(mesh_exporter.meshes[obj_clean_name]['colors']) > 0:
                    geo.appendChild(doc.createElement('stream')).appendChild(doc.createTextNode(c_name))
                    
                for i, pg in enumerate(pg_list):
                    pge = doc.createElement('primitiveGroup'); pge.appendChild(doc.createTextNode(str(i))); geo.appendChild(pge)
                    me = doc.createElement('material'); pge.appendChild(me); me.appendChild(doc.createElement('identifier')).appendChild(doc.createTextNode(pg['mat_name']))
                    me.appendChild(doc.createElement('fx')).appendChild(doc.createTextNode(pg['fx']))
                    
                    bmat = pg.get('bmat')
                    props_to_write = {}
                    
                    if bmat:
                        # Sadece Custom Properties içindeki bw_float_*, bw_bool_*, bw_tex_*, bw_int_*, bw_vector4_* export edilir.
                        # Shading tarafında sonradan eklenen PBS_Tank__/Math/Mix/Separate/helper texture node'ları buraya asla girmez.
                        props_to_write = collect_visual_properties_from_custom_props(bmat)

                    if props_to_write:
                        for p_name, (p_type, p_val) in props_to_write.items():
                            prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(p_name)); me.appendChild(prop)
                            prop.appendChild(doc.createElement(p_type)).appendChild(doc.createTextNode(p_val))
                    else:
                        default_bools = [('doubleSided','Bool','false'),('alphaReference','Int','0'),('g_useNormalPackDXT1','Bool','false')]
                        alpha_val = get_visual_property_value(bmat, 'alphaTestEnable', 'Bool') if bmat else 'false'
                        if alpha_val is None: alpha_val = 'false'
                        default_bools.insert(1, ('alphaTestEnable', 'Bool', alpha_val))
                        for p_n, p_t, p_v in default_bools:
                             prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(p_n)); me.appendChild(prop)
                             prop.appendChild(doc.createElement(p_t)).appendChild(doc.createTextNode(p_v))
                             
                        for p, s in [('diffuseMap','AM'),('normalMap','ANM'),('metallicGlossMap','GMM'),('excludeMaskAndAOMap','AO'),('colorIdMap','ID')]:
                            prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(p)); me.appendChild(prop)
                            prop.appendChild(doc.createElement('Texture')).appendChild(doc.createTextNode(f"{TANK_BASE_PATH}/{TEXTURE_BASENAME}_{s}.dds"))
                        prop = doc.createElement('property'); prop.appendChild(doc.createTextNode('metallicDetailMap')); me.appendChild(prop)
                        prop.appendChild(doc.createElement('Texture')).appendChild(doc.createTextNode("vehicles/russian/Tank_detail/Details_map.dds"))
                        for p_n, p_v in [('g_detailUVTiling',"4.000000 4.000000 0.000000 0.000000"),('g_detailParams',"0.000000 0.000000 0.000000 0.000000")]:
                            prop = doc.createElement('property'); prop.appendChild(doc.createTextNode(p_n)); me.appendChild(prop)
                            prop.appendChild(doc.createElement('Vector4')).appendChild(doc.createTextNode(p_v))
                        prop = doc.createElement('property'); prop.appendChild(doc.createTextNode('g_useDetailMetallic')); me.appendChild(prop)
                        prop.appendChild(doc.createElement('Bool')).appendChild(doc.createTextNode("true"))
                
            bb = doc.createElement('boundingBox'); root.appendChild(bb)
            bb.appendChild(doc.createElement('min')).appendChild(doc.createTextNode(f"{bb_min.x:.3f} {bb_min.y:.3f} {bb_min.z:.3f}"))
            bb.appendChild(doc.createElement('max')).appendChild(doc.createTextNode(f"{bb_max.x:.3f} {bb_max.y:.3f} {bb_max.z:.3f}"))
            with open(final_visual_path, 'w') as f: f.write(doc.toprettyxml())
            
            mdm = impl.createDocument(None, 'root', None); mroot = mdm.documentElement
            
            exp_lods = export_info.get("wot_export_with_lods", False)
            exp_lod = export_info.get("wot_export_lod", "lod0")
            exp_parent = export_info.get("wot_export_has_parent", False)
            exp_extent = export_info.get("wot_export_extent", 20.0)
            
            if "wot_base_path" in export_info:
                base_path = export_info["wot_base_path"]
                if not base_path.endswith('/'): base_path += '/'
                
                if exp_lods:
                    if exp_parent:
                        current_lod_num = int(exp_lod.replace("lod", ""))
                        parent_lod = f"lod{current_lod_num + 1}"
                        parent_path = f"{base_path}{parent_lod}/{FORCED_FILENAME}"
                        mroot.appendChild(mdm.createElement('parent')).appendChild(mdm.createTextNode(parent_path))
                        mroot.appendChild(mdm.createElement('extent')).appendChild(mdm.createTextNode(f"{exp_extent:.6f}"))
                    nodefull_path = f"{base_path}{exp_lod}/{FORCED_FILENAME}"
                else:
                    nodefull_path = f"{base_path}lod0/{FORCED_FILENAME}"
            else:
                base_path = GAME_REL_DIR
                if not base_path.endswith('/'): base_path += '/'
                nodefull_path = f"{base_path}{FORCED_FILENAME}"
                
            mroot.appendChild(mdm.createElement('nodefullVisual')).appendChild(mdm.createTextNode(nodefull_path))
            
            mbb = mdm.createElement('visibilityBox'); mroot.appendChild(mbb)
            mbb.appendChild(mdm.createElement('min')).appendChild(mdm.createTextNode(f"{bb_min.x:.3f} {bb_min.y:.3f} {bb_min.z:.3f}"))
            mbb.appendChild(mdm.createElement('max')).appendChild(mdm.createTextNode(f"{bb_max.x:.3f} {bb_max.y:.3f} {bb_max.z:.3f}"))
            
            mroot.appendChild(mdm.createElement('tank')).appendChild(mdm.createTextNode("true"))
            with open(final_model_path, 'w') as f: f.write(mdm.toprettyxml())

        # --- EXPORT: TEXTURES ---
        if export_info.get("export_textures", True):
            export_dir = os.path.dirname(model_filepath)
            processed_images = set() 
            
            for pg_list in mesh_groups_by_obj.values():
                for pg in pg_list:
                    bmat = pg.get('bmat')
                    if not bmat or not bmat.use_nodes: continue
                    
                    for node in bmat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            try:
                                img = node.image
                                _ = img.name 
                                if img.size[0] == 0 or img.size[1] == 0:
                                    continue
                            except ReferenceError:
                                continue
                                
                            if img.name in processed_images:
                                continue
                                
                            processed_images.add(img.name)
                            
                            original_dds_name = img.name.replace(".tga", ".dds").replace(".png", ".dds")
                            target_rel_path = ""
                            prop_exact_name = ""  
                            
                            for key, val in bmat.items():
                                if key.startswith("bw_tex_") and original_dds_name.lower() in str(val).lower():
                                    target_rel_path = str(val).replace('\\', '/')
                                    prop_exact_name = key[7:] 
                                    break
                                    
                            if target_rel_path:
                                norm_export = export_dir.replace('\\', '/')
                                
                                if '/res_mods/' in norm_export:
                                    parts = norm_export.split('/res_mods/')
                                    rest = parts[1].split('/')
                                    
                                    if len(rest) > 0 and rest[0]:
                                        version_folder = rest[0]
                                        base_root = f"{parts[0]}/res_mods/{version_folder}"
                                        final_tex_path = os.path.join(base_root, target_rel_path).replace('\\', '/')
                                    else:
                                        final_tex_path = os.path.join(export_dir, os.path.basename(target_rel_path)).replace('\\', '/')
                                else:
                                    final_tex_path = os.path.join(export_dir, os.path.basename(target_rel_path)).replace('\\', '/')
                            else:
                                final_tex_path = os.path.join(export_dir, img.name).replace('\\', '/')
                            
                            is_png = img.name.lower().endswith(".png")
                            temp_ext = ".png" if is_png else ".tga"
                            blender_format = 'PNG' if is_png else 'TARGA'

                            final_tex_path_temp = final_tex_path.replace(".dds", temp_ext).replace(".DDS", temp_ext)
                            os.makedirs(os.path.dirname(final_tex_path_temp), exist_ok=True)
                            
                            scene = bpy.context.scene
                            old_format = scene.render.image_settings.file_format
                            old_color_mode = scene.render.image_settings.color_mode
                            old_view_transform = scene.view_settings.view_transform
                            
                            try:
                                scene.render.image_settings.file_format = blender_format
                                scene.render.image_settings.color_mode = 'RGBA'
                                scene.view_settings.view_transform = 'Raw'
                                
                                img.save_render(filepath=final_tex_path_temp, scene=scene)
                                
                                forced_format = bmat.get(f"bw_dds_format_{prop_exact_name}", "")
                                if not forced_format:
                                    if "_anm" in final_tex_path_temp.lower(): forced_format = "BC7_UNORM"
                                    else: forced_format = "BC1_UNORM"
                                    
                                convert_to_dds(final_tex_path_temp, forced_format)
                            except Exception as outer_e:
                                print(f"[Error] Failed to process texture {img.name}: {outer_e}")
                            finally:
                                scene.render.image_settings.file_format = old_format
                                scene.render.image_settings.color_mode = old_color_mode
                                scene.view_settings.view_transform = old_view_transform