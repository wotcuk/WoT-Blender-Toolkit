# -*- coding: utf-8 -*-
"""SkepticalFox 2015-2024 & Wotcuk (03.07.2026)"""

bl_info = {
    "name": "BigWorld Model With Bones .primitives,.model (.eff .vfx wip not working)",
    "author": "SkepticalFox & Wotcuk",
    "version": (2,0,0),
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
    from .common.XmlUnpacker import XmlUnpacker
    from .export_bw_primitives import BigWorldModelExporter
    from .export_bw_primitives_processed import BigWorldModelExporterProcessed
    from .export_bw_primitives_skinned import BigWorldModelExporterSkinned
    from .export_bw_primitives_skinned_processed import BigWorldModelExporterSkinnedProcessed
    from .export_bw_vfx import export_vfx_pipeline
    from .import_bw_primitives import load_bw_primitive_from_file 
    from .import_bw_primitives_textured import load_bw_primitive_textured 
    from .import_bw_sequence import load_bw_sequence
    from .import_bw_effects import import_bw_effect_pipeline 
    from .import_bw_vfx import load_vfx_pipeline
    from .import_bw_animation import load_bw_animation
    from .loadctree import ctree_load
    from .file_finder import WoTFileFinder

except ImportError as e:
    print(f"[BigWorld Import] Module Import Error: {e}")

logging.basicConfig()
logger = logging.getLogger(__name__)

# --- GLOBAL FINDER ---
_global_finder = WoTFileFinder()

# --- AUTO NODE LOAD ---
@persistent
def auto_load_vfx_lib_handler(dummy):
    addon_dir = os.path.dirname(__file__)
    lib_path = os.path.join(addon_dir, "vfx_lib.blend")
    if os.path.exists(lib_path):
        try:
            with bpy.data.libraries.load(lib_path, link=False) as (data_from, data_to):
                groups_to_load = [ng for ng in data_from.node_groups if ng not in bpy.data.node_groups]
                if groups_to_load:
                    data_to.node_groups = groups_to_load
        except Exception as e:
            print(f"[VFX LOG] Auto-load error: {e}")


# --- MENU FUNCTIONS ---
def menu_func_import_ctree(self, context):
    self.layout.operator(Import_From_CtreeFile.bl_idname, text="BigWorld (.ctree)")

def menu_func_import(self, context):
    self.layout.operator(Import_From_ModelFile.bl_idname, text="BigWorld (.model)")

def menu_func_import_eff(self, context):
    self.layout.operator(Import_From_EffFile.bl_idname, text="BigWorld Effect (.eff / .effbin)")

def menu_func_import_vfx(self, context):
    self.layout.operator(Import_From_VfxFile.bl_idname, text="BigWorld VFX (.vfx / .vfxbin)")

def menu_func_import_anim(self, context):
    self.layout.operator(Import_From_AnimFile.bl_idname, text="BigWorld Animation (.anim_processed / .animation)")

def menu_func_export(self, context):
    obj = context.active_object
    if not obj:
        return

    # Tank root empty seciliyken eski LOD / parent LOD ayar penceresini ac.
    # Bu obje Import_WoT_Dummy_Load tarafinda bw_export_base_path aliyor.
    if obj.type == 'EMPTY' and "bw_export_base_path" in obj:
        op = self.layout.operator(Export_WoT_Tank_Quick.bl_idname, text="BigWorld Tank Export / LOD (.model)")
        op.show_dialog = True
        return

    # Armature veya normal empty ile manuel tek model export penceresi acilsin.
    if obj.type in {'EMPTY', 'ARMATURE'}:
        self.layout.operator(Export_ModelFile.bl_idname, text="BigWorld Manual Export (.model)")

def menu_func_export_vfx(self, context):
    self.layout.operator(Export_VfxFile.bl_idname, text="BigWorld VFX (.vfxxml / .vfxbin)")

def menu_func_import_seq(self, context):
    icon_id = custom_icons["wot_icon"].icon_id if custom_icons and "wot_icon" in custom_icons else 0
    self.layout.operator(Import_WoT_Sequence.bl_idname, text="BigWorld Sequence (.seq)", icon_value=icon_id)
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
    
# --- DYNAMIC SKIN & PART SCANNER  ---
tank_xml_cache = {
    "hull": {},
    "chassis": [],
    "turrets": [],
    "skins": ["default"],
    "lods": ["lod0"]
}

def get_chassis_items(self, context):
    items = []
    for i, ch in enumerate(tank_xml_cache.get("chassis", [])):
        items.append((str(i), f"Part {i} ({ch.get('name', 'Unknown')})", ""))
    return items if items else [("0", "None", "")]

def get_turret_items(self, context):
    items = []
    for i, tur in enumerate(tank_xml_cache.get("turrets", [])):
        items.append((str(i), f"Part {i} ({tur.get('name', 'Unknown')})", ""))
    return items if items else [("0", "None", "")]

def get_gun_items(self, context):
    scn = context.scene
    turret_idx = int(scn.wot_turret_index) if scn.wot_turret_index.isdigit() else 0
    items = []
    turrets = tank_xml_cache.get("turrets", [])
    if turrets and turret_idx < len(turrets):
        guns = turrets[turret_idx].get("guns", [])
        for i, gun in enumerate(guns):
            items.append((str(i), f"Part {i} ({gun.get('name', 'Unknown')})", ""))
    return items if items else [("0", "None", "")]

def get_dynamic_skins(self, context):
    return [(s, s, "") for s in tank_xml_cache.get("skins", ["default"])]

def get_dynamic_lods(self, context):
    lods = tank_xml_cache.get("lods", ["lod0"])
    return [(l, l, "") for l in lods]

def update_tank_parts(self, context):
    scn = context.scene
    try:
        turret_idx = int(scn.wot_turret_index) if scn.wot_turret_index.isdigit() else 0
        turrets = tank_xml_cache.get("turrets", [])
        if turrets and turret_idx < len(turrets):
            guns = turrets[turret_idx].get("guns", [])
            current_gun_idx = int(scn.wot_gun_index) if scn.wot_gun_index.isdigit() else 0
            if current_gun_idx >= len(guns):
                scn.wot_gun_index = "0"
    except:
        pass

def analyze_tank_structure(self, context):
    global tank_xml_cache
    tank_xml_cache = {"hull": {}, "chassis": [], "turrets": [], "skins": set(["default"]), "lods": set(["lod0"])}
    
    scn = context.scene
    if not scn.wot_tank_list or scn.wot_tank_list_index < 0: return

    tank_id = scn.wot_tank_list[scn.wot_tank_list_index].tank_id
    nation = scn.wot_selected_nation 
    
    internal_xml_path = f"scripts/item_defs/vehicles/{nation}/{tank_id}.xml"
    xml_file_path = _global_finder.find(target_file=f"{tank_id}.xml", base_dir="", internal_path=internal_xml_path, context_pkg="scripts.pkg")
    
    if not xml_file_path: 
        print(f"[WoT XML Error] XML Dosyası Bulunamadı: {internal_xml_path}")
        return

    try:
        with open(xml_file_path, "rb") as f:
            raw_data = f.read()
            if b"<root" in raw_data[:100]:
                root = ET.fromstring(raw_data)
            else:
                unpacker = XmlUnpacker()
                root = unpacker.read(BytesIO(raw_data))
                
        if root is None: return

        def extract_models(node):
            models_node = node.find("models")
            if models_node is None: return {}
            
            data = {
                "default": {
                    "undamaged": models_node.findtext("undamaged", "").strip(),
                    "destroyed": models_node.findtext("destroyed", "").strip(),
                    "exploded": models_node.findtext("exploded", "").strip()
                },
                "sets": {}
            }
            sets_node = models_node.find("sets")
            if sets_node is not None:
                for skin_node in sets_node:
                    skin_name = skin_node.tag
                    tank_xml_cache["skins"].add(skin_name)
                    try:
                        scn.wot_chassis_index = "0"
                        scn.wot_turret_index = "0"
                        scn.wot_gun_index = "0"
                        scn.wot_selected_skin = "default"
                        scn.wot_selected_lod = "lod0"
                    except Exception:
                        pass
                    data["sets"][skin_name] = {
                        "undamaged": skin_node.findtext("undamaged", "").strip(),
                        "destroyed": skin_node.findtext("destroyed", "").strip(),
                        "exploded": skin_node.findtext("exploded", "").strip()
                    }
            return data

        # 1. Hull 
        hull_node = root.find("hull")
        if hull_node is not None:
            tank_xml_cache["hull"] = extract_models(hull_node)

        # 2. Chassis 
        chassis_root = root.find("chassis")
        if chassis_root is not None:
            for ch_node in chassis_root:
                if ch_node.tag in ('xmlns:xmlref', 'userString', 'shared'): continue
                tank_xml_cache["chassis"].append({
                    "name": ch_node.tag,
                    "models": extract_models(ch_node)
                })

        # 3. Turrets & Guns 
        turrets_root = root.find("turrets0")
        if turrets_root is not None:
            for tur_node in turrets_root:
                if tur_node.tag in ('xmlns:xmlref', 'userString', 'shared'): continue
                
                turret_data = {
                    "name": tur_node.tag,
                    "models": extract_models(tur_node),
                    "guns": []
                }
                
                guns_root = tur_node.find("guns")
                if guns_root is not None:
                    for gun_node in guns_root:
                        if gun_node.tag in ('xmlns:xmlref', 'userString', 'shared'): continue
                        turret_data["guns"].append({
                            "name": gun_node.tag,
                            "models": extract_models(gun_node)
                        })
                
                tank_xml_cache["turrets"].append(turret_data)

        # 4. LOD
        hull_undamaged = tank_xml_cache["hull"].get("default", {}).get("undamaged", "")
        if hull_undamaged:
            lod_base_dir = os.path.dirname(hull_undamaged) 
            state_dir_path = lod_base_dir.replace("lod0", "").rstrip("/")
            
            prefs = bpy.context.preferences.addons[__package__].preferences
            packages_dir = os.path.join(prefs.wot_game_path, "res", "packages")
            tier = context.scene.wot_selected_tier
            pkgs_to_check = glob.glob(os.path.join(packages_dir, f"vehicles_level_{tier}*.pkg"))
            
            found_lods = set(["lod0"])
            for pkg in pkgs_to_check:
                try:
                    with zipfile.ZipFile(pkg, 'r') as z:
                        for name in z.namelist():
                            if name.startswith(state_dir_path) and "/lod" in name:
                                parts = name.split('/')
                                for part in parts:
                                    if part.startswith("lod"): found_lods.add(part)
                except: pass
            
            tank_xml_cache["lods"] = sorted(list(found_lods))

    except Exception as e:
        import traceback
        print(f"[WoT XML Parser Error] {e}")
        traceback.print_exc()
        
    tank_xml_cache["skins"] = sorted(list(tank_xml_cache["skins"]))

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

    wot_use_jit_compiler: bpy.props.BoolProperty(
        name="Use Jit Compiler (WG's Unified editor)",
        description="Açık: WG'nin aracı ile derler. Kapalı: Dahili yeni Python Packer kullanır.",
        default=False
    )
    wot_game_path: bpy.props.StringProperty(
        name="Game Path",
        subtype='DIR_PATH',
        default=r"C:\Games\World_of_Tanks_EU",
        update=update_game_path_pref
    )
    wot_asset_pipeline_path: bpy.props.StringProperty(
        name="Asset Pipeline Path",
        subtype='DIR_PATH',
        default=r"C:\BigWorld\asset_pipeline",
        description="batch_compiler.exe'nin bulunduğu asset_pipeline klasörü"
    )
    wot_mem_target_file: bpy.props.StringProperty(
        name="Target .vfxbin (Memory Inject)",
        subtype='FILE_PATH',
        description="Bellekte aranacak orijinal .vfxbin dosyası"
    )
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "wot_game_path")
        layout.prop(self, "wot_use_jit_compiler")
        
        if self.wot_use_jit_compiler:
            layout.prop(self, "wot_asset_pipeline_path")
            
        layout.prop(self, "wot_mem_target_file")
        
        # --- SHORTCUT CONFIGURATION MENU ---
        layout.separator()
        layout.label(text="Shortcut Configuration:", icon='KEYINGSET')
        wm = context.window_manager
        kc = wm.keyconfigs.user
        if kc:
            km = kc.keymaps.get('3D View')
            if km:
                import rna_keymap_ui
                layout.context_pointer_set("keymap", km)
                
                kmi_tank = None
                for item in km.keymap_items:
                    if item.idname == Export_WoT_Tank_Quick.bl_idname:
                        kmi_tank = item
                        break
                        
                if kmi_tank:
                    rna_keymap_ui.draw_kmi([], kc, km, kmi_tank, layout, 0)
                else:
                    layout.label(text="Tank Shortcut deleted!", icon='ERROR')

                kmi_vfx = None
                for item in km.keymap_items:
                    if item.idname == "export_model.wot_vfx_memory_quick": 
                        kmi_vfx = item
                        break
                        
                if kmi_vfx:
                    rna_keymap_ui.draw_kmi([], kc, km, kmi_vfx, layout, 0)
                else:
                    layout.label(text="VFX Shortcut deleted!", icon='ERROR')

                if not kmi_tank or not kmi_vfx:
                    row = layout.row()
                    row.operator("preferences.wot_restore_keymap", text="Restore Default Shortcuts (Alt+\")", icon='RECOVER_LAST')

