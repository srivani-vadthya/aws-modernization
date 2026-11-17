using System.Web.Http;
using Shop.Data;
using Shop.Web.Services;

namespace Shop.Web.Controllers
{
    public class BaseApiController : ApiController
    {
        private UnitOfWork _uow;
        public UnitOfWork Uow
        {
            get
            {
                if (_uow == null)
                    _uow = new UnitOfWork();
                return _uow;
            }
        }

        protected Logger Log { get; } = new Logger();
    }
}
