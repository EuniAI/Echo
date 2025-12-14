import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

"""
Tools for loading patch from the given path.
"""


@dataclass
class ToolSpec:
    description: str
    input_schema: type


class LoadPatchInput(BaseModel):
    instance_id: str = Field(description="The instance id of the patch to load")
    patch_path: str = Field(description="The path of the patch JSON file to load from")


def load_patch(instance_id: str, patch_path: str) -> str:
    """
    Load the patch from the given patches.json file using the instance_id.
    
    Args:
        instance_id: The instance id of the patch to load (e.g., "astropy__astropy-14365")
        patch_path: The path to the patches.json file
        
    Returns:
        The patch content (model_patch) as a string, or an error message if not found
    """
    # Convert to Path object
    patch_file = Path(patch_path)
    
    # Check if file exists
    if not patch_file.exists():
        return f"Error: The patch file {patch_path} does not exist."
    
    # Check if it's a JSON file
    if not patch_file.suffix.lower() == '.json':
        return f"Error: The file {patch_path} is not a JSON file."
    
    try:
        # Read and parse JSON file
        with patch_file.open('r', encoding='utf-8') as f:
            patches_data = json.load(f)
        
        # Check if instance_id exists in the patches data
        if instance_id not in patches_data:
            available_ids = list(patches_data.keys())[:10]  # Show first 10 as examples
            return f"Error: Instance ID '{instance_id}' not found in patches.json. Available IDs (showing first 10): {available_ids}"
        
        # Get the patch data
        patch_info = patches_data[instance_id]
        
        # Extract the model_patch field
        if 'model_patch' not in patch_info:
            return f"Error: The patch for instance '{instance_id}' does not contain 'model_patch' field."
        
        model_patch = patch_info['model_patch']
        
        return model_patch
        
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse JSON file {patch_path}: {str(e)}"
    except Exception as e:
        return f"Error: Failed to load patch: {str(e)}"