class PREFERENCES_OT_wot_restore_keymap(bpy.types.Operator):
    """Restores the deleted WoT Auto-Export shortcuts"""
    bl_idname = "preferences.wot_restore_keymap"
    bl_label = "Restore Keymap"
    
    def execute(self, context):
        wm = context.window_manager
        kc = wm.keyconfigs.user
        if not kc: return {'CANCELLED'}
            
        km = kc.keymaps.get('3D View')
        if not km:
            km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
            
        items_to_remove = [item for item in km.keymap_items if item.idname in {Export_WoT_Tank_Quick.bl_idname, "export_model.wot_vfx_memory_quick"}]
        for item in items_to_remove:
            km.keymap_items.remove(item)
                
        kmi_tank = km.keymap_items.new(Export_WoT_Tank_Quick.bl_idname, 'QUOTE', 'PRESS', alt=True)
        kmi_tank.properties.show_dialog = False
        
        kmi_vfx = km.keymap_items.new("export_model.wot_vfx_memory_quick", 'QUOTE', 'PRESS', alt=True)
        
        self.report({'INFO'}, "Shortcuts restored successfully!")
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
        box.label(text="Part Variations:")
        box.prop(scn, "wot_chassis_index", text="Chassis")
        box.prop(scn, "wot_turret_index", text="Turret")
        box.prop(scn, "wot_gun_index", text="Gun")
        
        box = layout.box()
        box.label(text="Model State & Skin:")
        box.row().prop(scn, "wot_model_state", expand=True)
        box.prop(scn, "wot_selected_skin", text="Skin")
        
        box.label(text="Available LODs:")
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


