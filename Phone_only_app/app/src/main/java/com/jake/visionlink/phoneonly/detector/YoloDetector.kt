package com.jake.visionlink.phoneonly.detector

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import org.tensorflow.lite.Interpreter
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel

/**
 * On-device YOLOv8 detector using TensorFlow Lite.
 *
 * Supports two common output shapes automatically:
 *   [1, 84, 8400]  — direct ultralytics TFLite export
 *   [1, 8400, 84]  — onnx2tf conversion (transposed)
 *
 * Place your model at:  app/src/main/assets/yolov8n.tflite
 */
class YoloDetector(context: Context) {

    private val interpreter: Interpreter
    private val inputBuffer: ByteBuffer
    /** true = [1, 84, 8400], false = [1, 8400, 84] */
    private val outputIsChannelsFirst: Boolean

    init {
        val model = loadModelFile(context, MODEL_FILE)
        interpreter = Interpreter(model, Interpreter.Options().apply {
            numThreads = 4
        })
        // [1, 640, 640, 3] * 4 bytes per float
        inputBuffer = ByteBuffer.allocateDirect(1 * INPUT_SIZE * INPUT_SIZE * 3 * 4)
            .also { it.order(ByteOrder.nativeOrder()) }

        // Detect output shape at runtime
        val outShape = interpreter.getOutputTensor(0).shape()
        // outShape = [1, dim1, dim2]
        outputIsChannelsFirst = outShape[1] == (NUM_CLASSES + 4)
        Log.i(TAG, "YoloDetector ready  model=$MODEL_FILE  " +
            "output=${outShape.toList()}  channels_first=$outputIsChannelsFirst")
    }

    /**
     * Run detection on [bitmap]. Returns all detections above [confThreshold]
     * after NMS. Coordinates are in [bitmap] pixel space.
     */
    fun detect(bitmap: Bitmap, confThreshold: Float = CONF_THRESHOLD): List<Detection> {
        val scaledBitmap = Bitmap.createScaledBitmap(bitmap, INPUT_SIZE, INPUT_SIZE, true)
        fillInputBuffer(scaledBitmap)
        if (scaledBitmap !== bitmap) scaledBitmap.recycle()

        val detections = if (outputIsChannelsFirst) {
            // [1, 84, 8400]
            val rawOutput = Array(1) { Array(NUM_CLASSES + 4) { FloatArray(NUM_CANDIDATES) } }
            interpreter.run(inputBuffer, rawOutput)
            decodeChannelsFirst(rawOutput[0], bitmap.width, bitmap.height, confThreshold)
        } else {
            // [1, 8400, 84]
            val rawOutput = Array(1) { Array(NUM_CANDIDATES) { FloatArray(NUM_CLASSES + 4) } }
            interpreter.run(inputBuffer, rawOutput)
            decodeChannelsLast(rawOutput[0], bitmap.width, bitmap.height, confThreshold)
        }
        return nms(detections)
    }

    fun close() = interpreter.close()

    // ── Preprocessing ─────────────────────────────────────────────────────────

    private fun fillInputBuffer(bitmap: Bitmap) {
        inputBuffer.rewind()
        val pixels = IntArray(INPUT_SIZE * INPUT_SIZE)
        bitmap.getPixels(pixels, 0, INPUT_SIZE, 0, 0, INPUT_SIZE, INPUT_SIZE)
        for (pixel in pixels) {
            inputBuffer.putFloat(((pixel shr 16) and 0xFF) / 255f)  // R
            inputBuffer.putFloat(((pixel shr 8)  and 0xFF) / 255f)  // G
            inputBuffer.putFloat((pixel           and 0xFF) / 255f)  // B
        }
    }

    // ── Decoding ──────────────────────────────────────────────────────────────

    /** Output shape [84, 8400]: row = channel, col = candidate */
    private fun decodeChannelsFirst(
        output: Array<FloatArray>,
        origW: Int, origH: Int, confThreshold: Float,
    ): List<Detection> {
        val scaleX = origW.toFloat() / INPUT_SIZE
        val scaleY = origH.toFloat() / INPUT_SIZE
        val results = mutableListOf<Detection>()
        for (i in 0 until NUM_CANDIDATES) {
            var maxScore = 0f; var classId = 0
            for (c in 0 until NUM_CLASSES) {
                val s = output[4 + c][i]
                if (s > maxScore) { maxScore = s; classId = c }
            }
            if (maxScore < confThreshold) continue
            val cx = output[0][i]; val cy = output[1][i]
            val w  = output[2][i]; val h  = output[3][i]
            results.add(makeDetection(cx, cy, w, h, scaleX, scaleY, origW, origH, classId, maxScore) ?: continue)
        }
        return results
    }

