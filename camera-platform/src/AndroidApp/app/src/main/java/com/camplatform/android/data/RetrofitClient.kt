package com.camplatform.android.data

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*

// ── Models ───────────────────────────────────────────────────────────────────
data class Camera(
    val id: Int,
    val name: String,
    val ipAddress: String,
    val hostname: String?,
    val macAddress: String?,
    val rtspConfirmed: Boolean,
    val onvifConfirmed: Boolean,
    val status: String,
)

data class Recording(
    val id: Int,
    val cameraId: Int,
    val sessionId: String,
    val destination: String,
    val outputPath: String,
    val blobUrl: String?,
    val status: String,
    val startedUtc: String,
    val stoppedUtc: String?,
)

data class RecordingStartRequest(
    val cameraId: Int,
    val rtspUrl: String,
    val destination: String,
    val outputPath: String?,
    val azureContainer: String?,
)

data class CommandResult(val cameraId: Int, val method: String, val status: String)

// ── API interface ─────────────────────────────────────────────────────────────
interface CameraApiService {
    @GET("api/camera")
    suspend fun listCameras(): List<Camera>

    @GET("api/camera/{id}/status")
    suspend fun cameraStatus(@Path("id") id: Int): Map<String, Any>

    @POST("api/camera/{id}/command/{method}")
    suspend fun command(@Path("id") id: Int, @Path("method") method: String): CommandResult

    @GET("api/recording")
    suspend fun listRecordings(@Query("cameraId") cameraId: Int?): List<Recording>

    @POST("api/recording/start")
    suspend fun startRecording(@Body req: RecordingStartRequest): Recording

    @POST("api/recording/{sessionId}/stop")
    suspend fun stopRecording(@Path("sessionId") sessionId: String): Recording

    @GET("api/stream/{cameraId}/frame")
    @Streaming
    suspend fun getFrame(@Path("cameraId") cameraId: Int): okhttp3.ResponseBody
}

// ── Retrofit factory ─────────────────────────────────────────────────────────
object RetrofitClient {
    fun create(prefs: GatewayPreferences): CameraApiService {
        val interceptor = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        val http = OkHttpClient.Builder()
            .addInterceptor(interceptor)
            .addInterceptor { chain ->
                val key = prefs.getApiKey()
                val req = if (key.isNotEmpty())
                    chain.request().newBuilder().addHeader("X-API-Key", key).build()
                else chain.request()
                chain.proceed(req)
            }
            .build()

        return Retrofit.Builder()
            .baseUrl(prefs.getBaseUrl().trimEnd('/') + "/")
            .client(http)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(CameraApiService::class.java)
    }
}
