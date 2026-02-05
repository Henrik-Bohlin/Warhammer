from PIL import Image
import cv2
import numpy as np

BOARD_WIDTH_IN = 32
BOARD_HEIGHT_IN = 20
CIRCLE_DIAMETER_IN = 12
IMAGE_PATH = "svart.jpg"
WINDOW_NAME = "Board Image"


def prepare_image(
    img: Image.Image,
    board_width_in: float,
    board_height_in: float,
    circle_diameter_in: float,
):

    w, h = img.size
    board_ar = board_width_in / board_height_in
    img_ar = w / h

    # Crop to match board aspect ratio
    if img_ar > board_ar:
        new_w = int(h * board_ar)
        crop_left = (w - new_w) // 2
        crop_right = crop_left + new_w
        img_cropped = img.crop((crop_left, 0, crop_right, h))
    else:
        new_h = int(w / board_ar)
        crop_top = (h - new_h) // 2
        crop_bottom = crop_top + new_h
        img_cropped = img.crop((0, crop_top, w, crop_bottom))

    # Compute pixels per inch
    width_px, height_px = img_cropped.size
    px_per_in_x = width_px / board_width_in
    px_per_in_y = height_px / board_height_in
    px_per_in = (px_per_in_x + px_per_in_y) / 2  # average

    # Circle radius in pixels
    circle_radius_px = int((circle_diameter_in / 2) * px_per_in)

    return img_cropped, circle_radius_px, px_per_in_x, px_per_in_y


def mouse_callback(event, x, y, flags, param):

    global current_circle_center, original_img, circle_radius_px

    if event == cv2.EVENT_LBUTTONDOWN:
        current_circle_center = (x, y)

    display_img = original_img.copy()

    # Draw circle if a center exists
    if current_circle_center is not None:
        cv2.circle(display_img, current_circle_center, circle_radius_px, (0, 0, 255), 2)

    # Display mouse coordinates
    text = f"X: {x}, Y: {y}"
    cv2.putText(
        display_img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2
    )

    cv2.imshow(WINDOW_NAME, display_img)


def main():
    global original_img, current_circle_center, circle_radius_px

    img = Image.open(IMAGE_PATH)

    # Prepare image and compute circle size
    img_cropped, circle_radius_px, px_per_in_x, px_per_in_y = prepare_image(
        img, BOARD_WIDTH_IN, BOARD_HEIGHT_IN, CIRCLE_DIAMETER_IN
    )

    # Convert to OpenCV format
    original_img = cv2.cvtColor(np.array(img_cropped), cv2.COLOR_RGB2BGR)
    current_circle_center = None

    # Setup window and callback
    cv2.imshow(WINDOW_NAME, original_img)
    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)

    while True:
        if cv2.waitKey(1) & 0xFF == 27:  # ESC
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
