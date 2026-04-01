''' SkepticalFox 2015-2024 '''

# imports
import os
import logging
from struct import pack
from xml.dom.minidom import getDOMImplementation

# blender imports
import bpy  # type: ignore

# local imports
from .common.consts import visual_property_descr_dict
from .common.export_utils import packNormal_tag3, set_nodes


logger = logging.getLogger(__name__)


class BigWorldModelExporterProcessed:
    def get_vertices_and_indices(self, export_obj):
        render_set = {
            'nodes': [],
            'geometry': {
                'vertices': 'vertices',
                'primitive': 'indices',
                'primitiveGroups': {},
                'indices_section_size': 0,
                'vertices_section_size': 0
            }
        }

        primitives_group = {
            'groups': {},
            'nIndices': 0,
            'nVertices': 0,
            'nTriangleGroups': 0,
            'nPrimitives': 0,
        }

        for mat_id, mat in enumerate(export_obj.data.materials):
            primitives_group['groups'][mat_id] = {
                'name': os.path.splitext(mat.name)[0],
                'id': mat_id,
                'fx': mat.BigWorld_Shader_Path,
                'normalMap': mat.BigWorld_normalMap,
                'specularMap': mat.BigWorld_specularMap,
                'diffuseMap': mat.BigWorld_diffuseMap,
                'metallicDetailMap': mat.BigWorld_metallicDetailMap,
                'metallicGlossMap': mat.BigWorld_metallicGlossMap,
                'excludeMaskAndAOMap': mat.BigWorld_excludeMaskAndAOMap,
                'g_detailMap': mat.BigWorld_g_detailMap,
                'diffuseMap2': mat.BigWorld_diffuseMap2,
                'crashTileMap': mat.BigWorld_crashTileMap,
                'g_albedoConversions': mat.BigWorld_g_albedoConversions,
                'g_glossConversions': mat.BigWorld_g_glossConversions,
                'g_metallicConversions': mat.BigWorld_g_metallicConversions,
                'g_detailUVTiling': mat.BigWorld_g_detailUVTiling,
                'g_albedoCorrection': mat.BigWorld_g_albedoCorrection,
                'g_detailRejectTiling': mat.BigWorld_g_detailRejectTiling,
                'g_detailInfluences': mat.BigWorld_g_detailInfluences,
                'g_crashUVTiling': mat.BigWorld_g_crashUVTiling,
                'g_defaultPBSConversionParams': mat.BigWorld_g_defaultPBSConversionParams,
                'g_useDetailMetallic': mat.BigWorld_g_useDetailMetallic,
                'g_useNormalPackDXT1': mat.BigWorld_g_useNormalPackDXT1,
                'alphaTestEnable': mat.BigWorld_alphaTestEnable,
                'doubleSided': mat.BigWorld_doubleSided,
                'alphaReference': mat.BigWorld_alphaReference,
                'g_detailPowerGloss': mat.BigWorld_g_detailPowerGloss,
                'g_detailPowerAlbedo': mat.BigWorld_g_detailPowerAlbedo,
                'g_maskBias': mat.BigWorld_g_maskBias,
                'g_detailPower': mat.BigWorld_g_detailPower,
                'groupOrigin': mat.BigWorld_groupOrigin,
                'vertices': [],
                'indices': []
            }
        iv = 0
        ii = 0
        uv_layer = export_obj.data.uv_layers.active.data[:]

        old2new = {}

        for mat_id, mat in primitives_group['groups'].items():
            mat['startVertex'] = iv
            mat['startIndex'] = ii

            for poly in export_obj.data.polygons:
                if poly.material_index == mat_id:
                    loop = poly.loop_indices
                    for vidx, i in enumerate(loop):
                        vert = export_obj.data.vertices[poly.vertices[vidx]]
                        x, y, z = vert.co
                        n = export_obj.data.loops[i].normal.copy()
                        n = packNormal_tag3(n)
                        u, v = uv_layer[i].uv
                        t = export_obj.data.loops[i].tangent.copy()
                        t = packNormal_tag3(t)
                        bn = export_obj.data.loops[i].bitangent.copy()
                        bn = packNormal_tag3(bn)
                        XYZNUVTB = (x, z, y, n, u, 1-v, t, bn)
                        mat['vertices'].append( XYZNUVTB )

                        old2new[i] = iv
                        iv += 1

                    if len(loop) == 3:
                        mat['indices'].append( (old2new[loop[2]], old2new[loop[1]], old2new[loop[0]]) )
                        ii += 3

                    elif len(loop) == 4:
                        mat['indices'].append( (old2new[loop[2]], old2new[loop[1]], old2new[loop[0]]) )
                        mat['indices'].append( (old2new[loop[3]], old2new[loop[2]], old2new[loop[0]]) )
                        ii += 6

            mat['nVertices'] = iv - mat['startVertex']
            mat['nPrimitives'] = (ii - mat['startIndex'])//3

        primitives_group['nIndices'] = ii
        primitives_group['nPrimitives'] = ii//3
        primitives_group['nVertices'] = iv
        primitives_group['nTriangleGroups'] = len(primitives_group['groups'])
        export_obj.data.free_tangents()

        render_set['geometry']['primitiveGroups'] = primitives_group

        return render_set

    def export(self, export_obj, model_filepath: str, export_info: dict):
        render_set = self.get_vertices_and_indices(export_obj)

        vertices_subname = b'BPVTxyznuvtb'
        vertices_format = b'set3/xyznuvtbpc'
        vertices_secsize = 32
        vertices_pcformat = '<3fI2f2I'

        vertices_subname = pack('68s', vertices_subname)
        vertices_format = pack('64s', vertices_format)

        primitives_filepath = '%s.primitives_processed' % os.path.splitext(model_filepath)[0]
        with open(primitives_filepath, 'wb') as f:
            #####################################################################
            # Primitives Header:
            f.write(pack('<I', 0x42a14e65))


            #####################################################################
            # VERTICES

            nVertices = render_set['geometry']['primitiveGroups']['nVertices']

            f.write(vertices_subname)
            f.write(vertices_format)
            f.write(pack('<I', nVertices))

            for pg in render_set['geometry']['primitiveGroups']['groups'].values():
                for v in pg['vertices']:
                    f.write(pack(vertices_pcformat, *v))

            vertices_section_size = nVertices*vertices_secsize + 136
            if vertices_section_size%4>0:
                f.write(pack('%ds' % (4 - vertices_section_size%4), b''))
                vertices_section_size += 4 - vertices_section_size%4


            #####################################################################
            # INDICES

            nTriangleGroups = render_set['geometry']['primitiveGroups']['nTriangleGroups']
            nIndices = render_set['geometry']['primitiveGroups']['nIndices']
            nPrimitives = render_set['geometry']['primitiveGroups']['nPrimitives']

            if render_set['geometry']['primitiveGroups']['nVertices'] < 0xFFFF:
                list_format = b'list'
                list_pcformat = '<3H'
                list_secsize = 6
                list_format = pack('64s', list_format)

            else:
                list_format = b'list32'
                list_pcformat = '<3I'
                list_secsize = 12
                list_format = pack('64s', list_format)

            f.write(list_format)
            f.write(pack('<2I', nIndices, nTriangleGroups))

            for pg in render_set['geometry']['primitiveGroups']['groups'].values():
                for face in pg['indices']:
                    f.write(pack(list_pcformat, *face))

            for pg in render_set['geometry']['primitiveGroups']['groups'].values():
                f.write(pack('<4I', pg['startIndex'], pg['nPrimitives'], pg['startVertex'], pg['nVertices']))

            indices_section_size = nPrimitives*list_secsize + 72 + 16*nTriangleGroups
            if indices_section_size%4>0:
                f.write(pack('%ds' % (4 - indices_section_size%4), b''))
                indices_section_size += 4 - indices_section_size%4


            #####################################################################
            # BSP2 MATERIALS

            bsp2_materials_section = '<temp_bsp_materials.xml>\n'
            for pg in render_set['geometry']['primitiveGroups']['groups'].values():
                bsp2_materials_section += '\t<id>\t%s\t</id>\n' % pg['name']
            bsp2_materials_section += '</temp_bsp_materials.xml>'

            bsp2_materials_section = bytes(bsp2_materials_section, encoding='utf-8')
            f.write(bsp2_materials_section)

            bsp2_materials_section_size = len(bsp2_materials_section)
            if bsp2_materials_section_size%4>0:
                f.write(pack('%ds' % (4 - bsp2_materials_section_size%4), b''))
                bsp2_materials_section_size += 4 - bsp2_materials_section_size%4


            #####################################################################
            # PACKED INFORMATION

            packed_groups_info = b''


            #####################################################################
            # Vertices

            vertices_section_name = b'vertices'
            vertices_section_name_length = len(vertices_section_name)
            vertices_null_bytes = 0
            if vertices_section_name_length%4>0:
                vertices_null_bytes = 4-vertices_section_name_length%4

            pc_format = '<l16sI%ds' % (vertices_section_name_length + vertices_null_bytes)
            pc_vals = (
                vertices_section_size,
                b'',
                vertices_section_name_length,
                vertices_section_name
            )
            packed_groups_info += pack(pc_format, *pc_vals)


            #####################################################################
            # Indices

            indices_section_name = b'indices'
            indices_section_name_length = len(indices_section_name)
            indices_null_bytes = 0
            if indices_section_name_length%4>0:
                indices_null_bytes = 4-indices_section_name_length%4

            pc_format = '<l16sI%ds' % (indices_section_name_length + indices_null_bytes)
            pc_vals = (
                indices_section_size,
                b'',
                indices_section_name_length,
                indices_section_name
            )
            packed_groups_info += pack(pc_format, *pc_vals)


            #####################################################################
            # BSP2 Materials

            bsp2_materials_section_name = b'bsp2_materials'
            bsp2_materials_section_name_length = len(bsp2_materials_section_name)
            bsp2_materials_null_bytes = 0
            if bsp2_materials_section_name_length%4>0:
                bsp2_materials_null_bytes = 4-bsp2_materials_section_name_length%4

            pc_format = '<l16sI%ds' % (bsp2_materials_section_name_length + bsp2_materials_null_bytes)
            pc_vals = (
                bsp2_materials_section_size,
                b'',
                bsp2_materials_section_name_length,
                bsp2_materials_section_name
            )
            packed_groups_info += pack(pc_format, *pc_vals)

            f.write(packed_groups_info)
            f.write(pack('<l', len(packed_groups_info)))


        #####################################################################
        # .visual

        impl = getDOMImplementation()
        visual_document = impl.createDocument(None, 'root', None)
        visual_element = visual_document.documentElement


        #####################################################################
        # node

        set_nodes(export_info['nodes'], visual_element, visual_document)


        #####################################################################
        # renderSet

        __renderSet = visual_document.createElement('renderSet')
        __treatAsWorldSpaceObject = visual_document.createElement('treatAsWorldSpaceObject')
        __treatAsWorldSpaceObject.appendChild(visual_document.createTextNode('false'))
        __renderSet.appendChild(__treatAsWorldSpaceObject)
        del __treatAsWorldSpaceObject

        __node = visual_document.createElement('node')
        __node.appendChild(visual_document.createTextNode(list(export_info['nodes'].keys())[0]))
        __renderSet.appendChild(__node)
        del __node


        #####################################################################
        # geometry

        __geometry = visual_document.createElement('geometry')

        __vertices = visual_document.createElement('vertices')
        __vertices.appendChild(visual_document.createTextNode('vertices'))
        __geometry.appendChild(__vertices)

        __primitive = visual_document.createElement('primitive')
        __primitive.appendChild(visual_document.createTextNode('indices'))
        __geometry.appendChild(__primitive)

        for mat_id, mat in render_set['geometry']['primitiveGroups']['groups'].items():
            __primitiveGroup = visual_document.createElement('primitiveGroup')
            __primitiveGroup.appendChild(visual_document.createTextNode(str(mat_id)))


            #####################################################################
            # primitiveGroup -> material

            __material = visual_document.createElement('material')

            __identifier = visual_document.createElement('identifier')
            __identifier.appendChild(visual_document.createTextNode(mat['name']))
            __material.appendChild(__identifier)

            __fx = visual_document.createElement('fx')
            __fx.appendChild(visual_document.createTextNode(mat['fx']))
            __material.appendChild(__fx)

            __collisionFlags = visual_document.createElement('collisionFlags')
            __collisionFlags.appendChild(visual_document.createTextNode('0'))
            __material.appendChild(__collisionFlags)

            __materialKind = visual_document.createElement('materialKind')
            __materialKind.appendChild(visual_document.createTextNode('0'))
            __material.appendChild(__materialKind)

            for prop_name, prop_descr in visual_property_descr_dict.items():
                if mat.get(prop_name):
                    __property = visual_document.createElement('property')
                    __property.appendChild(visual_document.createTextNode(prop_name))
                    __property_value = visual_document.createElement(prop_descr.type)
                    __property_value.appendChild(visual_document.createTextNode(mat[prop_name]))
                    __property.appendChild(__property_value)
                    __material.appendChild(__property)

            __primitiveGroup.appendChild(__material)

            if mat.get('groupOrigin'):
                __groupOrigin = visual_document.createElement('groupOrigin')
                __groupOrigin.appendChild(visual_document.createTextNode(mat['groupOrigin']))
                __primitiveGroup.appendChild(__groupOrigin)

            __geometry.appendChild(__primitiveGroup)

        __renderSet.appendChild(__geometry)
        visual_element.appendChild(__renderSet)

        __boundingBox = visual_document.createElement('boundingBox')

        __min = visual_document.createElement('min')
        __min.appendChild(visual_document.createTextNode('%f %f %f' % export_info['bb_min']))
        __boundingBox.appendChild(__min)

        __max = visual_document.createElement('max')
        __max.appendChild(visual_document.createTextNode('%f %f %f' % export_info['bb_max']))
        __boundingBox.appendChild(__max)

        visual_element.appendChild(__boundingBox)


        #####################################################################
        # save .visual

        visual_filepath = '%s.visual_processed' % os.path.splitext(model_filepath)[0]
        with open(visual_filepath, 'w') as f:
            f.write(visual_document.toprettyxml())


        #####################################################################
        # .temp_model

        model_document = impl.createDocument(None, 'root', None)
        model_element = model_document.documentElement

        __info_block = model_document.createComment('\n\tblender_version: %s\n\texporter_version: %s\n\t' % (bpy.app.version_string, export_info['exporter_version']))
        model_element.appendChild(__info_block)

        __nodefullVisual = model_document.createElement('nodefullVisual')
        __nodefullVisual.appendChild(model_document.createTextNode(os.path.splitext(visual_filepath)[0]))
        model_element.appendChild(__nodefullVisual)


        #####################################################################
        # save .temp_model

        with open(model_filepath, 'w') as f:
            f.write(model_document.toprettyxml())
