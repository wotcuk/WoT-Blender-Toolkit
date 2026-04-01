# -*- coding: utf-8 -*-
"""SkepticalFox 2015-2024 & Wotcuk (2026)"""

bl_info = {
    "name": "BigWorld Model With Bones .primitives,.model (.eff .vfx wip not working)",
    "author": "SkepticalFox & Wotcuk",
    "version": (1,0,0),
    "blender": (4, 3, 0),
    "location": "File > Import-Export",
    "description": "BigWorld Model and Effect Import/Export plugin",
    "warning": "Test version",
    "wiki_url": "https://kr.cm/f/t/28240/",
    "category": "Import-Export",
}

import logging
import os
import traceback
import tempfile
import re
import zipfile
import glob
import bpy
import bpy.utils.previews

from itertools import groupby
from pathlib import Path
from io import BytesIO
from xml.etree import ElementTree as ET
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Vector, Matrix

try:
    from .common.consts import visual_property_descr_dict
    from .export_bw_primitives import BigWorldModelExporter
    from .export_bw_primitives_processed import BigWorldModelExporterProcessed
    from .export_bw_primitives_skinned import BigWorldModelExporterSkinned
    from .export_bw_primitives_skinned_processed import BigWorldModelExporterSkinnedProcessed
    from .import_bw_primitives import load_bw_primitive_from_file 
    from .import_bw_primitives_textured import load_bw_primitive_textured 
    from .loadctree import ctree_load
#    from .import_bw_effects import import_bw_effect_pipeline 
#    from .import_bw_vfx import load_vfx_pipeline
#    from .export_bw_vfx import export_vfx_pipeline
    from .common.XmlUnpacker import XmlUnpacker

except ImportError as e:
    print(f"[BigWorld Import] Module Import Error: {e}")

logging.basicConfig()
logger = logging.getLogger(__name__)





# --- MENU FUNCTIONS ---
def menu_func_import_ctree(self, context):
    self.layout.operator(Import_From_CtreeFile.bl_idname, text="BigWorld (.ctree)")

def menu_func_import(self, context):
    self.layout.operator(Import_From_ModelFile.bl_idname, text="BigWorld (.model)")

def menu_func_import_eff(self, context):
    self.layout.operator(Import_From_EffFile.bl_idname, text="BigWorld Effect (.eff / .effbin) [WIP]")

def menu_func_import_vfx(self, context):
    self.layout.operator(Import_From_VfxFile.bl_idname, text="BigWorld VFX (.vfx / .vfxbin) [WIP]")

def menu_func_export(self, context):
    obj = context.active_object
    if obj and obj.type == 'EMPTY' and "bw_export_base_path" in obj:
        op = self.layout.operator(Export_WoT_Tank_Quick.bl_idname, text="BigWorld (.model)")
        op.show_dialog = True 
    else:
        self.layout.operator(Export_ModelFile.bl_idname, text="BigWorld (.model)")

def menu_func_export_vfx(self, context):
    self.layout.operator(Export_VfxFile.bl_idname, text="BigWorld VFX (.vfxxml / .vfxbin) [WIP]")


# --- TANK DATABASE & ICONS ---
custom_icons = None
tank_db = {}
cached_tiers = []
cached_nations = set()
ROMAN_NUMERALS = {"01": "I", "02": "II", "03": "III", "04": "IV", "05": "V", 
                  "06": "VI", "07": "VII", "08": "VIII", "09": "IX", "10": "X", "11": "XI"}

def scan_wot_packages(game_path):
    global tank_db, cached_tiers, cached_nations
    tank_db.clear()
    cached_tiers.clear()
    
    packages_dir = os.path.join(game_path, "res", "packages")
    scripts_pkg = os.path.join(packages_dir, "scripts.pkg")
    if not os.path.exists(scripts_pkg): 
        return False

    unpacker = XmlUnpacker()
    found_tiers = set()

    try:
        with zipfile.ZipFile(scripts_pkg, 'r') as z:
            list_files = [f for f in z.namelist() if f.startswith('scripts/item_defs/vehicles/') and f.endswith('/list.xml')]
            for xml_file in list_files:
                nation = xml_file.split('/')[3] 
                with z.open(xml_file) as f:
                    raw_data = f.read()
                    if b"<root" in raw_data[:100]: 
                        root = ET.fromstring(raw_data)
                    else: 
                        root = unpacker.read(BytesIO(raw_data))

                    if root is None: continue

                    for vehicle_node in root:
                        if vehicle_node.tag in ('xmlns:xmlref', 'userString'): continue
                        
                        tank_id = vehicle_node.tag 
                        tags_node = vehicle_node.find("tags")
                        level_node = vehicle_node.find("level")

                        if tags_node is not None and level_node is not None and tags_node.text:
                            level = int(level_node.text.strip())
                            lvl_str = f"{level:02d}"
                            tags_text = tags_node.text
                            v_type = "unknown"
                            for tc in ["lightTank", "mediumTank", "heavyTank", "AT-SPG", "SPG"]:
                                if tc in tags_text:
                                    v_type = tc
                                    break

                            is_locked = False
                            not_in_shop = vehicle_node.find("notInShop")
                            if not_in_shop is not None and not_in_shop.text and "true" in not_in_shop.text.lower():
                                is_locked = True

                            user_string = vehicle_node.findtext("userString")
                            display_name = tank_id
                            if user_string: 
                                display_name = user_string.split(':')[-1] if ':' in user_string else user_string

                            if lvl_str not in tank_db: tank_db[lvl_str] = {}
                            if nation not in tank_db[lvl_str]: tank_db[lvl_str][nation] = {}
                            if v_type not in tank_db[lvl_str][nation]: tank_db[lvl_str][nation][v_type] = []

                            tank_db[lvl_str][nation][v_type].append((tank_id, display_name, is_locked))
                            found_tiers.add(lvl_str)
                            
    except Exception as e:
        logger.error(f"[WoT Scanner] Error: {e}")

    for lvl in sorted(found_tiers):
        roman = ROMAN_NUMERALS.get(lvl, str(int(lvl)))
        cached_tiers.append((lvl, roman, f"Tier {roman}"))
    return True
    
