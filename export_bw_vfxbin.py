# -*- coding: utf-8 -*-
import bpy
import os
import shutil
import subprocess
from .export_bw_vfx import export_vfx_pipeline

def log(msg):
    print(f"[VFXBIN EXPORT] {msg}")

def export_vfxbin_pipeline(context, root_obj, target_filepath):
    prefs = context.preferences.addons[__package__].preferences
    asset_pipeline_dir = prefs.wot_asset_pipeline_path
    
    if not asset_pipeline_dir or not os.path.exists(asset_pipeline_dir):
        raise Exception("The Asset Pipeline folder path is incorrect or not set!")
        
    batch_compiler_path = os.path.join(asset_pipeline_dir, "batch_compiler.exe")
    if not os.path.exists(batch_compiler_path):
        raise Exception(f"batch_compiler.exe not found: {batch_compiler_path}")

    filename = os.path.basename(target_filepath)
    filename_base = os.path.splitext(filename)[0]
    
    asset_parent = os.path.dirname(os.path.normpath(asset_pipeline_dir))
    res_particles_dir = os.path.join(asset_parent, "res", "particles")
    os.makedirs(res_particles_dir, exist_ok=True)
    
    temp_vfx_path = os.path.join(res_particles_dir, f"{filename_base}.vfx")
    compiled_vfxbin_path = os.path.join(asset_parent, ".jit", "output", "particles", f"{filename_base}.vfxbin")

    if os.path.exists(temp_vfx_path):
        try:
            os.remove(temp_vfx_path)
            log("The old temporary .vfx file has been cleaned up.")
        except Exception as e:
            raise Exception(f"The old .vfx file could not be deleted! It might be being used by another program: {e}")

    if os.path.exists(compiled_vfxbin_path):
        try:
            os.remove(compiled_vfxbin_path)
            log("The old compiled .vfxbin file has been cleaned up.")
        except Exception as e:
            raise Exception(f"The old .vfx bin file could not be deleted! The batch compiler may still be running in the background: {e}")
    # ---------------------------------

    log(f"Creating a temporary .vfx file: {temp_vfx_path}")
    export_vfx_pipeline(root_obj, temp_vfx_path)

    log("batch_compiler.exe running...")
    cmd = [
        batch_compiler_path, 
        "-j", "0",
        "--plugins-config-file", "batch_compiler_plugins.txt",
        "--intermediate-path", "../.jit/intermediate",
        "--output-path", "../.jit/output",
        f"particles\\{filename_base}.vfx"
    ]
    
    try:
        import subprocess
        subprocess.run(
            cmd, 
            cwd=asset_pipeline_dir, 
            check=True, 
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except subprocess.CalledProcessError as e:
        raise Exception(f"Compilation error (batch_compiler): {e}")

    if not os.path.exists(compiled_vfxbin_path):
        raise Exception(f"Compilation completed but .vfxbin file not found! Expected path: {compiled_vfxbin_path}")

    final_vfxbin_dest = os.path.splitext(target_filepath)[0] + ".vfxbin"
    
    import shutil
    shutil.copy2(compiled_vfxbin_path, final_vfxbin_dest)
    log(f"Operation successful. File transferred.: {final_vfxbin_dest}")