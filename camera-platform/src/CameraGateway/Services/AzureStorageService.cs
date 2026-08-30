namespace CameraGateway.Services;

/// <summary>Uploads clips and snapshots to Azure Blob Storage.</summary>
public class AzureStorageService(IConfiguration config, ILogger<AzureStorageService> logger)
{
    private readonly string? _connectionString = config["Azure:StorageConnectionString"];
    private readonly string _container = config["Azure:BlobContainer"] ?? "camera-recordings";

    public async Task<string?> UploadClipAsync(string sessionId)
    {
        if (string.IsNullOrEmpty(_connectionString))
        {
            logger.LogWarning("Azure Storage not configured; upload skipped");
            return null;
        }

        // TODO: resolve output path from DB, then upload
        // Example:
        //   var client = new BlobContainerClient(_connectionString, _container);
        //   await client.UploadBlobAsync(blobName, fileStream);
        logger.LogInformation("Clip upload queued for session {SessionId}", sessionId);
        return null;
    }

    public async Task<string?> UploadSnapshotAsync(string localPath, string blobName)
    {
        if (string.IsNullOrEmpty(_connectionString)) return null;
        try
        {
            using var fs = File.OpenRead(localPath);
            var client = new Azure.Storage.Blobs.BlobContainerClient(_connectionString, _container);
            await client.CreateIfNotExistsAsync();
            var blob = client.GetBlobClient(blobName);
            await blob.UploadAsync(fs, overwrite: true);
            logger.LogInformation("Snapshot uploaded: {Name}", blobName);
            return blob.Uri.ToString();
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Snapshot upload failed for {Path}", localPath);
            return null;
        }
    }
}
