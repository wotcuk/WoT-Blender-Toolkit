# -*- coding: utf-8 -*-
import os
import zipfile
import tempfile
import shutil
import bpy
_pkg_list_cache = {} 
class WoTFileFinder:
    def __init__(self):
        self.temp_dir = os.path.join(tempfile.gettempdir(), "WoT_Addon_Temp")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        self.last_found_pkg = None 
    def _get_game_path(self):
        addon_name = __package__.split('.')[0]
        try:
            prefs = bpy.context.preferences.addons[addon_name].preferences
            return prefs.wot_game_path
        except: return ""
    def find(self, target_file, base_dir, internal_path, force_pkg=False, 
             pkg_name=None, tier_level=None, context_pkg=None):
        base_dir = str(base_dir)
        internal_path = internal_path.replace("\\", "/")
        filename = os.path.basename(target_file)
        if not force_pkg:
            attempt_1 = os.path.join(base_dir, filename)
            if os.path.exists(attempt_1): return attempt_1
            attempt_2 = self._search_aligned(base_dir, internal_path)
            if attempt_2: return attempt_2
            attempt_3 = self._deep_search(base_dir, filename)
            if attempt_3: return attempt_3
        game_path = self._get_game_path()
        if not game_path: return None
        pkg_dir = os.path.join(game_path, "res", "packages")
        search_order = []
        if context_pkg: search_order.append(context_pkg)
        if pkg_name: search_order.append(pkg_name)
        for p in search_order:
            found = self._check_package(pkg_dir, p, internal_path)
            if found: return found
        for pkg_file in os.listdir(pkg_dir):
            if pkg_file.endswith(".pkg"):
                found = self._check_package(pkg_dir, pkg_file, internal_path)
                if found: return found
        return None
    def _search_aligned(self, base_dir, internal_path):
        parts = internal_path.split("/")
        for part in parts:
            if part in base_dir:
                root_path = base_dir.split(part)[0]
                full_path = os.path.join(root_path, internal_path).replace("/", os.sep)
                if os.path.exists(full_path): return full_path
        return None
    def _deep_search(self, base_dir, filename):
        for root, dirs, files in os.walk(base_dir):
            if filename in files: return os.path.join(root, filename)
        return None
    def _check_package(self, pkg_dir, pkg_name, internal_path):
        if not pkg_name.endswith(".pkg"): pkg_name += ".pkg"
        pkg_path = os.path.join(pkg_dir, pkg_name)
        if not os.path.exists(pkg_path): return None
        try:
            if pkg_path not in _pkg_list_cache:
                with zipfile.ZipFile(pkg_path, 'r') as z:
                    _pkg_list_cache[pkg_path] = set(z.namelist())
            if internal_path in _pkg_list_cache[pkg_path]:
                with zipfile.ZipFile(pkg_path, 'r') as z:
                    extract_path = os.path.join(self.temp_dir, internal_path)
                    os.makedirs(os.path.dirname(extract_path), exist_ok=True)
                    with z.open(internal_path) as src, open(extract_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    self.last_found_pkg = pkg_name 
                    return extract_path
        except: pass
        return None