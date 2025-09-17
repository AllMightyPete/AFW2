import bpy
from bpy.types import Panel
from .operator import MATERIAL_OT_merge_materials

class MATERIAL_PT_material_merger_panel(Panel):
    """Creates a Panel in the Shader Editor sidebar"""
    bl_label = "Material Merger"
    bl_idname = "MATERIAL_PT_material_merger_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tool' # Or 'Material' or a custom category

    def draw(self, context):
        layout = self.layout


        row = layout.row()
        row.label(text="Select Materials to Merge:")

        # Use properties from the operator to store selected material names
        # The operator will read these when executed.
        # We'll use StringProperty for simplicity in the UI for now.
        # A more advanced UI might use PointerProperty to bpy.data.materials

        row = layout.row()
        row.prop(context.scene, "material_merger_mat_a", text="Material A")

        row = layout.row()
        row.prop(context.scene, "material_merger_mat_b", text="Material B")


        row = layout.row()
        row.operator(MATERIAL_OT_merge_materials.bl_idname, text=MATERIAL_OT_merge_materials.bl_label).material_a_name = context.scene.material_merger_mat_a
        row.operator(MATERIAL_OT_merge_materials.bl_idname, text=MATERIAL_OT_merge_materials.bl_label).material_b_name = context.scene.material_merger_mat_b


# To store the selected material names, we need scene properties
# These will be registered and unregistered with the addon
def register_properties():
    bpy.types.Scene.material_merger_mat_a = StringProperty(
        name="Material A Name",
        description="Name of the first material to merge",
        default=""
    )
    bpy.types.Scene.material_merger_mat_b = StringProperty(
        name="Material B Name",
        description="Name of the second material to merge",
        default=""
    )

def unregister_properties():
    del bpy.types.Scene.material_merger_mat_a
    del bpy.types.Scene.material_merger_mat_b


def register():
    register_properties()
    bpy.utils.register_class(MATERIAL_PT_material_merger_panel)
    print("MATERIAL_PT_material_merger_panel registered")

def unregister():
    bpy.utils.unregister_class(MATERIAL_PT_material_merger_panel)
    unregister_properties()
    print("MATERIAL_PT_material_merger_panel unregistered")

if __name__ == "__main__":
    # This block is for running the script directly in Blender's text editor
    # It's useful for testing the panel layout without installing the addon
    register()