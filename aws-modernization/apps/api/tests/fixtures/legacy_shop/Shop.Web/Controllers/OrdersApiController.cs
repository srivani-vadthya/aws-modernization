using System.Linq;
using System.Net;
using System.Net.Http;
using System.Web.Http;
using Shop.Entities;
using Shop.Web.Models;
using Shop.Web.Services;

namespace Shop.Web.Controllers
{
    [RoutePrefix("api/OrdersApi")]
    public class OrdersApiController : BaseApiController
    {
        private NotificationService _notifications = new NotificationService();

        public HttpResponseMessage Get(int id)
        {
            var order = Uow.Orders.GetById(id);
            return Request.CreateResponse(HttpStatusCode.OK, order);
        }

        public HttpResponseMessage Post(OrderModel model)
        {
            var entity = AutoMapper.Mapper.Map<Order>(model);
            entity.StatusId = Uow.OrderStatuses.GetAll().First(s => s.Name == "New").Id;
            SaveNew(entity);
            return Request.CreateResponse(HttpStatusCode.OK);
        }

        private void SaveNew(Order entity)
        {
            Uow.Orders.Add(entity);
            foreach (var line in entity.Lines)
            {
                Uow.OrderLines.Add(line);
            }
            Uow.SaveChanges();
            Log.Info("created");
        }

        [HttpPatch]
        [Route("Cancel")]
        public HttpResponseMessage Cancel(OrderModel model)
        {
            var entity = Uow.Orders.GetById(model.Id);
            Uow.Orders.Update(entity);
            Uow.Orders.Detach(entity);
            Uow.SaveChanges();
            _notifications.OrderCancelled(entity.Id);
            return Request.CreateResponse(HttpStatusCode.OK);
        }

        public void Delete(int id)
        {
            Uow.OrderLines.Delete(id);
        }
    }
}
