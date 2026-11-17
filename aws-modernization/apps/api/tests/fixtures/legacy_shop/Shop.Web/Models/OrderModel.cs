namespace Shop.Web.Models
{
    public class OrderModel
    {
        public int Id { get; set; }
        public double Total { get; set; }
        public string Reference { get; set; }
        public string CustomerName { get; set; }
    }

    public class CustomerModel
    {
        public int Id { get; set; }
        public string Name { get; set; }
    }
}
