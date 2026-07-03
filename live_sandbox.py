#Don't use it, it's very incomplete.
import bpy
import ctypes
from ctypes import wintypes
import mmap
import struct
import threading
import time

IPC_MEM_NAME = "Local\\WOT_Blender_IPC"

# 100 Byte'lık format.
pack_format = '<iqiiiiiiiiiiiqiiiiiqq'
IPC_SIZE = struct.calcsize(pack_format)

sync_running = False
ipc_map = None
sync_thread = None
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 64-bit Veri Bütünlüğü İçin
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

shared_cursor_handle = 0
is_hovering_blender_global = False 

def get_blender_hwnd():
    return user32.GetActiveWindow()

def update_cursor_timer():
    global shared_cursor_handle
    try:
        hwnd = getattr(bpy, "sandbox_hwnd", 0)
        if not hwnd: return 0.05
        
        if not is_hovering_blender_global:
            shared_cursor_handle = 0  
            return 0.05
            
        user32.SendMessageW(hwnd, 0x0020, hwnd, (0x0200 << 16) | 1)
        user32.GetCursor.restype = ctypes.c_void_p
        cur = user32.GetCursor()
        
        if cur is None or cur == 0:
            shared_cursor_handle = -1 
        else:
            shared_cursor_handle = cur
                
    except Exception:
        pass
    return 0.05

