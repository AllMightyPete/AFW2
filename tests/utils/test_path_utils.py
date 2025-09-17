import pytest
from pathlib import Path
from utils.path_utils import sanitize_filename, generate_path_from_pattern

# Tests for sanitize_filename
def test_sanitize_filename_valid():
    assert sanitize_filename("valid_filename.txt") == "valid_filename.txt"

def test_sanitize_filename_with_spaces():
    assert sanitize_filename("file name with spaces.txt") == "file_name_with_spaces.txt"

def test_sanitize_filename_with_special_characters():
    assert sanitize_filename("file!@#$%^&*()[]{};:'\",.<>/?\\|.txt") == "file____________________.txt"

def test_sanitize_filename_with_leading_trailing_whitespace():
    assert sanitize_filename("  filename_with_spaces  .txt") == "filename_with_spaces.txt"

def test_sanitize_filename_empty_string():
    assert sanitize_filename("") == ""

def test_sanitize_filename_with_none():
    with pytest.raises(TypeError):
        sanitize_filename(None)

def test_sanitize_filename_mixed_case():
    assert sanitize_filename("MixedCaseFileName.PNG") == "MixedCaseFileName.PNG"

def test_sanitize_filename_long_filename():
    long_name = "a" * 255 + ".txt"
    # Assuming the function doesn't truncate, but sanitizes.
    # If it's meant to handle OS limits, this test might need adjustment
    # based on the function's specific behavior for long names.
    assert sanitize_filename(long_name) == long_name

def test_sanitize_filename_unicode_characters():
    assert sanitize_filename("文件名前缀_文件名_后缀.jpg") == "文件名前缀_文件名_后缀.jpg"

def test_sanitize_filename_multiple_extensions():
    assert sanitize_filename("archive.tar.gz") == "archive.tar.gz"

def test_sanitize_filename_no_extension():
    assert sanitize_filename("filename") == "filename"

def test_sanitize_filename_only_special_chars():
    assert sanitize_filename("!@#$%^") == "______"

def test_sanitize_filename_with_hyphens_and_underscores():
    assert sanitize_filename("file-name_with-hyphens_and_underscores.zip") == "file-name_with-hyphens_and_underscores.zip"

# Tests for generate_path_from_pattern
def test_generate_path_basic():
    result = generate_path_from_pattern(
        base_path="output",
        pattern="{asset_name}/{map_type}/{filename}",
        asset_name="MyAsset",
        map_type="Diffuse",
        filename="MyAsset_Diffuse.png",
        source_rule_name="TestRule",
        incrementing_value=None,
        sha5_value=None
    )
    expected = Path("output/MyAsset/Diffuse/MyAsset_Diffuse.png")
    assert Path(result) == expected

def test_generate_path_all_placeholders():
    result = generate_path_from_pattern(
        base_path="project_files",
        pattern="{source_rule_name}/{asset_name}/{map_type}_{incrementing_value}_{sha5_value}/{filename}",
        asset_name="AnotherAsset",
        map_type="Normal",
        filename="NormalMap.tif",
        source_rule_name="ComplexRule",
        incrementing_value="001",
        sha5_value="abcde"
    )
    expected = Path("project_files/ComplexRule/AnotherAsset/Normal_001_abcde/NormalMap.tif")
    assert Path(result) == expected

def test_generate_path_optional_placeholders_none():
    result = generate_path_from_pattern(
        base_path="data",
        pattern="{asset_name}/{filename}",
        asset_name="SimpleAsset",
        map_type="Albedo", # map_type is in pattern but not used if not in string
        filename="texture.jpg",
        source_rule_name="Basic",
        incrementing_value=None,
        sha5_value=None
    )
    expected = Path("data/SimpleAsset/texture.jpg")
    assert Path(result) == expected

def test_generate_path_optional_incrementing_value_present():
    result = generate_path_from_pattern(
        base_path="assets",
        pattern="{asset_name}/{map_type}/v{incrementing_value}/{filename}",
        asset_name="VersionedAsset",
        map_type="Specular",
        filename="spec.png",
        source_rule_name="VersioningRule",
        incrementing_value="3",
        sha5_value=None
    )
    expected = Path("assets/VersionedAsset/Specular/v3/spec.png")
    assert Path(result) == expected

def test_generate_path_optional_sha5_value_present():
    result = generate_path_from_pattern(
        base_path="cache",
        pattern="{asset_name}/{sha5_value}/{filename}",
        asset_name="HashedAsset",
        map_type="Roughness",
        filename="rough.exr",
        source_rule_name="HashingRule",
        incrementing_value=None,
        sha5_value="f1234"
    )
    expected = Path("cache/HashedAsset/f1234/rough.exr")
    assert Path(result) == expected

def test_generate_path_base_path_is_path_object():
    result = generate_path_from_pattern(
        base_path=Path("output_path"),
        pattern="{asset_name}/{filename}",
        asset_name="ObjectAsset",
        map_type="AO",
        filename="ao.png",
        source_rule_name="PathObjectRule",
        incrementing_value=None,
        sha5_value=None
    )
    expected = Path("output_path/ObjectAsset/ao.png")
    assert Path(result) == expected

