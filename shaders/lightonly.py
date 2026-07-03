# -*- coding: utf-8 -*-

CUSTOM_PREFIX = "LightOnly__"


def _node(nodes, *names):
    wanted = [str(n) for n in names if n]
    for n in wanted:
        nd = nodes.get(n)
        if nd:
            return nd
    wanted_l = [n.lower() for n in wanted]
    for nd in nodes:
        nm = (getattr(nd, "name", "") or "").lower()
        lb = (getattr(nd, "label", "") or "").lower()
        for w in wanted_l:
            if nm == w or lb == w or nm.startswith(w + ".") or lb.startswith(w + "."):
                return nd
    return None


def _sock(sockets, *names):
    for name in names:
        if not name:
            continue
        try:
            return sockets[name]
        except Exception:
            pass
    for s in sockets:
        sid = getattr(s, "identifier", "")
        if s.name in names or sid in names:
            return s
    return None


def _out(node, *names):
    if not node:
        return None
    return _sock(node.outputs, *names)


def _inp(node, *names):
    if not node:
        return None
    return _sock(node.inputs, *names)


def _link(links, out_socket, in_socket):
    if out_socket is None or in_socket is None:
        return False
    try:
        for old in list(getattr(in_socket, "links", [])):
            try:
                links.remove(old)
            except Exception:
                pass
        links.new(out_socket, in_socket)
        return True
    except Exception:
        return False


def _new(nodes, bl_idname, name, loc):
    nd = nodes.new(bl_idname)
    nd.name = CUSTOM_PREFIX + name
    nd.label = name
    nd.location = loc
    return nd


def _remove_old(nodes):
    for nd in list(nodes):
        if (getattr(nd, "name", "") or "").startswith(CUSTOM_PREFIX):
            try:
                nodes.remove(nd)
            except Exception:
                pass


def _first_output(node):
    if not node or not len(node.outputs):
        return None
    # Texture/Attribute için Color, Value için Value, RGB için Color, CombineXYZ için Vector.
    return (_out(node, "Color", "RGBA", "Vector", "Value", "Alpha") or node.outputs[0])


def _color_output(node):
    if not node:
        return None
    return _out(node, "Color", "RGBA", "Image") or _first_output(node)


def _alpha_output(node):
    if not node:
        return None
    return _out(node, "Alpha")


def _float_value(node, default=0.0):
    if not node or not len(node.outputs):
        return default
    try:
        v = node.outputs[0].default_value
        if isinstance(v, (list, tuple)):
            return float(v[0])
        return float(v)
    except Exception:
        pass
    return default


def _x_socket(nodes, links, node, name, loc):
    """RGB/Vector/Value node'un X veya Red kanalını döndürür."""
    if not node:
        return None
    if node.type == 'RGB':
        sep = _new(nodes, 'ShaderNodeSeparateColor', name + '_SeparateColor', loc)
        _link(links, _out(node, 'Color'), _inp(sep, 'Color'))
        return _out(sep, 'Red', 'R')
    if node.type in {'COMBXYZ', 'VECT_MATH', 'MAPPING'} or _out(node, 'Vector'):
        sep = _new(nodes, 'ShaderNodeSeparateXYZ', name + '_SeparateXYZ', loc)
        _link(links, _out(node, 'Vector') or node.outputs[0], _inp(sep, 'Vector'))
        return _out(sep, 'X')
    return node.outputs[0] if len(node.outputs) else None


def _mix_multiply_rgba(nodes, links, a, b, name, loc):
    mix = _new(nodes, 'ShaderNodeMix', name, loc)
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    try:
        mix.inputs[0].default_value = 1.0
    except Exception:
        pass
    # Blender 4.x Mix RGBA: Factor=0, A=6, B=7, Result=2.
    _link(links, a, mix.inputs[6])
    _link(links, b, mix.inputs[7])
    return mix.outputs[2]


def _math_mul(nodes, links, a, b, name, loc, value_a=None, value_b=None):
    m = _new(nodes, 'ShaderNodeMath', name, loc)
    m.operation = 'MULTIPLY'
    if value_a is not None:
        m.inputs[0].default_value = value_a
    if value_b is not None:
        m.inputs[1].default_value = value_b
    if a is not None:
        _link(links, a, m.inputs[0])
    if b is not None:
        _link(links, b, m.inputs[1])
    return m.outputs[0]


