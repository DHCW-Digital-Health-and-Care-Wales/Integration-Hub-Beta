# Local testing only: a real SQL Server hosting a mock WRRS DRS database and dbo.prQueueMessage procedure.
# The image is linux/amd64 only; on Apple Silicon it runs under emulation (platform is set in compose).
FROM mcr.microsoft.com/mssql/server:2022-latest

USER root
COPY --chown=mssql:root entrypoint.sh /opt/mock_db_receiver/entrypoint.sh
COPY --chown=mssql:root sql/init.sql /opt/mock_db_receiver/init.sql
RUN chmod 0555 /opt/mock_db_receiver/entrypoint.sh

USER mssql
EXPOSE 1433

ENTRYPOINT ["/opt/mock_db_receiver/entrypoint.sh"]
