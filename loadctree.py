"""SkepticalFox 2015-2024"""

# imports
from pathlib import Path
import logging

# blender imports
import bpy  # type: ignore
from mathutils import Vector  # type: ignore
from bpy_extras.image_utils import load_image  # type: ignore

# local imports
from .TreesReader import TreesReader
from .common.consts import VERBOSE_VALIDATE


logger = logging.getLogger(__name__)


def ctree_load(col: bpy.types.Collection, filepath: Path):
    with filepath.open("rb") as f:
        tree = TreesReader.read(f)

    for obj in tree.objects:
        faces = []
        match obj.name:
            case "stock" | "branches":
                for triStrip in obj.indices:
                    for i in range(len(triStrip) - 2):
                        if i % 2 == 0:
                            a = triStrip[i + 0]
                            b = triStrip[i + 1]
                            c = triStrip[i + 2]
                        else:
                            a = triStrip[i + 2]
                            b = triStrip[i + 1]
                            c = triStrip[i + 0]
                        faces.append([a, b, c])
            case "billboard" | "leaves":
                for triStrip in obj.indices:
                    for i in range(0, len(triStrip) - 3, 3):
                        faces.append(triStrip[i : i + 3])

        verts = [v.position.xzy for v in obj.vertices]

        bmesh = bpy.data.meshes.new(obj.name)
        bmesh.from_pydata(verts, [], faces)

        uv_layer = bmesh.uv_layers.new()
        uv_layer.active = True
        uv_layer = uv_layer.data[:]

        for poly in bmesh.polygons:
            for li in poly.loop_indices:
                vi = bmesh.loops[li].vertex_index
                uv_layer[li].uv = obj.vertices[vi].uv

        material = bpy.data.materials.new("Material_" + obj.name)
        material.use_nodes = True

        node_tree = material.node_tree
        node_tree.nodes.clear()

        out_node = node_tree.nodes.new('ShaderNodeOutputMaterial')

        shader_node = node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        shader_node.inputs['Roughness'].default_value = 1.0
        node_tree.links.new(shader_node.outputs['BSDF'], out_node.inputs['Surface'])

        diffuseMap = filepath.parent / obj.diffMap.name
        normalMap = filepath.parent / obj.normMap.name

        if diffuseMap.is_file():
            tex_node = node_tree.nodes.new('ShaderNodeTexImage')
            tex_node.image = load_image(str(diffuseMap), check_existing=True)
            node_tree.links.new(tex_node.outputs['Color'], shader_node.inputs['Base Color'])
            node_tree.links.new(tex_node.outputs['Alpha'], shader_node.inputs['Alpha'])

        if normalMap.is_file():
            # TODO:
            tex_node = node_tree.nodes.new('ShaderNodeTexImage')
            tex_node.image = load_image(str(normalMap), check_existing=True)
            tex_node.image.colorspace_settings.name = 'Non-Color'

        bmesh.materials.append(material)

        logger.info("validating bmesh...")
        bmesh.validate(verbose=VERBOSE_VALIDATE)
        bmesh.update()

        ob = bpy.data.objects.new(obj.name, bmesh)
        ob.location = Vector((0, 0, 0))
        col.objects.link(ob)
