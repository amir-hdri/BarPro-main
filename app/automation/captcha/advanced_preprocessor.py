"""
Advanced image preprocessing for captcha solving.
"""

import cv2
import numpy as np


class AdvancedPreprocessor:
    """Advanced image preprocessing with noise reduction and enhancement."""

    @staticmethod
    def enhance_image(image: np.ndarray) -> list[np.ndarray]:
        """Generate multiple enhanced variants of the input image."""
        variants = []

        # Denoise
        denoised1 = cv2.fastNlMeansDenoising(image, None, 10, 7, 21)
        denoised2 = cv2.bilateralFilter(image, 9, 75, 75)

        for base_img in [image, denoised1, denoised2]:
            for scale in [2.5, 3.0, 3.5, 4.0]:
                enlarged = cv2.resize(base_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

                # Sharpen
                kernel_sharp = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
                sharpened = cv2.filter2D(enlarged, -1, kernel_sharp)

                # CLAHE
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                enhanced = clahe.apply(sharpened)

                variants.append(enhanced)

        return variants

    @staticmethod
    def binarize_advanced(image: np.ndarray) -> list[np.ndarray]:
        """Apply advanced binarization techniques."""
        results = []
        blurred = cv2.GaussianBlur(image, (5, 5), 0)

        # Otsu
        _, otsu1 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        results.append(otsu1)

        # Adaptive thresholding
        for block_size in [11, 15, 21, 31, 41]:
            for c in [2, 5, 8, 11]:
                adaptive = cv2.adaptiveThreshold(
                    blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block_size, c
                )
                results.append(adaptive)

        # Sauvola
        mean = cv2.blur(image, (15, 15))
        sqmean = cv2.blur(image.astype(np.float32) ** 2, (15, 15))
        std = np.sqrt(sqmean - mean**2)
        threshold = mean * (1 + 0.2 * ((std / 128) - 1))
        # cv2 stubs return an imprecise dtype for bitwise_not; keep the variable
        # at the bare np.ndarray type so the reassignment below typechecks.
        sauvola: np.ndarray = ((image > threshold) * 255).astype(np.uint8)
        sauvola = cv2.bitwise_not(sauvola)
        results.append(sauvola)

        return results

    @staticmethod
    def morphological_cleanup(binary: np.ndarray) -> np.ndarray:
        """Advanced morphological operations."""
        kernel_small = np.ones((2, 2), dtype=np.uint8)
        # cv2.morphologyEx stubs return an imprecise dtype that fails
        # connectedComponentsWithStats overload matching below; the bare
        # np.ndarray annotation keeps the runtime value unchanged.
        cleaned: np.ndarray = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_small)

        kernel_close = np.ones((3, 3), dtype=np.uint8)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel_close)

        # Remove tiny components
        # connectivity=8 as keyword: the stub types the 2nd positional as the
        # `labels` output array, so a positional 8 defeats overload matching.
        # Verified on the project's cv2 (5.0.0): keyword and positional forms
        # return identical results; this only names the argument.
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
        for i in range(1, num_labels):
            if stats[i, cv2.CC_STAT_AREA] < 8:
                cleaned[labels == i] = 0

        return cleaned
