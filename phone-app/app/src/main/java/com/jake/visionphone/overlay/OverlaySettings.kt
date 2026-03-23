package com.jake.visionphone.overlay

data class OverlaySettings(
    val showPolygon: Boolean = false,  // true = polygon contour, false = bounding rect (default)
    val showLabels: Boolean = true,    // show object ID label at centroid
    val showCentroid: Boolean = true,  // show centroid dot
)