def setup_nodes(mat, nodes, links):
    out = _node(nodes, "Material Output")
    bsdf = _node(nodes, "Principled BSDF")
    if not out or not bsdf:
        return

    _remove_old(nodes)

    diffuse = _node(nodes, "diffuseMap")
    vcol = _node(nodes, "VertexColor", "BPVScolour")
    dest_blend = _node(nodes, "destBlend")
    l_mult = _node(nodes, "lightMultipliers")
    uv_speed = _node(nodes, "diffuseUVSpeedAlphaOffset")
    tint = _node(nodes, "TintlColor", "TintColor")
    fresh = _node(nodes, "FreshnelColor", "FresnelColor")
    ramp = _node(nodes, "rampFreshnelMap")
    alpha_fresh = _node(nodes, "alphaFreshnelEnable")
    alpha_fade = _node(nodes, "alphaFadeAmountSoft")
    alpha_test = _node(nodes, "alphaTestEnable")

    # Eski textured import mantığı: ışık modeli / additive modellerde VertexColor ana akışa girer.
    vcol_color = _out(vcol, "Color") if vcol else None
    # ÖNEMLİ: LightOnly beam/rays tarafında VertexColor Alpha bağlanınca ışık tek yöne/yukarı akıyormuş gibi bozuluyor.
    # Bu yüzden sadece VertexColor Color kullanılır; Alpha bilinçli olarak yok sayılır.
    vcol_alpha = None

    dest_blend_val = _float_value(dest_blend, 1.0)
    is_additive = abs(dest_blend_val - 2.0) < 0.001

    # UV hız/offset. Eski kodda vector/RGBA property direkt Mapping Location'a giriyordu.
    uv_out = None
    if uv_speed:
        uv_node = _new(nodes, 'ShaderNodeTexCoord', 'UVSpeed_TexCoord', (-1100, 230))
        mapping = _new(nodes, 'ShaderNodeMapping', 'diffuseUVSpeedAlphaOffset_Mapping', (-900, 230))
        _link(links, _out(uv_node, 'UV'), _inp(mapping, 'Vector'))
        _link(links, _first_output(uv_speed), _inp(mapping, 'Location'))
        uv_out = _out(mapping, 'Vector')

    final_color = vcol_color
    final_alpha = None

    if diffuse:
        if uv_out:
            _link(links, uv_out, _inp(diffuse, 'Vector'))
        diffuse_color = _color_output(diffuse)
        diffuse_alpha = _alpha_output(diffuse)
        if vcol_color:
            final_color = _mix_multiply_rgba(nodes, links, diffuse_color, vcol_color,
                                             'Diffuse_x_VertexColor', (-360, 150))
        else:
            final_color = diffuse_color
        # VertexColor Alpha kullanılmaz. Alpha sadece diffuseMap Alpha'dan gelir.
        final_alpha = diffuse_alpha

    # Tint / Fresnel color multiply. Bunlar özellikle light/glow materyallerinde renk tonunu düzeltiyor.
    if tint and final_color:
        final_color = _mix_multiply_rgba(nodes, links, final_color, _color_output(tint),
                                         'TintlColor_Multiply', (-130, 145))

    if fresh and final_color:
        final_color = _mix_multiply_rgba(nodes, links, final_color, _color_output(fresh),
                                         'FreshnelColor_Multiply', (70, 145))

    # Ramp/Freshnel gradyan. Mevcut lightonly.py'de eksik olan ana parça bu.
    use_ramp = bool(alpha_fresh and _float_value(alpha_fresh, 0.0) > 0.5 and ramp)
    if use_ramp:
        lw = _new(nodes, 'ShaderNodeLayerWeight', 'RampFreshnel_LayerWeight', (-1040, -310))

        # ÖNEMLİ:
        # Blender LayerWeight/Facing bu ışık quad'larında yan/grazing açıda yüksek çıkıyor.
        # Rays/flash oyunda tam önden görünmeli, bu yüzden front mask = 1 - Facing.
        # V2'de bu ramp alpha'yı da boğduğu için neredeyse görünmüyordu; V4'te ramp alpha'yı öldürmüyor,
        # sadece front mask ile görünürlük yönünü düzeltiyoruz.
        inv = _new(nodes, 'ShaderNodeMath', 'RampFreshnel_1_minus_Facing', (-840, -310))
        inv.operation = 'SUBTRACT'
        inv.inputs[0].default_value = 1.0
        _link(links, _out(lw, 'Facing'), inv.inputs[1])
        ramp_x_socket = inv.outputs[0]

        comb = _new(nodes, 'ShaderNodeCombineXYZ', 'RampFreshnel_Vector_X', (-640, -310))
        _link(links, ramp_x_socket, _inp(comb, 'X'))
        _link(links, _out(comb, 'Vector'), _inp(ramp, 'Vector'))

        if is_additive:
            # Rays/flash: ramp alpha ile tamamen söndürme. Oyunda bu tip ışıklar
            # kamera tam karşıdayken güçlüdür; ramp daha çok renk/yoğunluk gradyanı gibi çalışır.
            cam_weight = _new(nodes, 'ShaderNodeLayerWeight', 'Additive_Rays_FrontFacing_Alpha', (-470, -520))
            try:
                cam_weight.inputs['Blend'].default_value = 0.35
            except Exception:
                pass
            front_inv = _new(nodes, 'ShaderNodeMath', 'Additive_Rays_1_minus_Facing', (-260, -520))
            front_inv.operation = 'SUBTRACT'
            front_inv.inputs[0].default_value = 1.0
            _link(links, _out(cam_weight, 'Facing'), front_inv.inputs[1])

            facing_mul = _new(nodes, 'ShaderNodeMath', 'Alpha_x_FrontFacing_FIXED', (-60, -520))
            facing_mul.operation = 'MULTIPLY'
            if final_alpha:
                _link(links, final_alpha, facing_mul.inputs[0])
            else:
                facing_mul.inputs[0].default_value = 1.0
            _link(links, front_inv.outputs[0], facing_mul.inputs[1])
            final_alpha = facing_mul.outputs[0]

            # Ramp rengi final renge girsin; alpha'yı ekstra boğmasın.
            if final_color:
                final_color = _mix_multiply_rgba(nodes, links, final_color, _color_output(ramp),
                                                 'Color_x_RampFreshnelMap_Rays', (-110, 30))
            else:
                final_color = _color_output(ramp)
        else:
            # Genel alpha-fresnel objeler için eski davranış: ramp alpha/visibility'ye çarpılır.
            ramp_alpha = _math_mul(nodes, links, final_alpha, _color_output(ramp),
                                   'Alpha_x_RampFreshnelMap', (-180, -230), value_a=1.0 if not final_alpha else None)
            final_alpha = ramp_alpha

            if final_color:
                final_color = _mix_multiply_rgba(nodes, links, final_color, _color_output(ramp),
                                                 'Color_x_RampFreshnelMap', (-110, 30))
            else:
                final_color = _color_output(ramp)

    # alphaFadeAmountSoft.x ile alpha azaltma.
    if alpha_fade and final_alpha:
        fade_x = _x_socket(nodes, links, alpha_fade, 'alphaFadeAmountSoft_X', (-220, -420))
        final_alpha = _math_mul(nodes, links, final_alpha, fade_x,
                                'Alpha_x_alphaFadeAmountSoftX', (0, -250))

    # Çıkış yapısı.
    if is_additive:
        if hasattr(mat, "blend_method"):
            mat.blend_method = 'BLEND'
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = 'BLENDED'
        if hasattr(mat, "show_transparent_back"):
            mat.show_transparent_back = True
        if hasattr(mat, "use_transparent_shadow"):
            mat.use_transparent_shadow = True

        transp = _new(nodes, 'ShaderNodeBsdfTransparent', 'Transparent_Additive_Base', (230, 300))
        emit = _new(nodes, 'ShaderNodeEmission', 'LightOnly_Emission', (230, 110))
        if final_color:
            _link(links, final_color, _inp(emit, 'Color'))

        strength_source = _x_socket(nodes, links, l_mult, 'lightMultipliers_X', (15, 310)) if l_mult else None
        if final_alpha:
            if strength_source:
                strength_source = _math_mul(nodes, links, strength_source, final_alpha,
                                            'EmissionStrength_x_Alpha', (120, 250))
            else:
                strength_source = final_alpha

        if strength_source:
            _link(links, strength_source, _inp(emit, 'Strength'))
        else:
            _inp(emit, 'Strength').default_value = 1.0

        add_shader = _new(nodes, 'ShaderNodeAddShader', 'Transparent_plus_Emission', (460, 200))
        _link(links, _out(transp, 'BSDF'), add_shader.inputs[0])
        _link(links, _out(emit, 'Emission'), add_shader.inputs[1])
        _link(links, _out(add_shader, 'Shader'), _inp(out, 'Surface'))

    else:
        if final_color:
            _link(links, final_color, _inp(bsdf, 'Base Color'))
        if final_alpha:
            _link(links, final_alpha, _inp(bsdf, 'Alpha'))

        if alpha_test and _float_value(alpha_test, 0.0) > 0.5:
            if hasattr(mat, "blend_method"):
                mat.blend_method = 'CLIP'
            if hasattr(mat, "alpha_threshold"):
                mat.alpha_threshold = 0.5
            if hasattr(mat, "surface_render_method"):
                mat.surface_render_method = 'DITHERED'

        # Additive olmayan lightonly varyantlarında da lightMultipliers emission'a gider.
        if l_mult and final_color:
            strength = _x_socket(nodes, links, l_mult, 'lightMultipliers_X_BSDF', (-210, 310))
            if 'Emission Color' in bsdf.inputs:
                _link(links, final_color, _inp(bsdf, 'Emission Color'))
                _link(links, strength, _inp(bsdf, 'Emission Strength'))
