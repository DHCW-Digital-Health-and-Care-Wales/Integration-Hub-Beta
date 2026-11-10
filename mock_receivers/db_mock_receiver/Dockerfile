# Local testing and the Azure DEV environment: a real SQL Server hosting a mock WRRS DRS database and
# dbo.prQueueMessage procedure, plus a mock TRRR Clinical_Results database and dbo.TRRRIDUpdate procedure. The image is linux/amd64 only (Azure Container Apps is amd64; on Apple Silicon it
# runs under emulation, the platform is set in compose).
FROM mcr.microsoft.com/mssql/server:2022-latest

USER root
# socat publishes port 1433 only once the schema is initialised (see entrypoint.sh).
RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*
COPY --chown=mssql:root entrypoint.sh /opt/mock_db_receiver/entrypoint.sh
COPY --chown=mssql:root sql/init.sql /opt/mock_db_receiver/init.sql
RUN chmod 0555 /opt/mock_db_receiver/entrypoint.sh

USER mssql
# Express is free to use in any environment; the default (Developer) is licensed for non-production use only.
ENV MSSQL_PID=Express
EXPOSE 1433

ENTRYPOINT ["/opt/mock_db_receiver/entrypoint.sh"]
