import bpy
from bpy.types import Operator
from bpy.props import StringProperty
from pathlib import Path

# Assuming the utility nodegroups file is located relative to the addon
# This path might need adjustment depending on final addon distribution
UTILITY_NODEGROUPS_FILE = Path(__file__).parent / "blender_files" / "utility_nodegroups.blend"
MATERIAL_MERGE_NODEGROUP_NAME = "MaterialMerge"
HANDLER_NODEGROUP_NAME = "PBR_Handler" # Assumption from plan
BSDF_NODEGROUP_NAME = "PBR_BSDF" # Assumption from plan

def copy_material_nodes(source_mat, target_tree, location_offset=(0, 0)):
    """
    Copies nodes from source_mat's node tree to target_tree, applying an offset.
    Identifies and returns the copied nodes corresponding to the final BSDF and Displacement outputs.

    Returns:
        tuple: (copied_node_map, copied_final_bsdf_node, copied_final_disp_node)
               Returns (None, None, None) on failure.
    """
    if not source_mat or not source_mat.node_tree:
        print(f"Error: Source material '{source_mat.name if source_mat else 'None'}' has no node tree.")
        return None, None, None

    source_tree = source_mat.node_tree
    copied_node_map = {}
    copied_final_bsdf_node = None
    copied_final_disp_node = None

    # --- Identify Final Output Nodes in Source Tree ---
    # This logic needs to handle both base materials and already-merged materials
    source_final_bsdf_node = None
    source_final_disp_node = None

    # Try finding a top-level MaterialMerge node first (for recursive merging)
    top_merge_node = None
    for node in source_tree.nodes:
        if node.type == 'GROUP' and node.node_tree and node.node_tree.name == MATERIAL_MERGE_NODEGROUP_NAME:
            # Check if it's connected to the Material Output (likely the top one)
            for link in source_tree.links:
                if link.from_node == node and link.to_node.type == 'OUTPUT_MATERIAL':
                    top_merge_node = node
                    break
            if top_merge_node:
                break

    if top_merge_node:
        print(f"  Identified top-level '{MATERIAL_MERGE_NODEGROUP_NAME}' in '{source_mat.name}'. Using its outputs.")
        source_final_bsdf_node = top_merge_node
        source_final_disp_node = top_merge_node # Both outputs come from the merge node
        if 'BSDF' not in source_final_bsdf_node.outputs or 'Displacement' not in source_final_disp_node.outputs:
             print(f"  Error: Identified merge node in '{source_mat.name}' lacks required BSDF/Displacement outputs.")
             return None, None, None
    else:
        # If no top-level merge node, assume it's a base material
        print(f"  No top-level merge node found in '{source_mat.name}'. Assuming base material structure.")
        source_final_bsdf_node = source_tree.nodes.get(BSDF_NODEGROUP_NAME)
        source_final_disp_node = source_tree.nodes.get(HANDLER_NODEGROUP_NAME) # Displacement from Handler
        if not source_final_bsdf_node:
            print(f"  Error: Could not find base BSDF node '{BSDF_NODEGROUP_NAME}' in '{source_mat.name}'.")
            return None, None, None
        if not source_final_disp_node:
            print(f"  Error: Could not find base Handler node '{HANDLER_NODEGROUP_NAME}' in '{source_mat.name}'.")
            return None, None, None
        if 'BSDF' not in source_final_bsdf_node.outputs:
             print(f"  Error: Identified BSDF node '{BSDF_NODEGROUP_NAME}' lacks BSDF output.")
             return None, None, None
        if 'Displacement' not in source_final_disp_node.outputs:
             print(f"  Error: Identified Handler node '{HANDLER_NODEGROUP_NAME}' lacks Displacement output.")
             return None, None, None


    # --- Copy Nodes ---
    print(f"  Copying nodes from '{source_mat.name}'...")
    for original_node in source_tree.nodes:
        if original_node.type == 'OUTPUT_MATERIAL':
            continue # Skip the material output node

        new_node = target_tree.nodes.new(type=original_node.bl_idname)
        # Copy properties (basic example, might need more specific handling)
        for prop in original_node.bl_rna.properties:
            if not prop.is_readonly and prop.identifier != "rna_type":
                try:
                    setattr(new_node, prop.identifier, getattr(original_node, prop.identifier))
                except AttributeError:
                    pass # Some properties might not be directly settable

        # Copy specific node group if it's a group node
        if original_node.type == 'GROUP' and original_node.node_tree:
            new_node.node_tree = original_node.node_tree # Link the same node group

        new_node.location = (original_node.location.x + location_offset[0],
                             original_node.location.y + location_offset[1])
        new_node.width = original_node.width
        new_node.label = original_node.label
        new_node.name = original_node.name # Keep original name if possible (Blender might rename on conflict)

        copied_node_map[original_node] = new_node

        # Store the *copied* versions of the identified final output nodes
        if original_node == source_final_bsdf_node:
            copied_final_bsdf_node = new_node
        if original_node == source_final_disp_node:
             # If source was merge node, both point to the same copied node
             # If source was base material, this points to the copied handler
            copied_final_disp_node = new_node

    # --- Copy Links ---
    print(f"  Copying links for '{source_mat.name}'...")
    for original_link in source_tree.links:
        original_from_node = original_link.from_node
        original_to_node = original_link.to_node

        # Check if both ends of the link were copied (i.e., not connected to Material Output)
        if original_from_node in copied_node_map and original_to_node in copied_node_map:
            new_from_node = copied_node_map[original_from_node]
            new_to_node = copied_node_map[original_to_node]

            # Find matching sockets by name (more robust than index)
            try:
                from_socket_name = original_link.from_socket.name
                to_socket_name = original_link.to_socket.name
                new_from_socket = new_from_node.outputs.get(from_socket_name)
                new_to_socket = new_to_node.inputs.get(to_socket_name)

                if new_from_socket and new_to_socket:
                    target_tree.links.new(new_from_socket, new_to_socket)
                else:
                     print(f"    Warning: Could not find matching sockets for link between '{original_from_node.name}' and '{original_to_node.name}' (Sockets: '{from_socket_name}', '{to_socket_name}')")
            except Exception as e:
                 print(f"    Error creating link between copied nodes '{new_from_node.name}' and '{new_to_node.name}': {e}")


    if not copied_final_bsdf_node:
         print(f"  Error: Failed to find the copied version of the final BSDF node for '{source_mat.name}'.")
         return None, None, None
    if not copied_final_disp_node:
         print(f"  Error: Failed to find the copied version of the final Displacement node for '{source_mat.name}'.")
         return None, None, None

    print(f"  Finished copying '{source_mat.name}'.")
    return copied_node_map, copied_final_bsdf_node, copied_final_disp_node


