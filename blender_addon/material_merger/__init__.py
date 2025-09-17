bl_info = {
    "name": "Material Merger",
    "author": "Your Name", # Replace with your name
    "version": (1, 0),
    "blender": (3, 6, 0), # Minimum Blender version
    "location": "Shader Editor > Sidebar > Material Merger",
    "description": "Merges two Asset Processor generated materials into a new material.",
    "warning": "",
    "doc_url": "", # Optional documentation URL
    "category": "Material",
}

import bpy

from . import operator
from . import panel

def register():
    operator.register()
    panel.register()
    print("Material Merger Addon Registered")

def unregister():
    panel.unregister()
    operator.unregister()
    print("Material Merger Addon Unregistered")

if __name__ == "__main__":
    register()