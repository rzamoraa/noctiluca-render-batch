bl_info = {
    "name": "Noctiluca Render Manager",
    "author": "Noctiluca",
    "version": (1, 2, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Render",
    "description": "Send current .blend to Noctiluca Render Manager",
    "category": "Render",
}

import bpy
import urllib.request
import json

class NoctilucaPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    
    manager_host: bpy.props.StringProperty(
        name="Manager Host",
        default="localhost"
    )
    
    manager_port: bpy.props.IntProperty(
        name="Manager Port",
        default=8000,
        min=1,
        max=65535
    )
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Render Manager Connection")
        layout.prop(self, "manager_host")
        layout.prop(self, "manager_port")

class NOCTILUCA_OT_send_to_manager(bpy.types.Operator):
    bl_idname = "noctiluca.send_to_manager"
    bl_label = "Send to Render Manager"
    
    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        manager_url = f"http://{prefs.manager_host}:{prefs.manager_port}"
        
        blend_file = bpy.data.filepath
        if not blend_file:
            self.report({'ERROR'}, "El archivo debe estar guardado")
            return {'CANCELLED'}
        
        scene = context.scene
        data = {
            "blend_file": blend_file,
            "total_frames": scene.frame_end - scene.frame_start + 1,
            "frame_range": {
                "start": scene.frame_start,
                "end": scene.frame_end
            },
            "resolution": {
                "x": scene.render.resolution_x,
                "y": scene.render.resolution_y
            },
            "render_engine": scene.render.engine,
            "output_path": scene.render.filepath
        }
        
        try:
            req = urllib.request.Request(
                manager_url + "/set_job",
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode())
                job_id = result.get('job_id', 'N/A')
                self.report({'INFO'}, f"Job enviado (ID: {job_id})")
        except Exception as e:
            self.report({'ERROR'}, f"Error: {e}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

class NOCTILUCA_PT_panel(bpy.types.Panel):
    bl_label = "Noctiluca Render Farm"
    bl_idname = "NOCTILUCA_PT_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.label(text="Job Info:", icon='INFO')
        col = box.column(align=True)
        total = scene.frame_end - scene.frame_start + 1
        col.label(text=f"Frames: {scene.frame_start} - {scene.frame_end} ({total})")
        col.label(text=f"Resolution: {scene.render.resolution_x}x{scene.render.resolution_y}")
        col.label(text=f"Engine: {scene.render.engine}")
        col.label(text=f"Output: {scene.render.filepath}", icon='FILE_FOLDER')
        
        layout.operator("noctiluca.send_to_manager", icon='RENDER_STILL')

def register():
    bpy.utils.register_class(NoctilucaPreferences)
    bpy.utils.register_class(NOCTILUCA_OT_send_to_manager)
    bpy.utils.register_class(NOCTILUCA_PT_panel)

def unregister():
    bpy.utils.unregister_class(NOCTILUCA_PT_panel)
    bpy.utils.unregister_class(NOCTILUCA_OT_send_to_manager)
    bpy.utils.unregister_class(NoctilucaPreferences)

if __name__ == "__main__":
    register()
