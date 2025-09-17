#project/assetorganiser 

## Input Zip Example:
```json
{
  "BarkBrown013.zip": [
    "BarkBrown013_AO_3K.jpg",
    "BarkBrown013_COL_3K.jpg",
    "BarkBrown013_Cube.jpg",
    "BarkBrown013_DISP_3K.jpg",
    "BarkBrown013_DISP16_3K.tif",
    "BarkBrown013_Flat.jpg",
    "BarkBrown013_GLOSS_3K.jpg",
    "BarkBrown013_NRM_3K.jpg",
    "BarkBrown013_REFL_3K.jpg",
    "BarkBrown013_Sphere.jpg"
  ]
}
```

## Internal Structure Example:
```json
{
  "Source01.zip": {
    "metadata": {
      "normal_format": "OpenGL",
      "supplier": "AssetSupplier01"
    },
    "contents": {
      "01": {
        "filename": "File01.jpg",
        "filetype": "MAP_COL"
      },
      "02": {
        "filename": "File02.jpg",
        "filetype": "MAP_NRM"
      },
      "03": {
        "filename": "File03.txt",
        "filetype": "IGNORE"
      },
      "04": {
        "filename": "File04.fbx",
        "filetype": "FILE_MODEL"
      },
      "05": {
        "filename": "File05.jpg",
        "filetype": "UNIDENTIFIED"
      }
    },
    "assets": {
      "asset_name_01": {
        "asset_type": "Model",
        "asset_tags": [
          "Tag01",
          "Tag02"
        ],
        "asset_contents": [
          "01",
          "02",
          "04",
          "05"
        ]
      }
    }
  }
}
```
