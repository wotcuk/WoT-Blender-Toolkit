# WoT-Blender-Toolkit
Advanced skeletal modding suite for World of Tanks &amp; BigWorld Engine. Full bone hierarchy support with direct skin-weight painting in Blender 4.3. Engineered for high-precision tank modeling and custom .primitives workflows. A panel for directly importing from the game has also been added.This project is an improved version, with added features, of the Blender Tank Viewer Add-on developed by **SkepticalFox.** 
**Features currently supported by the addon imports:**
- You can import the model using the .model, .primitives_processed, and .visual_processed files.
- Imported models have a bone painting; you can see it in the Weight painting section.
- If the imported model has vertex coloring, the alpha channel is connected by default.
- If you try to import textures during the import process, the code automatically attempts to find the textures using a hierarchy scan, so the textures of the materials are included in the import.
- By pressing the N key, you can open a menu that directly scans the game's .pkg files and imports the desired vehicle model along with its textures.
**Features currently supported by the addon exports:**
- All models can be exported with a 40-byte tank structure with bone components. The exported bones are exported/imported with their inclined axes.
- For exported models, .model, .visual, .primitives, and texture files are automatically created. Depending on the export location, the res_mods hierarchy attempts to write to the .visual and .model files. If the path is incorrect, the game will crash when trying to load the model.
- Texture changes you make in Blender are saved as modified .dds files in the export folder during export. If there is a hierarchy for tanks (tank_name/normal/lod0), texture files are saved directly to the (tank_name) folder; if the file path cannot be found, they are saved to the model's folder.
- Although simple lighting models can currently be imported, they cause problems during export. The main reason for this is that the .visual file is written differently. If you replace the mesh names in the original .visual file with those in the exported file and use that file, you can export the lighting models (with vertex colors).
- The quick export shortcut can be changed in the addon settings.
**Features I plan to add in the future:** 
- There is an infrastructure that directly imports vfxbin (and indirectly .effbin) files, but I haven't shared it yet because it fails in the export phase.
- To add gravity physics, Turn towards the camera, and initial velocity physics to exported models via Blender, write an automatic script (in the res_mods folder) (for the bones on the tank).
- Writing automated scripts to add gravity physics, initial velocity physics, initial random rotation motion, rotational acceleration, collision motor, and bounce motor to exported models using Blender (for World models).
- Exporting World models (currently only tanks and basic lights are supported, but you can use tank models as World models)
- Direct import and export of .seq files.
/---------------------------------------------------------------------------------------------
**How to install:** 
Download the project files directly as a zip file 
![Pasted image 20260402100858](images%20(readme)/Pasted%20image%2020260402100858.png)
and extract them into the Blender folder (Blender Foundation\Blender 4.3\4.3\scripts\addons_core), meaning the files should be in the (Blender Foundation\Blender 4.3\4.3\scripts\addons_core\WoT-Blender-Toolkit-main) folder. The main installation location of Blender is usually (C:\Program Files\Blender Foundation). After setup, activate the addon from the addon settings and assign your own quick export key.
![601](images%20(readme)/Pasted%20image%2020260402101914.png)
You can then set your game location and the quick export shortcut from here:
![Pasted image 20260402102041](images%20(readme)/Pasted%20image%2020260402102041.png)
/---------------------------------------------------------------------------------------------
**How to use:**
1. **Automatic import**:
	After turning on the blender, press the N button to open and close the side menus.
	![Pasted image 20260402101516](images%20(readme)/Pasted%20image%2020260402101516.png)
	![Pasted image 20260402102251](images%20(readme)/Pasted%20image%2020260402102251.png)![152](images%20(readme)/Pasted%20image%2020260402102341.png)
	To update the list, you need to click on any filter.
	![Pasted image 20260402102548](images%20(readme)/Pasted%20image%2020260402102548.png)
	After finding your tank, the models are loaded according to the option you choose from the extra settings: Normal model (the one that is not destroyed and is visible in the game) and Crashed (the destroyed tank model). If the model you choose has a skin (some skins have the hull in different locations, so only the turret and chassis may be included), you need to select a skin from the skin list. Based on all the above selections, all available LODs within that package file are presented as options. Since LOD0 is the most detailed model, if you are doing a simple operation, I recommend loading and modifying the LOD0 model and exporting it using quick export. And press the LOAD button.Blender may freeze for a while, but this is normal because import and export processes take time.
	![204](images%20(readme)/Pasted%20image%2020260402103057.png)
	After loading your model, you can switch to material mode to see the texture on the tank. Hold down the Z key and select the option at the bottom.
	![564](images%20(readme)/Pasted%20image%2020260402103353.png)
	![Pasted image 20260402103505](images%20(readme)/Pasted%20image%2020260402103505.png)
