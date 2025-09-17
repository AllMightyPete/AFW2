import pytest
from unittest import mock
import numpy as np
from pathlib import Path
import sys

# Attempt to import the module under test
# This assumes that the 'tests' directory is at the same level as the 'processing' directory,
# and pytest handles the PYTHONPATH correctly.
try:
    from processing.utils import image_processing_utils as ipu
    import cv2 # Import cv2 here if it's used for constants like cv2.COLOR_BGR2RGB
except ImportError:
    # Fallback for environments where PYTHONPATH might not be set up as expected by pytest initially
    # This adds the project root to sys.path to find the 'processing' module
    # Adjust the number of Path.parent calls if your test structure is deeper or shallower
    project_root = Path(__file__).parent.parent.parent.parent 
    sys.path.insert(0, str(project_root))
    from processing.utils import image_processing_utils as ipu
    import cv2 # Import cv2 here as well

# If cv2 is imported directly in image_processing_utils, you might need to mock it globally for some tests
# For example, at the top of the test file:
# sys.modules['cv2'] = mock.MagicMock() # Basic global mock if needed
# We will use more targeted mocks with @mock.patch where cv2 is used.

# --- Tests for Mathematical Helpers ---

def test_is_power_of_two():
    assert ipu.is_power_of_two(1) is True
    assert ipu.is_power_of_two(2) is True
    assert ipu.is_power_of_two(4) is True
    assert ipu.is_power_of_two(16) is True
    assert ipu.is_power_of_two(1024) is True
    assert ipu.is_power_of_two(0) is False
    assert ipu.is_power_of_two(-2) is False
    assert ipu.is_power_of_two(3) is False
    assert ipu.is_power_of_two(100) is False

def test_get_nearest_pot():
    assert ipu.get_nearest_pot(1) == 1
    assert ipu.get_nearest_pot(2) == 2
    # Based on current implementation:
    # For 3: lower=2, upper=4. (3-2)=1, (4-3)=1. Else branch returns upper_pot. So 4.
    assert ipu.get_nearest_pot(3) == 4
    assert ipu.get_nearest_pot(50) == 64 # (50-32)=18, (64-50)=14 -> upper
    assert ipu.get_nearest_pot(100) == 128 # (100-64)=36, (128-100)=28 -> upper
    assert ipu.get_nearest_pot(256) == 256
    assert ipu.get_nearest_pot(0) == 1
    assert ipu.get_nearest_pot(-10) == 1
    # For 700: value.bit_length() = 10. lower_pot = 1<<(10-1) = 512. upper_pot = 1<<10 = 1024.
    # (700-512) = 188. (1024-700) = 324. (188 < 324) is True. Returns lower_pot. So 512.
    assert ipu.get_nearest_pot(700) == 512
    assert ipu.get_nearest_pot(6) == 8 # (6-4)=2, (8-6)=2. Returns upper.
    assert ipu.get_nearest_pot(5) == 4 # (5-4)=1, (8-5)=3. Returns lower.


