using System.Data.Entity.ModelConfiguration;
using Shop.Entities;

namespace Shop.Data.Configurations
{
    class OrderConfiguration : EntityTypeConfiguration<Order>
    {
        public OrderConfiguration()
        {
            this.HasRequired(o => o.Customer);
            this.HasMany(o => o.Lines)
                .WithRequired(l => l.Order);
        }
    }
}
