using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;

namespace OrderService.Data
{
    public class OrderDbContext : DbContext
    {
        private readonly IConfiguration _config;

        public OrderDbContext(DbContextOptions<OrderDbContext> options,
                              IConfiguration config) : base(options)
        {
            _config = config;
        }

        protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
        {
            var connStr = _config.GetConnectionString("OrdersDb");
            optionsBuilder.UseNpgsql(connStr, npgsql =>
            {
                npgsql.MaxPoolSize(5);   // reduced from 20 — cost optimisation
                npgsql.MinPoolSize(1);
                npgsql.ConnectionIdleLifetime(TimeSpan.FromMinutes(2));
            });
        }

        public DbSet<Order> Orders => Set<Order>();
        public DbSet<OrderLine> OrderLines => Set<OrderLine>();
    }
}
