using AutoMapper;
using Shop.Entities;
using Shop.Web.Models;

namespace Shop.Web
{
    public static class MapConfig
    {
        public static void RegisterMaps()
        {
            Mapper.CreateMap<Order, OrderModel>()
                .ForMember(dest => dest.CustomerName, opt => opt.MapFrom(src => src.Customer.Name))
                .ReverseMap();
            Mapper.CreateMap<Customer, CustomerModel>();
        }
    }
}
