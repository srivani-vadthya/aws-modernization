using System.Net.Mail;

namespace Shop.Web.Services
{
    public class NotificationService
    {
        public void OrderCancelled(int orderId)
        {
            // Publish an OrderCancelled event to EventBridge (comment only - not a publisher)
            var client = new SmtpClient("smtp.example.com", 587);
            client.Send("shop@example.com", "ops@example.com", "Cancelled", orderId.ToString());
        }
    }
}
