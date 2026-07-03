# -*- coding: utf-8 -*-
"""
The .dds files using shaders 7d4a896b5aac80ba-ps.txt and 3998677a26377018-vs.txt, along with their input parameters,
 were retrieved from the game using 3dmigoto. The retrieved information and texture properties were fed into the chat GPT file,
 and a shader was requested. After approximately 15-16 attempts and modifications, the current version was obtained, 
but even this version is still not sufficiently consistent. Therefore, I am leaving the AI ​​comments in this code.
PBS_tank.fx için Blender node kurulumu.

V7: GMM akışı korunur. AlphaTest sadece sahnede alphaTestEnable node'u varsa çalışır. V6'daki yanlış T2DA Blue->Bump kaldırıldı. T2DA shaderdaki gibi iki sample/micro-detail mantığına yaklaştırıldı: A+G normal, B overlay/intensity, ikinci sample blend.

Bu dosya özellikle şu shader/material yolu için yazıldı:
    shaders/std_effects/PBS_tank.fx
    tank_turret_01 / Black_Rock turret

Kullanılan ana texture node adları:
    diffuseMap              -> *_AM.dds
    normalMap               -> *_ANM.dds  (normal X = Alpha, normal Y = Green; alpha-test = Red)
    metallicGlossMap        -> *_GMM.dds  (R = metallic/base metal, G = gloss, B = wear/helper)
    excludeMaskAndAOMap     -> *_AO.dds
    metallicDetailMap       -> Details_map.dds
    DetailsMaps             -> Detail_T2DA.dds / micro detail atlas

Not:
Blender standart node sistemi Texture2DArray layer seçimini birebir yapamadığı için
Detail_T2DA tarafı 2D texture olarak yaklaşık kurulur. Ancak .visual içindeki
parametreler, g_detailParams decode bilgisi ve tüm güç/bias değerleri node ağında
kullanılır / görünür bırakılır.
"""

try:
    import bpy
except Exception:
    bpy = None


# -----------------------------------------------------------------------------
# Shader sabitleri: .visual_processed içindeki değerler
# -----------------------------------------------------------------------------
DEFAULTS = {
    "g_detailPowerGloss": 0.35,
    "g_detailPowerAlbedo": 0.11,
    "g_maskBias": 0.18,
    "g_detailPower": 5.0,
    "g_useDetailMetallic": 1.0,
    "g_defaultDetail": 0.0,
    "alphaReference": 128.0,
    "alphaTestEnable": 0.0,
    # alphaTestEnable node yoksa alpha bağlanmaz.
    # Blender DDS importunda/kanal yorumunda metallicDetailMap R/B ters görünüyorsa 1.
    # Bu v5'te varsayılan 1: GMM'ye dokunmadan sadece Details_map R/B swizzle edilir.
    "pbs_tank_detail_rb_swap": 1.0,
    # Detail_T2DA normal gücü. Shaderdaki micro-detail zırh pütürlerini daha belirgin yapmak için.
    "pbs_tank_micro_normal_strength": 0.12,
    "pbs_tank_t2da_overlay_strength": 0.55,
    "pbs_tank_t2da_second_sample_blend": 0.35,
    "g_dirtLevel": 0.46,
    "g_glossMin": 0.22,
    "g_glossMax": 0.75,
}

DEFAULT_DETAIL_UV_TILING = (8.416438, 4.208219, 0.0, 0.0)
DEFAULT_TILING_RATIO = (1.0, 0.5)

# .visual g_detailParams uint4x4
DEFAULT_DETAIL_PARAMS = [
    67064832, 999948288, 134179840, 926089216,
    362372997, 982466120, 4261412864, 0,
    4261412864, 0, 921196574, 942211072,
    436168704, 966393856, 4261412864, 0,
]

CUSTOM_PREFIX = "PBS_Tank__"


# -----------------------------------------------------------------------------
# Genel node yardımcıları
# -----------------------------------------------------------------------------
def _as_float(v, default=0.0):
    try:
        if isinstance(v, (list, tuple)):
            return float(v[0])
        return float(v)
    except Exception:
        return float(default)


def _mat_get_any(mat, names, default):
    for key in names:
        try:
            if key in mat:
                return mat[key]
        except Exception:
            pass
    return default


def _socket_by_names(sockets, names):
    for name in names:
        try:
            return sockets[name]
        except Exception:
            pass
    for s in sockets:
        if s.name in names or getattr(s, "identifier", "") in names:
            return s
    return None


def _out(node, *names):
    if not node:
        return None
    return _socket_by_names(node.outputs, names)


def _inp(node, *names):
    if not node:
        return None
    return _socket_by_names(node.inputs, names)


def _link(links, out_socket, in_socket):
    if out_socket is None or in_socket is None:
        return False
    try:
        # Node inputları tek link kabul ettiği için eski import bağlantılarını temizle.
        for old_link in list(getattr(in_socket, "links", [])):
            try:
                links.remove(old_link)
            except Exception:
                pass
        links.new(out_socket, in_socket)
        return True
    except Exception:
        return False


def _new(nodes, bl_idname, name, loc=(0, 0)):
    n = nodes.new(bl_idname)
    n.name = name
    n.label = name.replace(CUSTOM_PREFIX, "")
    n.location = loc
    return n


def _remove_old_custom_nodes(nodes):
    for n in list(nodes):
        if n.name.startswith(CUSTOM_PREFIX):
            try:
                nodes.remove(n)
            except Exception:
                pass


def _get_value(mat, nodes, name, default):
    """Önce node, sonra material custom property, en son DEFAULTS."""
    node = nodes.get(name)
    if node and len(node.outputs):
        try:
            return _as_float(node.outputs[0].default_value, default)
        except Exception:
            pass

    lower = name.lower()
    candidates = [
        name,
        lower,
        "bw_" + name,
        "bw_" + lower,
        "bw_float_" + name,
        "bw_float_" + lower,
        "bw_int_" + name,
        "bw_int_" + lower,
        "bw_bool_" + name,
        "bw_bool_" + lower,
    ]
    return _as_float(_mat_get_any(mat, candidates, default), default)


