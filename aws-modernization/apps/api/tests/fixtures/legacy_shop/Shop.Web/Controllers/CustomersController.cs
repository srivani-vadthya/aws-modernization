using System.Linq;
using System.Web.Mvc;
using Shop.Data;

namespace Shop.Web.Controllers
{
    public class CustomersController : Controller
    {
        private readonly UnitOfWork _uow = new UnitOfWork();

        public ActionResult Index()
        {
            var customers = _uow.Customers.GetAll().ToList();
            return View(customers);
        }
    }
}
