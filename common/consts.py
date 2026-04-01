"""SkepticalFox 2015-2024"""

from dataclasses import dataclass
from enum import StrEnum


# for debugging purpose
VERBOSE_VALIDATE = False


class PropType(StrEnum):
    Texture = "Texture"
    Vector4 = "Vector4"
    Bool = "Bool"
    Int = "Int"
    Float = "Float"


@dataclass
class PropDescr:
    description: str
    type: PropType


# Shader properties with description
visual_property_descr_dict: dict[str, PropDescr] = {
    "normalMap": PropDescr(
        "The normal map for the material",
        PropType.Texture,
    ),
    "specularMap": PropDescr(
        "The specular map for the material",
        PropType.Texture,
    ),
    "diffuseMap": PropDescr(
        "The diffuse map for the material",
        PropType.Texture,
    ),
    "metallicDetailMap": PropDescr(
        "",
        PropType.Texture,
    ),
    "metallicGlossMap": PropDescr(
        "",
        PropType.Texture,
    ),
    "excludeMaskAndAOMap": PropDescr(
        "",
        PropType.Texture,
    ),
    "g_detailMap": PropDescr(
        "",
        PropType.Texture,
    ),
    "diffuseMap2": PropDescr(
        "The diffuse map2 for the materials",
        PropType.Texture,
    ),
    "crashTileMap": PropDescr(
        "",
        PropType.Texture,
    ),
    "g_albedoConversions": PropDescr(
        "",
        PropType.Vector4,
    ),
    "g_glossConversions": PropDescr(
        "",
        PropType.Vector4,
    ),
    "g_metallicConversions": PropDescr(
        "",
        PropType.Vector4,
    ),
    "g_detailUVTiling": PropDescr(
        "",
        PropType.Vector4,
    ),
    "g_albedoCorrection": PropDescr(
        "",
        PropType.Vector4,
    ),
    "g_detailRejectTiling": PropDescr(
        "",
        PropType.Vector4,
    ),
    "g_detailInfluences": PropDescr(
        "",
        PropType.Vector4,
    ),
    "g_crashUVTiling": PropDescr(
        "",
        PropType.Vector4,
    ),
    "g_defaultPBSConversionParams": PropDescr(
        "(true/false)",
        PropType.Bool,
    ),
    "g_useDetailMetallic": PropDescr(
        "(true/false)",
        PropType.Bool,
    ),
    "g_useNormalPackDXT1": PropDescr(
        "(true/false)",
        PropType.Bool,
    ),
    "alphaTestEnable": PropDescr(
        "Whether an alpha test should be performed (true/false)",
        PropType.Bool,
    ),
    "doubleSided": PropDescr(
        "Whether the material is draw on both sides (true/false)",
        PropType.Bool,
    ),
    "dynamicObject": PropDescr(
        "(true/false)",
        PropType.Bool,
    ),
    "lightEnable": PropDescr(
        "(true/false)",
        PropType.Bool,
    ),
    "alphaReference": PropDescr(
        "The alpha value cut-off value (0..255)",
        PropType.Int,
    ),
    "destBlend": PropDescr(
        "D3D Destination blend factor for blending with backbuffer",
        PropType.Int,
    ),
    "srcBlend": PropDescr(
        "D3D Source blend factor for blending with backbuffer",
        PropType.Int,
    ),
    "g_detailPowerGloss": PropDescr(
        "",
        PropType.Float,
    ),
    "g_detailPowerAlbedo": PropDescr(
        "",
        PropType.Float,
    ),
    "g_maskBias": PropDescr(
        "",
        PropType.Float,
    ),
    "g_detailPower": PropDescr(
        "",
        PropType.Float,
    ),
    "selfIllumination": PropDescr(
        "The self illumination factor for the material",
        PropType.Float,
    ),
    "diffuseLightExtraModulation": PropDescr(
        "The diffuse light extra modulation factor",
        PropType.Float,
    ),
    "opacity": PropDescr(
        "The opacity level of the shimmer",
        PropType.Float,
    ),
}
