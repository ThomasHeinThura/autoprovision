# ---- build ----
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY src/TaskDesk.Api.csproj ./src/
RUN dotnet restore ./src/TaskDesk.Api.csproj
COPY src/ ./src/
RUN dotnet publish ./src/TaskDesk.Api.csproj -c Release -o /app /p:UseAppHost=false

# ---- runtime ----
FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
COPY --from=build /app ./
ENV ASPNETCORE_URLS=http://+:8080 \
    DB_PATH=/data/taskdesk.db \
    DOTNET_EnableDiagnostics=0
# non-root + writable data dir for the SQLite file
# The aspnet:10.0 image already ships a non-root "app" user (uid 1654); adduser/addgroup aren't installed.
RUN mkdir -p /data && chown -R app:app /data /app
USER app
EXPOSE 8080
ENTRYPOINT ["dotnet", "TaskDesk.Api.dll"]