@pytest.mark.parametrize(
    "orig_w, orig_h, target_w, target_h, resize_mode, ensure_pot, allow_upscale, target_max_dim, expected_w, expected_h",
    [
        # FIT mode
        (1000, 800, 500, None, "fit", False, False, None, 500, 400), # Fit width
        (1000, 800, None, 400, "fit", False, False, None, 500, 400), # Fit height
        (1000, 800, 500, 500, "fit", False, False, None, 500, 400), # Fit to box (width constrained)
        (800, 1000, 500, 500, "fit", False, False, None, 400, 500), # Fit to box (height constrained)
        (100, 80, 200, None, "fit", False, False, None, 100, 80),   # Fit width, no upscale
        (100, 80, 200, None, "fit", False, True, None, 200, 160),   # Fit width, allow upscale
        (100, 80, 128, None, "fit", True, False, None, 128, 64), # Re-evaluated
        (100, 80, 128, None, "fit", True, True, None, 128, 128), # Fit width, ensure_pot, allow upscale (128, 102 -> pot 128, 128)

        # STRETCH mode
        (1000, 800, 500, 400, "stretch", False, False, None, 500, 400),
        (100, 80, 200, 160, "stretch", False, True, None, 200, 160), # Stretch, allow upscale
        (100, 80, 200, 160, "stretch", False, False, None, 100, 80), # Stretch, no upscale
        (100, 80, 128, 128, "stretch", True, True, None, 128, 128), # Stretch, ensure_pot, allow upscale
        (100, 80, 70, 70, "stretch", True, False, None, 64, 64), # Stretch, ensure_pot, no upscale (70,70 -> pot 64,64)

        # MAX_DIM_POT mode
        (1000, 800, None, None, "max_dim_pot", True, False, 512, 512, 512),
        (800, 1000, None, None, "max_dim_pot", True, False, 512, 512, 512),
        (1920, 1080, None, None, "max_dim_pot", True, False, 1024, 1024, 512),
        (100, 100, None, None, "max_dim_pot", True, False, 60, 64, 64),
        # Edge cases for calculate_target_dimensions
        (0, 0, 512, 512, "fit", False, False, None, 512, 512), 
        (10, 10, 512, 512, "fit", True, False, None, 8, 8),
        (100, 100, 150, 150, "fit", True, False, None, 128, 128),
    ]
)
def test_calculate_target_dimensions(orig_w, orig_h, target_w, target_h, resize_mode, ensure_pot, allow_upscale, target_max_dim, expected_w, expected_h):
    if resize_mode == "max_dim_pot" and target_max_dim is None:
        with pytest.raises(ValueError, match="target_max_dim_for_pot_mode must be provided"):
            ipu.calculate_target_dimensions(orig_w, orig_h, target_width=target_w, target_height=target_h, 
                                            resize_mode=resize_mode, ensure_pot=ensure_pot, allow_upscale=allow_upscale,
                                            target_max_dim_for_pot_mode=target_max_dim)
    elif (resize_mode == "fit" and target_w is None and target_h is None) or \
         (resize_mode == "stretch" and (target_w is None or target_h is None)):
        with pytest.raises(ValueError):
             ipu.calculate_target_dimensions(orig_w, orig_h, target_width=target_w, target_height=target_h, 
                                            resize_mode=resize_mode, ensure_pot=ensure_pot, allow_upscale=allow_upscale,
                                            target_max_dim_for_pot_mode=target_max_dim)
    else:
        actual_w, actual_h = ipu.calculate_target_dimensions(
            orig_w, orig_h, target_width=target_w, target_height=target_h, 
            resize_mode=resize_mode, ensure_pot=ensure_pot, allow_upscale=allow_upscale,
            target_max_dim_for_pot_mode=target_max_dim
        )
        assert (actual_w, actual_h) == (expected_w, expected_h), \
            f"Input: ({orig_w},{orig_h}), T=({target_w},{target_h}), M={resize_mode}, POT={ensure_pot}, UPSC={allow_upscale}, TMAX={target_max_dim}"


def test_calculate_target_dimensions_invalid_mode():
    with pytest.raises(ValueError, match="Unsupported resize_mode"):
        ipu.calculate_target_dimensions(100, 100, 50, 50, resize_mode="invalid_mode")

@pytest.mark.parametrize(
    "ow, oh, rw, rh, expected_str",
    [
        (100, 100, 100, 100, "EVEN"),
        (100, 100, 200, 200, "EVEN"),
        (200, 200, 100, 100, "EVEN"),
        (100, 100, 150, 100, "X15Y1"),
        (100, 100, 50, 100, "X05Y1"),
        (100, 100, 100, 150, "X1Y15"),
        (100, 100, 100, 50, "X1Y05"),
        (100, 50, 150, 75, "EVEN"),
        (100, 50, 150, 50, "X15Y1"),
        (100, 50, 100, 75, "X1Y15"),
        (100, 50, 120, 60, "EVEN"),
        (100, 50, 133, 66, "EVEN"),
        (100, 100, 133, 100, "X133Y1"),
        (100, 100, 100, 133, "X1Y133"),
        (100, 100, 133, 133, "EVEN"),
        (100, 100, 67, 100, "X067Y1"),
        (100, 100, 100, 67, "X1Y067"),
        (100, 100, 67, 67, "EVEN"),
        (1920, 1080, 1024, 576, "EVEN"), 
        (1920, 1080, 1024, 512, "X112Y1"),
        (0, 100, 50, 50, "InvalidInput"),
        (100, 0, 50, 50, "InvalidInput"),
        (100, 100, 0, 50, "InvalidResize"),
        (100, 100, 50, 0, "InvalidResize"),
    ]
)
def test_normalize_aspect_ratio_change(ow, oh, rw, rh, expected_str):
    assert ipu.normalize_aspect_ratio_change(ow, oh, rw, rh) == expected_str