# --- DYNAMIC SKIN & LOD SCANNER ---
tank_structure_cache = {"skins": ["default"], "lods": {}}

def analyze_tank_structure(self, context):
    global tank_structure_cache
    tank_structure_cache = {"skins": ["default"], "lods": {}}
    scn = context.scene
    prefs = bpy.context.preferences.addons[__package__].preferences

    if not scn.wot_tank_list or scn.wot_tank_list_index < 0: return

    tank_id = scn.wot_tank_list[scn.wot_tank_list_index].tank_id
    pkg_nation = NATION_ICON_MAP.get(scn.wot_selected_nation, scn.wot_selected_nation)
    tier = scn.wot_selected_tier

    packages_dir = os.path.join(prefs.wot_game_path, "res", "packages")
    pkgs_to_check = glob.glob(os.path.join(packages_dir, f"vehicles_level_{tier}*.pkg"))
    pkgs_to_check += glob.glob(os.path.join(packages_dir, "vehicles_customization*.pkg"))

    search_prefix = f"vehicles/{pkg_nation}/{tank_id}/"
    found_paths = set()

    for pkg in pkgs_to_check:
        try:
            with zipfile.ZipFile(pkg, 'r') as z:
                for name in z.namelist():
                    if name.startswith(search_prefix) and "/lod" in name: 
                        found_paths.add(name)
        except: pass

    skins = set(["default"])
    for path in found_paths:
        parts = path.split('/')
        try:
            tank_idx = parts.index(tank_id)
            sub_parts = parts[tank_idx+1:] 

            if sub_parts[0] == "_skins":
                skin_name = sub_parts[1]
                state = sub_parts[2]
                lod = sub_parts[3]
                skins.add(skin_name)
                cache_key = f"{skin_name}_{state}"
            else:
                state = sub_parts[0]
                lod = sub_parts[1]
                cache_key = f"default_{state}"

            if cache_key not in tank_structure_cache["lods"]:
                tank_structure_cache["lods"][cache_key] = set()
            tank_structure_cache["lods"][cache_key].add(lod)
        except: pass

    tank_structure_cache["skins"] = sorted(list(skins))
    for k in tank_structure_cache["lods"]:
        tank_structure_cache["lods"][k] = sorted(list(tank_structure_cache["lods"][k]))

def get_dynamic_skins(self, context):
    global tank_structure_cache
    return [(s, s, "") for s in tank_structure_cache.get("skins", ["default"])]

def get_dynamic_lods(self, context):
    global tank_structure_cache
    scn = context.scene
    state = "crash" if scn.wot_model_state == "CRASHED" else "normal"
    skin = scn.wot_selected_skin if scn.wot_selected_skin else "default"
    cache_key = f"{skin}_{state}"
    lods = tank_structure_cache.get("lods", {}).get(cache_key, [])
    if not lods: return [("lod0", "lod0", "")]
    return [(l, l, "") for l in lods]

def update_dummy(self, context): pass

def update_tank_list(self, context):
    scn = context.scene
    scn.wot_tank_list.clear() 
    t, n, v = scn.wot_selected_tier, scn.wot_selected_nation, scn.wot_selected_type
    
    if not tank_db or t not in tank_db or n not in tank_db[t] or v not in tank_db[t][n]: return
        
    for tank_id, display_name, is_locked in sorted(tank_db[t][n][v], key=lambda x: x[1]):
        item = scn.wot_tank_list.add()
        item.tank_id = tank_id
        item.display_name = display_name
        item.is_locked = is_locked
        
    scn.wot_tank_list_index = 0 
    analyze_tank_structure(None, context)

def get_dynamic_tiers(self, context):
    if not cached_tiers: return [("NONE", "None", "")]
    return cached_tiers

FIXED_NATIONS = ['china', 'czech', 'france', 'germany', 'italy', 'japan', 'poland', 'sweden', 'uk', 'usa', 'ussr']

NATION_ICON_MAP = {
    'usa': 'american', 'ussr': 'russian', 'uk': 'british', 'germany': 'german',
    'france': 'french', 'china': 'chinese', 'czech': 'czech', 'italy': 'italy',
    'japan': 'japan', 'poland': 'poland', 'sweden': 'sweden'
}

