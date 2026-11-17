using System.Configuration;
using System.Data.Entity;
using Shop.Data.Configurations;
using Shop.Entities;

namespace Shop.Data
{
    public class ShopContext : DbContext
    {
        public ShopContext() : base(ConfigurationManager.AppSettings["ConnectionName"]) { }

        public DbSet<Order> Orders { get; set; }
        public DbSet<OrderLine> OrderLines { get; set; }
        public DbSet<Customer> Customers { get; set; }
        public DbSet<OrderStatus> OrderStatuses { get; set; }

        protected override void OnModelCreating(DbModelBuilder modelBuilder)
        {
            modelBuilder.Configurations.Add(new OrderConfiguration());
        }
    }
}