def test_generate_path_empty_pattern():
    result = generate_path_from_pattern(
        base_path="output",
        pattern="", # Empty pattern should just use base_path and filename
        asset_name="MyAsset",
        map_type="Diffuse",
        filename="MyAsset_Diffuse.png",
        source_rule_name="TestRule",
        incrementing_value=None,
        sha5_value=None
    )
    expected = Path("output/MyAsset_Diffuse.png")
    assert Path(result) == expected

def test_generate_path_pattern_with_no_placeholders():
    result = generate_path_from_pattern(
        base_path="fixed_output",
        pattern="some/static/path", # Pattern has no placeholders
        asset_name="MyAsset",
        map_type="Diffuse",
        filename="MyAsset_Diffuse.png",
        source_rule_name="TestRule",
        incrementing_value=None,
        sha5_value=None
    )
    expected = Path("fixed_output/some/static/path/MyAsset_Diffuse.png")
    assert Path(result) == expected

def test_generate_path_filename_with_subdirs_in_pattern():
    result = generate_path_from_pattern(
        base_path="output",
        pattern="{asset_name}", # Filename itself will be appended
        asset_name="AssetWithSubdirFile",
        map_type="Color",
        filename="textures/variant1/color.png", # Filename contains subdirectories
        source_rule_name="SubdirRule",
        incrementing_value=None,
        sha5_value=None
    )
    # The function is expected to join pattern result with filename
    expected = Path("output/AssetWithSubdirFile/textures/variant1/color.png")
    assert Path(result) == expected

def test_generate_path_no_filename_provided():
    # This test assumes that if filename is None or empty, it might raise an error
    # or behave in a specific way, e.g. not append anything or use a default.
    # Adjust based on actual function behavior for missing filename.
    # For now, let's assume it might raise TypeError if filename is critical.
    with pytest.raises(TypeError): # Or ValueError, depending on implementation
        generate_path_from_pattern(
            base_path="output",
            pattern="{asset_name}/{map_type}",
            asset_name="MyAsset",
            map_type="Diffuse",
            filename=None, # No filename
            source_rule_name="TestRule",
            incrementing_value=None,
            sha5_value=None
        )

def test_generate_path_all_values_are_empty_strings_or_none_where_applicable():
    result = generate_path_from_pattern(
        base_path="", # Empty base_path
        pattern="{asset_name}/{map_type}/{incrementing_value}/{sha5_value}",
        asset_name="", # Empty asset_name
        map_type="",   # Empty map_type
        filename="empty_test.file",
        source_rule_name="", # Empty source_rule_name
        incrementing_value="", # Empty incrementing_value
        sha5_value=""          # Empty sha5_value
    )
    # Behavior with empty strings might vary. Assuming they are treated as literal empty segments.
    # Path("///empty_test.file") might resolve to "/empty_test.file" on POSIX
    # or just "empty_test.file" if base_path is current dir.
    # Let's assume Path() handles normalization.
    # If base_path is "", it means current directory.
    # So, "//empty_test.file" relative to current dir.
    # Path objects normalize this. e.g. Path('//a') -> Path('/a') on POSIX
    # Path('a//b') -> Path('a/b')
    # Path('/a//b') -> Path('/a/b')
    # Path('//a//b') -> Path('/a/b')
    # If base_path is empty, it's like Path('.////empty_test.file')
    expected = Path("empty_test.file") # Simplified, actual result might be OS dependent or Path lib norm.
    # More robust check:
    # result_path = Path(result)
    # expected_path = Path.cwd() / "" / "" / "" / "" / "empty_test.file" # This is not quite right
    # Let's assume the function joins them: "" + "/" + "" + "/" + "" + "/" + "" + "/" + "empty_test.file"
    # which becomes "////empty_test.file"
    # Path("////empty_test.file") on Windows becomes "\\empty_test.file" (network path attempt)
    # Path("////empty_test.file") on Linux becomes "/empty_test.file"
    # Given the function likely uses os.path.join or Path.joinpath,
    # and base_path="", asset_name="", map_type="", inc_val="", sha5_val=""
    # pattern = "{asset_name}/{map_type}/{incrementing_value}/{sha5_value}" -> "///"
    # result = base_path / pattern_result / filename
    # result = "" / "///" / "empty_test.file"
    # Path("") / "///" / "empty_test.file" -> Path("///empty_test.file")
    # This is tricky. Let's assume the function is robust.
    # If all path segments are empty, it should ideally resolve to just the filename relative to base_path.
    # If base_path is also empty, then filename relative to CWD.
    # Let's test the expected output based on typical os.path.join behavior:
    # os.path.join("", "", "", "", "", "empty_test.file") -> "empty_test.file" on Windows
    # os.path.join("", "", "", "", "", "empty_test.file") -> "empty_test.file" on Linux
    assert Path(result) == Path("empty_test.file")


def test_generate_path_with_dots_in_placeholders():
    result = generate_path_from_pattern(
        base_path="output",
        pattern="{asset_name}/{map_type}",
        asset_name="My.Asset.V1",
        map_type="Diffuse.Main",
        filename="texture.png",
        source_rule_name="DotsRule",
        incrementing_value=None,
        sha5_value=None
    )
    expected = Path("output/My.Asset.V1/Diffuse.Main/texture.png")
    assert Path(result) == expected