def get_static_nations(self, context):
    global custom_icons
    items = []
    for i, nat in enumerate(FIXED_NATIONS): 
        icon_name = NATION_ICON_MAP.get(nat, nat)
        if custom_icons and icon_name in custom_icons:
            icon_id = custom_icons[icon_name].icon_id
            name_display = "" 
        else:
            icon_id = 0
            name_display = nat.capitalize() 
        items.append((nat, name_display, f"{nat.capitalize()}", icon_id, i))
    return items

def get_static_types(self, context):
    global custom_icons
    base_types = [
        ("lightTank", "Light Tank"), 
        ("mediumTank", "Medium Tank"), 
        ("heavyTank", "Heavy Tank"), 
        ("AT-SPG", "Tank Destroyer"), 
        ("SPG", "SPG")
    ]
    items = []
    for i, (v_id, v_desc) in enumerate(base_types):
        if custom_icons and v_id in custom_icons:
            icon_id = custom_icons[v_id].icon_id
            name_display = ""
        else:
            icon_id = 0
            name_display = v_desc
        items.append((v_id, name_display, v_desc, icon_id, i))
    return items

# --- PATH VALIDATION & PREFERENCES ---
def update_game_path_pref(self, context):
    packages_dir = os.path.join(self.wot_game_path, "res", "packages")
    if os.path.exists(packages_dir):
        bpy.context.scene.wot_is_path_valid = True
        scan_wot_packages(self.wot_game_path)
    else:
        bpy.context.scene.wot_is_path_valid = False

class WoT_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    wot_game_path: bpy.props.StringProperty(
        name="Game Path",
        subtype='DIR_PATH',
        default=r"C:\Games\World_of_Tanks_EU",
        update=update_game_path_pref
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "wot_game_path")
        
        # --- SHORTCUT CONFIGURATION MENU ---
        layout.separator()
        layout.label(text="Shortcut Configuration:", icon='KEYINGSET')
        wm = context.window_manager
        kc = wm.keyconfigs.user
        km = kc.keymaps.get('3D View')
        if km:
            kmi = None
            for item in km.keymap_items:
                if item.idname == Export_WoT_Tank_Quick.bl_idname:
                    kmi = item
                    break
            if kmi:
                import rna_keymap_ui
                layout.context_pointer_set("keymap", km)
                rna_keymap_ui.draw_kmi([], kc, km, kmi, layout, 0)
            else:
                layout.label(text="Shortcut deleted!", icon='ERROR')
                row = layout.row()
                row.operator("preferences.wot_restore_keymap", text="Restore Default Shortcut (Alt+\")", icon='RECOVER_LAST')

class PREFERENCES_OT_wot_restore_keymap(bpy.types.Operator):
    """Restores the deleted WoT Auto-Export shortcut"""
    bl_idname = "preferences.wot_restore_keymap"
    bl_label = "Restore Keymap"
    
    def execute(self, context):
        wm = context.window_manager
        kc = wm.keyconfigs.user
        if not kc: return {'CANCELLED'}
            
        km = kc.keymaps.get('3D View')
        if not km:
            km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
            
        for item in km.keymap_items:
            if item.idname == Export_WoT_Tank_Quick.bl_idname:
                km.keymap_items.remove(item)
                
        kmi = km.keymap_items.new(Export_WoT_Tank_Quick.bl_idname, 'QUOTE', 'PRESS', alt=True)
        kmi.properties.show_dialog = False
        
        self.report({'INFO'}, "Shortcut restored successfully!")
        return {'FINISHED'}

# --- UI PANELS ---
class WoT_TankItem(bpy.types.PropertyGroup):
    tank_id: bpy.props.StringProperty()
    display_name: bpy.props.StringProperty()
    is_locked: bpy.props.BoolProperty()

class WOT_UL_TankList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if item.is_locked: layout.label(text=item.display_name, icon='LOCKED')
        else: layout.label(text=item.display_name)

class VIEW3D_PT_wot_import_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "WoT Import"
    bl_label = "Tank Import By wotcuk"

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        prefs = context.preferences.addons[__package__].preferences

        if not scn.wot_is_path_valid:
            layout.alert = True
            layout.label(text="! Games Folder Can't be found", icon='ERROR')
            layout.alert = False
            layout.prop(prefs, "wot_game_path", text="")
            return

        layout.prop(prefs, "wot_game_path", text="Path")
        layout.separator()

        layout.label(text="Tier:")
        layout.row().prop(scn, "wot_selected_tier", expand=True)

        layout.label(text="Nation:")
        layout.row(align=True).prop(scn, "wot_selected_nation", expand=True)

        layout.label(text="Vehicle Type:")
        layout.row(align=True).prop(scn, "wot_selected_type", expand=True)

        box = layout.box()
        box.label(text="Tank List:")
        box.template_list("WOT_UL_TankList", "", scn, "wot_tank_list", scn, "wot_tank_list_index", rows=6)

        box = layout.box()
        box.label(text="Extra Settings")
        box.row().prop(scn, "wot_model_state", expand=True)
        box.prop(scn, "wot_selected_skin", text="Skin")
        box.label(text="Available LODs")
        box.row().prop(scn, "wot_selected_lod", expand=True)

        layout.separator()
        row = layout.row()
        row.scale_y = 1.5
        row.operator("import_model.dummy_load", text="LOAD", icon='IMPORT')

