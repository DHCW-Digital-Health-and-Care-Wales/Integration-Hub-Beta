# Cosmos DB for Monitoring Dashboard Data Persistence 

!!! info

    **Status**: Proposed
    
    **Level**: 1

    **Proposer**:  Gareth Edwards 

    **Authors**:  Gareth Edwards, Bethan Flowers 

    **Stakeholders / Reviewers**: Integration Hub Team

    **Updated**:  2026-08-13

## Summary

The current process relies on local configuration files to store dashboard settings, meaning data is not persisted beyond individual executions. As pipeline runs overwrite existing settings, historical and operational configuration data can be lost, creating challenges for consistency and alarm configuration. This ADR explores options for persisting configuration data outside of local files, with a particular focus on the introduction of a database-backed solution.

## Drivers

The current approach stores pipeline configuration in local files, which are overwritten during execution and do not provide persistent storage. This limits the ability to persist configuration, maintain historical data, and support future enhancements that require reliable state management. To overcome these constraints, Azure Cosmos DB has been selected as the persistent data store, providing a scalable and resilient solution for configuration management.

## Options

### Microsoft SQL Server
Microsoft SQL Server is a relational database management system developed by Microsoft. It provides structured data storage, advanced querying capabilities, reporting features, and integration with the wider Microsoft technology stack. SQL Server can be deployed on-premises, in virtual machines, or consumed through Azure SQL services.

Facts:
- Enterprise-grade relational database platform.
- Uses SQL for data definition and querying.
- Supports high availability, backup, and disaster recovery features.
- Integrates with Microsoft technologies and Azure services.
- Available as SQL Server or Azure SQL Database.

Documentation:

https://learn.microsoft.com/sql/ 
https://learn.microsoft.com/azure/azure-sql/

### PostgreSQL
PostgreSQL is an open-source relational database management system (RDBMS) that supports structured data storage using tables, schemas, and SQL. It provides strong data consistency, ACID compliance, and extensive support for complex querying and reporting requirements. PostgreSQL can be self-hosted or consumed as a managed Azure Database for PostgreSQL service.

Facts:
- Open-source relational database platform.
- Supports SQL queries, transactions, and relational modelling.
- ACID-compliant with strong consistency guarantees.
- Available as a managed service within Azure.

Documentation:

https://www.postgresql.org/docs/
https://learn.microsoft.com/azure/postgresql/

### Azure Cosmos DB
Azure Cosmos DB is a fully managed, globally distributed NoSQL database service provided by Microsoft Azure. It is designed to provide high availability, scalability, and low-latency access to data. Cosmos DB integrates natively with other Azure services and supports automatic scaling options.

Facts:
- Managed Azure service with minimal infrastructure management.
- Supports partitioning and horizontal scaling.
- Provides built-in high availability and disaster recovery capabilities.
- Offers multiple APIs, including NoSQL, MongoDB, Cassandra, and Gremlin.
- Native integration with Azure services and Azure identity management.

Documentation:
https://learn.microsoft.com/azure/cosmos-db/
https://learn.microsoft.com/azure/cosmos-db/nosql/

### Local Configuration Files (JSON)
Local JSON configuration files store application settings directly on the file system where the application or pipeline executes. Configuration values are read and written during runtime and are managed as files rather than through a dedicated data store.

Facts:
- Data is stored as JSON files on a local or shared file system.
- No dedicated database infrastructure is required.
- Configuration changes are made by updating files directly.
- Data persistence depends on file management and storage location.
- Files can be overwritten during execution if not explicitly preserved.
- Limited querying, auditing, and concurrent update capabilities compared to database solutions.

Documentation:
https://www.json.org/json-en.html

## Options Analysis

### Microsoft SQL Server Assessment
**Pros:**
* Enterprise-grade platform with strong security, backup, recovery, and governance capabilities.
* Well integrated with Microsoft technologies and Azure services.
* Highly reliable and familiar to Integration Services.
* Strong support for reporting, auditing, and administrative tooling.

**Cons:**
* More complex than required for simple configuration storage requirements.
* Relational design can introduce additional overhead for relatively simple configuration datasets.
* Potentially higher operational and licensing costs depending on the deployment model.

**Other Considerations:**
* Appropriate if future requirements expand into broader application data management or reporting capabilities.
* Existing organisational expertise may reduce support and onboarding effort.

**Financial Implications:**
* Higher total cost of ownership than other options due to licensing and operational considerations.
* Ongoing hosting, support, and maintenance costs.

### PostgreSQL Assessment
**Pros:**
* Mature and widely adopted database platform with extensive documentation and community support.
* Provides strong consistency and reliability for storing configuration data.
* Available as a managed Azure service, reducing infrastructure management requirements.
* Supports structured data models and robust querying capabilities.

**Cons:**
* May introduce unnecessary complexity where configuration data does not require a relational model.
* Requires schema design and ongoing schema management.
* Additional effort may be required when adapting configuration structures over time.

**Other Considerations:**
* Well suited if future requirements involve complex relationships between configuration entities.
* Familiar technology for some teams in DHCW.

**Financial Implications:**
* Ongoing hosting and operational costs.
* Additional development and maintenance effort associated with schema management.
* No licensing costs when using open-source PostgreSQL.

### Azure Cosmos DB Assessment
**Pros:**
* Provides a persistent and highly available store for configuration data, preventing configuration loss between pipeline executions.
* Fully managed Azure service, reducing the operational effort associated with database administration, patching, backups, and infrastructure maintenance.
* Scales easily to accommodate future growth in configuration volume or additional use cases.
* Offers low-latency access and built-in resilience through Azure-managed replication and availability features.
* Supports flexible data structures, allowing configuration models to evolve without significant schema changes.
* Aligns with a cloud-first architecture and integrates well with the existing Azure ecosystem.

