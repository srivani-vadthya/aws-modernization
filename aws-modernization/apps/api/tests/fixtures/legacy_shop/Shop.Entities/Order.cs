using System;
using System.Collections.Generic;

namespace Shop.Entities
{
    public class Order
    {
        public int Id { get; set; }
        public decimal Total { get; set; }
        public string Reference { get; set; }
        public int CustomerId { get; set; }
        public int StatusId { get; set; }
        public virtual Customer Customer { get; set; }
        public virtual OrderStatus Status { get; set; }
        public virtual IList<OrderLine> Lines { get; set; }
    }

    public class OrderLine
    {
        public int Id { get; set; }
        public int Quantity { get; set; }
        public int OrderId { get; set; }
        public virtual Order Order { get; set; }
    }

    public class OrderStatus
    {
        public int Id { get; set; }
        public string Name { get; set; }
    }
}