def extract_tank_files(game_path, tier, pkg_nation, tank_id, state, lod, skin, temp_dir):
    packages_dir = os.path.join(game_path, "res", "packages")
    pkgs = glob.glob(os.path.join(packages_dir, f"vehicles_level_{tier}*.pkg"))
    pkgs += glob.glob(os.path.join(packages_dir, "vehicles_customization*.pkg"))
    pkgs += glob.glob(os.path.join(packages_dir, "shared_content*.pkg"))

    track_prefix = f"vehicles/{pkg_nation}/tracks/"
    base_prefix = f"vehicles/{pkg_nation}/{tank_id}/"
    
    if skin == "default":
        lod_prefix = f"{base_prefix}{state}/{lod}/"
        skin_prefix = None
    else:
        skin_prefix = f"vehicles/{pkg_nation}/{tank_id}/_skins/{skin}/"
        lod_prefix = f"{skin_prefix}{state}/{lod}/"

    extracted = False
    for pkg in pkgs:
        try:
            with zipfile.ZipFile(pkg, 'r') as z:
                for item in z.namelist():
                    # Skip empty directory entries in ZIP
                    if item.endswith('/'): continue
                    
                    should_extract = False
                    if item.startswith(track_prefix) and item.endswith('.dds'): should_extract = True
                    elif item.startswith(lod_prefix): should_extract = True
                    elif item.endswith('.dds'):
                        if skin == "default":
                            if item.startswith(base_prefix) and "/_skins/" not in item: should_extract = True
                        else:
                            if item.startswith(skin_prefix): should_extract = True
                            elif item.startswith(base_prefix) and "/_skins/" not in item: should_extract = True

                    if should_extract:
                        try:
                            dest = os.path.join(temp_dir, item)
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            with z.open(item) as source, open(dest, "wb") as target: 
                                target.write(source.read())
                            extracted = True
                        except Exception: pass
        except Exception: pass

    return extracted, lod_prefix

def find_hp_node(parent, name):
    """Search for a specific Hardpoint name in object children."""
    if not parent: return None
    for child in parent.children:
        if name in child.name: return child
        found = find_hp_node(child, name)
        if found: return found
    return None

def import_and_get_root(col, path):
    """Import model and return the top-level EMPTY object."""
    if not path or not os.path.exists(path): return None
    old_objs = set(col.objects)
    load_bw_primitive_textured(col, Path(path), import_empty=True)
    new_objs = set(col.objects) - old_objs
    
    for obj in new_objs:
        if obj.parent not in new_objs and obj.type == 'EMPTY': 
            # Save original filename to custom properties
            obj["bw_export_filename"] = os.path.splitext(os.path.basename(path))[0]
            return obj
    return None

class Import_WoT_Dummy_Load(bpy.types.Operator):
    bl_idname = "import_model.dummy_load"
    bl_label = "Load Tank"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scn = context.scene
        prefs = context.preferences.addons[__package__].preferences
        
        if not scn.wot_tank_list or scn.wot_tank_list_index < 0:
            self.report({'WARNING'}, "Select a tank from the list!")
            return {'CANCELLED'}

        tank_id = scn.wot_tank_list[scn.wot_tank_list_index].tank_id
        pkg_nation = NATION_ICON_MAP.get(scn.wot_selected_nation, scn.wot_selected_nation)
        tier = scn.wot_selected_tier
        state = "crash" if scn.wot_model_state == "CRASHED" else "normal"
        skin = scn.wot_selected_skin if scn.wot_selected_skin else "default"
        lod = scn.wot_selected_lod

        temp_dir = os.path.join(tempfile.gettempdir(), "WoT_Blender_Extracted")
        success, prefix = extract_tank_files(prefs.wot_game_path, tier, pkg_nation, tank_id, state, lod, skin, temp_dir)

        if not success:
            self.report({'ERROR'}, "Files not found in PKG!")
            return {'CANCELLED'}

        tank_path = os.path.join(temp_dir, os.path.normpath(prefix))
        col = context.view_layer.active_layer_collection.collection

        tank_master = bpy.data.objects.new(tank_id, None)
        col.objects.link(tank_master)
        
        if skin == "default": base_export_path = f"vehicles/{pkg_nation}/{tank_id}/{state}/"
        else: base_export_path = f"vehicles/{pkg_nation}/{tank_id}/_skins/{skin}/{state}/"
        tank_master["bw_export_base_path"] = base_export_path

        def get_files_by_prefix(prefix_name):
            if not os.path.exists(tank_path): return []
            return [f for f in os.listdir(tank_path) if f.startswith(prefix_name) and f.endswith(".model")]
            
        # Update UI progress to prevent Blender from freezing
        wm = context.window_manager
        wm.progress_begin(0, 100)
        
        def update_ui_progress(pct, text):
            wm.progress_update(pct)
            context.workspace.status_text_set(f"WoT Import: {text} ({pct}%)")
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            
        update_ui_progress(10, "Loading Chassis...")
        chassis_obj = None
        for f in get_files_by_prefix("Chassis"):
            c = import_and_get_root(col, os.path.join(tank_path, f))
            if c:
                c["wot_part"] = "Chassis"
                c.parent = tank_master
                if not chassis_obj: chassis_obj = c

        update_ui_progress(35, "Loading Hull...")
        hull_obj = None
        for f in get_files_by_prefix("Hull"):
            h = import_and_get_root(col, os.path.join(tank_path, f))
            if h:
                h["wot_part"] = "Hull"
                h.parent = tank_master
                if chassis_obj:
                    context.view_layer.update()
                    target = find_hp_node(chassis_obj, "V")
                    if target: h.matrix_world = target.matrix_world.copy()
                if not hull_obj: hull_obj = h

        update_ui_progress(60, "Loading Turret...")
        turret_objs = []
        for f in get_files_by_prefix("Turret_"):
            t = import_and_get_root(col, os.path.join(tank_path, f))
            if t:
                t["wot_part"] = "Turret"
                t.parent = tank_master
                if hull_obj:
                    context.view_layer.update()
                    target = find_hp_node(hull_obj, "HP_turretJoint")
                    if target: t.matrix_world = target.matrix_world.copy()
                turret_objs.append(t)

        update_ui_progress(85, "Loading Gun...")
        for f in get_files_by_prefix("Gun_"):
            g = import_and_get_root(col, os.path.join(tank_path, f))
            if g:
                g["wot_part"] = "Gun"
                g.parent = tank_master
                if turret_objs:
                    context.view_layer.update()
                    target = find_hp_node(turret_objs[0], "HP_gunJoint")
                    if target: g.matrix_world = target.matrix_world.copy()

        update_ui_progress(100, "Finishing...")
        wm.progress_end()
        context.workspace.status_text_set(None)

        self.report({'INFO'}, f"{tank_id} successfully imported!")
        import shutil
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            tex_temp = os.path.join(tempfile.gettempdir(), "WoT_Blender_Temp_Textures")
            shutil.rmtree(tex_temp, ignore_errors=True)
        except: pass
        return {'FINISHED'}