class MATERIAL_OT_merge_materials(Operator):
    """Merge two selected Asset Processor materials"""
    bl_idname = "material.merge_materials"
    bl_label = "Merge Selected Materials"
    bl_options = {'REGISTER', 'UNDO'}

    # These will be set by the UI panel
    material_a_name: StringProperty(
        name="Material A",
        description="First material to merge"
    )
    material_b_name: StringProperty(
        name="Material B",
        description="Second material to merge"
    )

    def execute(self, context):
        mat_a = bpy.data.materials.get(self.material_a_name)
        mat_b = bpy.data.materials.get(self.material_b_name)

        if not mat_a or not mat_b:
            self.report({'ERROR'}, "Please select two valid materials to merge.")
            return {'CANCELLED'}

        if mat_a == mat_b:
             self.report({'ERROR'}, "Cannot merge a material with itself.")
             return {'CANCELLED'}

        # --- Core Merging Logic (Based on Plan) ---

        # 1. Create new material
        new_mat_name = f"MAT_Merged_{mat_a.name}_{mat_b.name}"
        if new_mat_name in bpy.data.materials:
             # Handle potential naming conflicts, maybe append a number
             new_mat_name = f"{new_mat_name}.001" # Simple increment for now
             # A more robust approach would check for existing names and find the next available number
             # For prototype, this simple approach is acceptable.

        new_mat = bpy.data.materials.new(name=new_mat_name)
        new_mat.use_nodes = True
        new_node_tree = new_mat.node_tree

        # Clear default nodes (Principled BSDF and Material Output)
        for node in new_node_tree.nodes:
            new_node_tree.nodes.remove(node)

        # Add Material Output node
        output_node = new_node_tree.nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (400, 0)

        # 2. Copy nodes from source materials
        print("Copying nodes for Material A...")
        copied_map_a, copied_bsdf_a, copied_disp_a = copy_material_nodes(mat_a, new_node_tree, location_offset=(0, 0))
        if not copied_bsdf_a or not copied_disp_a:
            self.report({'ERROR'}, f"Failed to copy nodes or identify outputs for material '{mat_a.name}'. Check console for details.")
            bpy.data.materials.remove(new_mat)
            return {'CANCELLED'}

        print("Copying nodes for Material B...")
        # Calculate offset for Material B based on Material A's nodes (simple approach)
        offset_x = 0
        if copied_map_a:
             max_x = max((n.location.x + n.width for n in copied_map_a.values()), default=0)
             min_x = min((n.location.x for n in copied_map_a.values()), default=0)
             offset_x = max_x - min_x + 100 # Add some spacing

        copied_map_b, copied_bsdf_b, copied_disp_b = copy_material_nodes(mat_b, new_node_tree, location_offset=(offset_x, 0))
        if not copied_bsdf_b or not copied_disp_b:
            self.report({'ERROR'}, f"Failed to copy nodes or identify outputs for material '{mat_b.name}'. Check console for details.")
            bpy.data.materials.remove(new_mat)
            return {'CANCELLED'}


        # 3. Link/Append MaterialMerge node group
        merge_node = None
        if not UTILITY_NODEGROUPS_FILE.is_file():
             self.report({'ERROR'}, f"Utility nodegroups file not found: {UTILITY_NODEGROUPS_FILE}")
             # TODO: Clean up newly created material if there's an error
             return {'CANCELLED'}

        # Check if the group is already in the current file
        merge_group = bpy.data.node_groups.get(MATERIAL_MERGE_NODEGROUP_NAME)

        if not merge_group:
            # Attempt to link the node group
            try:
                with bpy.data.libraries.load(str(UTILITY_NODEGROUPS_FILE), link=True) as (data_from, data_to):
                    if MATERIAL_MERGE_NODEGROUP_NAME in data_from.node_groups:
                        data_to.node_groups = [MATERIAL_MERGE_NODEGROUP_NAME]
                    else:
                        self.report({'ERROR'}, f"Node group '{MATERIAL_MERGE_NODEGROUP_NAME}' not found in '{UTILITY_NODEGROUPS_FILE.name}'.")
                        # TODO: Clean up newly created material if there's an error
                        return {'CANCELLED'}

                merge_group = bpy.data.node_groups.get(MATERIAL_MERGE_NODEGROUP_NAME)
                if not merge_group:
                     self.report({'ERROR'}, f"Failed to link node group '{MATERIAL_MERGE_NODEGROUP_NAME}'.")
                     # TODO: Clean up newly created material if there's an error
                     return {'CANCELLED'}

            except Exception as e:
                self.report({'ERROR'}, f"Error linking '{MATERIAL_MERGE_NODEGROUP_NAME}' from '{UTILITY_NODEGROUPS_FILE.name}': {e}")
                # TODO: Clean up newly created material if there's an error
                return {'CANCELLED'}

        # Add the linked/appended group to the new material's node tree
        merge_node = new_node_tree.nodes.new(type='ShaderNodeGroup')
        merge_node.node_tree = merge_group
        merge_node.label = MATERIAL_MERGE_NODEGROUP_NAME
        merge_node.location = (200, 0)


        # 4. Make Connections
        links = new_node_tree.links

        # Connect BSDFs to Merge node
        bsdf_output_socket_a = copied_bsdf_a.outputs.get('BSDF')
        shader_input_socket_a = merge_node.inputs.get('Shader A')
        bsdf_output_socket_b = copied_bsdf_b.outputs.get('BSDF')
        shader_input_socket_b = merge_node.inputs.get('Shader B')

        if not all([bsdf_output_socket_a, shader_input_socket_a, bsdf_output_socket_b, shader_input_socket_b]):
             self.report({'ERROR'}, "Could not find required BSDF/Shader sockets for linking.")
             bpy.data.materials.remove(new_mat)
             return {'CANCELLED'}

        link_bsdf_a = links.new(bsdf_output_socket_a, shader_input_socket_a)
        link_bsdf_b = links.new(bsdf_output_socket_b, shader_input_socket_b)

        # Connect Displacements to Merge node
        disp_output_socket_a = copied_disp_a.outputs.get('Displacement')
        disp_input_socket_a = merge_node.inputs.get('Displacement A')
        disp_output_socket_b = copied_disp_b.outputs.get('Displacement')
        disp_input_socket_b = merge_node.inputs.get('Displacement B')

        if not all([disp_output_socket_a, disp_input_socket_a, disp_output_socket_b, disp_input_socket_b]):
             self.report({'ERROR'}, "Could not find required Displacement sockets for linking.")
             bpy.data.materials.remove(new_mat)
             return {'CANCELLED'}

        link_disp_a = links.new(disp_output_socket_a, disp_input_socket_a)
        link_disp_b = links.new(disp_output_socket_b, disp_input_socket_b)

        # Connect Merge node outputs to Material Output
        merge_bsdf_output = merge_node.outputs.get('BSDF')
        output_surface_input = output_node.inputs.get('Surface')
        merge_disp_output = merge_node.outputs.get('Displacement')
        output_disp_input = output_node.inputs.get('Displacement')

        if not all([merge_bsdf_output, output_surface_input, merge_disp_output, output_disp_input]):
             self.report({'ERROR'}, "Could not find required Merge/Output sockets for linking.")
             bpy.data.materials.remove(new_mat)
             return {'CANCELLED'}

        link_merge_bsdf = links.new(merge_bsdf_output, output_surface_input)
        link_merge_disp = links.new(merge_disp_output, output_disp_input)


        # 5. Layout (Optional)
        # TODO: Implement better node layout

        new_node_tree.nodes.update()

        self.report({'INFO'}, f"Successfully merged '{mat_a.name}' and '{mat_b.name}' into '{new_mat.name}'")

        return {'FINISHED'}

    # Optional: Add invoke method if needed for more complex setup before execute
    # Commented-out code moved to Deprecated/Old-Code/blender_addon_material_merger_operator_py_invoke_method_line_326.py

def register():
    bpy.utils.register_class(MATERIAL_OT_merge_materials)
    print("MATERIAL_OT_merge_materials registered")

def unregister():
    bpy.utils.unregister_class(MATERIAL_OT_merge_materials)
    print("MATERIAL_OT_merge_materials unregistered")

if __name__ == "__main__":
    # This block is for running the script directly in Blender's text editor
    # It's useful for testing the operator logic without installing the addon
    register()

    # Example usage (replace with actual material names in your file)
    # bpy.ops.material.merge_materials(material_a_name="MAT_Wood01", material_b_name="MAT_SandBeach01")