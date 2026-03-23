package com.jake.visionphone.network

import com.jake.visionphone.camera.CameraFrame
import com.jake.visionphone.camera.FrameSendStats
import com.jake.visionphone.camera.FrameSender
import com.jake.visionphone.util.RecentStore
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

class VideoStreamClient(
    onStats: ((FrameSendStats) -> Unit)? = null,
    sendStatsStore: RecentStore? = null,
) {
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .build()

    private val frameSender = FrameSender(httpClient, onStats, sendStatsStore)

    fun sendFrame(frame: CameraFrame) {
        frameSender.sendFrame(frame)
    }

    fun shutdown() {
        frameSender.shutdown()
        httpClient.dispatcher.executorService.shutdown()
        httpClient.connectionPool.evictAll()
    }
}
