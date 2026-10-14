package com.wolff.camcontrol

import android.Manifest
import android.content.pm.PackageManager
import android.media.MediaRecorder
import android.os.Build
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

class MainActivity : FlutterActivity() {
	companion object {
		private const val AUDIO_CHANNEL = "camcontrol/audio"
		private const val MICROPHONE_PERMISSION_REQUEST = 4107
	}

	private var recorder: MediaRecorder? = null
	private var recordingPath: String? = null
	private var permissionResult: MethodChannel.Result? = null

	override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
		super.configureFlutterEngine(flutterEngine)
		MethodChannel(flutterEngine.dartExecutor.binaryMessenger, AUDIO_CHANNEL)
			.setMethodCallHandler { call, result ->
				when (call.method) {
					"requestPermission" -> requestMicrophonePermission(result)
					"start" -> startRecording(result)
					"stop" -> stopRecording(result)
					else -> result.notImplemented()
				}
			}
	}

	private fun requestMicrophonePermission(result: MethodChannel.Result) {
		if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
			PackageManager.PERMISSION_GRANTED
		) {
			result.success(true)
			return
		}
		if (permissionResult != null) {
			result.error("permission_pending", "Microphone permission request is active", null)
			return
		}
		permissionResult = result
		requestPermissions(
			arrayOf(Manifest.permission.RECORD_AUDIO),
			MICROPHONE_PERMISSION_REQUEST,
		)
	}

	private fun startRecording(result: MethodChannel.Result) {
		if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) !=
			PackageManager.PERMISSION_GRANTED
		) {
			result.error("permission_denied", "Microphone permission is required", null)
			return
		}
		if (recorder != null) {
			result.error("already_recording", "A voice message is already recording", null)
			return
		}

		val path = File(cacheDir, "camcontrol-voice-${System.currentTimeMillis()}.m4a").path
		try {
			val mediaRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
				MediaRecorder(this)
			} else {
				@Suppress("DEPRECATION")
				MediaRecorder()
			}
			mediaRecorder.setAudioSource(MediaRecorder.AudioSource.MIC)
			mediaRecorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
			mediaRecorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
			mediaRecorder.setAudioChannels(1)
			mediaRecorder.setAudioSamplingRate(16000)
			mediaRecorder.setAudioEncodingBitRate(24000)
			mediaRecorder.setOutputFile(path)
			mediaRecorder.prepare()
			mediaRecorder.start()
			recorder = mediaRecorder
			recordingPath = path
			result.success(path)
		} catch (error: Exception) {
			recorder?.release()
			recorder = null
			recordingPath = null
			File(path).delete()
			result.error("recording_failed", error.message, null)
		}
	}

	private fun stopRecording(result: MethodChannel.Result) {
		val mediaRecorder = recorder
		val path = recordingPath
		if (mediaRecorder == null || path == null) {
			result.error("not_recording", "No voice message is recording", null)
			return
		}
		try {
			mediaRecorder.stop()
			result.success(path)
		} catch (error: RuntimeException) {
			File(path).delete()
			result.error("recording_failed", "Voice message was too short", null)
		} finally {
			mediaRecorder.release()
			recorder = null
			recordingPath = null
		}
	}

	override fun onRequestPermissionsResult(
		requestCode: Int,
		permissions: Array<out String>,
		grantResults: IntArray,
	) {
		super.onRequestPermissionsResult(requestCode, permissions, grantResults)
		if (requestCode == MICROPHONE_PERMISSION_REQUEST) {
			val granted = grantResults.isNotEmpty() &&
				grantResults[0] == PackageManager.PERMISSION_GRANTED
			permissionResult?.success(granted)
			permissionResult = null
		}
	}

	override fun onDestroy() {
		recorder?.release()
		recorder = null
		super.onDestroy()
	}
}