# --- REFACTORED IMPORT LOGIC (USING FILEFINDER) ---
def get_bone_matrix_world(armature_obj, bone_name_substring):
    if not armature_obj or armature_obj.type != 'ARMATURE': return None
    for bone in armature_obj.pose.bones:
        if bone_name_substring in bone.name: 
            return armature_obj.matrix_world @ bone.matrix
    return None

def import_and_get_root(col, internal_path, finder, context):
    """Lojistik Merkezi üzerinden modeli bulur ve yükler."""
    found_path = finder.find(target_file=internal_path, base_dir="", internal_path=internal_path, context_pkg=context.get('last_pkg'))
    if not found_path: return None
    
    old_objs = set(col.objects)
    load_bw_primitive_textured(col, Path(found_path), import_empty=True, finder=finder, context=context)
    new_objs = set(col.objects) - old_objs
    
    for obj in new_objs:
        if obj.type == 'ARMATURE': 
            obj.hide_set(False) 
            obj["bw_export_filename"] = os.path.splitext(os.path.basename(found_path))[0]
            if finder.last_found_pkg: context['last_pkg'] = finder.last_found_pkg
            return obj
    return None

class Import_WoT_Sequence(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.wot_sequence"
    bl_label = "Import BigWorld Sequence (.seq)"
    bl_options = {'PRESET', 'UNDO'}
    
    filename_ext = ".seq"
    filter_glob: bpy.props.StringProperty(default="*.seq", options={'HIDDEN'})
    
    def execute(self, context):
        return load_bw_sequence(self.filepath)

class Import_WoT_Dummy_Load(bpy.types.Operator):
    bl_idname = "import_model.dummy_load"
    bl_label = "Load Tank"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scn = context.scene
        if not scn.wot_tank_list or scn.wot_tank_list_index < 0:
            self.report({'WARNING'}, "Select a tank from the list!")
            return {'CANCELLED'}

        finder = _global_finder
        import_ctx = {'last_pkg': None}
        col = context.view_layer.active_layer_collection.collection
        
        tank_id = scn.wot_tank_list[scn.wot_tank_list_index].tank_id
        state = "destroyed" if scn.wot_model_state == "CRASHED" else "undamaged"
        skin = scn.wot_selected_skin if scn.wot_selected_skin else "default"
        selected_lod = scn.wot_selected_lod

        tank_master = bpy.data.objects.new(tank_id, None)
        col.objects.link(tank_master)
        pkg_nation = NATION_ICON_MAP.get(scn.wot_selected_nation, scn.wot_selected_nation)
        state_folder = "crash" if scn.wot_model_state == "CRASHED" else "normal"
        
        if skin == "default":
            tank_master["bw_export_base_path"] = f"vehicles/{pkg_nation}/{tank_id}/{state_folder}/"
        else:
            tank_master["bw_export_base_path"] = f"vehicles/{pkg_nation}/{tank_id}/_skins/{skin}/{state_folder}/"
        # Path Resolver Helper
        def get_model_path(part_models_dict):
            if not part_models_dict: return None
            
            if skin != "default" and skin in part_models_dict.get("sets", {}):
                base_path = part_models_dict["sets"][skin].get(state, "")
            else:
                base_path = part_models_dict.get("default", {}).get(state, "")
                
            if not base_path: return None
            
            if selected_lod != "lod0":
                base_path = base_path.replace("lod0", selected_lod)
            return base_path

        wm = context.window_manager
        wm.progress_begin(0, 100)
        
        def load_part(int_path, part_name, parent_obj, align_target_obj=None, align_bone=None):
            if not int_path: return None
            
            obj = import_and_get_root(col, int_path, finder, import_ctx)
            if obj:
                obj["wot_part"] = part_name
                obj["bw_export_filename"] = os.path.splitext(os.path.basename(int_path))[0]
                obj.parent = parent_obj 
                
                if align_target_obj and align_bone:
                    context.view_layer.update()
                    target_mtx = get_bone_matrix_world(align_target_obj, align_bone)
                    if target_mtx: obj.matrix_world = target_mtx.copy()
            return obj

        ch_idx = int(scn.wot_chassis_index) if scn.wot_chassis_index.isdigit() else 0
        tur_idx = int(scn.wot_turret_index) if scn.wot_turret_index.isdigit() else 0
        gun_idx = int(scn.wot_gun_index) if scn.wot_gun_index.isdigit() else 0

        wm.progress_update(20)
        chassis_list = tank_xml_cache.get("chassis", [])
        chassis_obj = None
        if chassis_list and ch_idx < len(chassis_list):
            ch_path = get_model_path(chassis_list[ch_idx].get("models", {}))
            chassis_obj = load_part(ch_path, "Chassis", tank_master)

        wm.progress_update(50)
        hull_path = get_model_path(tank_xml_cache.get("hull", {}))
        hull_obj = load_part(hull_path, "Hull", tank_master, chassis_obj, "V")

        wm.progress_update(75)
        turret_list = tank_xml_cache.get("turrets", [])
        turret_obj = None
        if turret_list and tur_idx < len(turret_list):
            tur_path = get_model_path(turret_list[tur_idx].get("models", {}))
            turret_obj = load_part(tur_path, "Turret", tank_master, hull_obj, "HP_turretJoint")
            
            guns_list = turret_list[tur_idx].get("guns", [])
            if guns_list and gun_idx < len(guns_list):
                gun_path = get_model_path(guns_list[gun_idx].get("models", {}))
                load_part(gun_path, "Gun", tank_master, turret_obj, "HP_gunJoint")

        wm.progress_update(100)
        wm.progress_end()
        
        self.report({'INFO'}, f"{tank_id} successfully loaded!")
        return {'FINISHED'}

class WOT_OT_LiveSandbox(bpy.types.Operator):
    bl_idname = "wot.live_sandbox"
    bl_label = "WoT Live Sandbox"
    bl_description = "Blender sahnesini oyun içi ImGui penceresine bağlar"

    def execute(self, context):
        try:
            from . import live_sandbox 
            live_sandbox.start_sync()
            self.report({'INFO'}, "WoT Live Sandbox bağlantısı başlatıldı!")
        except ImportError:
            self.report({'ERROR'}, "live_sandbox.py dosyası bulunamadı! Lütfen oluşturun.")
        except Exception as e:
            self.report({'ERROR'}, f"Bağlantı Hatası: {e}")
        return {'FINISHED'}

def menu_func_window_sandbox(self, context):
    self.layout.separator()
    self.layout.operator(WOT_OT_LiveSandbox.bl_idname, icon='PLAY')
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
        try: import_bw_effect_pipeline(str(self.filepath))
        except Exception as e: return {"CANCELLED"}
        return {"FINISHED"}

class Import_From_VfxFile(bpy.types.Operator, ImportHelper):
    bl_idname = "import_model.bw_vfx_new"
    bl_label = "Import VFX"
    bl_options = {"UNDO"}
    filename_ext = ".vfx;.vfxbin"
    filter_glob: bpy.props.StringProperty(default="*.vfx;*.vfxbin", options={"HIDDEN"})
    
    def execute(self, context):
        filepath_str = str(self.filepath)
        
        try: 
            if filepath_str.endswith(".vfxbin"):
                from . import core_vfx_unpacker
                out_xml = filepath_str.replace(".vfxbin", ".vfx")
                core_vfx_unpacker.unpack_single_vfxbin(filepath_str, out_xml)
                self.report({'INFO'}, "VFXBIN başarıyla XML'e çevrildi, sahneye yükleniyor...")
                load_vfx_pipeline(out_xml)
            else:
                load_vfx_pipeline(filepath_str)
        except Exception as e: 
            import traceback
            traceback.print_exc() 
            self.report({'ERROR'}, f"VFX Import Hatası: {e}") 
            return {"CANCELLED"}
        return {"FINISHED"}

class Import_From_AnimFile(bpy.types.Operator, ImportHelper):
    bl_idname = "import_model.bwanim"
    bl_label = "Import Animation"
    bl_options = {"UNDO"}
    filename_ext = ""
    filter_glob: bpy.props.StringProperty(
        default="*.anim*", 
        options={"HIDDEN"}
    )
    
    def execute(self, context):
        try:
            load_bw_animation(str(self.filepath))
        except Exception as e:
            self.report({'ERROR'}, f"Animasyon Import Hatasi: {e}")
            return {"CANCELLED"}
        return {"FINISHED"}

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
            if self.import_textures: load_bw_primitive_textured(col, Path(self.filepath), self.import_empty, finder=_global_finder, context={'last_pkg': None})
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
        # Only poll True if the object is a MESH and has an active material.
        return obj and obj.type == 'MESH' and obj.active_material

    def execute(self, context):
        obj = context.active_object
        mat = obj.active_material
        
        if not mat.use_nodes:
            self.report({'WARNING'}, "Material does not use nodes!")
            return {'CANCELLED'}
            
        mesh = obj.data
        if not mesh.uv_layers.active:
            self.report({'WARNING'}, "No active UV map found on object!")
            return {'CANCELLED'}
            
        # Get all UV coordinates from the active UV layer
        uv_layer = mesh.uv_layers.active.data
        uvs = [loop_uv.uv for loop_uv in uv_layer]
        
        if not uvs:
            return {'CANCELLED'}
            
        # Calculate bounding box
        min_u = min([uv[0] for uv in uvs])
        max_u = max([uv[0] for uv in uvs])
        min_v = min([uv[1] for uv in uvs])
        max_v = max([uv[1] for uv in uvs])
        
        # Find the VFX Animation Node
        anim_node = None
        for node in mat.node_tree.nodes:
            if node.type == 'GROUP' and node.node_tree and "VFX_WoT_Animation_Node" in node.node_tree.name:
                anim_node = node
                break
            elif node.name == "VFX_WoT_Animation_Node":
                anim_node = node
                break
                
        if not anim_node:
            self.report({'WARNING'}, "VFX_WoT_Animation_Node not found in material!")
            return {'CANCELLED'}
            
        # Apply values to the specific inputs shown in the image
        try:
            anim_node.inputs["particle.UV_set.left"].default_value = min_u
            anim_node.inputs["particle.UV_set.right"].default_value = max_u
            anim_node.inputs["particle.UV_set.down"].default_value = min_v
            anim_node.inputs["particle.UV_set.up"].default_value = max_v
            
            self.report({'INFO'}, f"UV bounds extracted: L:{min_u:.3f} R:{max_u:.3f} D:{min_v:.3f} U:{max_v:.3f}")
        except KeyError as e:
            self.report({'ERROR'}, f"Input socket not found on node: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

VFX_EXPORT_FORMATS = [
    ("VFX", "XML Source (.vfx)", "İnsan okunabilir XML formatında dışa aktar"),
    ("VFXBIN", "Compiled Binary (.vfxbin)", "Derlenmiş binary formatı (Şu an işlevsiz)"),
    ("MEMORY", "WriteGameMemory", "Doğrudan oyun belleğine yaz (Şu an işlevsiz)")
]

class EXPORT_OT_scan_wot_memory(bpy.types.Operator):
    """Seçilen .vfxbin dosyasını World of Tanks belleğinde arar"""
    bl_idname = "export_model.scan_wot_memory"
    bl_label = "Bellekte Tara ve Bul"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scn = context.scene
        prefs = context.preferences.addons[__package__].preferences
        target_file = prefs.wot_mem_target_file
        
        if not target_file or not os.path.exists(target_file):
            self.report({'ERROR'}, "Lütfen eklenti ayarlarından (Preferences) hedef bir .vfxbin dosyası seçin!")
            return {'CANCELLED'}

        try:
            from .export_bw_memory import scan_vfxbin_in_memory
            
            address, pid, max_size = scan_vfxbin_in_memory(target_file)
            
            if address and address != 0:
                # DÜZELTME: Blender'ın 32-bit int sınırını aşmak için adresi STRING'e çeviriyoruz
                scn["wot_mem_address_str"] = str(address)
                scn["wot_mem_pid"] = pid
                scn["wot_mem_max_size"] = max_size
                
                self.report({'INFO'}, f"Bulundu! Bellek Adresi: {hex(address)}")
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "Dosya oyun belleğinde bulunamadı! Efektin oyunda oynatıldığından emin olun.")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Bellek Tarama Hatası: {str(e)}")
            return {'CANCELLED'}


class Export_VfxFile(bpy.types.Operator, ExportHelper):
    bl_idname = "export_model.bw_vfx_new"
    bl_label = "Export VFX"
    
    filename_ext = "" 
    filter_glob: bpy.props.StringProperty(default="*", options={"HIDDEN"})
    
    export_format: bpy.props.EnumProperty(
        name="Export Format",
        description="VFX çıktı formatını seçin",
        items=VFX_EXPORT_FORMATS,
        default="VFX"
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != 'EMPTY':
            return False
        return obj.name.startswith("Root_") or "hybrid_effect" in obj

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        prefs = context.preferences.addons[__package__].preferences
        layout.prop(self, "export_format")
        
        if self.export_format == "MEMORY":
            layout.separator()
            box = layout.box()
            box.label(text="Canlı Bellek Enjeksiyonu", icon='MEMORY')
            
            if not prefs.wot_mem_target_file:
                box.label(text="Ayarlardan hedef dosya seçin!", icon='ERROR')
            else:
                box.label(text=f"Hedef: {os.path.basename(prefs.wot_mem_target_file)}", icon='FILE')
            
            row = box.row()
            row.scale_y = 1.5
            row.operator(EXPORT_OT_scan_wot_memory.bl_idname, icon='VIEWZOOM')
            
            mem_address_str = scn.get("wot_mem_address_str", "0")
            mem_address = int(mem_address_str) if isinstance(mem_address_str, str) else 0
            
            if mem_address != 0:
                mem_pid = scn.get("wot_mem_pid", 0)
                mem_max_size = scn.get("wot_mem_max_size", 0)
                
                box.label(text=f"PID: {mem_pid}", icon='CONSOLE')
                box.label(text=f"Adres: {hex(mem_address)}", icon='BOOKMARKS')
                box.label(text=f"Max Limit: {mem_max_size} byte", icon='SORTSIZE')
            else:
                box.label(text="Durum: Bekleniyor...", icon='INFO')

    def execute(self, context):
        root_obj = context.active_object
        export_dir = os.path.dirname(self.filepath)
        filename_base = os.path.splitext(os.path.basename(self.filepath))[0]
        scn = context.scene
        prefs = context.preferences.addons[__package__].preferences
        
        if self.export_format == "MEMORY":
            mem_address_str = scn.get("wot_mem_address_str", "0")
            mem_address = int(mem_address_str) if isinstance(mem_address_str, str) else 0
            
            if mem_address == 0:
                self.report({'ERROR'}, "Önce bellekte tarama yapıp hedef adresi bulmalısınız!")
                return {'CANCELLED'}
                
            mem_pid = scn.get("wot_mem_pid", 0)
            mem_max_size = scn.get("wot_mem_max_size", 0)
            mem_target_file = prefs.wot_mem_target_file
                
            from .export_bw_memory import export_memory_pipeline
            filepath = os.path.join(export_dir, filename_base + ".vfxbin")
            
            try:
                export_memory_pipeline(context, root_obj, filepath, mem_pid, mem_address, mem_max_size, mem_target_file)
                self.report({'INFO'}, f"Oyun Belleğine Başarıyla Enjekte Edildi!")
                return {"FINISHED"}
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.report({'ERROR'}, f"Memory Injection Hatası: {str(e)}")
                return {"CANCELLED"}
                
        elif self.export_format == "VFXBIN":
            filepath = os.path.join(export_dir, filename_base + ".vfxbin")
            
            if prefs.wot_use_jit_compiler:
                from .export_bw_vfxbin import export_vfxbin_pipeline
                try:
                    export_vfxbin_pipeline(context, root_obj, filepath)
                    self.report({'INFO'}, f"VFXBIN (WG JIT) Başarıyla Derlendi: {filename_base}.vfxbin")
                    return {"FINISHED"}
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.report({'ERROR'}, f"JIT Export Hatası: {str(e)}")
                    return {"CANCELLED"}
            else:
                from . import core_vfx_packer
                from .export_bw_vfx import export_vfx_pipeline
                
                temp_xml_path = os.path.join(export_dir, filename_base + "_temp.vfx")
                try:
                    export_vfx_pipeline(root_obj, temp_xml_path)
                    core_vfx_packer.pack_vfx_to_vfxbin(temp_xml_path, filepath)
                    
                    if os.path.exists(temp_xml_path):
                        os.remove(temp_xml_path)
                        
                    self.report({'INFO'}, f"VFXBIN (Dahili Packer) Başarıyla Derlendi: {filename_base}.vfxbin")
                    return {"FINISHED"}
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.report({'ERROR'}, f"Dahili Packer Hatası: {str(e)}")
                    return {"CANCELLED"}
            
        # Standart VFX XML Export
        filepath = os.path.join(export_dir, filename_base + ".vfx")
        try: 
            from .export_bw_vfx import export_vfx_pipeline
            export_vfx_pipeline(root_obj, filepath)
        except Exception as e: 
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"VFX Export Hatası: {str(e)}")
            return {"CANCELLED"}
            
        self.report({'INFO'}, f"VFX Başarıyla Dışa Aktarıldı: {filename_base}.vfx")
        return {"FINISHED"}


# --- EXPORT HELPERS ---
def get_nodes_by_empty(obj, export_info, bone=None, is_root=True):
    from mathutils import Matrix
    
    if is_root:
        node_name = "Scene Root"
        matrix_to_write = [list(row) for row in Matrix()]
        export_info[node_name] = {"matrix": matrix_to_write, "children": {}}
        
        if obj and obj.type == 'ARMATURE':
            for root_bone in obj.data.bones:
                if not root_bone.parent:
                    if root_bone.name == "Scene Root":
                        for child_bone in root_bone.children:
                            get_nodes_by_empty(obj, export_info[node_name]["children"], child_bone, False)
                    else:
                        get_nodes_by_empty(obj, export_info[node_name]["children"], root_bone, False)
        obj_models = [c for c in obj.children if c.type == 'MESH']
        return obj_models
    
    else:
        node_name = bone.name
        if node_name == "Scene Root":
             for child_bone in bone.children:
                 get_nodes_by_empty(obj, export_info, child_bone, False)
             return

        if bone.parent:
            local_mat = bone.parent.matrix_local.inverted() @ bone.matrix_local
        else:
            local_mat = bone.matrix_local
            
        matrix_to_write = [list(row) for row in local_mat]
        export_info[node_name] = {"matrix": matrix_to_write, "children": {}}
        
        for child_bone in bone.children:
            get_nodes_by_empty(obj, export_info[node_name]["children"], child_bone, False)
VF_ITEMS = [
    ("set3/xyznuviiiwwtbpc", "40-byte (Skinned/Standard)", ""),
    ("set3/xyznuvitbpc", "36-byte (xyznuvitbpc)", ""),
    ("set3/xyznuvtbpc", "32-byte (xyznuvtbpc)", ""),
    ("set3/xyznuviiiwwpc", "32-byte (xyznuviiiwwpc)", ""),
    ("set3/xyznuvpc", "24-byte (xyznuvpc)", ""),
    ("xyz", "12-byte (xyz)", "")
]

SHADER_ITEMS = [
    ("shaders/controlPoint/wg_controlPointRadius.fx", "wg_controlPointRadius.fx", ""),
    ("shaders/custom/coloronly_alpha.fx", "coloronly_alpha.fx", ""),
    ("shaders/custom/emissive.fx", "emissive.fx", ""),
    ("shaders/custom/emissive_angle_falloff.fx", "emissive_angle_falloff.fx", ""),
    ("shaders/custom/emissive_playground.fx", "emissive_playground.fx", ""),
    ("shaders/custom/env_color_mask.fx", "env_color_mask.fx", ""),
    ("shaders/custom/hw_volumetric_effect_vtx.fx", "hw_volumetric_effect_vtx.fx", ""),
    ("shaders/custom/interior_mapping.fx", "interior_mapping.fx", ""),
    ("shaders/custom/intersection_sphere.fx", "intersection_sphere.fx", ""),
    ("shaders/custom/shield_shimmer.fx", "shield_shimmer.fx", ""),
    ("shaders/custom/ui_3D.fx", "ui_3D.fx", ""),
    ("shaders/custom/VAT.fx", "VAT.fx", ""),
    ("shaders/custom/vector_animation.fx", "vector_animation.fx", ""),
    ("shaders/custom/vector_animation_2.fx", "vector_animation_2.fx", ""),
    ("shaders/custom/volumetric_effect.fx", "volumetric_effect.fx", ""),
    ("shaders/custom/volumetric_effect_freshnel_invert.fx", "volumetric_effect_freshnel_invert.fx", ""),
    ("shaders/custom/volumetric_effect_layer_vtx.fx", "volumetric_effect_layer_vtx.fx", ""),
    ("shaders/custom/volumetric_effect_vtx.fx", "volumetric_effect_vtx.fx", ""),
    ("shaders/custom/volumetric_effect_vtx_skinned.fx", "volumetric_effect_vtx_skinned.fx", ""),
    ("shaders/decals/PBS_mesh_decal.fx", "PBS_mesh_decal.fx", ""),
    ("shaders/environment/light_flare.fx", "light_flare.fx", ""),
    ("shaders/environment/sky_box.fx", "sky_box.fx", ""),
    ("shaders/environment/sky_box_HDR.fx", "sky_box_HDR.fx", ""),
    ("shaders/gpu_particles/gpu_particle_pbs_ext.fx", "gpu_particle_pbs_ext.fx", ""),
    ("shaders/particles/wg_particles.fx", "wg_particles.fx", ""),
    ("shaders/std_effects/fur_skinned.fx", "fur_skinned.fx", ""),
    ("shaders/std_effects/glow.fx", "glow.fx", ""),
    ("shaders/std_effects/glow_tone_mapping_compensation.fx", "glow_tone_mapping_compensation.fx", ""),
    ("shaders/std_effects/lightonly.fx", "lightonly.fx", ""),
    ("shaders/std_effects/lightonly_add.fx", "lightonly_add.fx", ""),
    ("shaders/std_effects/lightonly_alpha.fx", "lightonly_alpha.fx", ""),
    ("shaders/std_effects/lightonly_alpha_modalpha.fx", "lightonly_alpha_modalpha.fx", ""),
    ("shaders/std_effects/lightonly_skinned.fx", "lightonly_skinned.fx", ""),
    ("shaders/std_effects/lightonly_specmap.fx", "lightonly_specmap.fx", ""),
    ("shaders/std_effects/normalmap_specmap.fx", "normalmap_specmap.fx", ""),
    ("shaders/std_effects/PBS_ext.fx", "PBS_ext.fx", ""),
    ("shaders/std_effects/PBS_ext_detail.fx", "PBS_ext_detail.fx", ""),
    ("shaders/std_effects/PBS_ext_detail_dual.fx", "PBS_ext_detail_dual.fx", ""),
    ("shaders/std_effects/PBS_ext_detail_repaint.fx", "PBS_ext_detail_repaint.fx", ""),
    ("shaders/std_effects/PBS_ext_detail_repaint_rigid_skinned.fx", "PBS_ext_detail_repaint_rigid_skinned.fx", ""),
    ("shaders/std_effects/PBS_ext_detail_rigid_skinned.fx", "PBS_ext_detail_rigid_skinned.fx", ""),
    ("shaders/std_effects/PBS_ext_dissolve_skinned_dual.fx", "PBS_ext_dissolve_skinned_dual.fx", ""),
    ("shaders/std_effects/PBS_ext_dual.fx", "PBS_ext_dual.fx", ""),
    ("shaders/std_effects/PBS_ext_dual_skinned.fx", "PBS_ext_dual_skinned.fx", ""),
    ("shaders/std_effects/PBS_ext_repaint.fx", "PBS_ext_repaint.fx", ""),
    ("shaders/std_effects/PBS_ext_repaint_rigid_skinned.fx", "PBS_ext_repaint_rigid_skinned.fx", ""),
    ("shaders/std_effects/PBS_ext_repaint_skinned.fx", "PBS_ext_repaint_skinned.fx", ""),
    ("shaders/std_effects/PBS_ext_rigid_skinned.fx", "PBS_ext_rigid_skinned.fx", ""),
    ("shaders/std_effects/PBS_ext_rigid_skinned_dual.fx", "PBS_ext_rigid_skinned_dual.fx", ""),
    ("shaders/std_effects/PBS_ext_skinned.fx", "PBS_ext_skinned.fx", ""),
    ("shaders/std_effects/PBS_ext_skinned_dual.fx", "PBS_ext_skinned_dual.fx", ""),
    ("shaders/std_effects/PBS_ext_skinned_repaint.fx", "PBS_ext_skinned_repaint.fx", ""),
    ("shaders/std_effects/PBS_flag.fx", "PBS_flag.fx", ""),
    ("shaders/std_effects/PBS_flag_skinned.fx", "PBS_flag_skinned.fx", ""),
    ("shaders/std_effects/PBS_glass.fx", "PBS_glass.fx", ""),
    ("shaders/std_effects/PBS_glass_rigid_skinned.fx", "PBS_glass_rigid_skinned.fx", ""),
    ("shaders/std_effects/PBS_glass_skinned.fx", "PBS_glass_skinned.fx", ""),
    ("shaders/std_effects/PBS_sss_skinned.fx", "PBS_sss_skinned.fx", ""),
    ("shaders/std_effects/PBS_tank.fx", "PBS_tank.fx", ""),
    ("shaders/std_effects/PBS_tank_crash.fx", "PBS_tank_crash.fx", ""),
    ("shaders/std_effects/PBS_tank_damage.fx", "PBS_tank_damage.fx", ""),
    ("shaders/std_effects/PBS_tank_fade.fx", "PBS_tank_fade.fx", ""),
    ("shaders/std_effects/PBS_tank_precise_edge.fx", "PBS_tank_precise_edge.fx", ""),
    ("shaders/std_effects/PBS_tank_skinned.fx", "PBS_tank_skinned.fx", ""),
    ("shaders/std_effects/PBS_tank_skinned_ao.fx", "PBS_tank_skinned_ao.fx", ""),
    ("shaders/std_effects/PBS_tank_skinned_crash.fx", "PBS_tank_skinned_crash.fx", ""),
    ("shaders/std_effects/PBS_tank_tracks.fx", "PBS_tank_tracks.fx", ""),
    ("shaders/std_effects/PBS_tank_uvtransform_skinned_ao.fx", "PBS_tank_uvtransform_skinned_ao.fx", ""),
    ("shaders/std_effects/pbs_tank_skinned.fx", "pbs_tank_skinned.fx (Lowercase)", ""),
    ("shaders/std_effects/PBS_tiled.fx", "PBS_tiled.fx", ""),
    ("shaders/std_effects/PBS_tiled_atlas_global.fx", "PBS_tiled_atlas_global.fx", ""),
    ("shaders/std_effects/PBS_tiled_global.fx", "PBS_tiled_global.fx", ""),
    ("shaders/std_effects/PBS_tiled_global_skinned.fx", "PBS_tiled_global_skinned.fx", ""),
    ("shaders/std_effects/PBS_tiled_rigid_skinned.fx", "PBS_tiled_rigid_skinned.fx", ""),
    ("shaders/std_effects/PBS_tiled_skinned.fx", "PBS_tiled_skinned.fx", ""),
    ("shaders/std_effects/PBS_wheel_skinned.fx", "PBS_wheel_skinned.fx", ""),
    ("shaders/std_effects/PBS_wheel_skinned_crash.fx", "PBS_wheel_skinned_crash.fx", ""),
    ("shaders/std_effects/red_wall_alpha.fx", "red_wall_alpha.fx", ""),
    ("shaders/wg_particles/pbs_mesh_particles.fx", "pbs_mesh_particles.fx", "")
]

SPACE_ITEMS = [
    ("LOCAL", "Local (Bone/Skinned)", ""),
    ("GLOBAL", "Global (Scene Root)", "")
]

class Export_ModelFile(bpy.types.Operator, ExportHelper):
    bl_idname = "export_model.bwmodel"
    bl_label = "Export Model"
    filename_ext = ".temp_model"
    filter_glob: bpy.props.StringProperty(default="*.temp_model", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type in {'EMPTY', 'ARMATURE'}
        
    export_template: bpy.props.EnumProperty(
        name="Export Templates",
        items=(("STANDARD", "Standard Tank", ""), ("SIMPLE", "Simple / Light", ""), ("MANUAL", "Manual (Advanced)", "")),
        default="STANDARD"
    )
    
    export_models: bpy.props.BoolProperty(name="Export Models (.model, .visual, .prim)", default=True)
    export_textures: bpy.props.BoolProperty(name="Export Textures (.dds)", default=True)
    exp_manual_tawso: bpy.props.BoolProperty(name="Manual TreatAsWorldSpace", default=False)
    exp_tawso: bpy.props.BoolProperty(name="Treat As World Space Object", default=True)
    exp_vcolors: bpy.props.BoolProperty(name="Export Vertex Colors", default=True)
    exp_manual_vf: bpy.props.BoolProperty(name="Manual Vertex Format", default=False)
    exp_vf: bpy.props.EnumProperty(items=VF_ITEMS)
    exp_manual_space: bpy.props.BoolProperty(name="Manual Coordinate Space", default=False)
    exp_space: bpy.props.EnumProperty(items=SPACE_ITEMS)
    exp_manual_shader: bpy.props.BoolProperty(name="Manual Shader", default=False)
    exp_shader: bpy.props.EnumProperty(items=SHADER_ITEMS)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_models")
        layout.prop(self, "export_textures")
        layout.separator()
        layout.prop(self, "export_template")
        if self.export_template == "MANUAL":
            box = layout.box()
            box.prop(self, "exp_vcolors")
            
            box.prop(self, "exp_manual_vf")
            if self.exp_manual_vf: box.prop(self, "exp_vf", text="")
                
            box.prop(self, "exp_manual_space")
            if self.exp_manual_space: box.prop(self, "exp_space", text="")
                
            box.prop(self, "exp_manual_shader")
            if self.exp_manual_shader: box.prop(self, "exp_shader", text="")
            
            box.prop(self, "exp_manual_tawso")
            if self.exp_manual_tawso: box.prop(self, "exp_tawso")

    def execute(self, context):
        obj = context.active_object
        if not obj: return {'CANCELLED'}
            
        export_info = {"nodes": {}}
        export_info["export_models"] = self.export_models
        export_info["export_textures"] = self.export_textures
        export_info["root_matrix"] = obj.matrix_world.copy()
        export_info["original_filename"] = obj.get("bw_export_filename", "")
        export_info["export_vcolors"] = True # Varsayılan
        
        if self.export_template == "STANDARD":
            export_info["use_manual_shader"] = False
            
        elif self.export_template == "SIMPLE":
            export_info["use_manual_shader"] = True
            export_info["manual_shader"] = "shaders/custom/vector_animation_2.fx"
            
        elif self.export_template == "MANUAL":
            export_info["export_vcolors"] = self.exp_vcolors
            export_info["use_manual_vf"] = self.exp_manual_vf
            export_info["manual_vf"] = self.exp_vf
            export_info["use_manual_space"] = self.exp_manual_space
            export_info["manual_space"] = self.exp_space
            export_info["use_manual_shader"] = self.exp_manual_shader
            export_info["manual_shader"] = self.exp_shader
            export_info["use_manual_tawso"] = self.exp_manual_tawso
            export_info["manual_tawso"] = self.exp_tawso

        obj_models = get_nodes_by_empty(obj, export_info["nodes"])
        if not len(obj_models): return {'CANCELLED'}

        from .export_bw_primitives import BigWorldModelExporter
        bw_exporter = BigWorldModelExporter()
        bw_exporter.export(obj_models, self.filepath, export_info)

        return {"FINISHED"}

class Export_WoT_Tank_Quick(bpy.types.Operator):
    bl_idname = "export_model.wot_tank_quick"
    bl_label = "Auto-Export Tank to res_mods"
    bl_options = {'REGISTER', 'UNDO'}
    show_dialog: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'EMPTY' and "bw_export_base_path" in obj
        
    def invoke(self, context, event):
        if self.show_dialog: return context.window_manager.invoke_props_dialog(self, width=400)
        else: return self.execute(context)
            
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
                
        layout.separator()
        layout.label(text="Advanced Overrides", icon='MODIFIER')
        box = layout.box()
        box.prop(scn, "wot_exp_vcolors")
        
        box.prop(scn, "wot_exp_manual_vf")
        if scn.wot_exp_manual_vf: box.prop(scn, "wot_exp_vf", text="")
            
        box.prop(scn, "wot_exp_manual_space")
        if scn.wot_exp_manual_space: box.prop(scn, "wot_exp_space", text="")
            
        box.prop(scn, "wot_exp_manual_shader")
        if scn.wot_exp_manual_shader: box.prop(scn, "wot_exp_shader", text="")
        box.prop(scn, "wot_exp_manual_tawso")
        if scn.wot_exp_manual_tawso: box.prop(scn, "wot_exp_tawso")
    def execute(self, context):
        scn = context.scene
        target_tank = context.active_object
        
        if not target_tank or "bw_export_base_path" not in target_tank:
            self.report({'ERROR'}, "Selected object is not a valid Tank Root!")
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
            "export_models": True, "export_textures": True,
            "wot_export_with_lods": scn.wot_export_with_lods,
            "wot_export_lod": scn.wot_export_lod,
            "wot_export_has_parent": scn.wot_export_has_parent,
            "wot_export_extent": scn.wot_export_extent,
            "wot_base_path": base_path,
            "export_vcolors": scn.wot_exp_vcolors,
            "use_manual_vf": scn.wot_exp_manual_vf,
            "manual_vf": scn.wot_exp_vf,
            "use_manual_space": scn.wot_exp_manual_space,
            "manual_space": scn.wot_exp_space,
            "use_manual_shader": scn.wot_exp_manual_shader,
            "manual_shader": scn.wot_exp_shader,
            "use_manual_tawso": scn.wot_exp_manual_tawso,
            "manual_tawso": scn.wot_exp_tawso
        }
        
        from .export_bw_primitives import BigWorldModelExporter
        exporter = BigWorldModelExporter()
        
        valid_children = [c for c in target_tank.children if c.type == 'ARMATURE' and "bw_export_filename" in c]
        total_parts = len(valid_children)
        
        wm = context.window_manager
        wm.progress_begin(0, 100) 
        
        exported_count = 0
        for idx, child in enumerate(valid_children):
            
            progress_pct = int((idx / max(total_parts, 1)) * 100)
            wm.progress_update(progress_pct)
            context.workspace.status_text_set(f"WoT Export: processing {child['bw_export_filename']} ({progress_pct}%)...")
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            
            part_nodes = {}
            meshes = get_nodes_by_empty(child, part_nodes) 
            
            if meshes:
                filename = child["bw_export_filename"]
                filepath = os.path.join(export_dir, filename + ".temp_model")
                
                export_info["original_filename"] = filename
                export_info["root_matrix"] = child.matrix_world.copy()
                export_info["nodes"] = part_nodes
                
                exporter.export(meshes, filepath, export_info)
                exported_count += 1
                
        wm.progress_end()
        context.workspace.status_text_set(None)
        
        self.report({'INFO'}, f"Tank ({version_str}) exported to res_mods folder!")
        return {'FINISHED'}

class Export_WoT_VFX_Memory_Quick(bpy.types.Operator):
    bl_idname = "export_model.wot_vfx_memory_quick"
    bl_label = "Auto-Export VFX to Game Memory"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return True
        
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        
        if prefs.wot_use_jit_compiler:
            self.report({'INFO'}, "JIT Compiler kullanılarak belleğe yazılıyor... (WIP)")
        else:
            self.report({'INFO'}, "Dahili Python Packer kullanılarak belleğe yazılıyor... (WIP)")
            
        return {'FINISHED'}

class VIEW3D_PT_wot_vfx_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "WoT Import"
    bl_label = "VFX & Effect Explorer"

    def draw(self, context):
        layout = self.layout
        scn = context.scene

        layout.label(text="Oyun Paketlerinden Ara:", icon='VIEWZOOM')
        layout.row().prop(scn, "wot_vfx_search_type", expand=True)
        
        box = layout.box()
        box.label(text="İleride burası dolacak...", icon='INFO')
        box.label(text="Dosya listesi burada yer alacak.")
        
        layout.separator()
        row = layout.row()
        row.scale_y = 1.2
        row.operator("import_model.dummy_load", text="Import Seçileni", icon='IMPORT') # Şimdilik dummy butonu bağladım
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
    Import_WoT_Sequence,
    Import_WoT_Dummy_Load,
    Import_From_AnimFile,
    Export_ModelFile,
    Export_VfxFile,
    EXPORT_OT_scan_wot_memory,
    NODE_OT_add_wot_vfx_node,
    NODE_MT_wot_vfx_submenu,
    MATERIAL_OT_read_uv_bounds,
    WoT_TankItem,                
    WOT_UL_TankList,
    VIEW3D_PT_wot_import_panel,
    VIEW3D_PT_wot_vfx_panel,
    Export_WoT_Tank_Quick,
    WOT_OT_LiveSandbox,
    Export_WoT_VFX_Memory_Quick
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_ctree)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_eff)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_vfx)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_anim)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_seq)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.NODE_MT_add.append(menu_func_add_wot_node)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_vfx)
    bpy.types.TOPBAR_MT_window.append(menu_func_window_sandbox)
    
    if auto_load_vfx_lib_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(auto_load_vfx_lib_handler)
    
    bpy.types.Material.BigWorld_Shader_Path = bpy.props.StringProperty(name="fx", default="shaders/std_effects/PBS_tank_skinned.fx")

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
    bpy.types.Scene.wot_mem_target_file = bpy.props.StringProperty(
        name="Hedef .vfxbin",
        description="Bellekte aranacak orijinal dosya",
        subtype='FILE_PATH'
    )
    bpy.types.Scene.wot_is_path_valid = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.wot_vfx_search_type = bpy.props.EnumProperty(
        items=[("VFXBIN", ".vfxbin (Particle)", ""), ("EFFBIN", ".effbin (Effect)", "")],
        name="Dosya Türü"
    )
    bpy.types.Scene.wot_exp_manual_tawso = bpy.props.BoolProperty(name="Manual TreatAsWorldSpace", default=False)
    bpy.types.Scene.wot_exp_tawso = bpy.props.BoolProperty(name="Treat As World Space Object", default=True)
    bpy.types.Scene.wot_exp_vcolors = bpy.props.BoolProperty(name="Export Vertex Colors", default=True)
    bpy.types.Scene.wot_exp_manual_vf = bpy.props.BoolProperty(name="Manual Vertex Format", default=False)
    bpy.types.Scene.wot_exp_vf = bpy.props.EnumProperty(items=VF_ITEMS)
    bpy.types.Scene.wot_exp_manual_space = bpy.props.BoolProperty(name="Manual Space", default=False)
    bpy.types.Scene.wot_exp_space = bpy.props.EnumProperty(items=SPACE_ITEMS)
    bpy.types.Scene.wot_exp_manual_shader = bpy.props.BoolProperty(name="Manual Shader", default=False)
    bpy.types.Scene.wot_exp_shader = bpy.props.EnumProperty(items=SHADER_ITEMS)
    bpy.types.Scene.wot_selected_tier = bpy.props.EnumProperty(items=get_dynamic_tiers, update=update_tank_list)
    bpy.types.Scene.wot_selected_nation = bpy.props.EnumProperty(items=get_static_nations, update=update_tank_list) 
    bpy.types.Scene.wot_selected_type = bpy.props.EnumProperty(items=get_static_types, update=update_tank_list) 
    bpy.types.Scene.wot_tank_list = bpy.props.CollectionProperty(type=WoT_TankItem)
    bpy.types.Scene.wot_tank_list_index = bpy.props.IntProperty(update=analyze_tank_structure)
    
    bpy.types.Scene.wot_chassis_index = bpy.props.EnumProperty(items=get_chassis_items, update=update_tank_parts)
    bpy.types.Scene.wot_turret_index = bpy.props.EnumProperty(items=get_turret_items, update=update_tank_parts)
    bpy.types.Scene.wot_gun_index = bpy.props.EnumProperty(items=get_gun_items, update=update_tank_parts)

    bpy.types.Scene.wot_model_state = bpy.props.EnumProperty(
        items=[("NORMAL", "Normal Model", ""), ("CRASHED", "Crashed Model", "")]
    )
    bpy.types.Scene.wot_selected_skin = bpy.props.EnumProperty(
        items=get_dynamic_skins, update=update_tank_parts
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
        
        kmi_tank = km.keymap_items.new(Export_WoT_Tank_Quick.bl_idname, 'QUOTE', 'PRESS', alt=True)
        kmi_tank.properties.show_dialog = False 
        addon_keymaps.append((km, kmi_tank))
        
        kmi_vfx = km.keymap_items.new(Export_WoT_VFX_Memory_Quick.bl_idname, 'QUOTE', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi_vfx))

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
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_anim)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_seq)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_vfx)
    bpy.types.NODE_MT_add.remove(menu_func_add_wot_node)
    bpy.types.TOPBAR_MT_window.remove(menu_func_window_sandbox)
    
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    if auto_load_vfx_lib_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(auto_load_vfx_lib_handler)
        
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    global custom_icons
    if custom_icons is not None:
        bpy.utils.previews.remove(custom_icons)
        
    del bpy.types.Scene.wot_vfx_search_type
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
    del bpy.types.Scene.wot_mem_target_file
    del bpy.types.Scene.wot_chassis_index
    del bpy.types.Scene.wot_turret_index
    del bpy.types.Scene.wot_gun_index

if __name__ == "__main__":
    register()