# --- MATERIAL PANEL ---
class BigWorld_Material_Panel(bpy.types.Panel):
    bl_label = "BigWorld Material"
    bl_idname = "MATERIAL_PT_bigworld_material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_options = {"DEFAULT_CLOSED"}
    bl_context = "material"

    def draw(self, context):
        mat = context.material
        if not mat: return
        layout = self.layout
        layout.prop(mat, "BigWorld_Shader_Path")
        layout.separator()
        if mat.use_nodes:
            box = layout.box()
            box.label(text="VFX Animation Tools:", icon='PARTICLES')
            box.operator(MATERIAL_OT_read_uv_bounds.bl_idname, icon='UV')
        layout.separator()
        if 'visual_property_descr_dict' in globals():
            for key, items in groupby(visual_property_descr_dict.items(), key=lambda it: it[1].type):
                layout.label(text=f"{key}:")
                for prop_name, _ in items: layout.prop(mat, f"BigWorld_{prop_name}")
                layout.separator()
        layout.prop(mat, "BigWorld_groupOrigin")


# --- OPERATORS ---
class Import_From_CtreeFile(bpy.types.Operator, ImportHelper):
    bl_idname = "import_model.ctree_model"
    bl_label = "Import Ctree Model"
    bl_options = {"UNDO"}
    filename_ext = ".ctree"
    filter_glob: bpy.props.StringProperty(default="*.ctree", options={"HIDDEN"})
    def execute(self, context):
        ctree_load(bpy.context.view_layer.active_layer_collection.collection, Path(self.filepath))
        return {"FINISHED"}

class Import_From_EffFile(bpy.types.Operator, ImportHelper):
    bl_idname = "import_model.bweff"
    bl_label = "Import Effect (Legacy)"
    bl_options = {"UNDO"}
    filename_ext = ".eff;.effbin"
    filter_glob: bpy.props.StringProperty(default="*.eff;*.effbin", options={"HIDDEN"})
    
    def execute(self, context):
        self.report({'WARNING'}, "Legacy Effect (.eff) Import is WIP / Not Working.")
        return {"CANCELLED"}

class Import_From_VfxFile(bpy.types.Operator, ImportHelper):
    bl_idname = "import_model.bw_vfx_new"
    bl_label = "Import VFX"
    bl_options = {"UNDO"}
    filename_ext = ".vfx;.vfxbin"
    filter_glob: bpy.props.StringProperty(default="*.vfx;*.vfxbin", options={"HIDDEN"})
    
    def execute(self, context):
        self.report({'WARNING'}, "VFX Import is currently WIP / Not Working.")
        return {"CANCELLED"}

class Import_From_ModelFile(bpy.types.Operator, ImportHelper):
    bl_idname = "import_model.bwmodel"
    bl_label = "Import Model"
    bl_options = {"UNDO"}
    filename_ext = ".model;.visual*;.primitives*"
    filter_glob: bpy.props.StringProperty(default="*.temp_model;*.model;*.visual*;*.primitives*", options={"HIDDEN"})
    import_empty: bpy.props.BoolProperty(name="Import Empty", default=True)
    import_textures: bpy.props.BoolProperty(name="Import Textures", default=True)

    def execute(self, context):
        try:
            col = bpy.context.view_layer.active_layer_collection.collection
            if self.import_textures: load_bw_primitive_textured(col, Path(self.filepath), self.import_empty)
            else: load_bw_primitive_from_file(col, Path(self.filepath), self.import_empty)
        except Exception: return {"CANCELLED"}
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "import_empty")
        layout.prop(self, "import_textures")


