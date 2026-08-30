using CameraGateway.Models;
using Microsoft.EntityFrameworkCore;

namespace CameraGateway.Data;

public class CameraDbContext(DbContextOptions<CameraDbContext> options) : DbContext(options)
{
    public DbSet<Camera> Cameras => Set<Camera>();
    public DbSet<Recording> Recordings => Set<Recording>();

    protected override void OnModelCreating(ModelBuilder mb)
    {
        mb.Entity<Camera>().HasIndex(c => c.IpAddress).IsUnique();
        mb.Entity<Camera>().HasMany(c => c.Recordings).WithOne(r => r.Camera)
            .HasForeignKey(r => r.CameraId);
    }
}
