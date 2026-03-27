/*
   This script seeds the monitoring.Message table with 1000 rows of test data based on a sample PHW HL7 message.
   The ReceivedAt timestamps are distributed across three days (25% today, 25% yesterday, and 25% tomorrow)
   with 25% of messages having a fixed timestamp of 2025-12-31 to allow testing of date range queries.

   The session ID stored in the DB and replayed is whichever was active when the message was written to the message
   store (depends on which stage of the flow you're replaying). This can vary - for example, the PHW receiver and
   MPI sender use different session IDs, same applies to the Paris flow. Since this mock DB is seeded with PHW messages
   from the sender it exclusively uses that session ID.
*/

USE IntegrationHub;
GO

SET NOCOUNT ON;
GO

DECLARE @TodayUtc DATE = CAST(SYSUTCDATETIME() AS DATE);

DECLARE @RawPayload NVARCHAR(MAX) = N'MSH|^~\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444444444|P|2.5|||||GBR||EN||ITKv1.0
EVN||20250502092900|20250505232332|||20250505232332
PID|||8888888^^^252^PI~4444444444^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19990101|M|||99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H~SECOND1^SECOND2^SECOND3^SECOND4^SB99 9SB^^H|||||||||||||||||||||01
PD1|||^^W00000^|G999999
PV1||U';

DECLARE @XmlPayload XML = N'<ns0:ADT_A05 xmlns:ns0="urn:hl7-org:v2xml">
<ns0:MSH><ns0:MSH.1>|</ns0:MSH.1><ns0:MSH.2>^~\&amp;</ns0:MSH.2><ns0:MSH.3>252</ns0:MSH.3><ns0:MSH.4>252</ns0:MSH.4><ns0:MSH.5>100</ns0:MSH.5><ns0:MSH.6>100</ns0:MSH.6><ns0:MSH.7>20250505232332</ns0:MSH.7><ns0:MSH.9>ADT^A31^ADT_A05</ns0:MSH.9><ns0:MSH.10>202505052323364444444444</ns0:MSH.10><ns0:MSH.11>P</ns0:MSH.11><ns0:MSH.12>2.5</ns0:MSH.12>
<ns0:MSH.17>GBR</ns0:MSH.17><ns0:MSH.19>EN</ns0:MSH.19><ns0:MSH.21>ITKv1.0</ns0:MSH.21></ns0:MSH>
<ns0:EVN><ns0:EVN.2>20250502092900</ns0:EVN.2><ns0:EVN.3>20250505232332</ns0:EVN.3><ns0:EVN.6>20250505232332</ns0:EVN.6></ns0:EVN>
<ns0:PID><ns0:PID.3>8888888^^^252^PI~4444444444^^^NHS^NH</ns0:PID.3>
<ns0:PID.5>MYSURNAME^MYFNAME^MYMNAME^^MR</ns0:PID.5><ns0:PID.7>19990101</ns0:PID.7><ns0:PID.8>M</ns0:PID.8>
<ns0:PID.11>99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H~SECOND1^SECOND2^SECOND3^SECOND4^SB99 9SB^^H</ns0:PID.11><ns0:PID.32>01</ns0:PID.32></ns0:PID>
<ns0:PD1><ns0:PD1.3>^^W00000</ns0:PD1.3><ns0:PD1.4>G999999</ns0:PD1.4></ns0:PD1>
<ns0:PV1><ns0:PV1.2>U</ns0:PV1.2></ns0:PV1>
</ns0:ADT_A05>';
WITH
    NumberedRows
    AS
    (
        SELECT TOP (1000)
            ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS RowNum
        FROM sys.all_objects AS a
    CROSS JOIN sys.all_objects AS b
    ),
    SeedRows
    AS
    (
        SELECT
            CASE
            WHEN RowNum <= 250 THEN DATEADD(SECOND, RowNum - 1, CAST(@TodayUtc AS DATETIME2(3)))
            WHEN RowNum <= 500 THEN DATEADD(SECOND, RowNum - 251, DATEADD(DAY, 1, CAST(@TodayUtc AS DATETIME2(3))))
            WHEN RowNum <= 750 THEN DATEADD(SECOND, RowNum - 501, DATEADD(DAY, -1, CAST(@TodayUtc AS DATETIME2(3))))
            ELSE DATEADD(SECOND, RowNum - 751, CAST('2025-12-31T00:00:00.000' AS DATETIME2(3)))
        END AS ReceivedAt,
            CAST(NEWID() AS NVARCHAR(100)) AS CorrelationId,
            N'mpi' AS SessionId
        FROM NumberedRows
    )
INSERT INTO monitoring.Message
    (
    ReceivedAt,
    StoredAt,
    CorrelationId,
    SessionId,
    SourceSystem,
    ProcessingComponent,
    TargetSystem,
    RawPayload,
    XmlPayload
    )
SELECT
    s.ReceivedAt,
    s.ReceivedAt,
    s.CorrelationId,
    s.SessionId,
    N'252',
    N'mpi_hl7_sender',
    N'MPI',
    @RawPayload,
    @XmlPayload
FROM SeedRows AS s;

SELECT @@ROWCOUNT AS InsertedRows;