# --- Tests for Image Manipulation ---

@mock.patch('cv2.imread')
def test_load_image_success_str_path(mock_cv2_imread):
    mock_img_data = np.array([[[1, 2, 3]]], dtype=np.uint8)
    mock_cv2_imread.return_value = mock_img_data
    
    result = ipu.load_image("dummy/path.png")
    
    mock_cv2_imread.assert_called_once_with("dummy/path.png", cv2.IMREAD_UNCHANGED)
    assert np.array_equal(result, mock_img_data)

@mock.patch('cv2.imread')
def test_load_image_success_path_obj(mock_cv2_imread):
    mock_img_data = np.array([[[1, 2, 3]]], dtype=np.uint8)
    mock_cv2_imread.return_value = mock_img_data
    dummy_path = Path("dummy/path.png")
    
    result = ipu.load_image(dummy_path)
    
    mock_cv2_imread.assert_called_once_with(str(dummy_path), cv2.IMREAD_UNCHANGED)
    assert np.array_equal(result, mock_img_data)

@mock.patch('cv2.imread')
def test_load_image_failure(mock_cv2_imread):
    mock_cv2_imread.return_value = None
    
    result = ipu.load_image("dummy/path.png")
    
    mock_cv2_imread.assert_called_once_with("dummy/path.png", cv2.IMREAD_UNCHANGED)
    assert result is None

@mock.patch('cv2.imread', side_effect=Exception("CV2 Read Error"))
def test_load_image_exception(mock_cv2_imread):
    result = ipu.load_image("dummy/path.png")
    mock_cv2_imread.assert_called_once_with("dummy/path.png", cv2.IMREAD_UNCHANGED)
    assert result is None


@mock.patch('cv2.cvtColor')
def test_convert_bgr_to_rgb_3_channel(mock_cv2_cvtcolor):
    bgr_image = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
    rgb_image_mock = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
    mock_cv2_cvtcolor.return_value = rgb_image_mock

    result = ipu.convert_bgr_to_rgb(bgr_image)

    mock_cv2_cvtcolor.assert_called_once_with(bgr_image, cv2.COLOR_BGR2RGB)
    assert np.array_equal(result, rgb_image_mock)

@mock.patch('cv2.cvtColor')
def test_convert_bgr_to_rgb_4_channel_bgra(mock_cv2_cvtcolor):
    bgra_image = np.random.randint(0, 255, (10, 10, 4), dtype=np.uint8)
    rgb_image_mock = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8) # cvtColor BGRA2RGB drops alpha
    mock_cv2_cvtcolor.return_value = rgb_image_mock # Mocking the output of BGRA2RGB

    result = ipu.convert_bgr_to_rgb(bgra_image)

    mock_cv2_cvtcolor.assert_called_once_with(bgra_image, cv2.COLOR_BGRA2RGB)
    assert np.array_equal(result, rgb_image_mock)


def test_convert_bgr_to_rgb_none_input():
    assert ipu.convert_bgr_to_rgb(None) is None

def test_convert_bgr_to_rgb_grayscale_input():
    gray_image = np.random.randint(0, 255, (10, 10), dtype=np.uint8)
    result = ipu.convert_bgr_to_rgb(gray_image)
    assert np.array_equal(result, gray_image) # Should return as is

@mock.patch('cv2.cvtColor')
def test_convert_rgb_to_bgr_3_channel(mock_cv2_cvtcolor):
    rgb_image = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
    bgr_image_mock = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
    mock_cv2_cvtcolor.return_value = bgr_image_mock

    result = ipu.convert_rgb_to_bgr(rgb_image)

    mock_cv2_cvtcolor.assert_called_once_with(rgb_image, cv2.COLOR_RGB2BGR)
    assert np.array_equal(result, bgr_image_mock)

def test_convert_rgb_to_bgr_none_input():
    assert ipu.convert_rgb_to_bgr(None) is None

def test_convert_rgb_to_bgr_grayscale_input():
    gray_image = np.random.randint(0, 255, (10, 10), dtype=np.uint8)
    result = ipu.convert_rgb_to_bgr(gray_image)
    assert np.array_equal(result, gray_image) # Should return as is

def test_convert_rgb_to_bgr_4_channel_input():
    rgba_image = np.random.randint(0, 255, (10, 10, 4), dtype=np.uint8)
    result = ipu.convert_rgb_to_bgr(rgba_image)
    assert np.array_equal(result, rgba_image) # Should return as is