class NODE_OT_add_wot_vfx_node(bpy.types.Operator):
    """Add VFX Node from Library"""
    bl_idname = "node.add_wot_vfx_node"
    bl_label = "VFX WoT Animation Node"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        return {'FINISHED'}

def menu_func_add_wot_node(self, context):
    layout = self.layout
    layout.separator()
    layout.menu("NODE_MT_wot_vfx_submenu", icon='PARTICLES')

class NODE_MT_wot_vfx_submenu(bpy.types.Menu):
    bl_label = "WoT VFX Tools"
    bl_idname = "NODE_MT_wot_vfx_submenu"
    def draw(self, context):
        layout = self.layout
        layout.operator(NODE_OT_add_wot_vfx_node.bl_idname, text="Add WoT VFX System", icon='NODE_COMPOSITING')

class MATERIAL_OT_read_uv_bounds(bpy.types.Operator):
    """Calculate UV bounds and write to VFX Node"""
    bl_idname = "material.read_bw_uv_bounds"
    bl_label = "Extract Values from UV"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.active_material
    def execute(self, context):
        return {'FINISHED'}

class Export_VfxFile(bpy.types.Operator, ExportHelper):
    bl_idname = "export_model.bw_vfx_new"
    bl_label = "Export VFX"
    filename_ext = ""
    filter_glob: bpy.props.StringProperty(default="*", options={"HIDDEN"})
    
    def execute(self, context):
        self.report({'WARNING'}, "VFX Export is currently WIP / Not Working.")
        return {"CANCELLED"}


# --- EXPORT HELPERS ---
def get_nodes_by_empty(obj, export_info, is_root=True):
    from mathutils import Matrix
    if is_root:
        node_name = "Scene Root"
        # Lock Kök/Scene Root matrix to identity (0,0,0) for the engine
        matrix_to_write = [list(row) for row in Matrix()]
    else:
        node_name = os.path.splitext(obj.name)[0]
        matrix_to_write = [list(row) for row in obj.matrix_local]
    
    export_info[node_name] = {
        "loc": (0.0, 0.0, 0.0) if is_root else obj.location.xzy.to_tuple(),
        "scale": (1.0, 1.0, 1.0) if is_root else obj.scale.xzy.to_tuple(),
        "matrix": matrix_to_write, 
        "children": {},
    }
    
    obj_models = []
    for child in obj.children:
        if (child.data is None) and isinstance(child, bpy.types.Object):
            get_nodes_by_empty(child, export_info[node_name]["children"], False)
        elif isinstance(child.data, bpy.types.Mesh):
            obj_models.append(child)
    
    flat_list = []
    for item in obj_models:
        if isinstance(item, list): flat_list.extend(item)
        else: flat_list.append(item)
    return flat_list