def _get_vector(mat, nodes, name, default_tuple):
    node = nodes.get(name)
    if node and len(node.outputs):
        try:
            v = node.outputs[0].default_value
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                return tuple(float(x) for x in v)
        except Exception:
            pass

    candidates = [
        name,
        name.lower(),
        "bw_" + name,
        "bw_" + name.lower(),
        "bw_vector_" + name,
        "bw_vector_" + name.lower(),
    ]
    v = _mat_get_any(mat, candidates, default_tuple)
    if isinstance(v, str):
        parts = v.replace(",", " ").split()
        try:
            return tuple(float(p) for p in parts)
        except Exception:
            return tuple(default_tuple)
    if isinstance(v, (list, tuple)):
        try:
            return tuple(float(x) for x in v)
        except Exception:
            return tuple(default_tuple)
    return tuple(default_tuple)


def _find_node(nodes, *names):
    for name in names:
        node = nodes.get(name)
        if node:
            return node
    # Bazı importerlar node isimlerini .001 gibi uzatabiliyor.
    low_names = [n.lower() for n in names]
    for node in nodes:
        node_name = node.name.lower()
        node_label = getattr(node, "label", "").lower()
        for wanted in low_names:
            if node_name.startswith(wanted) or node_label.startswith(wanted):
                return node
    return None


def _set_image_colorspace(node, name):
    if not node:
        return
    try:
        if node.image:
            node.image.colorspace_settings.name = name
    except Exception:
        pass


def _set_non_color(*nodes_):
    for n in nodes_:
        _set_image_colorspace(n, "Non-Color")


def _set_srgb(*nodes_):
    for n in nodes_:
        _set_image_colorspace(n, "sRGB")


def _math(nodes, links, op, a=None, b=None, value_a=None, value_b=None,
          name="Math", loc=(0, 0), clamp=False):
    n = _new(nodes, "ShaderNodeMath", CUSTOM_PREFIX + name, loc)
    n.operation = op
    try:
        n.use_clamp = bool(clamp)
    except Exception:
        pass
    if value_a is not None:
        n.inputs[0].default_value = value_a
    if value_b is not None and len(n.inputs) > 1:
        n.inputs[1].default_value = value_b
    if a is not None:
        _link(links, a, n.inputs[0])
    if b is not None and len(n.inputs) > 1:
        _link(links, b, n.inputs[1])
    return n


def _clamp01(nodes, links, sock, name, loc=(0, 0)):
    return _math(nodes, links, "MULTIPLY", a=sock, value_b=1.0,
                 name=name, loc=loc, clamp=True).outputs[0]


def _sep_color(nodes, links, color_socket, name, loc=(0, 0)):
    try:
        n = _new(nodes, "ShaderNodeSeparateColor", CUSTOM_PREFIX + name, loc)
        _link(links, color_socket, _inp(n, "Color"))
        return n
    except Exception:
        n = _new(nodes, "ShaderNodeSeparateRGB", CUSTOM_PREFIX + name, loc)
        _link(links, color_socket, _inp(n, "Image"))
        return n


def _combine_color(nodes, links, r=None, g=None, b=None, a=None, name="CombineColor", loc=(0, 0)):
    try:
        n = _new(nodes, "ShaderNodeCombineColor", CUSTOM_PREFIX + name, loc)
        rin, gin, binp, ain = _inp(n, "Red", "R"), _inp(n, "Green", "G"), _inp(n, "Blue", "B"), _inp(n, "Alpha", "A")
    except Exception:
        n = _new(nodes, "ShaderNodeCombineRGB", CUSTOM_PREFIX + name, loc)
        rin, gin, binp, ain = _inp(n, "R", "Red"), _inp(n, "G", "Green"), _inp(n, "B", "Blue"), None
    if r is not None:
        _link(links, r, rin)
    if g is not None:
        _link(links, g, gin)
    if b is not None:
        _link(links, b, binp)
    if a is not None and ain is not None:
        _link(links, a, ain)
    return n


def _mix_rgb(nodes, links, blend, color1=None, color2=None, fac=1.0,
             name="MixRGB", loc=(0, 0), clamp=False):
    n = _new(nodes, "ShaderNodeMixRGB", CUSTOM_PREFIX + name, loc)
    n.blend_type = blend
    n.inputs[0].default_value = fac
    try:
        n.use_clamp = bool(clamp)
    except Exception:
        pass
    if color1 is not None:
        _link(links, color1, n.inputs[1])
    if color2 is not None:
        _link(links, color2, n.inputs[2])
    return n


def _value_node(nodes, name, value, loc=(0, 0)):
    n = _new(nodes, "ShaderNodeValue", CUSTOM_PREFIX + name, loc)
    n.outputs[0].default_value = float(value)
    return n


def _vector_value_node(nodes, name, value, loc=(0, 0)):
    n = _new(nodes, "ShaderNodeCombineXYZ", CUSTOM_PREFIX + name, loc)
    n.inputs[0].default_value = float(value[0])
    n.inputs[1].default_value = float(value[1])
    n.inputs[2].default_value = float(value[2]) if len(value) > 2 else 0.0
    return n


def _make_uv_scaled(nodes, links, uv_socket, scale_xy, name, loc=(0, 0)):
    scale_vec = _vector_value_node(nodes, name + "_Scale", (scale_xy[0], scale_xy[1], 1.0), (loc[0] - 220, loc[1] - 120))
    vm = _new(nodes, "ShaderNodeVectorMath", CUSTOM_PREFIX + name, loc)
    vm.operation = "MULTIPLY"
    _link(links, uv_socket, _inp(vm, "Vector"))
    _link(links, scale_vec.outputs[0], _inp(vm, "Vector_001", "Vector 2"))
    return _out(vm, "Vector")


def _duplicate_image_texture(nodes, src_node, name, loc=(0, 0)):
    if not src_node:
        return None
    dup = _new(nodes, "ShaderNodeTexImage", CUSTOM_PREFIX + name, loc)
    try:
        dup.image = src_node.image
    except Exception:
        pass
    for attr in ("extension", "interpolation", "projection"):
        try:
            setattr(dup, attr, getattr(src_node, attr))
        except Exception:
            pass
    return dup


# -----------------------------------------------------------------------------
# g_detailParams decode. Blender node sistemi Texture2DArray seçemediği için
# bu bilgiler node ağında etiket/sabit olarak tutulur ve micro detail scale/rot
# için kullanılır.
# -----------------------------------------------------------------------------
def _half_to_float_from_u16(h):
    # IEEE 754 half -> float, numpy gerektirmez.
    h = int(h) & 0xffff
    sign = -1.0 if (h & 0x8000) else 1.0
    exp = (h >> 10) & 0x1f
    mant = h & 0x03ff
    if exp == 0:
        if mant == 0:
            return -0.0 if sign < 0 else 0.0
        return sign * (mant / 1024.0) * (2.0 ** -14)
    if exp == 31:
        return sign * float("inf") if mant == 0 else float("nan")
    return sign * (1.0 + mant / 1024.0) * (2.0 ** (exp - 15))


