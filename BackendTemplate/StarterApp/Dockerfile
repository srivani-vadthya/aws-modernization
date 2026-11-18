# Build backend WebAPI
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build-backend
WORKDIR /app
COPY backend/*.csproj ./
RUN dotnet restore
COPY backend/ ./
RUN dotnet publish -c Release -o /out

# Runtime container
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY --from=build-backend /out ./
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "IMS.Modernized.WebAPI.dll"]
