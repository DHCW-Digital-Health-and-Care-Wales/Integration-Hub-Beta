We are already using CosmosDB for the Dashboard config persistance.
In the old system, values we stored in a SQLServer database and looked up with a stored procedure.
The number of values required to be stored is very little. Less than 100.  Values will need to be looked up using 2 keys.
We require a new container service that can quickly lookup and return values that can be called by various transformer containers.
Write a report on the suitablily of using the existing CosmosDB for this requirement.
Write a plan of how this can be achieved as a markdown file and include diagrams.
Consider that the service should be thread safe and performant. 
