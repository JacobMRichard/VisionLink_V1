package com.jake.visionphone.camera

/**
 * A single captured frame ready to be sent to the laptop.
 * [encodeDurationMs] is the time spent compressing bitmap → JPEG on the phone.
 */
data class CameraFrame(
    val frameId: Long,
    val timestampMs: Long,
    val width: Int,
    val height: Int,
    val rotationDegrees: Int,
    val jpegBytes: ByteArray,
    val encodeDurationMs: Long = 0,
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is CameraFrame) return false
        return frameId == other.frameId
    }

    override fun hashCode(): Int = frameId.hashCode()
}