**Cons:**
* Introduces additional service costs compared to file-based configuration management.
* Creates a dependency on a specific Azure platform service.
* Requires the team to understand and support another technology platform.

**Other Considerations:**
* Suitable for future enhancements such as configuration versioning, auditing, environment-specific settings, and operational metadata.
* Reduces reliance on local execution environments and supports centralised configuration management.

**Financial Implications:**
* Consumption-based pricing with costs dependent on storage and throughput requirements.
* Reduced infrastructure administration costs due to the fully managed service model.
* Potentially higher direct costs than local configuration files but lower operational overhead over time.

### Local Configuration Files Assessment
**Pros:**
* Simple to implement and understand.

* No additional infrastructure, hosting, or licensing requirements.
* Low initial development effort.

**Cons:**
* Configuration can be overwritten during pipeline execution, resulting in loss of persisted settings.

* Difficult to manage configuration centrally across environments and services.
* Limited support for auditing, versioning, access control, and change tracking.
* Creates dependency on local runtime environments and file management processes.
* Does not provide built-in resilience, backup, or scalability features.

**Other Considerations:**
* Suitable only for static or short-lived configuration requirements.

* Becomes increasingly difficult to manage as the number of pipelines, environments, or configuration parameters grows.

**Financial Implications:**
* Lowest direct cost option.

* Potential indirect costs resulting from data loss, operational support effort, and manual intervention when configuration issues occur.

## Recommendation

**Azure Cosmos DB** has been selected as the preferred solution because it directly addresses the key limitations of the current approach. The existing use of local configuration files does not provide reliable persistence, resulting in configuration data being overwritten during pipeline execution and preventing the retention of historical settings. This creates operational challenges and limits the ability to introduce future capabilities that depend on maintaining state over time.

While PostgreSQL and SQL Server would both provide durable and reliable storage, their relational database models introduce additional design, administration, and maintenance overhead that is not currently required for this use case. In contrast, Cosmos DB offers a fully managed, scalable, and highly available platform that can be integrated with minimal operational burden while still supporting future growth.

The decision aligns with the organisation's cloud strategy and provides a centralised configuration repository that improves reliability, maintainability, and resilience. It also establishes a foundation for potential future requirements such as configuration versioning, auditing, environment-specific configuration management, and enhanced operational visibility. As a result, Cosmos DB provides the best balance of functionality, scalability, operational simplicity, and long-term strategic fit for the solution.

### Consequences

**Pro:** 
- Dashboard configuration data will be persisted independently of pipeline execution, ensuring configuration is retained between runs and reducing the risk of settings being lost or overwritten.

- Configuration can be managed on a per-environment basis, enabling different settings to be maintained for development, test, and production environments without reliance on local files.
- Storing configuration centrally creates opportunities to support dashboard monitoring and alerting capabilities, allowing alarms and operational insights to be surfaced through the dashboard.
- The solution provides a scalable and resilient foundation for future enhancements that require reliable state management and configuration persistence.

**Con:**
- Integration Services will need to develop knowledge and support capabilities for Azure Cosmos DB, introducing a learning curve and potential short-term training overhead.

- The introduction of a managed database service will increase operational costs. However the Cosmos DB instance will use serverless capacity, given the low volume of configuration and state data being stored, ongoing operational costs are expected to be minimal.
- The solution introduces a dependency on an Azure platform service, meaning configuration management will rely on the availability and governance of Cosmos DB.
- Careful consideration must be taken with regards to backwards compatibility if the configuration is to be modified in the future.  JSON data structures are more difficult to migrate than SQL.

**Other:** 
- No significant impact is expected for end users, stakeholders, or consuming systems, as the change is focused on the internal storage and management of configuration data for the monitoring dashboard.

- This decision establishes a centralised configuration repository that can support future capabilities such as auditing, configuration versioning, and enhanced operational monitoring if required.
- The dashboard has been designed to degrade gracefully when Cosmos DB is unavailable or not configured, allowing the application to continue operating while persistence functionality is disabled.

### Confirmation

Implementation of this decision will be verified through a combination of functional testing, peer review, and team validation activities. The primary verification method will be to configure alarms within the dashboard, execute a pipeline that updates dashboard configuration data, and then confirm that the configured alarms remain in place after the pipeline run. Successful persistence of the configuration will demonstrate that data is being stored and retrieved correctly from Cosmos DB rather than being overwritten during execution.

The implementation will also be subject to code review and peer review by another developer to ensure that the solution aligns with agreed architectural standards and design principles. In addition, testing will be carried out by another member of the Integration Services team, with the completed solution demonstrated during a sprint review to provide wider team visibility and validation.

Ongoing adherence to this decision will be maintained through updates to team guidance, development standards, and knowledge-sharing activities. Training and documentation will be provided where necessary to ensure team members understand how configuration data should be managed and persisted using Cosmos DB.

Responsibility for overseeing compliance with this ADR rests with the Lead Developer and Senior Product Owner. If the decision is not followed, dashboard configuration data may not be persisted correctly, resulting in the loss of configuration between pipeline executions. Alternative approaches could also introduce unnecessary complexity, increasing development and support overhead while reducing consistency across the solution.

### More Information 
Access to Cosmos DB will be managed using Azure Managed Identity and Cosmos DB data-plane RBAC. Account-key authentication will not be used in cloud environments, reducing credential management overhead and improving security.