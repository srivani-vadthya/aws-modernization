using Shop.Data.Repositories;

namespace Shop.Data
{
    public class UnitOfWork
    {
        private ShopContext _context = new ShopContext();

        private OrderRepository _orders;
        public OrderRepository Orders
        {
            get
            {
                if (_orders == null)
                    _orders = new OrderRepository(_context);
                return _orders;
            }
        }

        public OrderLineRepository OrderLines => new OrderLineRepository(_context);
        public CustomerRepository Customers => new CustomerRepository(_context);
        public OrderStatusRepository OrderStatuses => new OrderStatusRepository(_context);

        public void SaveChanges()
        {
            _context.SaveChanges();
        }
    }
}