    /** Output shape [8400, 84]: row = candidate, col = channel */
    private fun decodeChannelsLast(
        output: Array<FloatArray>,
        origW: Int, origH: Int, confThreshold: Float,
    ): List<Detection> {
        val scaleX = origW.toFloat() / INPUT_SIZE
        val scaleY = origH.toFloat() / INPUT_SIZE
        val results = mutableListOf<Detection>()
        for (i in 0 until NUM_CANDIDATES) {
            var maxScore = 0f; var classId = 0
            for (c in 0 until NUM_CLASSES) {
                val s = output[i][4 + c]
                if (s > maxScore) { maxScore = s; classId = c }
            }
            if (maxScore < confThreshold) continue
            val cx = output[i][0]; val cy = output[i][1]
            val w  = output[i][2]; val h  = output[i][3]
            results.add(makeDetection(cx, cy, w, h, scaleX, scaleY, origW, origH, classId, maxScore) ?: continue)
        }
        return results
    }

    private fun makeDetection(
        cx: Float, cy: Float, w: Float, h: Float,
        scaleX: Float, scaleY: Float,
        origW: Int, origH: Int,
        classId: Int, confidence: Float,
    ): Detection? {
        val x1 = ((cx - w / 2f) * scaleX).toInt().coerceIn(0, origW)
        val y1 = ((cy - h / 2f) * scaleY).toInt().coerceIn(0, origH)
        val x2 = ((cx + w / 2f) * scaleX).toInt().coerceIn(0, origW)
        val y2 = ((cy + h / 2f) * scaleY).toInt().coerceIn(0, origH)
        if (x2 <= x1 || y2 <= y1) return null
        return Detection(
            label      = COCO_CLASSES.getOrElse(classId) { "cls$classId" },
            confidence = confidence,
            x1 = x1, y1 = y1, x2 = x2, y2 = y2,
        )
    }

    // ── NMS ───────────────────────────────────────────────────────────────────

    private fun nms(detections: List<Detection>): List<Detection> {
        val sorted  = detections.sortedByDescending { it.confidence }.toMutableList()
        val keep    = mutableListOf<Detection>()
        val removed = BooleanArray(sorted.size)
        for (i in sorted.indices) {
            if (removed[i]) continue
            keep.add(sorted[i])
            for (j in i + 1 until sorted.size) {
                if (!removed[j] && iou(sorted[i], sorted[j]) > NMS_IOU_THRESHOLD) removed[j] = true
            }
        }
        return keep
    }

    private fun iou(a: Detection, b: Detection): Float {
        val ix1 = maxOf(a.x1, b.x1); val iy1 = maxOf(a.y1, b.y1)
        val ix2 = minOf(a.x2, b.x2); val iy2 = minOf(a.y2, b.y2)
        val inter = maxOf(0, ix2 - ix1).toFloat() * maxOf(0, iy2 - iy1)
        if (inter == 0f) return 0f
        return inter / (a.width * a.height + b.width * b.height - inter)
    }

    // ── Model loading ─────────────────────────────────────────────────────────

    private fun loadModelFile(context: Context, filename: String): ByteBuffer {
        val fd = context.assets.openFd(filename)
        return FileInputStream(fd.fileDescriptor).channel.map(
            FileChannel.MapMode.READ_ONLY,
            fd.startOffset,
            fd.declaredLength
        )
    }

    companion object {
        private const val TAG               = "YoloDetector"
        private const val MODEL_FILE        = "yolov8n.tflite"
        private const val INPUT_SIZE        = 640
        private const val NUM_CANDIDATES    = 8400
        private const val NUM_CLASSES       = 80
        private const val CONF_THRESHOLD    = 0.10f
        private const val NMS_IOU_THRESHOLD = 0.45f

        val COCO_CLASSES = listOf(
            "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
            "truck", "boat", "traffic light", "fire hydrant", "stop sign",
            "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
            "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
            "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
            "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
            "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
            "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
            "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
            "couch", "potted plant", "bed", "dining table", "toilet", "tv",
            "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
            "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
            "scissors", "teddy bear", "hair drier", "toothbrush"
        )
    }
}