class Export_ModelFile(bpy.types.Operator, ExportHelper):
    bl_idname = "export_model.bwmodel"
    bl_label = "Export Model"
    filename_ext = ".temp_model"
    filter_glob: bpy.props.StringProperty(default="*.temp_model", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'EMPTY' and "bw_export_base_path" not in obj

    export_system: bpy.props.EnumProperty(
        name="Export System",
        items=(("WOTCUK", "by wotcuk (Modern)", ""), ("LEGACY", "by SkepticalFox (Legacy)", "")),
        default="WOTCUK"
    )

    vertex_format: bpy.props.EnumProperty(
        name="Vertex Format",
        items=(("STANDARD", "Standard Tank", ""), ("LIGHT_VOLUME", "Simple / light", "")),
        default="STANDARD"
    )
    
    export_models: bpy.props.BoolProperty(name="Export Models (.model, .visual, .prim)", default=True)
    export_textures: bpy.props.BoolProperty(name="Export Textures (.dds)", default=True)

    visual_type: bpy.props.EnumProperty(name="Visual type", items=(("STATIC", "Static", ""), ("SKINNED", "Animated", "")), default="SKINNED")
    is_processed: bpy.props.BoolProperty(name="Processed", default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_system")
        layout.separator()
        if self.export_system == "WOTCUK":
            box = layout.box()
            box.prop(self, "vertex_format")
            box.prop(self, "export_models")
            box.prop(self, "export_textures")
        else:
            box = layout.box()
            box.prop(self, "visual_type")
            box.prop(self, "is_processed")

    def execute(self, context):
        obj = context.selected_objects[0]
        export_info = {"nodes": {}}
        export_info["vertex_format"] = self.vertex_format 
        export_info["export_models"] = self.export_models
        export_info["export_textures"] = self.export_textures
        export_info["root_matrix"] = obj.matrix_world.copy()
        export_info["original_filename"] = obj.get("bw_export_filename", "")
        obj_models = get_nodes_by_empty(obj, export_info["nodes"])

        if not len(obj_models): return {'CANCELLED'}
        export_info["exporter_version"] = "%s.%s.%s" % bl_info["version"]

        if self.export_system == "WOTCUK":
            bw_exporter = BigWorldModelExporter()
            bw_exporter.export(obj_models, self.filepath, export_info)
        else:
            if self.visual_type == "STATIC":
                export_model = self.get_export_object(obj_models)
                export_model.data.transform(export_model.matrix_world)
                bw_exporter = BigWorldModelExporterProcessed() if self.is_processed else BigWorldModelExporter()
                bw_exporter.export(export_model, self.filepath, export_info)
                bpy.data.objects.remove(export_model)
            else:
                bw_exporter = BigWorldModelExporterSkinnedProcessed() if self.is_processed else BigWorldModelExporterSkinned()
                bw_exporter.export(obj_models, self.filepath, export_info)

        return {"FINISHED"}

class Export_WoT_Tank_Quick(bpy.types.Operator):
    bl_idname = "export_model.wot_tank_quick"
    bl_label = "Auto-Export Tank to res_mods"
    bl_options = {'REGISTER', 'UNDO'}
    
    show_dialog: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    
    @classmethod
    def poll(cls, context):
        return True 
        
    def invoke(self, context, event):
        if self.show_dialog:
            return context.window_manager.invoke_props_dialog(self, width=400)
        else:
            return self.execute(context)
            
    def draw(self, context):
        layout = self.layout
        scn = context.scene
        
        layout.label(text="Auto-Export Settings", icon='EXPORT')
        layout.prop(scn, "wot_export_with_lods")
        
        if scn.wot_export_with_lods:
            layout.row().prop(scn, "wot_export_lod", expand=True)
            layout.prop(scn, "wot_export_has_parent")
            if scn.wot_export_has_parent:
                layout.prop(scn, "wot_export_extent")
    
    def execute(self, context):
        scn = context.scene
        obj = context.active_object
        
        # SMART TARGET FINDER: Climb up from active object to find Tank Root
        target_tank = None
        curr = obj
        while curr:
            if curr.type == 'EMPTY' and "bw_export_base_path" in curr:
                target_tank = curr
                break
            curr = curr.parent
            
        # Fallback: Scan scene objects to find the first valid tank root
        if not target_tank:
            for o in scn.objects:
                if o.type == 'EMPTY' and "bw_export_base_path" in o:
                    target_tank = o
                    break
                    
        if not target_tank:
            self.report({'ERROR'}, "No Tank Root (Empty) object found in the scene to export!")
            return {'CANCELLED'}
            
        prefs = context.preferences.addons[__package__].preferences
        base_path = target_tank["bw_export_base_path"]
        
        # --- AUTO-VERSION READER (version.xml) ---
        version_str = "1.24.0.0" 
        version_file = os.path.join(prefs.wot_game_path, "version.xml")
        if os.path.exists(version_file):
            try:
                with open(version_file, "r", encoding="utf-8", errors="ignore") as f:
                    match = re.search(r'<version>\s*v\.([0-9\.]+)\s*#', f.read())
                    if match: version_str = match.group(1)
            except: pass
            
        res_mods_dir = os.path.join(prefs.wot_game_path, "res_mods", version_str)
        
        # Force lod0 if LODs are disabled
        lod_folder = scn.wot_export_lod if scn.wot_export_with_lods else "lod0"
        export_dir = os.path.normpath(os.path.join(res_mods_dir, base_path, lod_folder))
        os.makedirs(export_dir, exist_ok=True)
        
        export_info = {
            "vertex_format": "STANDARD", 
            "export_models": True,
            "export_textures": True,
            "wot_export_with_lods": scn.wot_export_with_lods,
            "wot_export_lod": scn.wot_export_lod,
            "wot_export_has_parent": scn.wot_export_has_parent,
            "wot_export_extent": scn.wot_export_extent,
            "wot_base_path": base_path
        }
        
        from .export_bw_primitives import BigWorldModelExporter
        exporter = BigWorldModelExporter()
        
        valid_children = [c for c in target_tank.children if c.type == 'EMPTY' and "bw_export_filename" in c]
        total_parts = len(valid_children)
        
        wm = context.window_manager
        wm.progress_begin(0, 100) 
        
        exported_count = 0
        for idx, child in enumerate(valid_children):
            
            progress_pct = int((idx / max(total_parts, 1)) * 100)
            wm.progress_update(progress_pct)
            context.workspace.status_text_set(f"WoT Export: processing {child['bw_export_filename']} ({progress_pct}%)...")
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            
            meshes = []
            def get_meshes(parent):
                for c in parent.children:
                    if c.type == 'MESH': meshes.append(c)
                    get_meshes(c)
            get_meshes(child)
            
            if meshes:
                filename = child["bw_export_filename"]
                filepath = os.path.join(export_dir, filename + ".temp_model")
                
                export_info["original_filename"] = filename
                export_info["root_matrix"] = child.matrix_world.copy()
                
                part_nodes = {}
                get_nodes_by_empty(child, part_nodes) 
                export_info["nodes"] = part_nodes
                
                exporter.export(meshes, filepath, export_info)
                exported_count += 1
                
        wm.progress_end()
        context.workspace.status_text_set(None)
        
        self.report({'INFO'}, f"Tank ({version_str}) exported to res_mods folder!")
        return {'FINISHED'}

# --- REGISTRATION ---
addon_keymaps = []
classes = (
    WoT_AddonPreferences,
    PREFERENCES_OT_wot_restore_keymap,
    BigWorld_Material_Panel,
    Import_From_CtreeFile,
    Import_From_ModelFile,
    Import_From_EffFile,
    Import_From_VfxFile,
    Export_ModelFile,
    Export_VfxFile,
    NODE_OT_add_wot_vfx_node,
    NODE_MT_wot_vfx_submenu,
    MATERIAL_OT_read_uv_bounds,
    WoT_TankItem,                
    WOT_UL_TankList,
    VIEW3D_PT_wot_import_panel,  
    Import_WoT_Dummy_Load,
    Export_WoT_Tank_Quick
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_ctree)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_eff)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_vfx)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.NODE_MT_add.append(menu_func_add_wot_node)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_vfx)
    

    
    bpy.types.Material.BigWorld_Shader_Path = bpy.props.StringProperty(name="fx", default="shaders/std_effects/lightonly.fx")

    if 'visual_property_descr_dict' in globals():
        for name, desc in visual_property_descr_dict.items():
            setattr(bpy.types.Material, f"BigWorld_{name}", bpy.props.StringProperty(name=name, description=desc.description))

    bpy.types.Material.BigWorld_groupOrigin = bpy.props.StringProperty(name="groupOrigin")
    global custom_icons
    custom_icons = bpy.utils.previews.new()
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    if os.path.exists(icons_dir):
        for img in os.listdir(icons_dir):
            if img.endswith(".png"):
                name = os.path.splitext(img)[0]
                custom_icons.load(name, os.path.join(icons_dir, img), 'IMAGE')

    bpy.types.Scene.wot_is_path_valid = bpy.props.BoolProperty(default=False)
    
    bpy.types.Scene.wot_selected_tier = bpy.props.EnumProperty(items=get_dynamic_tiers, update=update_tank_list)
    bpy.types.Scene.wot_selected_nation = bpy.props.EnumProperty(items=get_static_nations, update=update_tank_list) 
    bpy.types.Scene.wot_selected_type = bpy.props.EnumProperty(items=get_static_types, update=update_tank_list) 
    bpy.types.Scene.wot_tank_list = bpy.props.CollectionProperty(type=WoT_TankItem)
    bpy.types.Scene.wot_tank_list_index = bpy.props.IntProperty(update=analyze_tank_structure)
    
    bpy.types.Scene.wot_model_state = bpy.props.EnumProperty(
        items=[("NORMAL", "Normal Model", ""), ("CRASHED", "Crashed Model", "")],
        update=update_dummy
    )
    bpy.types.Scene.wot_selected_skin = bpy.props.EnumProperty(
        items=get_dynamic_skins,
        update=update_dummy
    )
    bpy.types.Scene.wot_selected_lod = bpy.props.EnumProperty(
        items=get_dynamic_lods
    )
    
    bpy.types.Scene.wot_export_with_lods = bpy.props.BoolProperty(name="Export With LODs", default=False)
    bpy.types.Scene.wot_export_lod = bpy.props.EnumProperty(
        name="LOD",
        items=[(f"lod{i}", f"lod{i}", "") for i in range(8)],
        default="lod0"
    )
    bpy.types.Scene.wot_export_has_parent = bpy.props.BoolProperty(name="There Is a Parent Lod", default=False)
    bpy.types.Scene.wot_export_extent = bpy.props.FloatProperty(name="Extent", default=20.0)

    # --- KEYMAP REGISTRATION ---
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(Export_WoT_Tank_Quick.bl_idname, 'QUOTE', 'PRESS', alt=True)
        kmi.properties.show_dialog = False 
        addon_keymaps.append((km, kmi))

    def safe_init_path():
        if bpy.context and hasattr(bpy.context, "preferences"):
            prefs = bpy.context.preferences.addons[__package__].preferences
            update_game_path_pref(prefs, bpy.context)
        return None 
        
    bpy.app.timers.register(safe_init_path, first_interval=1.0)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_ctree)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_eff)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_vfx)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_vfx)
    bpy.types.NODE_MT_add.remove(menu_func_add_wot_node)
    
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    

        
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    global custom_icons
    if custom_icons is not None:
        bpy.utils.previews.remove(custom_icons)
        
    del bpy.types.Scene.wot_is_path_valid
    del bpy.types.Scene.wot_selected_tier
    del bpy.types.Scene.wot_selected_nation
    del bpy.types.Scene.wot_selected_type
    del bpy.types.Scene.wot_model_state
    del bpy.types.Scene.wot_selected_skin
    del bpy.types.Scene.wot_selected_lod
    del bpy.types.Scene.wot_tank_list
    del bpy.types.Scene.wot_tank_list_index
    del bpy.types.Scene.wot_export_with_lods
    del bpy.types.Scene.wot_export_lod
    del bpy.types.Scene.wot_export_has_parent
    del bpy.types.Scene.wot_export_extent

if __name__ == "__main__":
    register()