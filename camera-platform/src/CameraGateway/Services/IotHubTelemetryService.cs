namespace CameraGateway.Services;

/// <summary>Periodically sends camera health telemetry to Azure IoT Hub.</summary>
public class IotHubTelemetryService(IConfiguration config, ILogger<IotHubTelemetryService> logger)
    : BackgroundService
{
    private readonly string? _connectionString = config["Azure:IoTHubConnectionString"];

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (string.IsNullOrEmpty(_connectionString))
        {
            logger.LogWarning("Azure IoT Hub not configured; telemetry disabled");
            return;
        }

        // TODO: create Microsoft.Azure.Devices.Client.DeviceClient and send periodic health messages
        while (!stoppingToken.IsCancellationRequested)
        {
            logger.LogDebug("IoT Hub telemetry tick");
            await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
        }
    }
}