@mock.patch('cv2.resize')
def test_resize_image_downscale(mock_cv2_resize):
    original_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    resized_image_mock = np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8)
    mock_cv2_resize.return_value = resized_image_mock
    target_w, target_h = 50, 50

    result = ipu.resize_image(original_image, target_w, target_h)

    mock_cv2_resize.assert_called_once_with(original_image, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
    assert np.array_equal(result, resized_image_mock)

@mock.patch('cv2.resize')
def test_resize_image_upscale(mock_cv2_resize):
    original_image = np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8)
    resized_image_mock = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    mock_cv2_resize.return_value = resized_image_mock
    target_w, target_h = 100, 100

    result = ipu.resize_image(original_image, target_w, target_h)

    mock_cv2_resize.assert_called_once_with(original_image, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    assert np.array_equal(result, resized_image_mock)

@mock.patch('cv2.resize')
def test_resize_image_custom_interpolation(mock_cv2_resize):
    original_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    resized_image_mock = np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8)
    mock_cv2_resize.return_value = resized_image_mock
    target_w, target_h = 50, 50

    result = ipu.resize_image(original_image, target_w, target_h, interpolation=cv2.INTER_NEAREST)

    mock_cv2_resize.assert_called_once_with(original_image, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
    assert np.array_equal(result, resized_image_mock)

def test_resize_image_none_input():
    with pytest.raises(ValueError, match="Cannot resize a None image."):
        ipu.resize_image(None, 50, 50)

@pytest.mark.parametrize("w, h", [(0, 50), (50, 0), (-1, 50)])
def test_resize_image_invalid_dims(w, h):
    original_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="Target width and height must be positive."):
        ipu.resize_image(original_image, w, h)


@mock.patch('cv2.imwrite')
@mock.patch('pathlib.Path.mkdir') # Mock mkdir to avoid actual directory creation
def test_save_image_success(mock_mkdir, mock_cv2_imwrite):
    mock_cv2_imwrite.return_value = True
    img_data = np.zeros((10,10,3), dtype=np.uint8) # RGB
    save_path = "output/test.png"

    # ipu.save_image converts RGB to BGR by default for non-EXR
    # So we expect convert_rgb_to_bgr to be called internally,
    # and cv2.imwrite to receive BGR data.
    # We can mock convert_rgb_to_bgr if we want to be very specific,
    # or trust its own unit tests and check the data passed to imwrite.
    # For simplicity, let's assume convert_rgb_to_bgr works and imwrite gets BGR.
    # The function copies data, so we can check the mock call.

    success = ipu.save_image(save_path, img_data, convert_to_bgr_before_save=True)

    assert success is True
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    
    # Check that imwrite was called. The first arg to assert_called_once_with is the path.
    # The second arg is the image data. We need to compare it carefully.
    # Since convert_rgb_to_bgr is called internally, the data passed to imwrite will be BGR.
    # Let's create expected BGR data.
    expected_bgr_data = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)
    
    args, kwargs = mock_cv2_imwrite.call_args
    assert args[0] == str(Path(save_path))
    assert np.array_equal(args[1], expected_bgr_data)


@mock.patch('cv2.imwrite')
@mock.patch('pathlib.Path.mkdir')
def test_save_image_success_exr_no_bgr_conversion(mock_mkdir, mock_cv2_imwrite):
    mock_cv2_imwrite.return_value = True
    img_data_rgb_float = np.random.rand(10,10,3).astype(np.float32) # RGB float for EXR
    save_path = "output/test.exr"

    success = ipu.save_image(save_path, img_data_rgb_float, output_format="exr", convert_to_bgr_before_save=False)
    
    assert success is True
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    args, kwargs = mock_cv2_imwrite.call_args
    assert args[0] == str(Path(save_path))
    assert np.array_equal(args[1], img_data_rgb_float) # Should be original RGB data

@mock.patch('cv2.imwrite')
@mock.patch('pathlib.Path.mkdir')
def test_save_image_success_explicit_bgr_false_png(mock_mkdir, mock_cv2_imwrite):
    mock_cv2_imwrite.return_value = True
    img_data_rgb = np.zeros((10,10,3), dtype=np.uint8) # RGB
    save_path = "output/test.png"

    # If convert_to_bgr_before_save is False, it should save RGB as is.
    # However, OpenCV's imwrite for PNG might still expect BGR.
    # The function's docstring says: "If True and image is 3-channel, converts RGB to BGR."
    # So if False, it passes the data as is.
    success = ipu.save_image(save_path, img_data_rgb, convert_to_bgr_before_save=False)
    
    assert success is True
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    args, kwargs = mock_cv2_imwrite.call_args
    assert args[0] == str(Path(save_path))
    assert np.array_equal(args[1], img_data_rgb)