def sync_loop(hwnd):
    global sync_running, ipc_map, shared_cursor_handle, is_hovering_blender_global

    try:
        ipc_map = mmap.mmap(-1, IPC_SIZE, IPC_MEM_NAME)
        ipc_map.seek(0)
        ipc_map.write(struct.pack(pack_format, 1, hwnd, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))

        last_w, last_h, last_sx, last_sy = 0, 0, -1, -1
        last_lc, last_rc, last_mc = 0, 0, 0
        last_mx, last_my = -1, -1
        
        last_hovering = False 
        active_game_thread = 0      
        active_blender_thread = 0   

        while sync_running:
            ipc_map.seek(0)
            data = ipc_map.read(IPC_SIZE)  
            
            (status, c_hwnd, target_w, target_h, scr_x, scr_y,
             mx, my, lc, rc, mc, scroll, mods, cursor_id, is_hovering_blender,
             force_x, force_y, do_force,
             key_msg, key_wparam, key_lparam) = struct.unpack(pack_format, data)

            is_hovering_blender_global = (is_hovering_blender == 1)

            # --- 1. 
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if not (ex_style & WS_EX_NOACTIVATE):
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE)

            GWL_STYLE = -16
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            bad_styles = 0x00C00000 | 0x00040000 | 0x00080000
            if style & bad_styles:
                user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~bad_styles)
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)

            if target_w > 50 and target_h > 50:
                if target_w != last_w or target_h != last_h or scr_x != last_sx or scr_y != last_sy:
                    # 1 = HWND_BOTTOM (Ekranın en dibi)
                    # 0x0010 = SWP_NOACTIVATE (Z-Order değişirken odaklanmayı engeller)
                    user32.SetWindowPos(hwnd, 1, scr_x, scr_y, target_w, target_h, 0x0010) 
                    last_w, last_h, last_sx, last_sy = target_w, target_h, scr_x, scr_y

            # --- 2. 
            if is_hovering_blender_global and not last_hovering:
                game_hwnd = user32.GetForegroundWindow()
                
                if game_hwnd and game_hwnd != hwnd:
                    active_game_thread = user32.GetWindowThreadProcessId(game_hwnd, None)
                    active_blender_thread = user32.GetWindowThreadProcessId(hwnd, None)
                    
                    if active_game_thread and active_game_thread != active_blender_thread:
                        user32.AttachThreadInput(active_blender_thread, active_game_thread, True)
                
                user32.PostMessageW(hwnd, 0x0007, 0, 0) # WM_SETFOCUS
                last_hovering = True

            elif not is_hovering_blender_global and last_hovering:
                user32.PostMessageW(hwnd, 0x0008, 0, 0) # WM_KILLFOCUS
                if active_game_thread and active_blender_thread and active_game_thread != active_blender_thread:
                    user32.AttachThreadInput(active_blender_thread, active_game_thread, False)
                    active_game_thread = 0
                    active_blender_thread = 0
                    
                last_hovering = False

            # --- 3. KLAVYE SİMÜLASYONU ---
            if key_msg != 0:
                user32.PostMessageW(hwnd, key_msg, wintypes.WPARAM(key_wparam), wintypes.LPARAM(key_lparam))

            # --- 4. FARE EKRAN SARMALAMA (WRAP) MANTIĞI ---
            new_do_force = 0
            new_force_x = mx
            new_force_y = my

            if (lc or rc or mc):
                margin = 2
                if target_w > margin * 2 and target_h > margin * 2:
                    if mx <= margin:
                        new_force_x = target_w - margin - 2
                        new_do_force = 1
                    elif mx >= target_w - margin:
                        new_force_x = margin + 2
                        new_do_force = 1
                        
                    if my <= margin:
                        new_force_y = target_h - margin - 2
                        new_do_force = 1
                    elif my >= target_h - margin:
                        new_force_y = margin + 2
                        new_do_force = 1

            lparam = ((my & 0xFFFF) << 16) | (mx & 0xFFFF)
            wparam = mods

            if (lc and not last_lc) or (rc and not last_rc) or (mc and not last_mc):
                user32.PostMessageW(hwnd, 0x0021, hwnd, (0x0201 << 16) | 1)

            if mx != last_mx or my != last_my:
                user32.PostMessageW(hwnd, 0x0200, wparam, lparam)
                last_mx, last_my = mx, my

            if lc != last_lc:
                msg = 0x0201 if lc else 0x0202
                user32.PostMessageW(hwnd, msg, wparam | (1 if lc else 0), lparam)
                last_lc = lc

            if rc != last_rc:
                msg = 0x0204 if rc else 0x0205
                user32.PostMessageW(hwnd, msg, wparam | (2 if rc else 0), lparam)
                last_rc = rc

            if mc != last_mc:
                msg = 0x0207 if mc else 0x0208
                user32.PostMessageW(hwnd, msg, wparam | (16 if mc else 0), lparam)
                last_mc = mc

            if scroll != 0:
                scr_lparam = ((scr_y & 0xFFFF) << 16) | (scr_x & 0xFFFF)
                scroll_wparam = ((scroll & 0xFFFF) << 16) | (mods & 0xFFFF)
                user32.PostMessageW(hwnd, 0x020A, scroll_wparam, scr_lparam)

            ipc_map.seek(0)
            ipc_map.write(struct.pack(pack_format, 1, hwnd, last_w, last_h, last_sx, last_sy,
                                      mx, my, lc, rc, mc, 0, mods, shared_cursor_handle, 
                                      1 if is_hovering_blender_global else 0,
                                      new_force_x, new_force_y, new_do_force,
                                      0, 0, 0))

            time.sleep(0.01)

    except Exception as e:
        print(f"[Live Sandbox] Hata: {e}")
        sync_running = False
    finally:
        if ipc_map:
            try:
                if active_game_thread and active_blender_thread and active_game_thread != active_blender_thread:
                    user32.AttachThreadInput(active_blender_thread, active_game_thread, False)
                user32.PostMessageW(hwnd, 0x0008, 0, 0) # Temiz çıkış için odak sil
                ipc_map.seek(0)
                ipc_map.write(struct.pack('<iq', 0, 0))
                ipc_map.close()
            except:
                pass

def start_sync():
    global sync_running, sync_thread
    if sync_running: return
    hwnd = get_blender_hwnd()
    if not hwnd: return

    bpy.sandbox_hwnd = hwnd

    if hasattr(bpy, "active_cursor_timer"):
        if bpy.app.timers.is_registered(bpy.active_cursor_timer):
            bpy.app.timers.unregister(bpy.active_cursor_timer)

    bpy.active_cursor_timer = update_cursor_timer
    bpy.app.timers.register(bpy.active_cursor_timer)

    sync_running = True
    sync_thread = threading.Thread(target=sync_loop, args=(hwnd,))
    sync_thread.daemon = True
    sync_thread.start()
    print("[Live Sandbox] Senkronizasyon Başlatıldı!")

def stop_sync():
    global sync_running
    sync_running = False
    if hasattr(bpy, "active_cursor_timer"):
        if bpy.app.timers.is_registered(bpy.active_cursor_timer):
            bpy.app.timers.unregister(bpy.active_cursor_timer)