def _decode_detail_pair(params, pair_index):
    """
    Yaklaşık yorum:
      even word düşük 16 bit  -> UV scale * 1/1024
      even word yüksek bitler -> Texture2DArray slice/index bilgisi
      odd word yüksek 16 bit  -> rotasyon half-float
      even word bit24         -> dirt/wear blend flag
      even word bits16..23    -> blend byte
    """
    i = pair_index * 2
    if i + 1 >= len(params):
        return {"enabled": False, "scale": 1.0, "angle": 0.0, "layer": 0, "blend": 0.0, "wear_flag": False}
    word0 = int(params[i]) & 0xffffffff
    word1 = int(params[i + 1]) & 0xffffffff
    if word0 == 0xfe000000:
        return {"enabled": False, "scale": 1.0, "angle": 0.0, "layer": 127, "blend": 0.0, "wear_flag": False}
    scale = (word0 & 0xffff) * 0.000976577401
    if scale <= 0.000001:
        scale = 1.0
    angle = _half_to_float_from_u16((word1 >> 16) & 0xffff)
    layer = (word0 >> 25) & 0x7f
    wear_flag = bool((word0 >> 24) & 1)
    blend = ((word0 >> 16) & 0xff) / 255.0
    return {"enabled": True, "scale": scale, "angle": angle, "layer": layer, "blend": blend, "wear_flag": wear_flag}


