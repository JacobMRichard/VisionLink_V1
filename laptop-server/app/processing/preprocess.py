import cv2
import numpy as np


def preprocess(frame: np.ndarray) -> np.ndarray:
    """Convert BGR frame to blurred grayscale for contour detection."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (11, 11), 0)
    return blurred
