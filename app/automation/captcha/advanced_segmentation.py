"""
Advanced character segmentation with overlap handling.
"""

import cv2
import numpy as np


class AdvancedSegmentation:
    """Advanced character segmentation."""

    @staticmethod
    def segment_characters(binary: np.ndarray, img_size: int = 28) -> list[np.ndarray]:
        """Segment characters with overlap detection."""
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)

        total_pixels = binary.shape[0] * binary.shape[1]
        min_area = max(15, int(total_pixels * 0.001))
        max_area = int(total_pixels * 0.4)

        components = []
        for i in range(1, num_labels):
            x, y, w, h, area = stats[i]

            if area < min_area or area > max_area:
                continue

            aspect = w / max(1, h)
            if aspect > 5 or aspect < 0.1:
                continue

            roi = binary[y:y+h, x:x+w]

            # Check if character is too wide (might be overlapping)
            if aspect > 1.8:
                # Try to split
                split_chars = AdvancedSegmentation._split_overlapping(roi, img_size)
                if split_chars:
                    for char in split_chars:
                        components.append((x, char))
                    continue

            normalized = AdvancedSegmentation._normalize_char(roi, img_size)
            components.append((x, normalized))

        components.sort(key=lambda c: c[0])
        return [char for _, char in components]

    @staticmethod
    def _split_overlapping(roi: np.ndarray, img_size: int) -> list[np.ndarray]:
        """Split overlapping characters using vertical projection."""
        projection = np.sum(roi, axis=0)

        # Find valleys (potential split points)
        mean_proj = np.mean(projection)
        threshold = mean_proj * 0.3

        valleys = []
        for i in range(1, len(projection) - 1):
            if projection[i] < threshold:
                if projection[i-1] >= threshold or projection[i+1] >= threshold:
                    valleys.append(i)

        if not valleys:
            return []

        # Find best split point (deepest valley near center)
        center = roi.shape[1] // 2
        best_valley = min(valleys, key=lambda v: (abs(v - center), -int(projection[v])))

        # Split at best valley
        left = roi[:, :best_valley]
        right = roi[:, best_valley:]

        chars = []
        for part in [left, right]:
            if part.shape[1] > 3 and np.sum(part) > 50:
                chars.append(AdvancedSegmentation._normalize_char(part, img_size))

        return chars if len(chars) == 2 else []

    @staticmethod
    def _normalize_char(bitmap: np.ndarray, img_size: int) -> np.ndarray:
        """Normalize character to fixed size."""
        ys, xs = np.where(bitmap > 0)
        if len(xs) == 0:
            return np.zeros((img_size, img_size), dtype=np.uint8)

        x1, x2 = xs.min(), xs.max() + 1
        y1, y2 = ys.min(), ys.max() + 1
        roi = bitmap[y1:y2, x1:x2]

        scale = min((img_size - 4) / roi.shape[1], (img_size - 4) / roi.shape[0])
        new_w = max(1, int(roi.shape[1] * scale))
        new_h = max(1, int(roi.shape[0] * scale))

        resized = cv2.resize(roi, (new_w, new_h),
                            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)

        canvas = np.zeros((img_size, img_size), dtype=np.uint8)
        offset_x = (img_size - new_w) // 2
        offset_y = (img_size - new_h) // 2
        canvas[offset_y:offset_y+new_h, offset_x:offset_x+new_w] = resized

        return canvas