def _add_detail_param_debug_nodes(nodes, detail_params, loc=(0, 0)):
    frame = _new(nodes, "NodeFrame", CUSTOM_PREFIX + "g_detailParams_decode", loc)
    frame.label = "g_detailParams decode / Texture2DArray layer bilgisi"
    x = loc[0] + 30
    y = loc[1] - 40
    for i in range(0, min(8, len(detail_params) // 2)):
        d = _decode_detail_pair(detail_params, i)
        n = _value_node(nodes, "detailParam_%d_scale" % i, d["scale"], (x, y - i * 90))
        n.parent = frame
        n.label = "pair %d scale %.3f / angle %.3f / layer %s / blend %.3f / wear %s" % (
            i, d["scale"], d["angle"], d["layer"], d["blend"], d["wear_flag"]
        )


# -----------------------------------------------------------------------------
# Ana kurulum
# -----------------------------------------------------------------------------
def setup_nodes(mat, nodes, links):
    out = nodes.get("Material Output")
    bsdf = nodes.get("Principled BSDF")
    if not out or not bsdf:
        return

    _remove_old_custom_nodes(nodes)

    # ------------------------------------------------------------------
    # Parametreleri .visual node/material değerlerinden oku
    # ------------------------------------------------------------------
    g_detail_power_gloss = _get_value(mat, nodes, "g_detailPowerGloss", DEFAULTS["g_detailPowerGloss"])
    g_detail_power_albedo = _get_value(mat, nodes, "g_detailPowerAlbedo", DEFAULTS["g_detailPowerAlbedo"])
    g_mask_bias = _get_value(mat, nodes, "g_maskBias", DEFAULTS["g_maskBias"])
    g_detail_power = _get_value(mat, nodes, "g_detailPower", DEFAULTS["g_detailPower"])
    g_use_detail_metallic = _get_value(mat, nodes, "g_useDetailMetallic", DEFAULTS["g_useDetailMetallic"])
    g_default_detail = _get_value(mat, nodes, "g_defaultDetail", DEFAULTS["g_defaultDetail"])
    alpha_ref = _get_value(mat, nodes, "alphaReference", DEFAULTS["alphaReference"])

    # ÖNEMLİ: alphaTestEnable default true sayılmayacak.
    # Sahnedeki gerçek alphaTestEnable node'u varsa ve 1 ise ANM.R -> Alpha bağlanır.
    # Node yoksa ya da 0 ise alpha bağlantısı kurulmaz.
    alpha_test_node = nodes.get("alphaTestEnable")
    alpha_test_enable = 0.0
    if alpha_test_node and len(alpha_test_node.outputs):
        try:
            alpha_test_enable = _as_float(alpha_test_node.outputs[0].default_value, 0.0)
        except Exception:
            alpha_test_enable = 0.0

    detail_rb_swap = _get_value(mat, nodes, "pbs_tank_detail_rb_swap", DEFAULTS["pbs_tank_detail_rb_swap"])
    micro_normal_strength = _get_value(mat, nodes, "pbs_tank_micro_normal_strength", DEFAULTS["pbs_tank_micro_normal_strength"])
    t2da_overlay_strength = _get_value(mat, nodes, "pbs_tank_t2da_overlay_strength", DEFAULTS["pbs_tank_t2da_overlay_strength"])
    t2da_second_blend = _get_value(mat, nodes, "pbs_tank_t2da_second_sample_blend", DEFAULTS["pbs_tank_t2da_second_sample_blend"])
    g_dirt_level = _get_value(mat, nodes, "g_dirtLevel", DEFAULTS["g_dirtLevel"])
    g_gloss_min = _get_value(mat, nodes, "g_glossMin", DEFAULTS["g_glossMin"])
    g_gloss_max = _get_value(mat, nodes, "g_glossMax", DEFAULTS["g_glossMax"])

    detail_uv_tiling = _get_vector(mat, nodes, "g_detailUVTiling", DEFAULT_DETAIL_UV_TILING)
    tiling_ratio = _get_vector(mat, nodes, "g_tilingRatio", DEFAULT_TILING_RATIO)

    # Shaderda detail aktifse g_detailUVTiling, kapalı/default yolda g_tilingRatio kullanılıyor.
    use_detail = (g_use_detail_metallic > 0.5) and (g_default_detail < 0.5)
    detail_tiling_xy = (detail_uv_tiling[0], detail_uv_tiling[1]) if use_detail else (tiling_ratio[0], tiling_ratio[1])

    detail_params = DEFAULT_DETAIL_PARAMS[:]
    try:
        raw = mat.get("g_detailParams") or mat.get("bw_g_detailParams") or mat.get("bw_matrix_g_detailParams")
        if isinstance(raw, (list, tuple)) and len(raw) >= 16:
            detail_params = [int(x) for x in raw[:16]]
    except Exception:
        pass

    # ------------------------------------------------------------------
    # Texture nodeları
    # ------------------------------------------------------------------
    diffuse = _find_node(nodes, "diffuseMap")
    normal = _find_node(nodes, "normalMap")
    gmm = _find_node(nodes, "metallicGlossMap")
    ao = _find_node(nodes, "excludeMaskAndAOMap")
    metallic_detail = _find_node(nodes, "metallicDetailMap")
    details_atlas = _find_node(nodes, "DetailsMaps", "g_defaultMicroDetailAtlas")

    _set_srgb(diffuse)
    _set_non_color(normal, gmm, ao, metallic_detail, details_atlas)

    # ------------------------------------------------------------------
    # Materyal ayarları: alpha test .visualdan gelir
    # ------------------------------------------------------------------
    try:
        mat.use_nodes = True
    except Exception:
        pass
    if alpha_test_enable > 0.5:
        try:
            mat.blend_method = "CLIP"
            mat.alpha_threshold = max(0.0, min(1.0, alpha_ref / 255.0))
        except Exception:
            pass
        try:
            mat.surface_render_method = "DITHERED"
        except Exception:
            pass
    else:
        try:
            mat.blend_method = "OPAQUE"
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UV akışları
    # ------------------------------------------------------------------
    texcoord = _new(nodes, "ShaderNodeTexCoord", CUSTOM_PREFIX + "TextureCoordinates", (-1500, 120))
    uv_socket = _out(texcoord, "UV")

    detail_uv = _make_uv_scaled(nodes, links, uv_socket, detail_tiling_xy,
                                "detailUV_g_detailUVTiling_or_g_tilingRatio", (-1220, -370))

    # Shaderda metallicDetailMap daima g_detailUVTiling.xy ile wrap sample ediliyor.
    metallic_detail_uv = _make_uv_scaled(nodes, links, uv_socket,
                                         (detail_uv_tiling[0], detail_uv_tiling[1]),
                                         "metallicDetailUV_g_detailUVTiling", (-1220, -120))

    for tex in (diffuse, normal, gmm, ao):
        if tex:
            _link(links, uv_socket, _inp(tex, "Vector"))
    if metallic_detail:
        _link(links, metallic_detail_uv, _inp(metallic_detail, "Vector"))
    if details_atlas:
        # DetailsMaps için primary micro detail scale/rotation yaklaşımı.
        primary = _decode_detail_pair(detail_params, 0)
        try:
            # Mapping node ile rotation/scale görsel olarak uygulanır.
            mapping = _new(nodes, "ShaderNodeMapping", CUSTOM_PREFIX + "DetailsMaps_Primary_Mapping", (-950, -640))
            mapping.inputs["Scale"].default_value[0] = max(0.0001, primary["scale"])
            mapping.inputs["Scale"].default_value[1] = max(0.0001, primary["scale"])
            mapping.inputs["Scale"].default_value[2] = 1.0
            mapping.inputs["Rotation"].default_value[2] = primary["angle"]
            _link(links, detail_uv, _inp(mapping, "Vector"))
            _link(links, _out(mapping, "Vector"), _inp(details_atlas, "Vector"))
        except Exception:
            _link(links, detail_uv, _inp(details_atlas, "Vector"))

    _add_detail_param_debug_nodes(nodes, detail_params, (-520, -1180))

    # ------------------------------------------------------------------
    # Diffuse / AM
    # ------------------------------------------------------------------
    final_color = _out(diffuse, "Color") if diffuse else None
    # PBS_tank pathinde AM/diffuse alpha ana alpha değildir.
    # alphaTestEnable true ise alpha normalMap/ANM RED kanalından gelir.
    final_alpha = None

    # AO / dirt: Blender'de ayrı AO gbuffer yok. Renk üstüne hafif multiply yapılır.
    # Bu branch g_dirtLevel'i kullanır ama oyundaki global dirt/wet pass'i birebir değildir.
    if ao and final_color:
        ao_sep = _sep_color(nodes, links, _out(ao, "Color"), "AO_Separate_RGBA", (-900, 240))
        # AO map kanal yapısı shaderda dirt/exclude ile karışık. Blender preview için Red'i AO çarpanı yapıyoruz.
        ao_r = _out(ao_sep, "Red", "R")
        dirt_strength = min(1.0, max(0.0, g_dirt_level * 0.35))
        ao_mix_color = _combine_color(nodes, links, r=ao_r, g=ao_r, b=ao_r,
                                      name="AO_to_RGB", loc=(-670, 260))
        ao_mul = _mix_rgb(nodes, links, "MULTIPLY", final_color, _out(ao_mix_color, "Color", "Image"),
                          fac=dirt_strength, name="AM_x_AO_g_dirtLevel", loc=(-430, 270), clamp=True)
        final_color = _out(ao_mul, "Color")

    # ------------------------------------------------------------------
    # GMM: shader akışında r0 = metallicGlossMap.
    # r0.x = metal/base metal kolu, r0.y = gloss kolu, r0.z = wear/helper.
    # Blender Roughness = 1 - finalGloss.
    # ------------------------------------------------------------------
    final_metallic = None
    final_gloss = None
    detail_mask = None

    if gmm:
        gmm_sep = _sep_color(nodes, links, _out(gmm, "Color"), "GMM_Separate_R_metal_G_gloss_B_wear", (-900, -120))
        gmm_r = _out(gmm_sep, "Red", "R")
        gmm_g = _out(gmm_sep, "Green", "G")
        gmm_b = _out(gmm_sep, "Blue", "B")

        final_metallic = gmm_r
        final_gloss = gmm_g

        # Detail mask: shaderdaki gloss/metal aralığına yakınlaştırılmış maske.
        # base = sqrt(saturate(GMM.G - g_glossMin))
        gloss_minus_min = _math(nodes, links, "SUBTRACT", a=gmm_g, value_b=g_gloss_min,
                                name="detailMask_glossMinusMin", loc=(-650, -210), clamp=True).outputs[0]
        gloss_sqrt = _math(nodes, links, "SQRT", a=gloss_minus_min,
                           name="detailMask_sqrt", loc=(-470, -210), clamp=True).outputs[0]

        # metal gate = saturate((0.8 - GMM.R) * 5)
        metal_gate_sub = _math(nodes, links, "SUBTRACT", b=gmm_r, value_a=0.8,
                               name="detailMask_0p8_minus_metal", loc=(-650, -300), clamp=False).outputs[0]
        metal_gate = _math(nodes, links, "MULTIPLY", a=metal_gate_sub, value_b=5.0,
                           name="detailMask_metalGate", loc=(-470, -300), clamp=True).outputs[0]

        # gloss gate = saturate((0.77 - GMM.G) * 5)
        gloss_gate_sub = _math(nodes, links, "SUBTRACT", b=gmm_g, value_a=0.77,
                               name="detailMask_0p77_minus_gloss", loc=(-650, -390), clamp=False).outputs[0]
        gloss_gate = _math(nodes, links, "MULTIPLY", a=gloss_gate_sub, value_b=5.0,
                           name="detailMask_glossGate", loc=(-470, -390), clamp=True).outputs[0]

        mask_a = _math(nodes, links, "MULTIPLY", a=gloss_sqrt, b=metal_gate,
                       name="detailMask_gloss_x_metalGate", loc=(-250, -260), clamp=True).outputs[0]
        mask_b = _math(nodes, links, "MULTIPLY", a=mask_a, b=gloss_gate,
                       name="detailMask_x_glossGate", loc=(-70, -260), clamp=True).outputs[0]

        # g_maskBias kullanımı: saturate((mask - bias) / (1 - bias))
        bias_sub = _math(nodes, links, "SUBTRACT", a=mask_b, value_b=g_mask_bias,
                         name="detailMask_minus_g_maskBias", loc=(110, -260), clamp=False).outputs[0]
        bias_mul = _math(nodes, links, "MULTIPLY", a=bias_sub,
                         value_b=(1.0 / max(0.0001, 1.0 - g_mask_bias)),
                         name="detailMask_biasNormalize", loc=(290, -260), clamp=True).outputs[0]

        # Shaderda r3.w sonradan g_detailPower=5 ile çarpılıyor ve final mad_sat aşamasında clamp ediliyor.
        # Bunu burada erken clamp edersek metalik çizikler oyun kadar parlamıyor.
        detail_mask = _math(nodes, links, "MULTIPLY", a=bias_mul,
                            value_b=(g_detail_power if use_detail else 0.0),
                            name="detailMask_x_g_detailPower_UNCLAMPED", loc=(470, -260), clamp=False).outputs[0]

        # GMM.B wear/exclude bilgisini node ağında görünür tutuyoruz.
        gmm_b_debug = _value_node(nodes, "GMM_B_used_by_wear_path_note", 1.0, (-650, -500))
        gmm_b_debug.label = "GMM.B shaderda wear/exclude yardımcı kanalıdır; Blender previewde doğrudan BSDF girişine bağlanmaz"
        # Link yapay olarak yok; sadece node ağında not.
        _ = gmm_b

    # ------------------------------------------------------------------
    # metallicDetailMap / Details_map: albedo + gloss + metallic detail
    # ------------------------------------------------------------------
    if metallic_detail and gmm and detail_mask:
        md_sep = _sep_color(nodes, links, _out(metallic_detail, "Color"),
                            "Details_map_Separate_RGB", (-900, -620))
        md_r = _out(md_sep, "Red", "R")
        md_g = _out(md_sep, "Green", "G")
        md_b = _out(md_sep, "Blue", "B")

        # Shader matematiği: r6.xyz = float3(0.5,-0.5,-0.5) + r6.xyz.
        # GMM akışına DOKUNMUYORUZ: v2'deki gibi GMM.R=metallic, GMM.G=gloss kalır.
        # Sadece metallicDetailMap R/B swizzle düzeltmesi:
        #   detail_rb_swap=1 -> scratch/gloss kolu Blender'daki Blue çıkışından, albedo/pütür kolu Red çıkışından alınır.
        #   detail_rb_swap=0 -> eski v2: scratch/gloss Red, albedo Blue.
        # Senin son testine göre default swap=1 bırakıldı. Yanlış gelirse materyalde pbs_tank_detail_rb_swap=0 yap.
        if detail_rb_swap > 0.5:
            md_scratch_src = md_b
            md_albedo_src = md_r
            swizzle_note = "R/B SWAPPED: scratch=Blue, albedo=Red"
        else:
            md_scratch_src = md_r
            md_albedo_src = md_b
            swizzle_note = "NO SWAP: scratch=Red, albedo=Blue"

        md_scratch_plus = _math(nodes, links, "ADD", a=md_scratch_src, value_b=0.5,
                                name="detail_SCRATCH_plus_0p5_glossMultiplier", loc=(-650, -610)).outputs[0]
        md_g_center = _math(nodes, links, "SUBTRACT", a=md_g, value_b=0.5,
                            name="detail_G_minus_0p5_metalGloss", loc=(-650, -700)).outputs[0]
        md_albedo_center = _math(nodes, links, "SUBTRACT", a=md_albedo_src, value_b=0.5,
                                 name="detail_ALBEDO_minus_0p5", loc=(-650, -790)).outputs[0]

        # finalGloss = GMM.G + GMM.G * ((DetailsScratch + 0.5) - 1) * mask
        rminus1 = _math(nodes, links, "SUBTRACT", a=md_scratch_plus, value_b=1.0,
                        name="detailGlossMultiplier_minus_1", loc=(-430, -610)).outputs[0]
        gloss_delta_a = _math(nodes, links, "MULTIPLY", a=final_gloss, b=rminus1,
                              name="detailGloss_delta_base", loc=(-250, -610)).outputs[0]
        gloss_delta = _math(nodes, links, "MULTIPLY", a=gloss_delta_a, b=detail_mask,
                            name="detailGloss_delta_x_mask", loc=(-70, -610)).outputs[0]
        final_gloss = _math(nodes, links, "ADD", a=final_gloss, b=gloss_delta,
                            name="finalGloss_GMM_plus_DetailsMap", loc=(130, -610), clamp=True).outputs[0]

        # finalMetallic/BaseMetal = GMM.R + (Details.G - 0.5) * mask * g_detailPowerGloss
        met_delta_a = _math(nodes, links, "MULTIPLY", a=md_g_center, b=detail_mask,
                            name="detailMetal_delta_x_mask", loc=(-250, -710)).outputs[0]
        met_delta = _math(nodes, links, "MULTIPLY", a=met_delta_a, value_b=g_detail_power_gloss,
                          name="detailMetal_x_g_detailPowerGloss", loc=(-70, -710)).outputs[0]
        final_metallic = _math(nodes, links, "ADD", a=final_metallic, b=met_delta,
                               name="finalMetallic_GMM_plus_DetailsMap", loc=(130, -710), clamp=True).outputs[0]

        # finalAlbedo = AM + (Details.B - 0.5) * mask * g_detailPowerAlbedo
        # Mavi kanal bu yüzden az görünür; shaderda albedoye sadece 0.11 güçle biniyor.
        if final_color:
            alb_delta_a = _math(nodes, links, "MULTIPLY", a=md_albedo_center, b=detail_mask,
                                name="detailAlbedo_delta_x_mask", loc=(-250, -820)).outputs[0]
            alb_delta = _math(nodes, links, "MULTIPLY", a=alb_delta_a, value_b=g_detail_power_albedo,
                              name="detailAlbedo_x_g_detailPowerAlbedo", loc=(-70, -820)).outputs[0]
            alb_delta_rgb = _combine_color(nodes, links, r=alb_delta, g=alb_delta, b=alb_delta,
                                           name="detailAlbedo_delta_RGB", loc=(130, -820))
            add_albedo = _mix_rgb(nodes, links, "ADD", final_color, _out(alb_delta_rgb, "Color", "Image"),
                                  fac=1.0, name="finalAlbedo_AM_plus_detail", loc=(360, -820), clamp=True)
            final_color = _out(add_albedo, "Color")

    # ------------------------------------------------------------------
    # Detail_T2DA / micro detail atlas yaklaşımı
    # ------------------------------------------------------------------
    micro_normal_socket = None
    if details_atlas and detail_mask:
        atlas_sep = _sep_color(nodes, links, _out(details_atlas, "Color"),
                               "Detail_T2DA_Primary_Separate", (-820, -980))
        atlas_r0 = _out(atlas_sep, "Red", "R")
        atlas_g0 = _out(atlas_sep, "Green", "G")
        atlas_b0 = _out(atlas_sep, "Blue", "B")
        atlas_a0 = _out(details_atlas, "Alpha") or atlas_b0

        # Shader T2DA'yı iki ayrı UV/rotation/layer ile sample ediyor:
        #   sample0 -> .wyxz swizzle
        #   sample1 -> .xyzw
        # Blender Texture2DArray layer seçemediği için aynı DDS'i ikinci kez, farklı detailParam scale/rotation ile sample ediyoruz.
        atlas_r, atlas_g, atlas_b, atlas_alpha = atlas_r0, atlas_g0, atlas_b0, atlas_a0
        secondary_tex = None
        try:
            secondary = _decode_detail_pair(detail_params, 1)
            if secondary.get("enabled", False) and t2da_second_blend > 0.001:
                secondary_tex = _duplicate_image_texture(nodes, details_atlas, "DetailsMaps_Secondary_Sample", (-1040, -1030))
                mapping2 = _new(nodes, "ShaderNodeMapping", CUSTOM_PREFIX + "DetailsMaps_Secondary_Mapping", (-1250, -1030))
                mapping2.inputs["Scale"].default_value[0] = max(0.0001, secondary["scale"])
                mapping2.inputs["Scale"].default_value[1] = max(0.0001, secondary["scale"])
                mapping2.inputs["Scale"].default_value[2] = 1.0
                mapping2.inputs["Rotation"].default_value[2] = secondary["angle"]
                _link(links, detail_uv, _inp(mapping2, "Vector"))
                _link(links, _out(mapping2, "Vector"), _inp(secondary_tex, "Vector"))
                sec_sep = _sep_color(nodes, links, _out(secondary_tex, "Color"),
                                     "Detail_T2DA_Secondary_Separate", (-820, -1260))
                sr = _out(sec_sep, "Red", "R")
                sg = _out(sec_sep, "Green", "G")
                sb = _out(sec_sep, "Blue", "B")
                sa = _out(secondary_tex, "Alpha") or sb
                blend = max(0.0, min(1.0, t2da_second_blend))
                def lerp_channel(a, b, nm, y):
                    d = _math(nodes, links, "SUBTRACT", a=b, b=a,
                              name=nm + "_sec_minus_primary", loc=(-600, y)).outputs[0]
                    dm = _math(nodes, links, "MULTIPLY", a=d, value_b=blend,
                               name=nm + "_x_secondBlend", loc=(-420, y)).outputs[0]
                    return _math(nodes, links, "ADD", a=a, b=dm,
                                 name=nm + "_mixed", loc=(-240, y), clamp=True).outputs[0]
                atlas_r = lerp_channel(atlas_r0, sr, "T2DA_R", -930)
                atlas_g = lerp_channel(atlas_g0, sg, "T2DA_G", -1010)
                atlas_b = lerp_channel(atlas_b0, sb, "T2DA_B", -1090)
                atlas_alpha = lerp_channel(atlas_a0, sa, "T2DA_A", -1170)
        except Exception:
            atlas_r, atlas_g, atlas_b, atlas_alpha = atlas_r0, atlas_g0, atlas_b0, atlas_a0

        # Önemli düzeltme: T2DA Blue artık Bump/Height değildir.
        # Shaderda normal için sample0.wy => Alpha + Green kullanılıyor; Blue ise intensity/overlay kolunda kullanılıyor.
        # V6'daki Blue->Bump bağlantısı oyundaki gibi olmayan şişkin/çamurlu yüzey oluşturuyordu.

        # Micro gloss: alpha ana kaynak; düşük güçle final gloss'a eklenir.
        if final_gloss:
            micro_gloss_center = _math(nodes, links, "SUBTRACT", a=atlas_alpha, value_b=0.5,
                                       name="microGlossA_minus_0p5", loc=(-20, -980)).outputs[0]
            micro_gloss_a = _math(nodes, links, "MULTIPLY", a=micro_gloss_center, b=detail_mask,
                                  name="microGlossA_x_mask", loc=(160, -980)).outputs[0]
            micro_gloss = _math(nodes, links, "MULTIPLY", a=micro_gloss_a, value_b=g_detail_power_gloss,
                                name="microGlossA_x_g_detailPowerGloss", loc=(340, -980)).outputs[0]
            final_gloss = _math(nodes, links, "ADD", a=final_gloss, b=micro_gloss,
                                name="finalGloss_plus_Detail_T2DA_A", loc=(520, -980), clamp=True).outputs[0]

        # T2DA Blue ile shaderdaki overlay/intensity yaklaşımı:
        #   r7.x = 1 - Blue
        #   overlayCoord = 0.5 + mask * ((1 - Blue) - 0.5)
        # Bu, base color üstünde zırhın kamuflajdan bağımsız mikro yüzey lekesini verir; height bump değildir.
        if final_color:
            half_minus_b = _math(nodes, links, "SUBTRACT", b=atlas_b, value_a=0.5,
                                 name="T2DA_0p5_minus_Blue", loc=(-20, -1110)).outputs[0]
            overlay_strength_socket = _math(nodes, links, "MULTIPLY", a=detail_mask,
                                            value_b=max(0.0, t2da_overlay_strength),
                                            name="T2DA_overlay_strength_x_mask", loc=(160, -1110), clamp=True).outputs[0]
            overlay_delta = _math(nodes, links, "MULTIPLY", a=half_minus_b, b=overlay_strength_socket,
                                  name="T2DA_overlay_delta", loc=(340, -1110)).outputs[0]
            overlay_gray = _math(nodes, links, "ADD", a=overlay_delta, value_b=0.5,
                                 name="T2DA_overlay_gray", loc=(520, -1110), clamp=True).outputs[0]
            overlay_rgb = _combine_color(nodes, links, r=overlay_gray, g=overlay_gray, b=overlay_gray,
                                         name="T2DA_overlay_gray_RGB", loc=(700, -1110))
            overlay_mix = _mix_rgb(nodes, links, "OVERLAY", final_color, _out(overlay_rgb, "Color", "Image"),
                                   fac=1.0, name="finalAlbedo_overlay_Detail_T2DA_Blue", loc=(900, -1110), clamp=True)
            final_color = _out(overlay_mix, "Color")

        # Primary micro normal = X from Alpha, Y from Green, Z reconstructed.
        t2da_nx = _math(nodes, links, "MULTIPLY_ADD", a=atlas_alpha, value_b=2.0,
                        name="T2DA_X_alpha_times2_minus1", loc=(-20, -1280)).outputs[0]
        try:
            nodes[CUSTOM_PREFIX + "T2DA_X_alpha_times2_minus1"].inputs[2].default_value = -1.0
        except Exception:
            pass
        t2da_ny = _math(nodes, links, "MULTIPLY_ADD", a=atlas_g, value_b=2.0,
                        name="T2DA_Y_green_times2_minus1", loc=(-20, -1375)).outputs[0]
        try:
            nodes[CUSTOM_PREFIX + "T2DA_Y_green_times2_minus1"].inputs[2].default_value = -1.0
        except Exception:
            pass
        t2da_nx2 = _math(nodes, links, "MULTIPLY", a=t2da_nx, b=t2da_nx,
                         name="T2DA_X_squared", loc=(160, -1280)).outputs[0]
        t2da_ny2 = _math(nodes, links, "MULTIPLY", a=t2da_ny, b=t2da_ny,
                         name="T2DA_Y_squared", loc=(160, -1375)).outputs[0]
        t2da_dot = _math(nodes, links, "ADD", a=t2da_nx2, b=t2da_ny2,
                         name="T2DA_dotXY", loc=(340, -1325), clamp=True).outputs[0]
        t2da_one_minus = _math(nodes, links, "SUBTRACT", b=t2da_dot, value_a=1.0,
                               name="T2DA_1_minus_dot", loc=(520, -1325), clamp=True).outputs[0]
        t2da_nz = _math(nodes, links, "SQRT", a=t2da_one_minus,
                        name="T2DA_Z_sqrt", loc=(700, -1325), clamp=True).outputs[0]
        t2da_nz_half = _math(nodes, links, "MULTIPLY", a=t2da_nz, value_b=0.5,
                             name="T2DA_Z_times0p5", loc=(880, -1325)).outputs[0]
        t2da_nz_enc = _math(nodes, links, "ADD", a=t2da_nz_half, value_b=0.5,
                            name="T2DA_Z_encoded", loc=(1060, -1325), clamp=True).outputs[0]
        micro_comb = _combine_color(nodes, links, r=atlas_alpha, g=atlas_g, b=t2da_nz_enc,
                                    name="Detail_T2DA_AG_to_NormalColor", loc=(1240, -1325))
        micro_nm = _new(nodes, "ShaderNodeNormalMap", CUSTOM_PREFIX + "Detail_T2DA_NormalMap_AG", (1460, -1325))
        nm_strength = _math(nodes, links, "MULTIPLY", a=detail_mask,
                            value_b=max(0.0, micro_normal_strength),
                            name="microNormal_strength_from_detailMask", loc=(1240, -1440), clamp=True).outputs[0]
        _link(links, _out(micro_comb, "Color", "Image"), _inp(micro_nm, "Color"))
        _link(links, nm_strength, _inp(micro_nm, "Strength"))
        micro_normal_socket = _out(micro_nm, "Normal")

        dbg = _value_node(nodes, "Detail_T2DA_R_debug_unusedish", 0.0, (1240, -1550))
        dbg.label = "Detail_T2DA R bu textureda çok zayıf; shader ağırlıklı A/G normal + B overlay/intensity kullanıyor"
        _ = atlas_r

    # ------------------------------------------------------------------
    # ANM normal: shader birebir X = Alpha, Y = Green, Z = sqrt(1 - dot(xy,xy))
    # Blender Normal Map node'una encoded RGB verilir.
    # ------------------------------------------------------------------
    base_normal_socket = None
    if normal:
        norm_sep = _sep_color(nodes, links, _out(normal, "Color"),
                              "ANM_Separate_R_alphaTest_G_normalY_A_normalX", (-900, -1380))
        norm_red = _out(norm_sep, "Red", "R")
        norm_alpha = _out(normal, "Alpha")
        norm_green = _out(norm_sep, "Green", "G")

        # .visual alphaTestEnable true ise alpha = ANM.RED.
        # Diffuse/AM alpha burada KULLANILMAZ.
        if alpha_test_enable > 0.5:
            final_alpha = norm_red

        # normal encoded R = ANM alpha, encoded G = ANM green.
        nx = _math(nodes, links, "MULTIPLY_ADD", a=norm_alpha, value_b=2.0,
                   name="ANM_X_alpha_times2_minus1", loc=(-650, -1320)).outputs[0]
        try:
            # MULTIPLY_ADD üçüncü input: -1
            nodes[CUSTOM_PREFIX + "ANM_X_alpha_times2_minus1"].inputs[2].default_value = -1.0
        except Exception:
            pass
        ny = _math(nodes, links, "MULTIPLY_ADD", a=norm_green, value_b=2.0,
                   name="ANM_Y_green_times2_minus1", loc=(-650, -1420)).outputs[0]
        try:
            nodes[CUSTOM_PREFIX + "ANM_Y_green_times2_minus1"].inputs[2].default_value = -1.0
        except Exception:
            pass

        nx2 = _math(nodes, links, "MULTIPLY", a=nx, b=nx,
                    name="ANM_X_squared", loc=(-450, -1320)).outputs[0]
        ny2 = _math(nodes, links, "MULTIPLY", a=ny, b=ny,
                    name="ANM_Y_squared", loc=(-450, -1420)).outputs[0]
        dot_xy = _math(nodes, links, "ADD", a=nx2, b=ny2,
                       name="ANM_dotXY", loc=(-250, -1370), clamp=True).outputs[0]
        one_minus = _math(nodes, links, "SUBTRACT", b=dot_xy, value_a=1.0,
                          name="ANM_1_minus_dot", loc=(-70, -1370), clamp=True).outputs[0]
        nz = _math(nodes, links, "SQRT", a=one_minus,
                   name="ANM_Z_sqrt", loc=(110, -1370), clamp=True).outputs[0]
        nz_enc_a = _math(nodes, links, "MULTIPLY", a=nz, value_b=0.5,
                         name="ANM_Z_times_0p5", loc=(290, -1370)).outputs[0]
        nz_enc = _math(nodes, links, "ADD", a=nz_enc_a, value_b=0.5,
                       name="ANM_Z_encoded", loc=(470, -1370), clamp=True).outputs[0]

        norm_color = _combine_color(nodes, links, r=norm_alpha, g=norm_green, b=nz_enc,
                                    name="ANM_repacked_A_G_Z", loc=(660, -1370))
        base_nm = _new(nodes, "ShaderNodeNormalMap", CUSTOM_PREFIX + "ANM_NormalMap_Xalpha_Ygreen", (900, -1370))
        try:
            base_nm.space = "TANGENT"
        except Exception:
            pass
        _link(links, _out(norm_color, "Color", "Image"), _inp(base_nm, "Color"))
        try:
            base_nm.inputs["Strength"].default_value = 1.0
        except Exception:
            pass
        base_normal_socket = _out(base_nm, "Normal")

    # Micro normal'i base normal üstüne bindir. Blender'da gerçek RNM yok, normalize add yaklaşımı.
    final_normal = base_normal_socket
    if base_normal_socket and micro_normal_socket:
        add_n = _new(nodes, "ShaderNodeVectorMath", CUSTOM_PREFIX + "Normal_base_plus_micro_approx", (1130, -1260))
        add_n.operation = "ADD"
        _link(links, base_normal_socket, _inp(add_n, "Vector"))
        _link(links, micro_normal_socket, _inp(add_n, "Vector_001", "Vector 2"))
        norm_n = _new(nodes, "ShaderNodeVectorMath", CUSTOM_PREFIX + "Normal_normalize", (1330, -1260))
        norm_n.operation = "NORMALIZE"
        _link(links, _out(add_n, "Vector"), _inp(norm_n, "Vector"))
        final_normal = _out(norm_n, "Vector")

    # ------------------------------------------------------------------
    # Final BSDF bağlantıları
    # ------------------------------------------------------------------
    if final_color:
        _link(links, final_color, _inp(bsdf, "Base Color"))

    if final_alpha:
        _link(links, final_alpha, _inp(bsdf, "Alpha"))

    if final_metallic:
        _link(links, final_metallic, _inp(bsdf, "Metallic"))

    if final_gloss:
        one_minus_gloss = _math(nodes, links, "SUBTRACT", b=final_gloss, value_a=1.0,
                                name="Roughness_1_minus_finalGloss", loc=(620, -420), clamp=True).outputs[0]
        _link(links, one_minus_gloss, _inp(bsdf, "Roughness"))

    if final_normal:
        _link(links, final_normal, _inp(bsdf, "Normal"))

    # Specular/IOR tarafını sabitle: oyun GBuffer PBR görünümüne daha yakın dursun.
    spec_in = _inp(bsdf, "Specular IOR Level", "Specular")
    if spec_in:
        try:
            spec_in.default_value = 0.5
        except Exception:
            pass

    # Emission bu modelde yok; varsa yanlış ışık vermemesi için sıfırla.
    em_strength = _inp(bsdf, "Emission Strength")
    if em_strength:
        try:
            em_strength.default_value = 0.0
        except Exception:
            pass

    # Surface bağlantısı kopmuşsa tekrar bağla.
    if out and bsdf:
        try:
            if not _inp(out, "Surface").is_linked:
                _link(links, _out(bsdf, "BSDF"), _inp(out, "Surface"))
        except Exception:
            pass

    # Parametre debug nodeları: .visual değerlerinin kaybolmadığını görmek için.
    debug_frame = _new(nodes, "NodeFrame", CUSTOM_PREFIX + "visual_params_used", (920, 260))
    debug_frame.label = ".visual params used by PBS_tank setup"
    debug_values = [
        ("g_detailPowerGloss", g_detail_power_gloss),
        ("g_detailPowerAlbedo", g_detail_power_albedo),
        ("g_maskBias", g_mask_bias),
        ("g_detailPower", g_detail_power),
        ("g_useDetailMetallic", g_use_detail_metallic),
        ("g_defaultDetail", g_default_detail),
        ("alphaReference", alpha_ref),
        ("alphaTestEnable_NODE_VALUE", alpha_test_enable),
        ("pbs_tank_micro_normal_strength", micro_normal_strength),
        ("g_dirtLevel", g_dirt_level),
        ("g_glossMin", g_gloss_min),
        ("g_glossMax", g_gloss_max),
        ("g_detailUVTiling.x", detail_uv_tiling[0]),
        ("g_detailUVTiling.y", detail_uv_tiling[1]),
        ("g_tilingRatio.x", tiling_ratio[0]),
        ("g_tilingRatio.y", tiling_ratio[1]),
    ]
    for i, (name, value) in enumerate(debug_values):
        n = _value_node(nodes, name, value, (debug_frame.location.x + 40, debug_frame.location.y - 40 - i * 55))
        n.parent = debug_frame

