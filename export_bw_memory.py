# -*- coding: utf-8 -*-
import bpy
import os
import ctypes
import struct
from ctypes import wintypes

def log(msg):
    print(f"[MEMORY INJECT] {msg}")

# --- WINDOWS API ---
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400

MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_READWRITE = 0x04
PAGE_READONLY = 0x02
PAGE_EXECUTE_READWRITE = 0x40

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]

kernel32 = ctypes.windll.kernel32

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.VirtualQueryEx.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.WriteProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.WriteProcessMemory.restype = wintypes.BOOL
kernel32.VirtualAllocEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
kernel32.VirtualAllocEx.restype = ctypes.c_void_p

def get_wot_pid():
    try:
        output = os.popen('tasklist /FI "IMAGENAME eq WorldOfTanks.exe" /NH').read()
        if "WorldOfTanks.exe" in output:
            parts = output.strip().split()
            return int(parts[1])
    except Exception as e:
        log(f"Error while searching for PID: {e}")
    return 0

def scan_vfxbin_in_memory(target_filepath):
    log("Memory scan is starting...")
    if not os.path.exists(target_filepath):
        raise Exception("The target .vfxbin file specified in the settings could not be found!")
        
    with open(target_filepath, "rb") as f:
        full_data = f.read()
        
    file_size = len(full_data)
    if file_size < 15:
        raise Exception("The file is too small and has an invalid vfxbin format!")

    pid = get_wot_pid()
    if pid == 0:
        raise Exception("WorldOfTanks.exe is not working! Make sure you have the game open.")

    log(f"WoT PID Found: {pid}. Searching for an exact file match ({file_size} byte)...")
    
    process_handle = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not process_handle:
        raise Exception("Could not connect to the game. Please run Blender as ADMINISTRATOR.")

    try:
        address = 0
        mbi = MEMORY_BASIC_INFORMATION()
        max_address = 0x7FFFFFFFFFFF 
        
        while address < max_address:
            result = kernel32.VirtualQueryEx(process_handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi))
            if result == 0: break 
            
            if mbi.State == MEM_COMMIT and mbi.Protect in [PAGE_READWRITE, PAGE_READONLY, PAGE_EXECUTE_READWRITE]:
                buffer = ctypes.create_string_buffer(mbi.RegionSize)
                bytes_read = ctypes.c_size_t(0)
                
                if kernel32.ReadProcessMemory(process_handle, ctypes.c_void_p(address), buffer, mbi.RegionSize, ctypes.byref(bytes_read)):
                    data = buffer.raw[:bytes_read.value]
                    offset = data.find(full_data)
                    
                    if offset != -1:
                        found_address = address + offset
                        log(f"Tam dosya eşleşti! Adres: {hex(found_address)}")
                        return found_address, pid, file_size
            address += mbi.RegionSize
    finally:
        kernel32.CloseHandle(process_handle)

    return 0, pid, file_size