@mock.patch('cv2.imwrite')
@mock.patch('pathlib.Path.mkdir')
def test_save_image_failure(mock_mkdir, mock_cv2_imwrite):
    mock_cv2_imwrite.return_value = False
    img_data = np.zeros((10,10,3), dtype=np.uint8)
    save_path = "output/fail.png"
    
    success = ipu.save_image(save_path, img_data)
    
    assert success is False
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_cv2_imwrite.assert_called_once() # Check it was called

def test_save_image_none_data():
    assert ipu.save_image("output/none.png", None) is False

@mock.patch('cv2.imwrite', side_effect=Exception("CV2 Write Error"))
@mock.patch('pathlib.Path.mkdir')
def test_save_image_exception(mock_mkdir, mock_cv2_imwrite_exception):
    img_data = np.zeros((10,10,3), dtype=np.uint8)
    save_path = "output/exception.png"
    
    success = ipu.save_image(save_path, img_data)
    
    assert success is False
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_cv2_imwrite_exception.assert_called_once()

# Test data type conversions in save_image
@pytest.mark.parametrize(
    "input_dtype, input_data_producer, output_dtype_target, expected_conversion_dtype, check_scaling",
    [
        (np.uint16, lambda: (np.random.randint(0, 65535, (10,10,3), dtype=np.uint16)), np.uint8, np.uint8, True),
        (np.float32, lambda: np.random.rand(10,10,3).astype(np.float32), np.uint8, np.uint8, True),
        (np.uint8, lambda: (np.random.randint(0, 255, (10,10,3), dtype=np.uint8)), np.uint16, np.uint16, True),
        (np.float32, lambda: np.random.rand(10,10,3).astype(np.float32), np.uint16, np.uint16, True),
        (np.uint8, lambda: (np.random.randint(0, 255, (10,10,3), dtype=np.uint8)), np.float16, np.float16, True),
        (np.uint16, lambda: (np.random.randint(0, 65535, (10,10,3), dtype=np.uint16)), np.float32, np.float32, True),
    ]
)
@mock.patch('cv2.imwrite')
@mock.patch('pathlib.Path.mkdir')
def test_save_image_dtype_conversion(mock_mkdir, mock_cv2_imwrite, input_dtype, input_data_producer, output_dtype_target, expected_conversion_dtype, check_scaling):
    mock_cv2_imwrite.return_value = True
    img_data = input_data_producer()
    original_img_data_copy = img_data.copy() # For checking scaling if needed

    ipu.save_image("output/dtype_test.png", img_data, output_dtype_target=output_dtype_target)

    mock_cv2_imwrite.assert_called_once()
    saved_img_data = mock_cv2_imwrite.call_args[0][1] # Get the image data passed to imwrite
    
    assert saved_img_data.dtype == expected_conversion_dtype

    if check_scaling:
        # This is a basic check. More precise checks would require known input/output values.
        if output_dtype_target == np.uint8:
            if input_dtype == np.uint16:
                expected_scaled_data = (original_img_data_copy.astype(np.float32) / 65535.0 * 255.0).astype(np.uint8)
                assert np.allclose(saved_img_data, cv2.cvtColor(expected_scaled_data, cv2.COLOR_RGB2BGR), atol=1) # Allow small diff due to float precision
            elif input_dtype in [np.float16, np.float32, np.float64]:
                expected_scaled_data = (np.clip(original_img_data_copy, 0.0, 1.0) * 255.0).astype(np.uint8)
                assert np.allclose(saved_img_data, cv2.cvtColor(expected_scaled_data, cv2.COLOR_RGB2BGR), atol=1)
        elif output_dtype_target == np.uint16:
            if input_dtype == np.uint8:
                expected_scaled_data = (original_img_data_copy.astype(np.float32) / 255.0 * 65535.0).astype(np.uint16)
                assert np.allclose(saved_img_data, cv2.cvtColor(expected_scaled_data, cv2.COLOR_RGB2BGR), atol=1)
            elif input_dtype in [np.float16, np.float32, np.float64]:
                expected_scaled_data = (np.clip(original_img_data_copy, 0.0, 1.0) * 65535.0).astype(np.uint16)
                assert np.allclose(saved_img_data, cv2.cvtColor(expected_scaled_data, cv2.COLOR_RGB2BGR), atol=1)
        # Add more scaling checks for float16, float32 if necessary