2. **Manual import:**
	If you are importing a model from a folder instead of a tank directly from the game, simply click File > Import > BigWorld(.model) and select the .model or .visual_processed file. However, for model import, the .primitives_processed file and the .visual or .visual_processed file must be present. Don't worry if the model is at the Earth's origin when you perform a manual import, because whether you load the entire tank model or just a single model, the export code always considers the SenceRoot nodes on the models as the origin. In other words, all the tank's parts are actually located at the Earth's origin; the game combines these parts by moving them from their SenceRoot locations to the positions of nodes like V and Hp_gunJoint.
	![Pasted image 20260402104257](images%20(readme)/Pasted%20image%2020260402104257.png)
	If you want to quickly export models you've manually imported, like a tank, you need to create a root node named "tank" (the name in the package) and make it the parent of all turret, hull, and chassis root nodes. You can do this by selecting the other root nodes, then selecting the node you just created and pressing CTRL+P while your mouse is inside the scene. You need to add a Custom Property to the main parent node (Tank name) and create a configuration there with the Property name **bw_export_base_path** of **type String**. Inside this property, you need to write the file path to which the exported files will be sent (e.g., vehicles/russian/R45_IS-7/skins/NYst/normal/) *without creating the lod folder.* Finally, you need to add two settings named **bw_export_filename** and **wot_part** (**type String**) to the Custom properties section of the Senceroot file for the models you imported. In the wot_part section, specify the part **(Chassis, Hull, Turret, Gun)**, and in the bw_export_filename section, specify the export name. It is very important that the bw_export_filename name matches the original file name because this name is also written in the .model file, and the game understands the function of the models based on their file names.![Pasted image 20260402105732](images%20(readme)/Pasted%20image%2020260402105732.png)
	That's all for the model import process.
	/---------------------------------------------------------------------------------------
3. **Editing Textures:**
	After importing your model, while in object mode, select the part of the tank whose textures you want to edit, go to Texture Paint in the top menu, and paint directly from the UV map on the left or from the tank on the right. Currently, it supports editing AM, GMM, and ANM maps; this may be improved in the future. However, if you try to edit textures in the old format here, the exported textures may appear corrupted due to formatting errors.
	![Pasted image 20260402112108](images%20(readme)/Pasted%20image%2020260402112108.png)
	![Pasted image 20260402110710](images%20(readme)/Pasted%20image%2020260402110710.png)
	![Pasted image 20260402112330](images%20(readme)/Pasted%20image%2020260402112330.png)
	I'm also modifying the ANM map a bit (for the gun).
	![Pasted image 20260402112317](images%20(readme)/Pasted%20image%2020260402112317.png)
	On blender:
	![Pasted image 20260402112458](images%20(readme)/Pasted%20image%2020260402112458.png)
	On Game:
	![Pasted image 20260402114804](images%20(readme)/Pasted%20image%2020260402114804.png)
4. **Editing Bones:**
	First, we need to create an empty space to which the bone will be attached. We can animate the tank using scripts by moving or rotating these empty spaces.
	![Pasted image 20260403213239](images%20(readme)/Pasted%20image%2020260403213239.png)
	Next, give the node you created a **DIFFERENT NAME FROM OTHER NODES** ending in  BlendBone, and create a vertex group with the same name. Then, you can connect the vertices to this vertex group by coloring them (for 100% connected bones, you can assign them without coloring by using the assign button).
	![Pasted image 20260403215138](images%20(readme)/Pasted%20image%2020260403215138.png)
	Make sure the node you create is under the SenceRoot you're working on. Every node moves with its parent; if its parent moves to the right, that node will also move to the right as if its position hadn't changed relative to that parent.
	![Pasted image 20260403221740](images%20(readme)/Pasted%20image%2020260403221740.png)
	For models that flex in places like cables, you can paint bone weights like I did.
	![Pasted image 20260403223344](images%20(readme)/Pasted%20image%2020260403223344.png)
	You can also position the node axes in an angled manner. What I mean by nodes are emptys. The minigun points in the direction the camera is looking (you currently need to manually enter the script, but I plan to automate this in future additions).
	![Pasted image 20260403225832](images%20(readme)/Pasted%20image%2020260403225832.png)
5. **Full Tank Export**
	![Pasted image 20260403230119](images%20(readme)/Pasted%20image%2020260403230119.png)
	If you are going to export a full tank, you can do so from here, provided you follow the rules I explained earlier. The difference from quick export is that you can adjust the load (LOD) from here.
	![Pasted image 20260403230308](images%20(readme)/Pasted%20image%2020260403230308.png)
	Files and textures are automatically exported to the game's res_mods folder. The export path is set according to the location you entered in the bw_export_base_path section (e.g., vehicles/american/A179_Black_Rock/normal/), and the folders are created accordingly.
6. **Manuel Export**
	If you are working on models other than tanks (such as lights), you will need to use manual export. Although it is currently possible to export light packages including vertex colors, the .visual files need to be manually edited, so I don't highly recommend using it at the moment First, the model you want to export must be under a senceroot program. After selecting senceroot, you need to choose File -> Export -> BigWorld (.model).
	![Pasted image 20260403231039](images%20(readme)/Pasted%20image%2020260403231039.png)
	What I mean by "Vertex format" is that it modifies both the .visual file and the contents of the packaged file (primitives_processed). If your model has vertex color, the color data will be written to the .primitives file, even if it's in a standard tank or under simple lighting.
	![Pasted image 20260403231410](images%20(readme)/Pasted%20image%2020260403231410.png)
	If the location where you export the file is a tool location within Resmods, the texture and model files will be automatically located and their file paths will be written. However, if you export to a different folder, you will need to change the file path within the .model file, and the texture files will also be exported to the same folder as the model.
	**in-game:**
	![Pasted image 20260403233944](images%20(readme)/Pasted%20image%2020260403233944.png)
Please note that this addon is still under development and still contains bugs. If you report them, I will try to fix them, but most of the bugs stem from attempts to automatically configure .visual settings. If you have any questions, you can reach me on Discord for a faster response. (wot0139)