def find_pointer_to_address(process_handle, target_address):
    log(f"Pointer scaning (Target: {hex(target_address)})...")
    target_bytes = struct.pack("<Q", target_address)

    address = 0
    mbi = MEMORY_BASIC_INFORMATION()
    max_address = 0x7FFFFFFFFFFF 
    
    while address < max_address:
        result = kernel32.VirtualQueryEx(process_handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if result == 0: break 
        
        if mbi.State == MEM_COMMIT and mbi.Protect in [PAGE_READWRITE, PAGE_READONLY]:
            buffer = ctypes.create_string_buffer(mbi.RegionSize)
            bytes_read = ctypes.c_size_t(0)
            
            if kernel32.ReadProcessMemory(process_handle, ctypes.c_void_p(address), buffer, mbi.RegionSize, ctypes.byref(bytes_read)):
                data = buffer.raw[:bytes_read.value]
                offset = data.find(target_bytes)
                
                if offset != -1:
                    found_ptr = address + offset
                    log(f"Pointer Bulundu! Adres: {hex(found_ptr)}")
                    return found_ptr
        address += mbi.RegionSize
    return 0

def export_memory_pipeline(context, root_obj, target_filepath, mem_pid, mem_address, mem_max_size, original_file):
    log("Injection procedures are being initiated...")
    
    process_handle = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION, False, mem_pid)
    if not process_handle:
        raise Exception("Unable to connect to the game with authorized permission. Is Blender running as administrator?")

    try:
        mbi = MEMORY_BASIC_INFORMATION()
        res = kernel32.VirtualQueryEx(process_handle, ctypes.c_void_p(mem_address), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if res == 0 or mbi.State != MEM_COMMIT:
            raise Exception("The memory address has been deleted from the game! Please press the 'Scan Memory' button again.")

        prefs = context.preferences.addons[__package__].preferences
        if prefs.wot_use_jit_compiler:
            log("JIT Compiler (WG) is being used. Freezing may occur...")
            from .export_bw_vfxbin import export_vfxbin_pipeline
            export_vfxbin_pipeline(context, root_obj, target_filepath)
        else:
            log("The built-in Python Packer is used. It will be injected!")
            from . import core_vfx_packer
            from .export_bw_vfx import export_vfx_pipeline
            
            temp_xml_path = target_filepath.replace(".vfxbin", "_temp.vfx")
            export_vfx_pipeline(root_obj, temp_xml_path)
            core_vfx_packer.pack_vfx_to_vfxbin(temp_xml_path, target_filepath)
            
            if os.path.exists(temp_xml_path):
                os.remove(temp_xml_path)

        if not os.path.exists(target_filepath):
            raise Exception("Derlenmiş vfxbin dosyası oluşturulamadı!")
            
        with open(target_filepath, "rb") as f:
            new_data = f.read()
            
        new_size = len(new_data)
        log(f"The compiled data: {new_size} byte. Current Limit: {mem_max_size} byte.")
        
        bytes_written = ctypes.c_size_t(0)

        if new_size > mem_max_size:
            log("File limit exceeded! Unlimited Hooking (1 Megabyte) is being triggered...")
            
            pointer_addr = find_pointer_to_address(process_handle, mem_address)
            if pointer_addr == 0:
                raise Exception("No pointer was found pointing to the original data. Hooking is not possible!")

            mega_size = 5 *1024 * 1024 
            new_allocated_mem = kernel32.VirtualAllocEx(process_handle, None, mega_size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
            if not new_allocated_mem:
                raise Exception("Could not create new space in game memory!")
            log(f"A new 1 MB plot of RAM was acquired for the game.: {hex(new_allocated_mem)}")

            success = kernel32.WriteProcessMemory(process_handle, ctypes.c_void_p(new_allocated_mem), new_data, new_size, ctypes.byref(bytes_written))
            if not success:
                raise Exception("Could not write data to the new memory!")

            new_ptr_bytes = struct.pack("<Q", new_allocated_mem)
            hook_success = kernel32.WriteProcessMemory(process_handle, ctypes.c_void_p(pointer_addr), new_ptr_bytes, 8, ctypes.byref(bytes_written))
            if not hook_success:
                raise Exception("Pointer could not be changed! (Hooking failed)")
                
            context.scene["wot_mem_address_str"] = str(new_allocated_mem)
            context.scene["wot_mem_max_size"] = mega_size
            log("Hooking successful! All subsequent exports will be written directly to this 1 MB dedicated space.")

        else:
            log("Normal Overwrite is being applied to the custom field...")
            success = kernel32.WriteProcessMemory(process_handle, ctypes.c_void_p(mem_address), new_data, new_size, ctypes.byref(bytes_written))
            if not success or bytes_written.value != new_size:
                raise Exception("An API error occurred while writing to game memory!")
            
    finally:
        kernel32.CloseHandle(process_handle)
        
    log("SUCCESS! Game memory has been manipulated.")