# --- Tests for calculate_image_stats ---

def test_calculate_image_stats_grayscale_uint8():
    img_data = np.array([[0, 128], [255, 10]], dtype=np.uint8)
    # Expected normalized: [[0, 0.50196], [1.0, 0.03921]] approx
    stats = ipu.calculate_image_stats(img_data)
    assert stats is not None
    assert np.isclose(stats["min"], 0/255.0)
    assert np.isclose(stats["max"], 255/255.0)
    assert np.isclose(stats["mean"], np.mean(img_data.astype(np.float64)/255.0))

def test_calculate_image_stats_color_uint8():
    img_data = np.array([
        [[0, 50, 100], [10, 60, 110]],
        [[255, 128, 200], [20, 70, 120]]
    ], dtype=np.uint8)
    stats = ipu.calculate_image_stats(img_data)
    assert stats is not None
    # Min per channel (normalized)
    assert np.allclose(stats["min"], [0/255.0, 50/255.0, 100/255.0])
    # Max per channel (normalized)
    assert np.allclose(stats["max"], [255/255.0, 128/255.0, 200/255.0])
    # Mean per channel (normalized)
    expected_mean = np.mean(img_data.astype(np.float64)/255.0, axis=(0,1))
    assert np.allclose(stats["mean"], expected_mean)

def test_calculate_image_stats_grayscale_uint16():
    img_data = np.array([[0, 32768], [65535, 1000]], dtype=np.uint16)
    stats = ipu.calculate_image_stats(img_data)
    assert stats is not None
    assert np.isclose(stats["min"], 0/65535.0)
    assert np.isclose(stats["max"], 65535/65535.0)
    assert np.isclose(stats["mean"], np.mean(img_data.astype(np.float64)/65535.0))

def test_calculate_image_stats_color_float32():
    # Floats are assumed to be in 0-1 range already by the function's normalization logic
    img_data = np.array([
        [[0.0, 0.2, 0.4], [0.1, 0.3, 0.5]],
        [[1.0, 0.5, 0.8], [0.05, 0.25, 0.6]]
    ], dtype=np.float32)
    stats = ipu.calculate_image_stats(img_data)
    assert stats is not None
    assert np.allclose(stats["min"], [0.0, 0.2, 0.4])
    assert np.allclose(stats["max"], [1.0, 0.5, 0.8])
    expected_mean = np.mean(img_data.astype(np.float64), axis=(0,1))
    assert np.allclose(stats["mean"], expected_mean)

def test_calculate_image_stats_none_input():
    assert ipu.calculate_image_stats(None) is None

def test_calculate_image_stats_unsupported_shape():
    img_data = np.zeros((2,2,2,2), dtype=np.uint8) # 4D array
    assert ipu.calculate_image_stats(img_data) is None

@mock.patch('numpy.mean', side_effect=Exception("Numpy error"))
def test_calculate_image_stats_exception_during_calculation(mock_np_mean):
    img_data = np.array([[0, 128], [255, 10]], dtype=np.uint8)
    stats = ipu.calculate_image_stats(img_data)
    assert stats == {"error": "Error calculating image stats"}

# Example of mocking ipu.load_image for a function that uses it (if calculate_image_stats used it)
# For the current calculate_image_stats, it takes image_data directly, so this is not needed for it.
# This is just an example as requested in the prompt for a hypothetical scenario.
@mock.patch('processing.utils.image_processing_utils.load_image') 
def test_hypothetical_function_using_load_image(mock_load_image):
    # This test is for a function that would call ipu.load_image internally
    # e.g. def process_image_from_path(path):
    #          img_data = ipu.load_image(path)
    #          return ipu.calculate_image_stats(img_data)
    
    mock_img_data = np.array([[[0.5]]], dtype=np.float32)
    mock_load_image.return_value = mock_img_data
    
    # result = ipu.hypothetical_process_image_from_path("dummy.png") 
    # mock_load_image.assert_called_once_with("dummy.png")
    # assert result["mean"] == 0.5 
    pass # This is a conceptual example