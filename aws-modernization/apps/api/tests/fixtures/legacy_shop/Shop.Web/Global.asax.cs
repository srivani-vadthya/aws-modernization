using System.Web;
using System.Web.Http;

namespace Shop.Web
{
    public class WebApiApplication : HttpApplication
    {
        protected void Application_Start()
        {
            GlobalConfiguration.Configure(WebApiConfig.Register);
            MapConfig.RegisterMaps();
        }
    }
}
