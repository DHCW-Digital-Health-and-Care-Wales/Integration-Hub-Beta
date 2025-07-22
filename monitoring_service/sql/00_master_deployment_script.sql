-- Master Deployment Script
-- Run this script to deploy all Integration Hub monitoring database objects

-- Deploy in correct order to handle dependencies
:r 01_create_queue_tables.sql
:r 02_create_processing_tables.sql  
:r 03_create_tracking_tables.sql
:r 04_create_status_tables.sql
:r 05_create_indexes.sql
:r 06_create_event_processing_procedures.sql
:r 07_create_status_monitoring_procedures.sql

PRINT 'Integration Hub monitoring database deployment completed successfully'