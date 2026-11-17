using System.Data.Entity;
using Shop.Entities;

namespace Shop.Data.Repositories
{
    public class OrderRepository : GenericRepository<Order>
    {
        public OrderRepository(DbContext context) : base(context) { }
    }

    public class OrderLineRepository : GenericRepository<OrderLine>
    {
        public OrderLineRepository(DbContext context) : base(context) { }
    }

    public class CustomerRepository : GenericRepository<Customer>
    {
        public CustomerRepository(DbContext context) : base(context) { }
    }

    public class OrderStatusRepository : GenericRepository<OrderStatus>
    {
        public OrderStatusRepository(DbContext context) : base(context) { }
    }
}
