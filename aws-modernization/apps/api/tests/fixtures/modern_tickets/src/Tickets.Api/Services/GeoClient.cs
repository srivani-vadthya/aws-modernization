using System.Net.Http;

namespace Tickets.Api.Services;

public class GeoClient
{
    private readonly HttpClient _http;

    public GeoClient(HttpClient http) => _http = http;

    public Task<string> Lookup(string city) => _http.GetStringAsync($"https://geo.example.com/{city}");
}
