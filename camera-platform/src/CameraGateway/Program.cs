using CameraGateway.Data;
using CameraGateway.Services;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// SQLite local DB – swap connection string for Azure SQL in production
builder.Services.AddDbContext<CameraDbContext>(opts =>
    opts.UseSqlite(builder.Configuration.GetConnectionString("DefaultConnection")
        ?? "Data Source=camera-platform.db"));

// Core platform services
builder.Services.AddSingleton<StreamService>();
builder.Services.AddSingleton<RecordingService>();
builder.Services.AddScoped<CameraService>();
builder.Services.AddScoped<AzureStorageService>();
builder.Services.AddHostedService<IotHubTelemetryService>();

// CORS – restrict to localhost and your Android backend in production
builder.Services.AddCors(options =>
    options.AddDefaultPolicy(p =>
        p.WithOrigins(
            builder.Configuration.GetSection("AllowedOrigins").Get<string[]>()
            ?? ["http://localhost:5173", "http://localhost:3000"]
        )
        .AllowAnyMethod()
        .AllowAnyHeader()));

var app = builder.Build();

// Apply migrations on startup
using (var scope = app.Services.CreateScope())
{
    scope.ServiceProvider.GetRequiredService<CameraDbContext>().Database.Migrate();
}

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseCors();
app.UseStaticFiles();      // serves WebPortal/wwwroot
app.MapControllers();
app.MapFallbackToFile("index.html"); // SPA fallback

app.Run();
